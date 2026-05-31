from __future__ import annotations

_OPERATOR_ESCALATION_KEYWORDS = (
    "human agent",
    "live agent",
    "transfer to operator",
    "transfer to human",
)


def should_escalate(
    *, text: str, confidence: float, intent: str = "general"
) -> tuple[bool, str]:
    lowered = (text or "").lower()

    if intent == "operator_handoff":
        return True, "user_requested_operator"

    if any(keyword in lowered for keyword in _OPERATOR_ESCALATION_KEYWORDS):
        return True, "user_requested_operator"

    escalation_keywords = [
        "refund",
        "lost access",
        "bug",
        "crash",
    ]

    if any(keyword in lowered for keyword in escalation_keywords):
        return True, "keyword_escalation"

    informational_intents = {
        "general",
        "general_info",
        "faq",
        "product_overview",
        "screener_analytics",
        "crypto_balls",
        "operator_handoff",
    }

    if intent not in informational_intents and confidence < 0.45:
        return True, "low_confidence"

    return False, ""

