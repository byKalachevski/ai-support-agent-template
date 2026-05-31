from __future__ import annotations


def _normalize_prompt_lang(lang: str | None) -> str:
    value = str(lang or "").strip().lower()
    if value.startswith("en"):
        return "en"
    return "ru"


def build_support_system_prompt(lang: str) -> str:
    normalized_lang = _normalize_prompt_lang(lang)

    if normalized_lang == "en":
        return """
You are a reusable AI support agent.

Your task is to provide precise, natural, useful, and user-facing answers based only on the passed conversation history and relevant knowledge.

Strict rules:
1. Answer only based on the conversation history and the "Relevant knowledge" block.
2. Do not invent product features, policies, prices, limits, links, or technical details.
3. If the provided knowledge is insufficient, say that the information is not available in the current knowledge base.
4. Do not expose internal engineering terms in user-facing text: intent, chunk, KB, retrieval, grounding, pipeline, policy, orchestrator.
5. Do not insert service wrappers, Python dictionaries, JSON keys, or serialized artifacts into the answer text.
6. Never ask for secrets: sensitive credentials phrases, private keys, passwords, recovery codes, API keys, tokens, or personal credentials.
7. If the user asks for a human operator, return needs_handoff=true and briefly confirm the handoff.
8. The final answer must be in the user's language.
9. Return exactly one JSON object without markdown and without surrounding explanation.

JSON format:
{
  "answer": "string",
  "intent": "string",
  "confidence": 0.0,
  "needs_handoff": false,
  "handoff_reason": "",
  "tags": ["tag1", "tag2"],
  "used_chunk_ids": ["chunk1", "chunk2"],
  "links": [
    {
      "label": "string",
      "url": "https://example.com/...",
      "group": "primary"
    }
  ]
}
""".strip()

    return """

{


  "confidence": 0.0,
  "needs_handoff": false,
  "handoff_reason": "",
  "tags": ["tag1", "tag2"],
  "used_chunk_ids": ["chunk1", "chunk2"],
  "links": [
    {

      "url": "https://example.com/...",
      "group": "primary"
    }
  ]
}
""".strip()


def build_support_user_prompt(
    *,
    user_text: str,
    lang: str,
    intent: str,
    history_text: str,
    kb_context: str,
) -> str:
    normalized_lang = _normalize_prompt_lang(lang)

    if normalized_lang == "en":
        return f"""
User language: en
Preliminary intent: {intent}

Conversation history:
{history_text}

Relevant knowledge:
{kb_context}

Current user message:
{user_text}

Instruction:
- Reply naturally, like a support specialist.
- Use only confirmed facts from the relevant knowledge.
- Do not use internal system terms.
- Do not output JSON keys inside the answer field.
- If the user asks for a human operator, set needs_handoff=true.
- If the relevant knowledge is insufficient, say so directly.
- Do not ask for secrets or private credentials.
- Return only one JSON object according to the schema.
""".strip()

    return f"""

{history_text}


{kb_context}


{user_text}

""".strip()


def build_regeneration_prompt(
    *,
    user_text: str,
    lang: str,
    intent: str,
    history_text: str,
    kb_context: str,
    previous_answer: str,
    failure_reason: str,
) -> str:
    normalized_lang = _normalize_prompt_lang(lang)

    if normalized_lang == "en":
        return f"""
User language: en
Preliminary intent: {intent}

Conversation history:
{history_text}

Relevant knowledge:
{kb_context}

Current user message:
{user_text}

The previous answer was rejected.

Rejection reason:
{failure_reason}

Rejected answer:
{previous_answer}

Generate a new answer:
- natural and user-facing;
- based only on relevant knowledge;
- without internal service terminology;
- without JSON keys inside answer;
- without secrets or private credential requests;
- with needs_handoff=true if a human operator is requested.

Return only one JSON object.
""".strip()

    return f"""

{history_text}


{kb_context}


{user_text}

{failure_reason}


{previous_answer}

""".strip()

