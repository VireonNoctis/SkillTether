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
