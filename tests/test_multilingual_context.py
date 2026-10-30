from __future__ import annotations

from pathlib import Path

from skilltether.compare import compare_packages
from skilltether.models import Invariant, InvariantManifest


def make_skill(path: Path, heading: str, instruction: str) -> Path:
    path.mkdir(parents=True)
    (path / "SKILL.md").write_text(
        "---\n"
        f"name: {path.name}\n"
        "description: A context alignment test skill.\n"
        "---\n\n"
        f"# {heading}\n"
        f"{instruction}\n",
        encoding="utf-8",
    )
    return path


def make_manifest() -> InvariantManifest:
    invariant = Invariant(
        id="SAFE-DELETE-01",
        statement="Never remove this backup file.",
        category="negation",
        severity="critical",
        source_path="SKILL.md",
        source_lines=(7, 7),
        source_text="Never remove this backup file.",
        negation_required=True,
        negation_markers=["jamais", "ne pas"],
        reviewed=True,
        reviewer="reviewer-1",
    )
    return InvariantManifest(
        source_locale="en",
        target_locale="fr",
        manifest_reviewed=True,
        manifest_reviewer="reviewer-1",
        invariants=[invariant],
    )


def test_translated_line_uses_high_uncertainty_positional_context_fallback(tmp_path: Path) -> None:
    source = make_skill(tmp_path / "source" / "sample-skill", "Instructions", "Never remove this backup file.")
    target = make_skill(tmp_path / "target" / "sample-skill", "Consignes", "Ne supprimez jamais cette sauvegarde.")
    report = compare_packages(source, target, make_manifest(), target_locale="fr")

    positional = next(
        finding for finding in report.findings
        if finding.code == "INVARIANT_TARGET_CONTEXT_POSITIONAL"
    )
    assert positional.analysis_method == "heuristic"
    assert positional.uncertainty == "high"
    assert positional.target_line == 7
    assert positional.target_context == "Ne supprimez jamais cette sauvegarde."
    assert not any(f.code == "INVARIANT_NEGATION_UNCERTAIN" for f in report.findings)


def test_positional_alignment_does_not_hide_missing_negation(tmp_path: Path) -> None:
    source = make_skill(tmp_path / "source" / "sample-skill", "Instructions", "Never remove this backup file.")
    target = make_skill(tmp_path / "target" / "sample-skill", "Consignes", "Supprimez cette sauvegarde.")
    report = compare_packages(source, target, make_manifest(), target_locale="fr")

    assert any(f.code == "INVARIANT_TARGET_CONTEXT_POSITIONAL" for f in report.findings)
    missing = next(f for f in report.findings if f.code == "INVARIANT_NEGATION_UNCERTAIN")
    assert missing.analysis_method == "heuristic"
    assert missing.uncertainty == "high"
