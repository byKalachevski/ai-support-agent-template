from datetime import timedelta

from app.schemas.sessions import SessionState
from app.utils.time import utc_now


class SessionManager:
    def __init__(self, ttl_seconds: int = 300) -> None:
        self.ttl_seconds = ttl_seconds
        self._store: dict[str, SessionState] = {}

    def build_session_key(
        self,
        *,
        user_key: str,
        ticket_id: str,
        thread_id: int,
        channel: str | None = None,
    ) -> str:
        safe_channel = (channel or "support").strip() or "support"
        safe_ticket_id = (ticket_id or "no-ticket").strip() or "no-ticket"
        return f"{safe_channel}:{safe_ticket_id}:{int(thread_id)}:{user_key}"

    def get(self, session_key: str) -> SessionState | None:
        return self._store.get(session_key)

    def get_or_create(
        self,
        *,
        session_key: str,
        user_key: str,
        ticket_id: str,
        thread_id: int,
        lang: str = "ru",
    ) -> SessionState:
        now = utc_now()
        session = self._store.get(session_key)

        if session:
            session.updated_at = now
            session.lang = lang or session.lang
            session.ticket_id = ticket_id or session.ticket_id
            session.thread_id = int(thread_id)
            return session

        session = SessionState(
            session_key=session_key,
            user_key=user_key,
            ticket_id=ticket_id,
            thread_id=int(thread_id),
            lang=lang or "ru",
            created_at=now,
            updated_at=now,
        )
        self._store[session_key] = session
        return session

    def add_message(self, session_key: str, role: str, text: str) -> None:
        session = self._store.get(session_key)
        if not session:
            return
        session.recent_messages.append({"role": role, "text": text})
        session.updated_at = utc_now()

    def set_last_intent(self, session_key: str, intent: str) -> None:
        session = self._store.get(session_key)
        if not session:
            return
        session.last_intent = (intent or "general").strip() or "general"
        session.updated_at = utc_now()

    def activate_handoff(
        self, session_key: str, reason: str = "user_requested_operator"
    ) -> None:
        session = self._store.get(session_key)
        if not session:
            return

        now = utc_now()
        session.needs_handoff = True
        session.handoff_locked = True
        session.handoff_status = "handoff_requested"
        session.handoff_reason = reason
        session.handoff_requested_at = now
        session.updated_at = now

    def set_human_active(
        self, session_key: str, operator_id: str | None = None
    ) -> None:
        session = self._store.get(session_key)
        if not session:
            return

        session.needs_handoff = True
        session.handoff_locked = True
        session.handoff_status = "human_active"
        session.human_operator_id = operator_id
        session.updated_at = utc_now()

    def resume_bot(self, session_key: str) -> None:
        session = self._store.get(session_key)
        if not session:
            return

        session.needs_handoff = False
        session.handoff_locked = False
        session.handoff_status = "bot_resumed"
        session.handoff_reason = ""
        session.human_operator_id = None
        session.updated_at = utc_now()

    def close_session(self, session_key: str) -> None:
        session = self._store.get(session_key)
        if not session:
            return

        session.needs_handoff = False
        session.handoff_locked = False
        session.handoff_status = "closed"
        session.handoff_reason = ""
        session.human_operator_id = None
        session.updated_at = utc_now()

    def is_handoff_locked(self, session_key: str) -> bool:
        session = self._store.get(session_key)
        if not session:
            return False

        return bool(
            session.handoff_locked
            and session.handoff_status in {"handoff_requested", "human_active"}
        )

    def cleanup(self) -> int:
        now = utc_now()
        expired: list[str] = []

        for session_key, session in self._store.items():
            if now - session.updated_at > timedelta(seconds=self.ttl_seconds):
                expired.append(session_key)

        for session_key in expired:
            self._store.pop(session_key, None)

        return len(expired)

    def stats(self) -> dict:
        locked = sum(
            1
            for session in self._store.values()
            if self.is_handoff_locked(session.session_key)
        )
        return {
            "active_sessions": len(self._store),
            "handoff_locked_sessions": locked,
            "ttl_seconds": self.ttl_seconds,
        }

