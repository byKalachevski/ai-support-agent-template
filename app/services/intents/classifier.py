from __future__ import annotations


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


OPERATOR_HANDOFF_KEYWORDS = (
    "human agent",
    "live agent",
    "human support",
    "connect me to an operator",
    "connect me to a human",
    "transfer to operator",
    "transfer to human",
)

BILLING_KEYWORDS = (
    "subscription",
    "plan",
    "billing",
    "invoice",
    "payment",
    "refund",
)

ACCOUNT_AUTH_KEYWORDS = (
    "login",
    "sign in",
    "sign up",
    "account",
    "password",
    "2fa",
    "mfa",
    "oauth",
    "auth",
)

INSTALLATION_KEYWORDS = (
    "download",
    "install",
    "installer",
    "setup",
    "platform",
    "windows",
    "macos",
    "linux",
)

INTEGRATION_KEYWORDS = (
    "integration",
    "api",
    "webhook",
    "connect",
)

TROUBLESHOOTING_KEYWORDS = (
    "error",
    "bug",
    "crash",
    "problem",
    "issue",
    "troubleshoot",
)

PRODUCT_OVERVIEW_KEYWORDS = (
    "what is",
    "overview",
    "features",
)

SECURITY_KEYWORDS = (
    "security",
    "privacy",
    "data",
    "credentials",
    "token",
    "api key",
)


def detect_intent(text: str) -> str:
    lowered = (text or "").lower().strip()

    if not lowered:
        return "general"

    if _contains_any(lowered, OPERATOR_HANDOFF_KEYWORDS):
        return "operator_handoff"

    if _contains_any(lowered, BILLING_KEYWORDS):
        return "billing"

    if _contains_any(lowered, ACCOUNT_AUTH_KEYWORDS):
        return "account_auth"

    if _contains_any(lowered, INSTALLATION_KEYWORDS):
        return "installation"

    if _contains_any(lowered, INTEGRATION_KEYWORDS):
        return "integration"

    if _contains_any(lowered, TROUBLESHOOTING_KEYWORDS):
        return "troubleshooting"

    if _contains_any(lowered, SECURITY_KEYWORDS):
        return "security"

    if _contains_any(lowered, PRODUCT_OVERVIEW_KEYWORDS):
        return "product_overview"

    return "general"

