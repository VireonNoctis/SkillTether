"""Bounded local detection of common credential indicators.

This module deliberately detects known formats and suspicious named assignments only.
It does not validate credentials, infer arbitrary high-entropy values, or prove a
package contains no secrets. Matched values are never copied into findings.
"""
from __future__ import annotations

import re
from collections.abc import Mapping

from .models import Finding, new_finding

_MAX_FINDINGS = 1000

_PRIVATE_KEY_HEADER = re.compile(
    r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"
    r"|-----BEGIN PGP PRIVATE KEY BLOCK-----"
)
_PROVIDER_TOKENS = re.compile(
    r"(?ix)\b(?:"
    r"gh[pousr]_[A-Za-z0-9]{20,}|"
    r"github_pat_[A-Za-z0-9_]{40,}|"
    r"sk-[A-Za-z0-9_-]{20,}|"
    r"xox[baprs]-[A-Za-z0-9-]{10,}|"
    r"AIza[0-9A-Za-z_-]{35}|"
    r"(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}|"
    r"SK[0-9a-f]{32}|"
    r"SG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}"
    r")\b"
)
_CLOUD_ACCESS_KEY_ID = re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")
_BEARER_TOKEN = re.compile(r"(?i)\bBearer\s+([A-Za-z0-9._~+/-]{20,}={0,2})")
_BASIC_TOKEN = re.compile(r"(?i)\bBasic\s+([A-Za-z0-9+/=]{20,})")
_URL_CREDENTIALS = re.compile(
    r"(?i)\bhttps?://[^/\s:@]+:(?P<password>[^@\s/]{8,})@"
)
_CREDENTIAL_ASSIGNMENT = re.compile(
    r"""(?ix)
    (?<![A-Z0-9])
    ["']?
    (?P<name>
        api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|
        secret(?:[_-]?(?:access[_-]?)?key)?|password|passwd|authorization|
        private[_-]?key|signing[_-]?key|aws[_-]?secret[_-]?access[_-]?key
    )
    ["']?\s*[:=]\s*
    (?P<value>
        "[^"\r\n]*"|'[^'\r\n]*'|\$\{[^}\r\n]*\}|\{\{[^}\r\n]*\}\}|
        <[^>\r\n]*>|\[[^\]\r\n]*\]|[^\s,;#}]+
    )
    """
)
_PLACEHOLDER_VALUE = re.compile(
    r"(?ix)^(?:"
    r"\$\{[^}]+\}|\{\{[^}]+\}\}|<[^>]+>|\[[^]]+\]|"
    r"(?:your|example|sample|placeholder|replace|change|dummy|fake|redacted|test)[a-z0-9._/-]*|"
    r"[x*._-]{6,}"
    r")$"
)

_RULES: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "SECRET_PRIVATE_KEY", "critical",
        "A private-key PEM or PGP header was detected; key contents are omitted.",
        "Private-key material can grant direct access. The scanner does not validate whether the key is active.",
        "Remove the key from the package and rotate/revoke it with its issuer if it may have been exposed.",
    ),
    (
        "SECRET_PROVIDER_TOKEN", "high",
        "A token matching a known provider credential format was detected; its value is omitted.",
        "The format is a credential indicator, not proof that the token is active or belongs to the named provider.",
        "Remove the token and rotate/revoke it with the issuing provider if it may have been exposed.",
    ),
    (
        "SECRET_BEARER_TOKEN", "high",
        "A bearer-style credential value was detected; its value is omitted.",
        "The pattern may identify an access token, but the scanner cannot determine whether it is active.",
        "Remove the value and rotate/revoke the credential if it may have been exposed.",
    ),
    (
        "SECRET_BASIC_CREDENTIAL", "high",
        "A Basic-authentication credential value was detected; its value is omitted.",
        "The pattern may contain an encoded username/password pair; the scanner does not decode or validate it.",
        "Remove the value and rotate the associated credentials if they may have been exposed.",
    ),
    (
        "SECRET_URL_CREDENTIALS", "high",
        "A URL containing user-info credentials was detected; the password is omitted.",
        "Credentials embedded in URLs can leak through documentation, logs, or copied links.",
        "Remove embedded credentials and use an approved secret store or environment-variable reference.",
    ),
    (
        "SECRET_CREDENTIAL_ASSIGNMENT", "medium",
        "A non-placeholder value was assigned to a credential-like field; the value is omitted.",
        "This heuristic flags named fields only. It can produce false positives and cannot determine whether a value is a real secret.",
        "Replace the value with a safe placeholder or environment-variable reference; rotate it if it was genuine and exposed.",
    ),
    (
        "SECRET_CLOUD_ACCESS_KEY_ID", "medium",
        "A cloud access-key identifier was detected; the identifier alone is not sufficient to authenticate.",
        "An access-key identifier can reveal credential metadata and is often stored alongside a separate secret value.",
        "Check whether a corresponding secret is present and remove unnecessary credential metadata from the package.",
    ),
)
_RULE_BY_CODE = {item[0]: item for item in _RULES}


def _is_placeholder(value: str) -> bool:
    candidate = value.strip().strip("\"'").strip()
    if len(candidate) < 12:
        return True
    lowered = candidate.lower()
    return bool(_PLACEHOLDER_VALUE.fullmatch(candidate)) or lowered in {
        "not-a-secret", "not_a_secret", "no-secret-value",
        "redacted-credential", "redacted_secret_value",
    }


def scan_secret_indicators(texts: Mapping[str, str]) -> list[Finding]:
    """Return redacted, location-only indicators from already bounded UTF-8 resources."""
    findings: list[Finding] = []
    seen: set[tuple[str, int, str]] = set()
    truncated = False

    def add(path: str, line_number: int, code: str) -> None:
        nonlocal truncated
        identity = (path, line_number, code)
        if identity in seen:
            return
        seen.add(identity)
        if len(findings) >= _MAX_FINDINGS:
            truncated = True
            return
        _rule, severity, message, rationale, proposed = _RULE_BY_CODE[code]
        findings.append(new_finding(
            code, severity, "secret_scan", message, rationale,
            path=path, source_line=line_number,
            proposed_change=proposed,
            requires_review=True,
            analysis_method="heuristic",
            uncertainty="medium",
            severity_rationale=(
                "A fixed credential-shaped pattern matched. The match is not an authenticity "
                "or activity check; review the indicated line without copying its value into a report."
            ),
        ))

    for path in sorted(texts):
        content = texts[path]
        for line_number, line in enumerate(content.splitlines(), start=1):
            if _PRIVATE_KEY_HEADER.search(line):
                add(path, line_number, "SECRET_PRIVATE_KEY")
            if _PROVIDER_TOKENS.search(line):
                add(path, line_number, "SECRET_PROVIDER_TOKEN")
            if _CLOUD_ACCESS_KEY_ID.search(line):
                add(path, line_number, "SECRET_CLOUD_ACCESS_KEY_ID")
            if _BEARER_TOKEN.search(line):
                add(path, line_number, "SECRET_BEARER_TOKEN")
            if _BASIC_TOKEN.search(line):
                add(path, line_number, "SECRET_BASIC_CREDENTIAL")
            if _URL_CREDENTIALS.search(line):
                add(path, line_number, "SECRET_URL_CREDENTIALS")
            assignment = _CREDENTIAL_ASSIGNMENT.search(line)
            if assignment and not _is_placeholder(assignment.group("value")):
                add(path, line_number, "SECRET_CREDENTIAL_ASSIGNMENT")
            if truncated:
                break
        if truncated:
            break

    if truncated:
        findings.append(new_finding(
            "SECRET_SCAN_FINDINGS_TRUNCATED", "medium", "secret_scan",
            f"Secret-scan findings exceeded the {_MAX_FINDINGS}-finding output limit.",
            "The scanner stops collecting indicators at a fixed limit to bound report size; the package may contain additional matches.",
            proposed_change="Review the package in smaller sections or remove credential-like material before rescanning.",
            requires_review=True,
            analysis_method="deterministic",
            uncertainty="high",
        ))
    return findings
