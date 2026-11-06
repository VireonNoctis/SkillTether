from __future__ import annotations

from pathlib import Path

import pytest

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


@pytest.mark.parametrize(
    ("locale", "target_sentence"),
    [
        ("ar", "الحد الأقصى هو ٣ محاولات."),
        ("hi", "अधिकतम ३ प्रयास हैं।"),
        ("ja", "最大試行回数は３回です。"),
        ("zh", "最多尝试３次。"),
        ("ru", "Не более 3 попыток."),
    ],
)
def test_human_anchored_numeric_invariants_cover_multiple_scripts(
    tmp_path: Path, locale: str, target_sentence: str,
) -> None:
    from skilltether.models import Invariant

    source_sentence = "Do not exceed 3 retries."
    source = make_skill(
        tmp_path / "source" / "sample-skill", "Instructions", source_sentence,
    )
    target = make_skill(
        tmp_path / "target" / "sample-skill", "Инструкции", target_sentence,
    )
    target_lines = (target / "SKILL.md").read_text(encoding="utf-8").splitlines()
    target_line = target_lines.index(target_sentence) + 1
    invariant = Invariant(
        id=f"SAFE-NUMBER-{locale.upper()}",
        statement=source_sentence,
        category="numeric_limit",
        severity="critical",
        source_path="SKILL.md",
        source_lines=(7, 7),
        source_text=source_sentence,
        target_lines=(target_line, target_line),
        target_text=target_sentence,
        expected_numbers=["3"],
        reviewed=True,
        reviewer="reviewer-1",
    )
    manifest = InvariantManifest(
        source_locale="en",
        target_locale=locale,
        manifest_reviewed=True,
        manifest_reviewer="reviewer-1",
        invariants=[invariant],
    )

    report = compare_packages(source, target, manifest, target_locale=locale)

    assert not any(
        finding.code in {
            "INVARIANT_REQUIRED_TOKEN_MISSING",
            "INVARIANT_TARGET_CONTEXT_UNCERTAIN",
            "INVARIANT_TARGET_CONTEXT_POSITIONAL",
        }
        for finding in report.findings
    )
    critical = next(
        finding for finding in report.findings
        if finding.code == "CRITICAL_INVARIANT_REVIEW_REQUIRED"
    )
    assert critical.target_line == target_line
    assert critical.target_context == target_sentence


def test_single_shared_word_does_not_confirm_target_context() -> None:
    from skilltether.compare import _find_invariant_context

    target = "This unrelated line mentions the source once.\nAnother unrelated instruction follows."
    alignment = _find_invariant_context(
        target,
        "Never delete the source file before inspection.",
    )
    assert alignment is None
