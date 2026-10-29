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


def test_init_manifest_refuses_output_inside_source_package(tmp_path: Path) -> None:
    source = tmp_path / "sample-skill"
    source.mkdir()
    (source / "SKILL.md").write_text(
        "---\nname: sample-skill\ndescription: A sample skill.\n---\n\nYou must preserve all constraints.\n",
        encoding="utf-8",
    )
    output = source / ".skilltether-invariants.yaml"

    result = main([
        "init-manifest", str(source), "--out", str(output),
        "--source-locale", "en", "--target-locale", "fr",
    ])

    assert result == 2
    assert not output.exists()
    assert sorted(path.name for path in source.iterdir()) == ["SKILL.md"]


def test_init_manifest_does_not_follow_destination_symlink(tmp_path: Path) -> None:
    import os

    if not hasattr(os, "symlink"):
        pytest.skip("symlinks are not available on this platform")
    source = tmp_path / "sample-skill"
    source.mkdir()
    (source / "SKILL.md").write_text(
        "---\nname: sample-skill\ndescription: A sample skill.\n---\n\nYou must preserve all constraints.\n",
        encoding="utf-8",
    )
    victim = tmp_path / "victim.txt"
    victim.write_text("keep this file", encoding="utf-8")
    output = tmp_path / "manifest.yaml"
    try:
        output.symlink_to(victim)
    except OSError:
        pytest.skip("symlink creation is not permitted")

    result = main([
        "init-manifest", str(source), "--out", str(output),
        "--source-locale", "en", "--target-locale", "fr",
    ])

    assert result == 2
    assert victim.read_text(encoding="utf-8") == "keep this file"
    assert output.is_symlink()


def test_init_manifest_refuses_symlink_created_during_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import os
    import skilltether.cli as cli

    if not hasattr(os, "symlink") or not hasattr(os, "link"):
        pytest.skip("hard links or symlinks are not available on this platform")
    source = tmp_path / "sample-skill"
    source.mkdir()
    (source / "SKILL.md").write_text(
        "---\nname: sample-skill\ndescription: A sample skill.\n---\n\nYou must preserve all constraints.\n",
        encoding="utf-8",
    )
    victim = tmp_path / "victim.txt"
    victim.write_text("keep this file", encoding="utf-8")
    output = tmp_path / "manifest.yaml"
    original_link = os.link

    def create_symlink_then_link(src, dst, *args, **kwargs):
        if Path(dst) == output and not output.exists() and not output.is_symlink():
            try:
                output.symlink_to(victim)
            except OSError:
                pytest.skip("symlink creation is not permitted")
        return original_link(src, dst, *args, **kwargs)

    monkeypatch.setattr(cli.os, "link", create_symlink_then_link)
    result = main([
        "init-manifest", str(source), "--out", str(output),
        "--source-locale", "en", "--target-locale", "fr",
    ])

    assert result == 2
    assert output.is_symlink()
    assert victim.read_text(encoding="utf-8") == "keep this file"


def test_init_manifest_writes_new_draft_without_overwriting_existing_file(tmp_path: Path) -> None:
    source = tmp_path / "sample-skill"
    source.mkdir()
    (source / "SKILL.md").write_text(
        "---\nname: sample-skill\ndescription: A sample skill.\n---\n\nYou must preserve all constraints.\n",
        encoding="utf-8",
    )
    output = tmp_path / "manifest.yaml"
    output.write_text("reviewed: true\n", encoding="utf-8")

    result = main([
        "init-manifest", str(source), "--out", str(output),
        "--source-locale", "en", "--target-locale", "fr",
    ])

    assert result == 2
    assert output.read_text(encoding="utf-8") == "reviewed: true\n"


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


def test_approve_refuses_broken_output_symlink_before_reading_report(tmp_path: Path) -> None:
    import os

    if not hasattr(os, "symlink"):
        pytest.skip("symlinks are not available on this platform")
    source = tmp_path / "source" / "sample-skill"
    target = tmp_path / "target" / "sample-skill"
    for package in (source, target):
        package.mkdir(parents=True)
        (package / "SKILL.md").write_text(
            "---\nname: sample-skill\ndescription: A sample skill.\n---\n\nInstructions.\n",
            encoding="utf-8",
        )
    output_parent = tmp_path / "approved"
    output_parent.mkdir()
    output = output_parent / "sample-skill"
    destination = tmp_path / "not-created" / "sample-skill"
    try:
        output.symlink_to(destination, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is not permitted")

    result = main([
        "approve", str(source), str(target),
        "--report", str(tmp_path / "missing-report.json"),
        "--output", str(output),
    ])

    assert result == 2
    assert output.is_symlink()
    assert not destination.exists()


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

    from skilltether.report import write_markdown_report
    markdown_out = tmp_path / "not-written.md"
    with pytest.raises(ValueError, match="safety limit"):
        write_markdown_report(comparison(critical_finding()), markdown_out)
    assert not markdown_out.exists()



def test_json_and_markdown_reports_redact_credential_like_text_and_paths(tmp_path: Path) -> None:
    from skilltether.report import write_markdown_report

    api_secret = "veryPrivateCredentialValue_123456789"
    provider_token = "ghp_" + "A" * 30
    finding = critical_finding()
    # Simulate a legacy/imported report whose context bypassed new_finding.
    finding.original_context = f"api_key='{api_secret}'"
    finding.target_context = f"Authorization: Bearer {provider_token}"
    report = comparison(finding)
    report.source_files = {f"references/api_key={api_secret}/guide.md": "b" * 64}
    json_path = tmp_path / "redacted.json"
    markdown_path = tmp_path / "redacted.md"

    write_json_report(report, json_path)
    write_markdown_report(report, markdown_path)

    serialized = json_path.read_text(encoding="utf-8")
    markdown = markdown_path.read_text(encoding="utf-8")
    for raw_secret in (api_secret, provider_token):
        assert raw_secret not in serialized
        assert raw_secret not in markdown
    assert "[REDACTED_PATH_" in serialized
    assert "[REDACTED]" in serialized


def test_new_finding_redacts_credentials_before_constructing_evidence() -> None:
    from skilltether.models import new_finding

    api_secret = "veryPrivateCredentialValue_123456789"
    token = "sk-" + "Z" * 30
    finding = new_finding(
        "LINE_CHANGED", "high", "line_diff",
        f"An api_key={api_secret} was included.",
        f"Credential token {token}",
        original_context=f"password='{api_secret}'",
        target_context=f"Bearer {token}",
    )

    assert api_secret not in finding.message
    assert api_secret not in (finding.original_context or "")
    assert token not in (finding.target_context or "")
    assert "[REDACTED]" in (finding.original_context or "")



def test_redaction_removes_truncated_private_key_blocks() -> None:
    from skilltether.redaction import redact_sensitive_text

    partial = "-----BEGIN PRIVATE KEY-----\n" + ("PRIVATEKEYDATA" * 100)
    redacted = redact_sensitive_text(partial)

    assert "PRIVATEKEYDATA" not in redacted
    assert redacted == "[REDACTED_PRIVATE_KEY]"



def _write_minimal_reviewed_manifest(path: Path) -> None:
    path.write_text(
        "\n".join([
            'manifest_version: "1.0"',
            "source_locale: en",
            "target_locale: fr",
            "manifest_reviewed: true",
            "manifest_reviewer: qa-reviewer",
            "invariants: []",
            "",
        ]),
        encoding="utf-8",
    )


def _write_identical_skill_package(root: Path) -> Path:
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text(
        "\n".join(["---", "name: sample-skill", "description: A test skill.", "---", "", "Instructions.", ""]),
        encoding="utf-8",
    )
    return root


def test_signed_compare_review_and_approve_flow(tmp_path: Path) -> None:
    from skilltether.report import read_json_report, verify_report_signature
    from skilltether.signing import create_signing_key

    source = _write_identical_skill_package(tmp_path / "source" / "sample-skill")
    target = _write_identical_skill_package(tmp_path / "target" / "sample-skill")
    manifest = tmp_path / "invariants.yaml"
    _write_minimal_reviewed_manifest(manifest)
    key = create_signing_key(tmp_path / "report.key")
    report = tmp_path / "review.json"

    compare_result = main([
        "compare", str(source), str(target),
        "--invariants", str(manifest), "--out", str(report),
        "--signing-key", str(key),
    ])
    assert compare_result == 0
    assert verify_report_signature(read_json_report(report), key, require_signature=True)

    output = tmp_path / "approved" / "sample-skill"
    approve_result = main([
        "approve", str(source), str(target),
        "--report", str(report), "--output", str(output),
        "--invariants", str(manifest), "--signing-key", str(key),
    ])

    assert approve_result == 0
    assert (output / "SKILL.md").is_file()
    assert (output / "SKILL.md").read_bytes() == (target / "SKILL.md").read_bytes()


def test_approve_rejects_tampered_signed_report_before_export(tmp_path: Path) -> None:
    import json

    from skilltether.signing import create_signing_key

    source = _write_identical_skill_package(tmp_path / "source" / "sample-skill")
    target = _write_identical_skill_package(tmp_path / "target" / "sample-skill")
    manifest = tmp_path / "invariants.yaml"
    _write_minimal_reviewed_manifest(manifest)
    key = create_signing_key(tmp_path / "report.key")
    report = tmp_path / "review.json"
    assert main([
        "compare", str(source), str(target),
        "--invariants", str(manifest), "--out", str(report),
        "--signing-key", str(key),
    ]) == 0

    payload = json.loads(report.read_text(encoding="utf-8"))
    payload["semantic_status"] = "review_recommended"
    report.write_text(json.dumps(payload), encoding="utf-8")
    output = tmp_path / "approved" / "sample-skill"
    result = main([
        "approve", str(source), str(target),
        "--report", str(report), "--output", str(output),
        "--invariants", str(manifest), "--signing-key", str(key),
    ])

    assert result == 2
    assert not output.exists()


def test_review_resigns_existing_signed_report_and_retains_history(tmp_path: Path) -> None:
    from skilltether.report import read_json_report, verify_report_signature, write_json_report
    from skilltether.signing import create_signing_key

    key = create_signing_key(tmp_path / "report.key")
    report_path = tmp_path / "review.json"
    finding = critical_finding()
    write_json_report(comparison(finding), report_path, signing_key=key)

    result = main([
        "review", str(report_path), finding.id,
        "--disposition", "approved", "--reviewer", "reviewer-1",
        "--note", "Compared source and target context.", "--signing-key", str(key),
    ])

    assert result == 0
    reviewed = read_json_report(report_path)
    assert len(reviewed.findings[0].review_history) == 1
    assert reviewed.findings[0].disposition == "approved"
    assert verify_report_signature(reviewed, key, require_signature=True)


def test_signed_approval_requires_matching_key_even_for_valid_unsigned_report(tmp_path: Path) -> None:
    from skilltether.signing import create_signing_key

    source = _write_identical_skill_package(tmp_path / "source" / "sample-skill")
    target = _write_identical_skill_package(tmp_path / "target" / "sample-skill")
    manifest = tmp_path / "invariants.yaml"
    _write_minimal_reviewed_manifest(manifest)
    report = tmp_path / "unsigned.json"
    assert main([
        "compare", str(source), str(target),
        "--invariants", str(manifest), "--out", str(report),
    ]) == 0

    key = create_signing_key(tmp_path / "report.key")
    output = tmp_path / "approved" / "sample-skill"
    result = main([
        "approve", str(source), str(target),
        "--report", str(report), "--output", str(output),
        "--invariants", str(manifest), "--signing-key", str(key),
    ])

    assert result == 2
    assert not output.exists()



def test_review_rejects_credential_like_reviewer_identifier_without_echoing_it() -> None:
    secret = "api_key=veryPrivateCredentialValue_123456789"

    with pytest.raises(ValueError, match="Reviewer identifier resembles credential material") as error:
        record_review(
            critical_finding(),
            disposition="approved",
            reviewer=secret,
            note="Reviewed the current source and target context.",
        )

    assert secret not in str(error.value)



def test_compare_refuses_signing_key_inside_source_package(tmp_path: Path) -> None:
    source = _write_identical_skill_package(tmp_path / "source" / "sample-skill")
    target = _write_identical_skill_package(tmp_path / "target" / "sample-skill")
    key = source / "report-signing.key"
    key.write_bytes(b"K" * 32)
    report_path = tmp_path / "report.json"

    result = main([
        "compare", str(source), str(target),
        "--out", str(report_path), "--signing-key", str(key),
    ])

    assert result == 2
    assert key.read_bytes() == b"K" * 32
    assert not report_path.exists()


def test_init_manifest_skips_fenced_examples_and_preserves_review_gate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    import yaml

    source = tmp_path / "source" / "sample-skill"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text(
        "\n".join([
            "---",
            "name: sample-skill",
            "description: A sample skill.",
            "---",
            "",
            "# Instructions",
            "| Rule | Example |",
            "| --- | --- |",
            "| Must preserve the original order. | Table content is not a separate invariant candidate. |",
            "Do not delete the source archive.",
            "~~~sh",
            "must not delete the source archive",
            "~~~",
            (chr(96) * 3) + "yaml",
            "must_not: false",
            chr(96) * 3,
            "At most 3 attempts are allowed.",
            "Only run this step if the file exists.",
            "Please must " + ("x" * 1201),
            "",
        ]),
        encoding="utf-8",
    )
    output = tmp_path / "review" / "invariants.yaml"

    status = main([
        "init-manifest", str(source), "--out", str(output),
        "--source-locale", "en", "--target-locale", "fr",
    ])

    assert status == 0
    payload = yaml.safe_load(output.read_text(encoding="utf-8"))
    assert payload["manifest_reviewed"] is False
    source_texts = [item["source_text"] for item in payload["invariants"]]
    assert source_texts == [
        "Do not delete the source archive.",
        "At most 3 attempts are allowed.",
        "Only run this step if the file exists.",
    ]
    assert [item["category"] for item in payload["invariants"]] == [
        "negation", "numeric_limit", "precondition",
    ]

    first_payload = output.read_bytes()
    status = main([
        "init-manifest", str(source), "--out", str(output),
        "--source-locale", "en", "--target-locale", "fr",
    ])

    captured = capsys.readouterr()
    assert status == 2
    assert "not overwritten" in captured.err
    assert output.read_bytes() == first_payload


def test_init_manifest_requires_readable_skill_markdown(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "empty-skill"
    source.mkdir()

    status = main([
        "init-manifest", str(source), "--out", str(tmp_path / "manifest.yaml"),
        "--source-locale", "en",
    ])

    captured = capsys.readouterr()
    assert status == 2
    assert "without a readable SKILL.md" in captured.err
    assert not (tmp_path / "manifest.yaml").exists()
