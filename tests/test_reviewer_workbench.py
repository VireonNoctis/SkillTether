from __future__ import annotations

from pathlib import Path


def test_reviewer_workbench_is_offline_and_renders_untrusted_content_as_text() -> None:
    document = Path("reviewer/index.html").read_text(encoding="utf-8")
    assert "FileReader" in document or "file.text()" in document
    assert "textContent" in document
    assert "createElement" in document
    assert "append(" in document
    assert "localStorage" not in document
    assert "sessionStorage" not in document
    assert "fetch(" not in document
    assert "XMLHttpRequest" not in document
    assert "innerHTML" not in document
    assert "integrity_signature" in document
    assert "review_history" in document
    assert "Content-Security-Policy" in document
    assert "connect-src 'none'" in document
    assert "historyIsConsistent" in document


def test_reviewer_workbench_keeps_signed_reports_read_only() -> None:
    document = Path("reviewer/index.html").read_text(encoding="utf-8")
    assert "if (signed) {" in document and "panel.append(form);" in document
    assert "does not verify HMAC seals" in document
    assert "review_history" in document
    assert "previous_disposition" in document


def test_reviewer_workbench_validates_history_entries_and_bounds_rendering() -> None:
    document = Path("reviewer/index.html").read_text(encoding="utf-8")
    assert "MAX_FINDINGS = 5000" in document
    assert "MAX_REVIEW_EVENTS = 500" in document
    assert "findingIds.has(finding.id)" in document
    assert "Array.isArray(reviewEvent)" in document
    assert "reviewEvent.previous_disposition" in document
    assert "reviewEvent.recorded_at.length > 64" in document
    assert "Number.isFinite(Date.parse(reviewEvent.recorded_at))" in document
    assert r"!/(?:Z|[+-]\d{2}:\d{2})$/i" in document
    assert r"!/(?:Z|[+-]\\d{2}:\\d{2})$/i" not in document
    assert "!historyIsConsistent(finding)" in document
    assert "finding.requires_review !== undefined" in document
    assert "Use the CLI to review larger reports." in document
