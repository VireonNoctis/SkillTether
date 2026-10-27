from __future__ import annotations

from pathlib import Path

import pytest

from skilltether.compare import compare_packages
from skilltether.models import Invariant, InvariantManifest


def make_package(root: Path, instruction: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "SKILL.md").write_text(
        f"---\nname: {root.name}\ndescription: A source-reference test skill.\n---\n\n"
        f"# Instructions\n\n{instruction}\n",
        encoding="utf-8",
    )
    return root


def reviewed_manifest(invariant: Invariant) -> InvariantManifest:
    return InvariantManifest(
        source_locale="en",
        target_locale="fr",
        manifest_reviewed=True,
        manifest_reviewer="test-reviewer",
        invariants=[invariant],
    )


def compare_with_invariant(
    tmp_path: Path,
    invariant: Invariant,
    source_instruction: str = "You must not run deploy without approval.",
) :
    source = make_package(tmp_path / "source" / "sample-skill", source_instruction)
    target = make_package(tmp_path / "target" / "sample-skill", source_instruction)
    return compare_packages(
        source, target, reviewed_manifest(invariant), target_locale="fr",
    )


def test_current_source_excerpt_and_line_range_are_accepted(tmp_path: Path) -> None:
    statement = "You must not run deploy without approval."
    report = compare_with_invariant(
        tmp_path,
        Invariant(
            id="INV-SOURCE-1",
            statement=statement,
            source_path="SKILL.md",
            source_lines=(8, 8),
            source_text=statement,
            reviewed=True,
            reviewer="qa-reviewer",
        ),
    )

    assert not any(
        finding.code == "INVARIANT_SOURCE_REFERENCE_INVALID"
        for finding in report.findings
    )


def test_stale_source_excerpt_with_valid_lines_is_a_critical_finding(tmp_path: Path) -> None:
    report = compare_with_invariant(
        tmp_path,
        Invariant(
            id="INV-SOURCE-2",
            statement="Never deploy without approval.",
            source_path="SKILL.md",
            source_lines=(8, 8),
            source_text="You must deploy without approval.",
            reviewed=True,
            reviewer="qa-reviewer",
        ),
    )

    finding = next(
        finding for finding in report.findings
        if finding.code == "INVARIANT_SOURCE_REFERENCE_INVALID"
    )
    assert finding.severity == "critical"
    assert finding.analysis_method == "deterministic"
    assert finding.uncertainty == "none"
    assert finding.requires_review is True


def test_source_line_range_beyond_current_resource_is_invalid(tmp_path: Path) -> None:
    report = compare_with_invariant(
        tmp_path,
        Invariant(
            id="INV-SOURCE-3",
            statement="Never deploy without approval.",
            source_path="SKILL.md",
            source_lines=(80, 81),
            source_text="Old source excerpt.",
            reviewed=True,
            reviewer="qa-reviewer",
        ),
    )

    finding = next(
        finding for finding in report.findings
        if finding.code == "INVARIANT_SOURCE_REFERENCE_INVALID"
    )
    assert "exceeds the current" in finding.message


def test_missing_source_resource_is_invalid_even_if_target_has_a_context(tmp_path: Path) -> None:
    source = make_package(
        tmp_path / "source" / "sample-skill",
        "You must not run deploy without approval.",
    )
    target = make_package(
        tmp_path / "target" / "sample-skill",
        "You must not run deploy without approval.",
    )
    (target / "references").mkdir()
    (target / "references" / "old.md").write_text(
        "Never deploy without approval.\n", encoding="utf-8",
    )
    invariant = Invariant(
        id="INV-SOURCE-4",
        statement="Never deploy without approval.",
        source_path="references/old.md",
        source_lines=(1, 1),
        source_text="Never deploy without approval.",
        reviewed=True,
        reviewer="qa-reviewer",
    )

    report = compare_packages(
        source, target, reviewed_manifest(invariant), target_locale="fr",
    )
    finding = next(
        finding for finding in report.findings
        if finding.code == "INVARIANT_SOURCE_REFERENCE_INVALID"
    )
    assert finding.path == "references/old.md"


def test_unanchored_invariants_remain_supported_when_optional_refs_are_omitted(
    tmp_path: Path,
) -> None:
    report = compare_with_invariant(
        tmp_path,
        Invariant(
            id="INV-SOURCE-5",
            statement="Never deploy without approval.",
            reviewed=True,
            reviewer="qa-reviewer",
        ),
    )

    assert not any(
        finding.code == "INVARIANT_SOURCE_REFERENCE_INVALID"
        for finding in report.findings
    )
