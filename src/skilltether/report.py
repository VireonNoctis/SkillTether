"""Stable JSON and reviewer-friendly Markdown report exports."""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

from .models import ComparisonReport


def write_json_report(report: ComparisonReport, path: str | Path) -> Path:
    output = Path(path).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output


def read_json_report(path: str | Path) -> ComparisonReport:
    return ComparisonReport.model_validate_json(Path(path).read_text(encoding="utf-8"))


def _fenced_context(value: str, limit: int = 4000) -> str:
    context = value[:limit]
    backtick_run = max((len(match.group(0)) for match in re.finditer(r"`+", context)), default=0)
    tilde_run = max((len(match.group(0)) for match in __import__("re").finditer(r"~+", context)), default=0)
    marker = "`" if backtick_run < tilde_run else "~"
    fence = marker * max(3, (backtick_run if marker == "`" else tilde_run) + 1)
    return f"{fence}text\n{context}\n{fence}"


def write_markdown_report(report: ComparisonReport, path: str | Path) -> Path:
    output = Path(path).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# SkillTether comparison report", "",
        f"- Tool version: {report.tool_version}",
        f"- Source fingerprint: {report.source_fingerprint}",
        f"- Target fingerprint: {report.target_fingerprint}",
        f"- Structural status: **{report.structural_status}**",
        f"- Semantic status: **{report.semantic_status}**",
        f"- Translation provider: {html.escape(report.translation_provider or '(not recorded)')}",
        f"- Invariant manifest fingerprint: {report.invariant_manifest_fingerprint or '(not supplied)'}",
        f"- Protected policy fingerprint: {report.protected_policy_fingerprint}",
        f"- Findings: {len(report.findings)}", "",
        "> This report detects risks; it does not prove semantic equivalence or safety.", "",
        "## Review queue", "",
    ]
    if not report.findings:
        lines.append("No findings were recorded.")
    for finding in report.findings:
        lines.extend([
            f"### {html.escape(finding.id)} — {html.escape(finding.severity.upper())}",
            "",
            f"- Code: {html.escape(finding.code)}",
            f"- Category: {html.escape(finding.category)}",
            f"- Path: {html.escape(finding.path or '(package-level)')}",
            f"- Source line: {finding.source_line if finding.source_line is not None else '—'}",
            f"- Target line: {finding.target_line if finding.target_line is not None else '—'}",
            f"- Human disposition: {html.escape(finding.disposition)}",
            f"- Review required: {'yes' if finding.requires_review or finding.severity == 'critical' else 'no'}",
            "", html.escape(finding.message), "", f"**Rationale:** {html.escape(finding.rationale)}", "",
        ])
        if finding.original_context:
            lines.extend(["**Original context**", "", _fenced_context(finding.original_context), ""])
        if finding.target_context:
            lines.extend(["**Target context**", "", _fenced_context(finding.target_context), ""])
        if finding.proposed_change:
            lines.extend([f"**Proposed change:** {html.escape(finding.proposed_change)}", ""])
        if finding.reviewer:
            lines.extend([f"**Reviewer:** {html.escape(finding.reviewer)}", ""])
        if finding.review_note:
            lines.extend([f"**Review note:** {html.escape(finding.review_note)}", ""])
    lines.extend(["## Limitations", ""])
    lines.extend(f"- {html.escape(item)}" for item in report.limitations)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output
