"""High-confidence credential redaction for persisted review artifacts.

These rules are deliberately narrow guardrails, not a complete secret scanner.
They must never be described as proof that a report contains no sensitive material.
"""
from __future__ import annotations

import re

_ASSIGNMENT = re.compile(
    r"""(?ix)
    \b(api[_-]?key|access[_-]?token|refresh[_-]?token|password|passwd|
       client[_-]?secret|secret(?:[_-]?(?:access[_-]?)?key)?|
       private[_-]?key|signing[_-]?key|authorization|aws[_-]?secret[_-]?access[_-]?key)\b
    (\s*[:=]\s*)
    (?:"[^"]*"|'[^']*'|[^\s,;]+)
    """
)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{8,}={0,2}")
_BASIC = re.compile(r"(?i)\bBasic\s+[A-Za-z0-9+/=]{20,}")
_PROVIDER_TOKENS = re.compile(
    r"(?i)\b(?:"
    r"gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{40,}|"
    r"sk-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16}|ASIA[A-Z0-9]{16}|"
    r"xox[baprs]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{35}|"
    r"(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}|"
    r"SK[0-9a-f]{32}|SG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}"
    r")\b"
)
_URL_CREDENTIALS = re.compile(r"(?i)(https?://[^/\s:@]+:)[^@\s/]+@")
_PRIVATE_KEY = re.compile(
    r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----.*?"
    r"(?:-----END (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----|$)|"
    r"-----BEGIN PGP PRIVATE KEY BLOCK-----.*?(?:-----END PGP PRIVATE KEY BLOCK-----|$)",
    re.DOTALL,
)
_REDACTED = "[REDACTED_CREDENTIAL]"


def redact_sensitive_text(value: str) -> str:
    """Redact common credential assignments, bearer tokens, provider keys, URLs, and PEM blocks."""
    if not isinstance(value, str) or not value:
        return value
    value = _PRIVATE_KEY.sub("[REDACTED_PRIVATE_KEY]", value)
    value = _ASSIGNMENT.sub(lambda match: match.group(1) + match.group(2) + "[REDACTED]", value)
    value = _BEARER.sub("Bearer " + _REDACTED, value)
    value = _BASIC.sub("Basic " + _REDACTED, value)
    value = _URL_CREDENTIALS.sub(r"\1[REDACTED]@", value)
    value = _PROVIDER_TOKENS.sub(_REDACTED, value)
    return value
