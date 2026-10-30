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


def test_reviewer_workbench_keeps_signed_reports_read_only() -> None:
    document = Path("reviewer/index.html").read_text(encoding="utf-8")
    assert "if (signed) return;" in document
    assert "does not verify HMAC seals" in document
    assert "review_history" in document
    assert "previous_disposition" in document
