from __future__ import annotations

import inspect
import re
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

from app.schemas.chat import ChatTestRequest
from app.schemas.jobs import SupportJob
from app.schemas.replies import AgentReply
from app.schemas.retrieval import KBChunk, KBLink
from app.services.intents.classifier import detect_intent
from app.services.kb.loader import KBLoader
from app.services.llm.client import LLMClient
from app.services.llm.parser import parse_agent_reply
from app.services.llm.prompts import (
    build_support_system_prompt,
    build_regeneration_prompt,
    build_support_user_prompt,
)
from app.services.policies.escalation_policy import should_escalate
from app.services.policies.factual_grounding import (
    detect_entities,
    is_broad_discovery_query,
    validate_grounding,
)
from app.services.policies.link_policy import choose_primary_links, should_force_links
from app.services.policies.response_postprocessor import postprocess_reply
from app.services.policies.safety_policy import contains_forbidden_wallet_request
from app.services.policies.support_policy import apply_support_policy
from app.services.retrieval.search import RetrievalService
from app.services.sessions.manager import SessionManager
from app.services.sessions.summarizer import summarize_messages

StageCallback = Callable[[str, str, dict[str, Any] | None], Awaitable[None] | None]

_URL_RE = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)
_TRAILING_URL_PUNCT = ".,;:!?)]}>\"'"
_GENERIC_PRODUCT_PATTERNS = (
    "this product is a platform",


)

_ALLOWED_LINK_DOMAINS: set[str] = set()

_ALLOWED_LINK_GROUPS = {
    "primary",
    "secondary",
}


_LATIN_RE = re.compile(r"[A-Za-z]")

_RU_MARKERS = {


}

_EN_MARKERS = {
    "what", "how", "why", "where", "when", "hello", "hi",
    "need", "can", "could", "please", "help", "thanks", "problem",
}


class SupportOrchestrator:
    def __init__(
        self,
        *,
        kb_loader: KBLoader,
        retrieval_service: RetrievalService,
        llm_client: LLMClient,
        session_manager: SessionManager,
    ) -> None:
        self.kb_loader = kb_loader
        self.retrieval_service = retrieval_service
        self.llm_client = llm_client
        self.session_manager = session_manager

    def _build_session_key(
        self,
        *,
        user_key: str,
        ticket_id: str,
        thread_id: int,
        channel: str = "support",
    ) -> str:
        return self.session_manager.build_session_key(
            user_key=user_key,
            ticket_id=ticket_id,
            thread_id=thread_id,
            channel=channel,
        )
    
    def _normalize_lang(self, value: str | None) -> str | None:
        cleaned = str(value or "").strip().lower()
        if not cleaned:
            return None

        if cleaned.startswith("ru"):
            return "ru"
        if cleaned.startswith("en"):
            return "en"

        return None

    def _detect_message_lang(self, text: str) -> str | None:
        source = str(text or "").strip()
        if not source:
            return None

        lowered = source.lower()

        cyr = len(_CYRILLIC_RE.findall(source))
        lat = len(_LATIN_RE.findall(source))

        ru_hits = sum(1 for word in _RU_MARKERS if word in lowered)
        en_hits = sum(1 for word in _EN_MARKERS if word in lowered)

        if cyr > 0 and lat == 0:
            return "ru"
        if lat > 0 and cyr == 0:
            return "en"

        if ru_hits >= 2 and ru_hits > en_hits:
            return "ru"
        if en_hits >= 2 and en_hits > ru_hits:
            return "en"

        if cyr >= lat * 1.5 and cyr > 0:
            return "ru"
        if lat >= cyr * 1.5 and lat > 0:
            return "en"

        return None

    def _resolve_effective_lang(
        self,
        *,
        lang_hint: str | None,
        text: str,
        session_lang: str | None,
    ) -> str:
        normalized_hint = self._normalize_lang(lang_hint)
        if normalized_hint:
            return normalized_hint

        detected = self._detect_message_lang(text)
        if detected:
            return detected

        normalized_session_lang = self._normalize_lang(session_lang)
        if normalized_session_lang:
            return normalized_session_lang

        return "ru"

    async def process_test_chat(self, payload: ChatTestRequest) -> AgentReply:
        session_key = self._build_session_key(
            user_key=payload.user_key,
            ticket_id=payload.ticket_id,
            thread_id=payload.thread_id,
            channel="chat_test",
        )

        hinted_lang = self._normalize_lang(payload.lang_hint)

        session = self.session_manager.get_or_create(
            session_key=session_key,
            user_key=payload.user_key,
            ticket_id=payload.ticket_id,
            thread_id=payload.thread_id,
            lang=hinted_lang or "ru",
        )

        resolved_lang = self._resolve_effective_lang(
            lang_hint=payload.lang_hint,
            text=payload.text,
            session_lang=session.lang,
        )
        session.lang = resolved_lang

        history_messages = [item.model_dump() for item in payload.history]
        history_messages.append({"role": "user", "text": payload.text})

        return await self._process_common(
            session_key=session_key,
            user_key=payload.user_key,
            ticket_id=payload.ticket_id,
            thread_id=payload.thread_id,
            lang=resolved_lang,
            text=payload.text,
            history=history_messages,
            session_lang=session.lang,
            stage_cb=None,
        )

    async def process_job(
        self,
        job: SupportJob,
        stage_cb: StageCallback | None = None,
    ) -> AgentReply:
        channel = str(getattr(job.meta, "channel", None) or "support").strip() or "support"

        session_key = self._build_session_key(
            user_key=job.user_key,
            ticket_id=job.ticket_id,
            thread_id=job.thread_id,
            channel=channel,
        )

        hinted_lang = self._normalize_lang(job.meta.lang_hint)

        session = self.session_manager.get_or_create(
            session_key=session_key,
            user_key=job.user_key,
            ticket_id=job.ticket_id,
            thread_id=job.thread_id,
            lang=hinted_lang or "ru",
        )

        resolved_lang = self._resolve_effective_lang(
            lang_hint=job.meta.lang_hint,
            text=job.message.text,
            session_lang=session.lang,
        )
        session.lang = resolved_lang

        history = [item.model_dump() for item in job.history]
        history.append({"role": "user", "text": job.message.text})

        return await self._process_common(
            session_key=session_key,
            user_key=job.user_key,
            ticket_id=job.ticket_id,
            thread_id=job.thread_id,
            lang=resolved_lang,
            text=job.message.text,
            history=history,
            session_lang=session.lang,
            stage_cb=stage_cb,
        )

    async def process_office_task(
        self,
        *,
        title: str,
        text: str,
        stage_cb: StageCallback | None = None,
    ) -> AgentReply:
        history: list[dict[str, str]] = []
        session_key = self._build_session_key(
            user_key="office:support",
            ticket_id=f"office:{title}",
            thread_id=0,
            channel="office",
        )

        session = self.session_manager.get_or_create(
            session_key=session_key,
            user_key="office:support",
            ticket_id=f"office:{title}",
            thread_id=0,
            lang="ru",
        )

        return await self._process_common(
            session_key=session_key,
            user_key="office:support",
            ticket_id=f"office:{title}",
            thread_id=0,
            lang="ru",
            text=text,
            history=history,
            session_lang=session.lang,
            stage_cb=stage_cb,
        )

    async def _emit(
        self,
        stage_cb: StageCallback | None,
        stage: str,
        message: str,
        meta: dict[str, Any] | None = None,
    ) -> None:
        if stage_cb is None:
            return
        result = stage_cb(stage, message, meta)
        if inspect.isawaitable(result):
            await result

    def _build_kb_context(self, chunks: list[KBChunk]) -> str:
        sections: list[str] = []

        for chunk in chunks:
            block = [f"[{chunk.id}] {chunk.title}", chunk.text]

            safe_links = [link for link in chunk.user_facing_links if self._is_allowed_link(link)]
            if safe_links:
                link_lines = []
                for link in safe_links[:5]:
                    link_lines.append(f"- {link.label}: {self._normalize_url(link.url)} ({link.group})")
                block.append("User-facing links:\n" + "\n".join(link_lines))

            sections.append("\n".join(block))

        return "\n\n".join(sections)

    def _normalize_url(self, value: str) -> str:
        clean = str(value or "").strip()

        while clean and clean[-1] in _TRAILING_URL_PUNCT:
            clean = clean[:-1]

        return clean.rstrip("/").strip()

    def _is_allowed_domain(self, url: str) -> bool:
        normalized = self._normalize_url(url)
        if not normalized:
            return False

        try:
            parsed = urlparse(normalized)
        except Exception:
            return False

        host = (parsed.netloc or "").lower().strip()
        return host in _ALLOWED_LINK_DOMAINS

    def _is_allowed_link(self, link: KBLink) -> bool:
        if not getattr(link, "url", None):
            return False

        group = (getattr(link, "group", "") or "").strip().lower()
        if group not in _ALLOWED_LINK_GROUPS:
            return False

        return self._is_allowed_domain(link.url)

    def _canonicalize_link(self, link: KBLink | None) -> KBLink | None:
        if link is None or not self._is_allowed_link(link):
            return None

        normalized = self._normalize_url(link.url)
        if not normalized:
            return None

        label = (getattr(link, "label", None) or normalized).strip() or normalized
        group = (getattr(link, "group", None) or "primary").strip().lower() or "primary"
        if group not in _ALLOWED_LINK_GROUPS:
            group = "primary"

        return KBLink(label=label, url=normalized, group=group)

    def _build_allowed_link_index(
        self,
        *,
        chunks: list[KBChunk],
        used_chunk_ids: list[str],
    ) -> dict[str, KBLink]:
        preferred_ids = set(used_chunk_ids or [])
        ordered_chunks: list[KBChunk] = []

        if preferred_ids:
            ordered_chunks.extend([chunk for chunk in chunks if chunk.id in preferred_ids])
            ordered_chunks.extend([chunk for chunk in chunks if chunk.id not in preferred_ids])
        else:
            ordered_chunks = list(chunks)

        allowed: dict[str, KBLink] = {}

        for chunk in ordered_chunks:
            for link in chunk.user_facing_links:
                canonical = self._canonicalize_link(link)
                if canonical is None:
                    continue
                allowed.setdefault(canonical.url, canonical)

        return allowed

    def _collect_links(
        self,
        *,
        chunks: list[KBChunk],
        used_chunk_ids: list[str],
        limit: int = 4,
    ) -> list[KBLink]:
        preferred_ids = set(used_chunk_ids or [])
        ordered_chunks: list[KBChunk] = []

        if preferred_ids:
            ordered_chunks.extend([chunk for chunk in chunks if chunk.id in preferred_ids])
            ordered_chunks.extend([chunk for chunk in chunks if chunk.id not in preferred_ids])
        else:
            ordered_chunks = list(chunks)

        result: list[KBLink] = []
        seen_urls: set[str] = set()

        for chunk in ordered_chunks:
            for link in chunk.user_facing_links:
                canonical = self._canonicalize_link(link)
                if canonical is None or canonical.url in seen_urls:
                    continue

                seen_urls.add(canonical.url)
                result.append(canonical)

                if len(result) >= limit:
                    return result

        return result

    def _validate_links(
        self,
        *,
        links: list[KBLink] | None,
        allowed_links: dict[str, KBLink],
        limit: int = 4,
    ) -> list[KBLink]:
        result: list[KBLink] = []
        seen_urls: set[str] = set()

        for link in links or []:
            normalized = self._normalize_url(getattr(link, "url", ""))
            canonical = allowed_links.get(normalized)
            if canonical is None or canonical.url in seen_urls:
                continue

            seen_urls.add(canonical.url)
            result.append(canonical)

            if len(result) >= limit:
                return result

        return result

    def _extract_links_from_answer(
        self,
        *,
        answer: str,
        allowed_links: dict[str, KBLink],
        limit: int = 4,
    ) -> list[KBLink]:
        text = str(answer or "").strip()
        if not text:
            return []

        result: list[KBLink] = []
        seen_urls: set[str] = set()

        for match in _URL_RE.finditer(text):
            raw_url = match.group(0)
            normalized = self._normalize_url(raw_url)
            canonical = allowed_links.get(normalized)
            if canonical is None or canonical.url in seen_urls:
                continue

            seen_urls.add(canonical.url)
            result.append(canonical)

            if len(result) >= limit:
                break

        return result

    def _merge_links(
        self,
        *,
        reply_links: list[KBLink] | None,
        deterministic_links: list[KBLink] | None,
        fallback_links: list[KBLink] | None,
        allowed_links: dict[str, KBLink],
        limit: int = 4,
    ) -> list[KBLink]:
        result: list[KBLink] = []
        seen_urls: set[str] = set()

        validated_reply_links = self._validate_links(
            links=reply_links,
            allowed_links=allowed_links,
            limit=limit,
        )

        for source in (deterministic_links or [], validated_reply_links, fallback_links or []):
            for link in source:
                normalized = self._normalize_url(getattr(link, "url", ""))
                canonical = allowed_links.get(normalized)
                if canonical is None or canonical.url in seen_urls:
                    continue

                seen_urls.add(canonical.url)
                result.append(canonical)

                if len(result) >= limit:
                    return result

        return result

    def _desired_link_limit(self, *, user_text: str, intent: str) -> int:
        lowered = (user_text or "").lower()

        if intent == "operator_handoff":
            return 0

        if any(phrase in lowered for phrase in ("link", "url", "documentation", "docs", "download")):
            return 3

        if intent in {"product_overview", "general"}:
            return 3

        return 4

    def _build_operator_handoff_reply(self, lang: str) -> AgentReply:
        answer = (
            "I am transferring the conversation to a human operator. "
            "You can briefly describe the issue in one message or clarify what should be checked."
        )

        return AgentReply(
            answer=answer,
            intent="operator_handoff",
            confidence=0.99,
            needs_handoff=True,
            handoff_reason="user_requested_operator",
            tags=["operator_handoff", "human_requested"],
            used_chunk_ids=[],
            links=[],
        )

    def _build_handoff_wait_reply(self, lang: str) -> AgentReply:
        answer = (
            "The conversation has already been transferred to a human operator. "
            "Your message has been saved for the operator."
        )

        return AgentReply(
            answer=answer,
            intent="operator_handoff",
            confidence=1.0,
            needs_handoff=True,
            handoff_reason="handoff_active",
            tags=["handoff_locked", "human_wait"],
            used_chunk_ids=[],
            links=[],
        )

    def _build_security_reply(self, lang: str) -> AgentReply:
        answer = (
            "For security, do not send seed phrases, private keys, passwords, API keys, "
            "access tokens, or other sensitive credentials. Describe the issue without "
            "sharing secrets, and I will try to help."
        )

        return AgentReply(
            answer=answer,
            intent="security",
            confidence=0.98,
            needs_handoff=False,
            tags=["security"],
            used_chunk_ids=[],
            links=[],
        )

    def _answer_is_generic_overview(self, answer: str, query: str) -> bool:
        lowered_answer = (answer or "").lower()
        if not lowered_answer:
            return True
        return any(pattern in lowered_answer for pattern in _GENERIC_PRODUCT_PATTERNS)

    def _answer_matches_query_topic(
        self,
        *,
        query: str,
        answer: str,
        intent: str,
        chunks: list[KBChunk],
    ) -> tuple[bool, str]:
        if intent == "operator_handoff":
            return True, "ok"

        if not answer.strip():
            return False, "empty answer"

        if self._answer_is_generic_overview(answer, query):
            return False, "answer drifted into generic product overview"

        grounded, reason = validate_grounding(
            query=query,
            answer=answer,
            chunks=chunks,
            intent=intent,
        )
        if not grounded:
            return False, reason

        return True, "ok"

    def _select_retry_chunks(
        self,
        *,
        chunks: list[KBChunk],
        query: str,
        intent: str,
    ) -> list[KBChunk]:
        if not chunks:
            return []

        if intent == "operator_handoff":
            return []

        if intent in {"product_overview", "general"} and is_broad_discovery_query(query):
            return chunks[:4]

        return chunks[:2]

    async def _generate_reply_with_retry(
        self,
        *,
        user_text: str,
        effective_lang: str,
        intent: str,
        history_text: str,
        chunks: list[KBChunk],
        stage_cb: StageCallback | None,
    ) -> AgentReply:
        if intent == "operator_handoff":
            await self._emit(stage_cb, "operator_handoff", "Operator handoff requested")
            return self._build_operator_handoff_reply(effective_lang)

        kb_context = self._build_kb_context(chunks)
        prompt = build_support_user_prompt(
            user_text=user_text,
            lang=effective_lang,
            intent=intent,
            history_text=history_text,
            kb_context=kb_context,
        )
        system_prompt = build_support_system_prompt(effective_lang)

        await self._emit(stage_cb, "llm_generation", "Generating answer with LLM")
        raw_text = await self.llm_client.generate(system=system_prompt, prompt=prompt)

        await self._emit(stage_cb, "reply_parsing", "Parsing structured reply")
        try:
            reply = parse_agent_reply(raw_text)
        except Exception:
            retry_prompt = build_regeneration_prompt(
                user_text=user_text,
                lang=effective_lang,
                intent=intent,
                history_text=history_text,
                kb_context=kb_context,
                previous_answer=raw_text,
                failure_reason="response was not a valid structured object",
            )
            raw_retry = await self.llm_client.generate(
                system=system_prompt,
                prompt=retry_prompt,
                temperature=0.1,
            )
            reply = parse_agent_reply(raw_retry)

        reply.intent = intent
        if not reply.used_chunk_ids:
            reply.used_chunk_ids = [chunk.id for chunk in chunks]

        is_valid, reason = self._answer_matches_query_topic(
            query=user_text,
            answer=reply.answer,
            intent=intent,
            chunks=chunks,
        )
        if is_valid:
            return reply

        retry_chunks = self._select_retry_chunks(chunks=chunks, query=user_text, intent=intent)
        retry_kb_context = self._build_kb_context(retry_chunks or chunks)

        retry_prompt = build_regeneration_prompt(
            user_text=user_text,
            lang=effective_lang,
            intent=intent,
            history_text=history_text,
            kb_context=retry_kb_context,
            previous_answer=reply.answer,
            failure_reason=reason,
        )
        await self._emit(
            stage_cb,
            "llm_regeneration",
            "Regenerating answer with stricter grounding",
            {"reason": reason},
        )
        raw_retry = await self.llm_client.generate(
            system=system_prompt,
            prompt=retry_prompt,
            temperature=0.1,
        )
        retry_reply = parse_agent_reply(raw_retry)
        retry_reply.intent = intent

        if not retry_reply.used_chunk_ids:
            retry_reply.used_chunk_ids = [chunk.id for chunk in (retry_chunks or chunks)]

        retry_is_valid, retry_reason = self._answer_matches_query_topic(
            query=user_text,
            answer=retry_reply.answer,
            intent=intent,
            chunks=(retry_chunks or chunks),
        )
        if retry_is_valid:
            return retry_reply

        fallback_answer = (
            "I cannot safely formulate a precise answer right now without risking meaning distortion. "
            "I can transfer the conversation to a human operator if needed."
        )

        return AgentReply(
            answer=fallback_answer,
            intent=intent,
            confidence=0.15,
            needs_handoff=True,
            handoff_reason=retry_reason,
            tags=["grounding_failed", "formatting_failed"],
            used_chunk_ids=[chunk.id for chunk in (retry_chunks or chunks)],
            links=[],
        )

    async def _process_common(
        self,
        *,
        session_key: str,
        user_key: str,
        ticket_id: str,
        thread_id: int,
        lang: str,
        text: str,
        history: list[dict],
        session_lang: str,
        stage_cb: StageCallback | None,
    ) -> AgentReply:
        await self._emit(stage_cb, "received_input", "Input received")

        effective_lang = self._resolve_effective_lang(
            lang_hint=lang,
            text=text,
            session_lang=session_lang,
        )
        intent = detect_intent(text)
        self.session_manager.set_last_intent(session_key, intent)

        await self._emit(stage_cb, "intent_detection", "Intent detected", {"intent": intent})

        if contains_forbidden_wallet_request(text):
            await self._emit(stage_cb, "security_check", "Forbidden sensitive credential request detected")
            reply = self._build_security_reply(effective_lang)
            self.session_manager.add_message(session_key, "user", text)
            self.session_manager.add_message(session_key, "assistant", reply.answer)
            return reply

        if self.session_manager.is_handoff_locked(session_key):
            await self._emit(stage_cb, "handoff_locked", "Session is already locked for operator")
            reply = self._build_handoff_wait_reply(effective_lang)
            self.session_manager.add_message(session_key, "user", text)
            self.session_manager.add_message(session_key, "assistant", reply.answer)
            return reply

        if intent == "operator_handoff":
            await self._emit(stage_cb, "operator_handoff", "Bypassing retrieval and LLM for operator handoff")
            reply = self._build_operator_handoff_reply(effective_lang)
            self.session_manager.activate_handoff(
                session_key,
                reason=reply.handoff_reason or "user_requested_operator",
            )
            reply = postprocess_reply(
                user_text=text,
                reply=reply,
            )
            reply = apply_support_policy(reply, lang=effective_lang)

            await self._emit(stage_cb, "session_save", "Saving session history")
            self.session_manager.add_message(session_key, "user", text)
            self.session_manager.add_message(session_key, "assistant", reply.answer)

            await self._emit(
                stage_cb,
                "completed",
                "Task completed",
                {
                    "intent": reply.intent,
                    "confidence": reply.confidence,
                    "needs_handoff": reply.needs_handoff,
                    "used_chunk_ids": reply.used_chunk_ids,
                    "links": [],
                },
            )
            return reply

        await self._emit(stage_cb, "retrieval", "Searching KB")
        chunks = self.retrieval_service.search(
            query=text,
            chunks=self.kb_loader.chunks,
            lang=effective_lang,
            intent=intent,
            top_k=5,
        )
        await self._emit(
            stage_cb,
            "retrieval_done",
            "KB search finished",
            {"chunks": [chunk.id for chunk in chunks]},
        )

        history_text = summarize_messages(history, max_items=10)
        await self._emit(stage_cb, "prompt_build", "Building prompt")
        reply = await self._generate_reply_with_retry(
            user_text=text,
            effective_lang=effective_lang,
            intent=intent,
            history_text=history_text,
            chunks=chunks,
            stage_cb=stage_cb,
        )

        forced_links_needed = should_force_links(
            user_text=text,
            answer_text=reply.answer,
            intent=reply.intent or intent,
            chunks=chunks,
        )

        allowed_links = self._build_allowed_link_index(
            chunks=chunks,
            used_chunk_ids=reply.used_chunk_ids,
        )

        desired_link_limit = self._desired_link_limit(
            user_text=text,
            intent=reply.intent or intent,
        )

        deterministic_links = self._collect_links(
            chunks=chunks,
            used_chunk_ids=reply.used_chunk_ids,
            limit=desired_link_limit,
        )

        policy_links = choose_primary_links(
            chunks=chunks,
            used_chunk_ids=reply.used_chunk_ids,
            intent=reply.intent or intent,
            user_text=text,
            limit=desired_link_limit,
        )

        fallback_links = self._extract_links_from_answer(
            answer=reply.answer,
            allowed_links=allowed_links,
            limit=desired_link_limit,
        )

        merged_links = self._merge_links(
            reply_links=reply.links,
            deterministic_links=policy_links + deterministic_links,
            fallback_links=fallback_links,
            allowed_links=allowed_links,
            limit=desired_link_limit,
        )

        if merged_links:
            reply.links = merged_links
        elif reply.links:
            reply.links = self._validate_links(
                links=reply.links,
                allowed_links=allowed_links,
                limit=desired_link_limit,
            )
        elif forced_links_needed:
            reply.links = deterministic_links[:desired_link_limit]
        else:
            reply.links = []

        reply = postprocess_reply(
            user_text=text,
            reply=reply,
        )

        await self._emit(stage_cb, "policy_check", "Applying policies")
        auto_escalate, reason = should_escalate(
            text=text,
            confidence=reply.confidence,
            intent=reply.intent or intent,
        )
        if auto_escalate and not reply.needs_handoff:
            reply.needs_handoff = True
            reply.handoff_reason = reason

        reply = apply_support_policy(reply, lang=effective_lang)

        if reply.needs_handoff or reply.intent == "operator_handoff":
            self.session_manager.activate_handoff(
                session_key,
                reason=reply.handoff_reason or "handoff_requested",
            )

        await self._emit(stage_cb, "session_save", "Saving session history")
        self.session_manager.add_message(session_key, "user", text)
        self.session_manager.add_message(session_key, "assistant", reply.answer)

        await self._emit(
            stage_cb,
            "completed",
            "Task completed",
            {
                "intent": reply.intent,
                "confidence": reply.confidence,
                "needs_handoff": reply.needs_handoff,
                "used_chunk_ids": reply.used_chunk_ids,
                "links": [link.model_dump() for link in reply.links],
            },
        )

        return reply
