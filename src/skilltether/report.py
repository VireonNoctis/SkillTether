"""Stable JSON and reviewer-friendly Markdown report exports."""
from __future__ import annotations

import html
import json
import os
import re
import tempfile
from pathlib import Path

from .models import ComparisonReport
from .safeio import read_bounded_regular_file
from .redaction import redact_sensitive_text
from .signing import sign_payload, verify_payload

MAX_REPORT_BYTES = 50 * 1024 * 1024


def _redact_path_map(values: dict[str, str]) -> dict[str, str]:
    """Redact credential-like path components without persisting the original key."""
    safe_values: dict[str, str] = {}
    for index, (path, digest) in enumerate(sorted(values.items()), start=1):
        safe_path = redact_sensitive_text(path)
        if safe_path != path:
            safe_path = f"[REDACTED_PATH_{index:05d}]"
        if safe_path in safe_values:
            safe_path = f"{safe_path}_{index:05d}"
        safe_values[safe_path] = digest
    return safe_values


def _redact_report(report: ComparisonReport) -> ComparisonReport:
    """Return a report copy with common credential forms removed from persisted strings."""
    safe = report.model_copy(deep=True)
    safe.translation_provider = (
        redact_sensitive_text(safe.translation_provider)
        if safe.translation_provider is not None else None
    )
    safe.source_files = _redact_path_map(safe.source_files)
    safe.target_files = _redact_path_map(safe.target_files)
    safe.limitations = [redact_sensitive_text(item) for item in safe.limitations]
    for finding in safe.findings:
        for field in ("path", "message", "rationale", "original_context", "target_context",
                      "proposed_change", "reviewer", "review_note", "rule_id", "severity_rationale"):
            value = getattr(finding, field)
            if isinstance(value, str):
                setattr(finding, field, redact_sensitive_text(value))
        for event in finding.review_history:
            event.reviewer = redact_sensitive_text(event.reviewer)
            event.note = redact_sensitive_text(event.note)
    return safe


def _atomic_write_text(output: Path, content: str) -> Path:
    """Atomically replace a report without following a destination symlink."""
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and output.is_dir():
        raise IsADirectoryError(f"Report output is a directory: {output}")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".tmp", dir=output.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if os.name == "posix":
            os.chmod(temporary, 0o600)
        # os.replace replaces a symlink itself instead of following it. The content
        # is fully written before the destination name is switched into place.
        os.replace(temporary, output)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    return output


def verify_report_signature(
    report: ComparisonReport,
    signing_key: str | Path | None = None,
    *,
    require_signature: bool = False,
) -> bool:
    """Verify an HMAC seal, fail closed for signed reports without the key."""
    safe_report = _redact_report(report)
    payload = safe_report.model_dump(mode="json")
    has_signature = bool(payload.get("integrity_signature"))
    if not has_signature:
        if require_signature:
            raise ValueError("A signed report is required for this operation")
        return False
    if signing_key is None:
        raise ValueError("Report is HMAC-signed; supply --signing-key to verify or update it")
    if not verify_payload(payload, signing_key):
        raise ValueError("Report signature verification failed; the report may have been modified")
    return True


def write_json_report(
    report: ComparisonReport,
    path: str | Path,
    *,
    signing_key: str | Path | None = None,
) -> Path:
    output = Path(path).expanduser()
    safe_report = _redact_report(report)
    data = safe_report.model_dump(mode="json")
    if signing_key is not None:
        data["integrity_algorithm"] = "hmac-sha256"
        data["integrity_signature"] = sign_payload(data, signing_key)
        # Keep the in-memory report consistent so a companion Markdown export can
        # accurately state that the authoritative JSON report has been sealed.
        report.integrity_algorithm = "hmac-sha256"
        report.integrity_signature = data["integrity_signature"]
    elif data.get("integrity_signature"):
        raise ValueError("Cannot rewrite a signed report without its signing key")
    payload = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if len(payload.encode("utf-8")) > MAX_REPORT_BYTES:
        raise ValueError(f"Report exceeds the {MAX_REPORT_BYTES}-byte safety limit")
    return _atomic_write_text(output, payload)


def read_json_report(path: str | Path) -> ComparisonReport:
    raw = read_bounded_regular_file(path, max_bytes=MAX_REPORT_BYTES, purpose="JSON report")
    return ComparisonReport.model_validate_json(raw)


def _fenced_context(value: str, limit: int = 4000) -> str:
    context = redact_sensitive_text(value[:limit])
    backtick_run = max((len(match.group(0)) for match in re.finditer(r"`+", context)), default=0)
    tilde_run = max((len(match.group(0)) for match in re.finditer(r"~+", context)), default=0)
    marker = "`" if backtick_run < tilde_run else "~"
    fence = marker * max(3, (backtick_run if marker == "`" else tilde_run) + 1)
    return f"{fence}text\n{context}\n{fence}"


def _markdown_escape(value: object) -> str:
    """Escape untrusted scalar text before inserting it into Markdown structure."""
    text = html.escape(str(value), quote=False).replace("\r", " ").replace("\n", " ")
    return re.sub(r"([\\\x60*_{}\[\]()#+.!|>~-])", r"\\\1", text)


def write_markdown_report(report: ComparisonReport, path: str | Path) -> Path:
    output = Path(path).expanduser()
    report = _redact_report(report)
    lines = [
        "# SkillTether comparison report", "",
        f"- Tool version: {report.tool_version}",
        f"- Source fingerprint: {report.source_fingerprint}",
        f"- Target fingerprint: {report.target_fingerprint}",
        f"- Structural status: **{report.structural_status}**",
        f"- Semantic status: **{report.semantic_status}**",
        f"- Translation provider: {_markdown_escape(report.translation_provider or '(not recorded)')}",
        f"- Invariant manifest fingerprint: {report.invariant_manifest_fingerprint or '(not supplied)'}",
        f"- Protected policy fingerprint: {report.protected_policy_fingerprint}",
        f"- Report integrity: {report.integrity_algorithm or 'unsigned'}",
        f"- Findings: {len(report.findings)}", "",
        "> This report detects risks; it does not prove semantic equivalence or safety.", "",
        "## Review queue", "",
    ]
    if not report.findings:
        lines.append("No findings were recorded.")
    for finding in report.findings:
        lines.extend([
            f"### {_markdown_escape(finding.id)} — {_markdown_escape(finding.severity.upper())}",
            "",
            f"- Code: {_markdown_escape(finding.code)}",
            f"- Rule ID: {_markdown_escape(finding.rule_id or finding.code)}",
            f"- Category: {_markdown_escape(finding.category)}",
            f"- Analysis method: {_markdown_escape(finding.analysis_method)}",
            f"- Signal uncertainty: {_markdown_escape(finding.uncertainty)}",
            f"- Path: {_markdown_escape(finding.path or '(package-level)')}",
            f"- Source line: {finding.source_line if finding.source_line is not None else '—'}",
            f"- Target line: {finding.target_line if finding.target_line is not None else '—'}",
            f"- Human disposition: {_markdown_escape(finding.disposition)}",
            f"- Review required: {'yes' if finding.requires_review or finding.severity == 'critical' else 'no'}",
            "", _markdown_escape(finding.message), "",
            f"**Why this severity:** {_markdown_escape(finding.severity_rationale or 'No severity rationale supplied.')}", "",
            f"**Rationale:** {_markdown_escape(finding.rationale)}", "",
        ])
        if finding.original_context:
            lines.extend(["**Original context**", "", _fenced_context(finding.original_context), ""])
        if finding.target_context:
            lines.extend(["**Target context**", "", _fenced_context(finding.target_context), ""])
        if finding.proposed_change:
            lines.extend([f"**Proposed change:** {_markdown_escape(finding.proposed_change)}", ""])
        if finding.reviewer:
            lines.extend(["**Latest reviewer**", "", _fenced_context(finding.reviewer, limit=200), ""])
        if finding.review_note:
            lines.extend(["**Latest review note**", "", _fenced_context(finding.review_note), ""])
        if finding.review_history:
            lines.extend(["**Review history**", ""])
            for event in finding.review_history:
                lines.extend([
                    f"- {_markdown_escape(event.recorded_at)} — {_markdown_escape(event.previous_disposition)} → {_markdown_escape(event.disposition)}",
                    "",
                    "  Reviewer:",
                    "",
                    _fenced_context(event.reviewer, limit=200),
                    "",
                    "  Rationale:",
                    "",
                    _fenced_context(event.note),
                    "",
                ])
    lines.extend(["## Limitations", ""])
    lines.extend(f"- {_markdown_escape(item)}" for item in report.limitations)
    markdown = "\n".join(lines) + "\n"
    if len(markdown.encode("utf-8")) > MAX_REPORT_BYTES:
        raise ValueError(f"Markdown report exceeds the {MAX_REPORT_BYTES}-byte safety limit")
    return _atomic_write_text(output, markdown)
