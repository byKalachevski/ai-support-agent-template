from __future__ import annotations

FORBIDDEN_SECRET_PATTERNS = (
    "seed phrase",
    "private key",
    "mnemonic phrase",
    "recovery phrase",
    "api key",
    "access token",
    "password",
    "secret key",
)


def contains_forbidden_wallet_request(text: str) -> bool:
    lowered = (text or "").lower()
    return any(pattern in lowered for pattern in FORBIDDEN_SECRET_PATTERNS)
