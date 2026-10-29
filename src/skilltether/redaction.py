"""High-confidence credential redaction for persisted review artifacts.

These rules are deliberately narrow guardrails, not a complete secret scanner.
They must never be described as proof that a report contains no sensitive material.
"""
from __future__ import annotations

import re

_ASSIGNMENT = re.compile(
    r"""(?ix)
    \b(api[_-]?key|access[_-]?token|refresh[_-]?token|password|
       client[_-]?secret|secret[_-]?key|authorization)\b
    (\s*[:=]\s*)
    (?:"[^"]*"|'[^']*'|[^\s,;]+)
    """
)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{8,}={0,2}")
_BASIC = re.compile(r"(?i)\bBasic\s+[A-Za-z0-9+/=]{20,}")
_PROVIDER_TOKENS = re.compile(
    r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,}|"
    r"AKIA[A-Z0-9]{16}|xox[baprs]-[A-Za-z0-9-]{10,})\b"
)
_PRIVATE_KEY = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----.*?"
    r"(?:-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|$)",
    re.DOTALL,
)
_REDACTED = "[REDACTED_CREDENTIAL]"


def redact_sensitive_text(value: str) -> str:
    """Redact common credential assignments, bearer tokens, provider keys, and PEM blocks."""
    if not isinstance(value, str) or not value:
        return value
    value = _PRIVATE_KEY.sub("[REDACTED_PRIVATE_KEY]", value)
    value = _ASSIGNMENT.sub(lambda match: match.group(1) + match.group(2) + "[REDACTED]", value)
    value = _BEARER.sub("Bearer " + _REDACTED, value)
    value = _BASIC.sub("Basic " + _REDACTED, value)
    value = _PROVIDER_TOKENS.sub(_REDACTED, value)
    return value
