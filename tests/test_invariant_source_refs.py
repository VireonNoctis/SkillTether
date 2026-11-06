from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from skilltether.cli import main
from skilltether.compare import compare_packages
from skilltether.models import Invariant, InvariantManifest
from skilltether.report import write_json_report


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


def _write_manifest(path: Path, invariant: Invariant) -> InvariantManifest:
    manifest = reviewed_manifest(invariant)
    path.write_text(
        yaml.safe_dump(manifest.model_dump(mode="json", exclude_none=True), sort_keys=False),
        encoding="utf-8",
    )
    return manifest


def test_human_verified_target_anchor_locates_translated_context_without_positional_guessing(
    tmp_path: Path,
) -> None:
    source_sentence = "Do not exceed 3 retries."
    target_sentence = "Ne dépassez pas 3 tentatives."
    source = make_package(
        tmp_path / "source" / "sample-skill",
        source_sentence,
    )
    target = make_package(
        tmp_path / "target" / "sample-skill",
        "An added introduction.\nAnother translated paragraph.\n" + target_sentence,
    )
    target_lines = (target / "SKILL.md").read_text(encoding="utf-8").splitlines()
    target_line = target_lines.index(target_sentence) + 1
    invariant = Invariant(
        id="INV-TARGET-ANCHOR-1",
        statement="Do not exceed 3 retries.",
        category="safety_constraint",
        severity="critical",
        source_path="SKILL.md",
        source_lines=(8, 8),
        source_text=source_sentence,
        target_lines=(target_line, target_line),
        target_text=target_sentence,
        expected_numbers=["3"],
        reviewed=True,
        reviewer="qa-reviewer",
    )

    report = compare_packages(
        source, target, reviewed_manifest(invariant), target_locale="fr",
    )

    assert not any(
        finding.code in {
            "INVARIANT_TARGET_CONTEXT_POSITIONAL",
            "INVARIANT_TARGET_CONTEXT_UNCERTAIN",
            "INVARIANT_REQUIRED_TOKEN_MISSING",
        }
        for finding in report.findings
    )
    critical = next(
        finding for finding in report.findings
        if finding.code == "CRITICAL_INVARIANT_REVIEW_REQUIRED"
    )
    assert critical.target_line == target_line
    assert critical.target_context == target_sentence
    # An exact human anchor identifies context; it does not remove critical sign-off.


@pytest.mark.parametrize(
    ("target_lines", "target_text", "expected_message"),
    [
        ((8, 8), "A stale excerpt.", "no longer matches"),
        ((80, 81), "A range beyond the resource.", "exceeds the current"),
    ],
)
def test_stale_target_anchor_is_a_deterministic_critical_blocker(
    tmp_path: Path,
    target_lines: tuple[int, int],
    target_text: str,
    expected_message: str,
) -> None:
    source_sentence = "Do not exceed 3 retries."
    target_sentence = "Ne dépassez pas 3 tentatives."
    source = make_package(tmp_path / "source" / "sample-skill", source_sentence)
    target = make_package(tmp_path / "target" / "sample-skill", target_sentence)
    invariant = Invariant(
        id="INV-TARGET-ANCHOR-STALE",
        statement="Do not exceed 3 retries.",
        severity="critical",
        source_path="SKILL.md",
        source_lines=(8, 8),
        source_text=source_sentence,
        target_lines=target_lines,
        target_text=target_text,
        reviewed=True,
        reviewer="qa-reviewer",
    )

    report = compare_packages(
        source, target, reviewed_manifest(invariant), target_locale="fr",
    )
    finding = next(
        finding for finding in report.findings
        if finding.code == "INVARIANT_TARGET_REFERENCE_INVALID"
    )

    assert expected_message in finding.message
    assert finding.severity == "critical"
    assert finding.analysis_method == "deterministic"
    assert finding.uncertainty == "none"
    assert finding.requires_review is True


def test_target_anchor_fields_must_be_paired() -> None:
    with pytest.raises(ValueError, match="target_lines and target_text must be supplied together"):
        Invariant(
            id="INV-TARGET-PAIR",
            statement="The target passage is reviewed.",
            target_lines=(8, 8),
        )


def test_target_anchor_manifest_matches_json_schema_and_rejects_incomplete_pair() -> None:
    import json
    import jsonschema

    schema = json.loads(
        Path("schemas/invariant-manifest.schema.json").read_text(encoding="utf-8")
    )
    validator = jsonschema.Draft202012Validator(schema)
    manifest = reviewed_manifest(Invariant(
        id="INV-TARGET-SCHEMA",
        statement="The source and target are anchored.",
        target_lines=(8, 8),
        target_text="Target-language excerpt.",
        reviewed=True,
        reviewer="qa-reviewer",
    ))
    payload = manifest.model_dump(mode="json", exclude_none=True)

    validator.validate(payload)
    payload["invariants"][0].pop("target_text")
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(payload)


def test_approval_cannot_override_stale_target_reference(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    source_sentence = "Do not exceed 3 retries."
    target_sentence = "Ne dépassez pas 3 tentatives."
    source = make_package(tmp_path / "source" / "sample-skill", source_sentence)
    target = make_package(tmp_path / "target" / "sample-skill", target_sentence)
    invariant = Invariant(
        id="INV-TARGET-ANCHOR-BLOCK",
        statement="Do not exceed 3 retries.",
        severity="critical",
        source_path="SKILL.md",
        source_lines=(8, 8),
        source_text=source_sentence,
        target_lines=(8, 8),
        target_text="Stale target excerpt.",
        reviewed=True,
        reviewer="qa-reviewer",
    )
    manifest_path = tmp_path / "invariants.yaml"
    manifest = _write_manifest(manifest_path, invariant)
    report = compare_packages(source, target, manifest, target_locale="fr")
    report_path = tmp_path / "report.json"
    write_json_report(report, report_path)
    blocker = next(
        item for item in report.findings
        if item.code == "INVARIANT_TARGET_REFERENCE_INVALID"
    )

    assert main([
        "review", str(report_path), blocker.id,
        "--disposition", "approved", "--reviewer", "qa-reviewer",
        "--note", "Reviewed the report but the target anchor must be corrected.",
    ]) == 0

    output = tmp_path / "approved" / "sample-skill"
    result = main([
        "approve", str(source), str(target),
        "--report", str(report_path), "--output", str(output),
        "--invariants", str(manifest_path),
    ])

    assert result == 2
    assert "invalid source/target references" in capsys.readouterr().err
    assert not output.exists()


def test_approval_cannot_override_stale_source_reference(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
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
        "Never deploy without approval.\\n", encoding="utf-8",
    )
    manifest = reviewed_manifest(Invariant(
        id="INV-SOURCE-BLOCK",
        statement="Never deploy without approval.",
        source_path="references/old.md",
        source_lines=(1, 1),
        source_text="Never deploy without approval.",
        reviewed=True,
        reviewer="qa-reviewer",
    ))
    manifest_path = tmp_path / "invariants.yaml"
    manifest_path.write_text(
        yaml.safe_dump(manifest.model_dump(mode="json", exclude_none=True), sort_keys=False),
        encoding="utf-8",
    )
    report = compare_packages(source, target, manifest, target_locale="fr")
    report_path = tmp_path / "report.json"
    write_json_report(report, report_path)
    output = tmp_path / "approved" / "sample-skill"

    result = main([
        "approve", str(source), str(target),
        "--report", str(report_path),
        "--output", str(output),
        "--invariants", str(manifest_path),
    ])

    assert result == 2
    assert "invalid source references" in capsys.readouterr().err
    assert not output.exists()
