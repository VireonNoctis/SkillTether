from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from skilltether.cli import build_parser, main
from skilltether.models import ComparisonReport, Finding, new_finding
from skilltether.report import read_json_report, write_json_report, write_markdown_report
from skilltether.reviewing import has_audited_approval, record_review


def critical_finding() -> Finding:
    return new_finding(
        "CRITICAL_INVARIANT_REVIEW_REQUIRED",
        "critical",
        "semantic_invariant",
        "This invariant requires a human decision.",
        "Automated checks do not establish semantic equivalence.",
        path="SKILL.md",
        original_context="Do not weaken this prerequisite.",
        target_context="Review target-language context.",
        requires_review=True,
    )


def comparison(finding: Finding) -> ComparisonReport:
    return ComparisonReport.create(
        tool_version="0.1.0",
        protected_policy_fingerprint="a" * 64,
        source_fingerprint="b" * 64,
        target_fingerprint="c" * 64,
        source_files={"SKILL.md": "b" * 64},
        target_files={"SKILL.md": "c" * 64},
        structural_status="pass",
        semantic_status="review_recommended",
        findings=[finding],
    )


def test_review_appends_auditable_decision_and_requires_rationale() -> None:
    finding = critical_finding()
    event = record_review(
        finding,
        disposition="approved",
        reviewer="  reviewer-1  ",
        note="Compared the complete source and target context.",
        recorded_at=datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc),
    )

    assert event.previous_disposition == "pending"
    assert event.disposition == "approved"
    assert event.reviewer == "reviewer-1"
    assert event.note.startswith("Compared")
    assert finding.disposition == "approved"
    assert has_audited_approval(finding)


def test_changed_decision_is_appended_and_old_approval_no_longer_gates_export() -> None:
    finding = critical_finding()
    record_review(
        finding,
        disposition="approved",
        reviewer="reviewer-1",
        note="Initial review completed.",
        recorded_at=datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc),
    )
    record_review(
        finding,
        disposition="deferred",
        reviewer="reviewer-2",
        note="Need a language specialist to check the modal strength.",
        recorded_at=datetime(2026, 10, 27, 12, 5, tzinfo=timezone.utc),
    )

    assert len(finding.review_history) == 2
    assert finding.review_history[1].previous_disposition == "approved"
    assert finding.review_history[1].disposition == "deferred"
    assert finding.disposition == "deferred"
    assert not has_audited_approval(finding)


def test_manually_set_approved_disposition_without_history_is_not_approval_evidence() -> None:
    finding = critical_finding()
    # Simulate an old or manually edited report with a bare approval field.
    finding.disposition = "approved"
    finding.reviewer = "reviewer-1"
    finding.review_note = "Looks good."

    assert not has_audited_approval(finding)


def test_legacy_approval_can_be_re_reviewed_and_start_a_history() -> None:
    finding = critical_finding()
    finding.disposition = "approved"
    finding.reviewer = "old-reviewer"
    finding.review_note = "Legacy report has no decision history."
    assert not has_audited_approval(finding)

    event = record_review(
        finding,
        disposition="approved",
        reviewer="reviewer-2",
        note="Re-reviewed the current source and target context.",
        recorded_at=datetime(2026, 10, 27, 12, 10, tzinfo=timezone.utc),
    )
    assert event.previous_disposition == "approved"
    assert has_audited_approval(finding)


@pytest.mark.parametrize("reviewer,note", [
    (" ", "A useful explanation."),
    ("reviewer-1", "  "),
])
def test_review_rejects_blank_actor_or_rationale(reviewer: str, note: str) -> None:
    with pytest.raises(ValueError, match="must not be blank"):
        record_review(critical_finding(), disposition="approved", reviewer=reviewer, note=note)


def test_review_rejects_obvious_credential_material_without_echoing_it() -> None:
    secret = "api_key=sk_live_this_is_a_fake_long_credential_value"
    with pytest.raises(ValueError, match="resembles credential material") as error:
        record_review(
            critical_finding(),
            disposition="approved",
            reviewer="reviewer-1",
            note=f"Approved after checking {secret}",
        )
    assert secret not in str(error.value)


def test_legacy_report_finding_remains_readable_with_additive_defaults() -> None:
    finding = Finding.model_validate({
        "id": "legacy-1",
        "code": "LINE_CHANGED",
        "severity": "info",
        "category": "line_diff",
        "message": "The lines differ.",
        "rationale": "A line change is not itself proof of semantic drift.",
        "disposition": "approved",
    })

    assert finding.analysis_method == "unknown"
    assert finding.uncertainty == "unknown"
    assert finding.review_history == []
    assert not has_audited_approval(finding)


def test_review_history_survives_json_and_markdown_exports(tmp_path: Path) -> None:
    finding = critical_finding()
    hostile_note = "<img src=x onerror=alert(1)>\n[click](javascript:alert(1))\n~~~"
    record_review(
        finding,
        disposition="approved",
        reviewer="reviewer-1",
        note=hostile_note,
        recorded_at=datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc),
    )
    report = comparison(finding)
    json_path = tmp_path / "report.json"
    markdown_path = tmp_path / "report.md"

    write_json_report(report, json_path)
    reloaded = read_json_report(json_path)
    assert len(reloaded.findings[0].review_history) == 1
    assert reloaded.findings[0].review_history[0].note == hostile_note

    write_markdown_report(reloaded, markdown_path)
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "**Review history**" in markdown
    assert "- Signal uncertainty:" in markdown
    assert "onerror=alert(1)" in markdown
    assert "[click](javascript:alert(1))" in markdown
    assert "```text" in markdown  # untrusted note is fenced instead of parsed as Markdown


def test_schema_documents_new_fields_without_breaking_old_required_contract() -> None:
    schema_path = Path("schemas/comparison-report.schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    finding_schema = schema["properties"]["findings"]["items"]
    properties = finding_schema["properties"]

    assert {"rule_id", "analysis_method", "uncertainty", "severity_rationale", "review_history"} <= set(properties)
    assert "review_history" not in finding_schema["required"]
    assert "review_history" in properties


def test_review_cli_requires_a_note() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([
            "review", "report.json", "finding-1",
            "--disposition", "approved", "--reviewer", "reviewer-1",
        ])



def test_report_schema_validates_actual_serialized_report(tmp_path: Path) -> None:
    from jsonschema import Draft202012Validator, FormatChecker

    schema = json.loads(Path("schemas/comparison-report.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    report = comparison(critical_finding())
    errors = sorted(validator.iter_errors(report.model_dump(mode="json")), key=lambda error: list(error.absolute_path))

    assert not errors, "\n".join(f"{list(error.absolute_path)}: {error.message}" for error in errors)


def test_report_schema_rejects_unknown_severity_value() -> None:
    from jsonschema import Draft202012Validator, FormatChecker

    schema = json.loads(Path("schemas/comparison-report.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    payload = comparison(critical_finding()).model_dump(mode="json")
    payload["findings"][0]["severity"] = "probably-safe"

    errors = list(validator.iter_errors(payload))

    assert any(list(error.absolute_path) == ["findings", 0, "severity"] for error in errors)



def test_report_metadata_escapes_markdown_structure_and_newlines(tmp_path: Path) -> None:
    from skilltether.report import write_markdown_report

    hostile = new_finding(
        "LINE_CHANGED",
        "info",
        "line_diff",
        "line one\n## Injected heading [click](javascript:alert(1))",
        "A rationale with *emphasis* and \nnew line.",
        path="refs/guide\n[link](javascript:alert(1)).md",
        proposed_change="Review [this](javascript:alert(1)) safely.",
    )
    path = tmp_path / "untrusted.md"
    write_markdown_report(comparison(hostile), path)
    markdown = path.read_text(encoding="utf-8")

    assert "\n## Injected heading" not in markdown
    assert "\\[click\\]" in markdown
    assert "\\(javascript:alert\\(1\\)\\)" in markdown
    assert "- Path: refs/guide " in markdown


def test_report_write_is_atomic_and_does_not_follow_destination_symlink(tmp_path: Path) -> None:
    import os
    import stat

    from skilltether.report import read_json_report, write_json_report

    if not hasattr(os, "symlink"):
        pytest.skip("symlinks are not available on this platform")
    victim = tmp_path / "victim.txt"
    victim.write_text("do not overwrite", encoding="utf-8")
    report_path = tmp_path / "report.json"
    try:
        report_path.symlink_to(victim)
    except OSError:
        pytest.skip("symlink creation is not permitted")

    write_json_report(comparison(critical_finding()), report_path)

    assert victim.read_text(encoding="utf-8") == "do not overwrite"
    assert not report_path.is_symlink()
    assert len(read_json_report(report_path).findings) == 1
    if os.name == "posix":
        assert stat.S_IMODE(report_path.stat().st_mode) == 0o600


def test_compare_refuses_report_path_inside_source_package(tmp_path: Path) -> None:
    source = tmp_path / "source" / "sample-skill"
    target = tmp_path / "target" / "sample-skill"
    for package in (source, target):
        package.mkdir(parents=True)
        (package / "SKILL.md").write_text(
            f"---\nname: sample-skill\ndescription: A skill.\n---\n\nInstructions.\n",
            encoding="utf-8",
        )
    before = (source / "SKILL.md").read_bytes()
    result = main(["compare", str(source), str(target), "--out", str(source / "report.json")])

    assert result == 2
    assert not (source / "report.json").exists()
    assert (source / "SKILL.md").read_bytes() == before


def test_translate_refuses_report_path_that_would_overwrite_source(tmp_path: Path) -> None:
    source = tmp_path / "source" / "sample-skill"
    source.mkdir(parents=True)
    skill_file = source / "SKILL.md"
    skill_file.write_text(
        "---\nname: sample-skill\ndescription: A skill.\n---\n\nTranslate this sentence.\n",
        encoding="utf-8",
    )
    before = skill_file.read_bytes()
    output = tmp_path / "candidate" / "sample-skill"
    result = main([
        "translate", str(source), str(output),
        "--source-locale", "en", "--target-locale", "fr", "--adapter", "identity",
        "--report", str(skill_file), "--history-db", str(tmp_path / "history.sqlite3"),
    ])

    assert result == 2
    assert not output.exists()
    assert skill_file.read_bytes() == before


def test_compare_refuses_same_json_and_markdown_output_path(tmp_path: Path) -> None:
    source = tmp_path / "source" / "sample-skill"
    target = tmp_path / "target" / "sample-skill"
    for package in (source, target):
        package.mkdir(parents=True)
        (package / "SKILL.md").write_text(
            f"---\nname: sample-skill\ndescription: A skill.\n---\n\nInstructions.\n",
            encoding="utf-8",
        )
    report_path = tmp_path / "report.out"
    result = main([
        "compare", str(source), str(target),
        "--out", str(report_path), "--markdown", str(report_path),
    ])

    assert result == 2
    assert not report_path.exists()



def test_review_events_must_be_chronological() -> None:
    finding = critical_finding()
    record_review(
        finding, disposition="approved", reviewer="reviewer-1",
        note="Reviewed initial target context.",
        recorded_at=datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc),
    )
    with pytest.raises(ValueError, match="must not precede"):
        record_review(
            finding, disposition="deferred", reviewer="reviewer-2",
            note="The decision needs further review.",
            recorded_at=datetime(2026, 10, 27, 11, 59, tzinfo=timezone.utc),
        )
    assert len(finding.review_history) == 1
    assert has_audited_approval(finding)


def test_audit_gate_rejects_manually_reordered_timestamps() -> None:
    finding = critical_finding()
    record_review(
        finding, disposition="approved", reviewer="reviewer-1",
        note="Initial review.", recorded_at=datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc),
    )
    record_review(
        finding, disposition="deferred", reviewer="reviewer-2",
        note="Needs a second look.", recorded_at=datetime(2026, 10, 27, 12, 1, tzinfo=timezone.utc),
    )
    record_review(
        finding, disposition="approved", reviewer="reviewer-3",
        note="Re-reviewed all context.", recorded_at=datetime(2026, 10, 27, 12, 2, tzinfo=timezone.utc),
    )
    finding.review_history[1].recorded_at = "2026-10-27T11:59:00+00:00"

    assert not has_audited_approval(finding)



def test_compare_fail_on_review_is_an_optional_ci_gate(tmp_path: Path) -> None:
    source = tmp_path / "source" / "sample-skill"
    target = tmp_path / "target" / "sample-skill"
    for package in (source, target):
        package.mkdir(parents=True)
        (package / "SKILL.md").write_text(
            f"---\nname: sample-skill\ndescription: A skill.\n---\n\nInstructions.\n",
            encoding="utf-8",
        )

    report_path = tmp_path / "report.json"
    default_result = main(["compare", str(source), str(target), "--out", str(report_path)])
    gated_result = main([
        "compare", str(source), str(target),
        "--out", str(report_path), "--fail-on-review",
    ])

    assert default_result == 0
    assert gated_result == 1
    assert report_path.exists()



def test_terminal_findings_collapse_untrusted_control_characters(capsys: pytest.CaptureFixture[str]) -> None:
    from skilltether.cli import _show_findings

    message = f"unsafe{chr(27)}[31mred{chr(27)}[0m\nforged"
    _show_findings([new_finding(
        "UNTRUSTED_TEST", "high", "test", message, "A test message with terminal controls.",
        path="name" + chr(27) + "[2J",
    )])
    output = capsys.readouterr().out

    assert chr(27) not in output
    assert "\nforged" not in output
    assert "unsafe" in output and "forged" in output



def test_report_path_guard_catches_symlink_inside_source_package(tmp_path: Path) -> None:
    source = tmp_path / "source" / "sample-skill"
    target = tmp_path / "target" / "sample-skill"
    for package in (source, target):
        package.mkdir(parents=True)
        (package / "SKILL.md").write_text(
            f"---\nname: sample-skill\ndescription: A skill.\n---\n\nInstructions.\n",
            encoding="utf-8",
        )
    external = tmp_path / "external.json"
    external.write_text("external sentinel", encoding="utf-8")
    report_link = source / "report.json"
    try:
        report_link.symlink_to(external)
    except OSError:
        pytest.skip("symlink creation is not permitted")
    before = external.read_bytes()

    result = main(["compare", str(source), str(target), "--out", str(report_link)])

    assert result == 2
    assert report_link.is_symlink()
    assert external.read_bytes() == before


def test_report_path_guard_catches_external_alias_to_source_package(tmp_path: Path) -> None:
    source = tmp_path / "source" / "sample-skill"
    target = tmp_path / "target" / "sample-skill"
    for package in (source, target):
        package.mkdir(parents=True)
        (package / "SKILL.md").write_text(
            f"---\nname: sample-skill\ndescription: A skill.\n---\n\nInstructions.\n",
            encoding="utf-8",
        )
    alias_parent = tmp_path / "source-alias"
    try:
        alias_parent.symlink_to(source, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlink creation is not permitted")
    report_path = alias_parent / "report.json"

    result = main(["compare", str(source), str(target), "--out", str(report_path)])

    assert result == 2
    assert not (source / "report.json").exists()



def test_report_pydantic_contract_rejects_bad_fingerprints_and_naive_timestamps() -> None:
    from pydantic import ValidationError

    report = comparison(critical_finding())
    payload = report.model_dump(mode="json")
    payload["source_fingerprint"] = "not-a-sha256"
    with pytest.raises(ValidationError):
        ComparisonReport.model_validate(payload)

    payload = report.model_dump(mode="json")
    payload["generated_at"] = "2026-10-27T12:00:00"
    with pytest.raises(ValidationError, match="timezone"):
        ComparisonReport.model_validate(payload)


def test_report_read_and_write_sizes_are_bounded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import skilltether.report as report_module

    monkeypatch.setattr(report_module, "MAX_REPORT_BYTES", 64)
    path = tmp_path / "oversized.json"
    path.write_text("{" + " " * 100 + "}", encoding="utf-8")
    with pytest.raises(ValueError, match="safety limit"):
        read_json_report(path)

    out = tmp_path / "not-written.json"
    with pytest.raises(ValueError, match="safety limit"):
        write_json_report(comparison(critical_finding()), out)
    assert not out.exists()
