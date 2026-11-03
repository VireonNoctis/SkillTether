from __future__ import annotations

from pathlib import Path

import skilltether.analysis as analysis


def test_percent_decoded_nul_in_local_link_is_reported_not_raised(
    tmp_path: Path, monkeypatch,
) -> None:
    package = tmp_path / "sample-skill"
    package.mkdir()
    monkeypatch.setattr(
        analysis,
        "markdown_link_targets",
        lambda _text: [("link_open", "references%00/guide.md")],
    )

    findings = analysis.validate_local_links(
        package, "SKILL.md", "See the linked reference."
    )

    invalid_path = [finding for finding in findings if finding.code == "LOCAL_LINK_PATH_INVALID"]
    assert len(invalid_path) == 1
    assert invalid_path[0].severity == "medium"
    assert invalid_path[0].requires_review is True
    assert invalid_path[0].analysis_method == "deterministic"
    assert invalid_path[0].uncertainty == "none"

def test_absolute_local_filesystem_links_are_flagged_but_web_and_mail_links_are_ignored(
    tmp_path: Path, monkeypatch,
) -> None:
    package = tmp_path / "sample-skill"
    package.mkdir()
    targets = [
        ("link_open", "file:///etc/passwd"),
        ("link_open", r"C:\\Users\\example\\private.txt"),
        ("link_open", r"\\\\server\\share\\private.txt"),
        ("link_open", "https://example.test/guide"),
        ("link_open", "mailto:owner@example.test"),
    ]
    monkeypatch.setattr(analysis, "markdown_link_targets", lambda _text: targets)

    findings = analysis.validate_local_links(
        package, "SKILL.md", "See the references."
    )

    local_paths = [finding for finding in findings if finding.code == "LOCAL_LINK_EXTERNAL_PATH"]
    assert len(local_paths) == 3
    assert all(finding.severity == "medium" for finding in local_paths)
    assert all(finding.requires_review for finding in local_paths)
    assert all(finding.analysis_method == "deterministic" for finding in local_paths)
    assert all(finding.uncertainty == "none" for finding in local_paths)
    assert not [finding for finding in findings if finding.code == "LOCAL_LINK_URL_INVALID"]
