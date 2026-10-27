from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from skilltether.cli import build_parser
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
