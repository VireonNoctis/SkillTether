from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from skilltether.cli import main
from skilltether.models import ComparisonReport
from skilltether.report import read_json_report, verify_report_signature, write_json_report
from skilltether.signing import create_signing_key, load_signing_key, sign_payload


def sample_report() -> ComparisonReport:
    return ComparisonReport.create(
        tool_version="0.1.0",
        source_locale="en",
        target_locale="fr",
        protected_policy_fingerprint="a" * 64,
        source_fingerprint="b" * 64,
        target_fingerprint="c" * 64,
        source_files={"SKILL.md": "b" * 64},
        target_files={"SKILL.md": "c" * 64},
        structural_status="pass",
        semantic_status="no_issue_detected",
        findings=[],
    )


def test_new_key_is_private_random_and_never_overwrites(tmp_path: Path) -> None:
    path = create_signing_key(tmp_path / "keys" / "report.key")

    assert len(load_signing_key(path)) == 32
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError, match="already exists"):
        create_signing_key(path)


def test_signing_key_loader_preserves_all_raw_bytes(tmp_path: Path) -> None:
    key_path = tmp_path / "binary.key"
    key_bytes = b"A" * 16 + b"\x1a\r\n" + b"B" * 20
    key_path.write_bytes(key_bytes)

    assert load_signing_key(key_path) == key_bytes


def test_signed_report_round_trip_and_tamper_detection(tmp_path: Path) -> None:
    key = create_signing_key(tmp_path / "report.key")
    report_path = tmp_path / "report.json"

    write_json_report(sample_report(), report_path, signing_key=key)
    signed = read_json_report(report_path)

    assert signed.integrity_algorithm == "hmac-sha256"
    assert signed.integrity_signature is not None
    assert verify_report_signature(signed, key, require_signature=True)

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    payload["tool_version"] = "0.1.0-tampered"
    report_path.write_text(json.dumps(payload), encoding="utf-8")
    tampered = read_json_report(report_path)
    with pytest.raises(ValueError, match="signature verification failed"):
        verify_report_signature(tampered, key, require_signature=True)


def test_signed_report_requires_key_for_verification_and_rewrite(tmp_path: Path) -> None:
    key = create_signing_key(tmp_path / "report.key")
    report_path = tmp_path / "report.json"
    write_json_report(sample_report(), report_path, signing_key=key)
    signed = read_json_report(report_path)

    with pytest.raises(ValueError, match="supply --signing-key"):
        verify_report_signature(signed)
    with pytest.raises(ValueError, match="without its signing key"):
        write_json_report(signed, report_path)


def test_unsigned_report_can_be_required_to_be_signed(tmp_path: Path) -> None:
    report = sample_report()
    with pytest.raises(ValueError, match="signed report is required"):
        verify_report_signature(report, require_signature=True)


def test_key_loader_rejects_symlink_and_overly_broad_permissions(tmp_path: Path) -> None:
    if not hasattr(os, "symlink"):
        pytest.skip("symlinks are not available")
    key = create_signing_key(tmp_path / "private.key")
    alias = tmp_path / "alias.key"
    try:
        alias.symlink_to(key)
    except OSError:
        pytest.skip("symlink creation is not permitted")
    with pytest.raises(ValueError, match="regular file"):
        load_signing_key(alias)
    if os.name == "posix":
        key.chmod(0o644)
        with pytest.raises(ValueError, match="permissions are too broad"):
            load_signing_key(key)


def test_report_schema_accepts_valid_signature_and_rejects_unpaired_fields(tmp_path: Path) -> None:
    schema = json.loads(Path("schemas/comparison-report.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    key = create_signing_key(tmp_path / "key")
    report = sample_report()
    report_path = tmp_path / "signed.json"
    write_json_report(report, report_path, signing_key=key)
    signed_payload = json.loads(report_path.read_text(encoding="utf-8"))

    assert not list(validator.iter_errors(signed_payload))
    signed_payload["integrity_signature"] = None
    errors = list(validator.iter_errors(signed_payload))
    assert errors

    # Signature generation itself is deterministic for a fixed payload and key.
    safe_payload = report.model_dump(mode="json")
    safe_payload["integrity_algorithm"] = "hmac-sha256"
    assert sign_payload(safe_payload, key) == sign_payload(safe_payload, key)



def test_verify_report_cli_checks_signature_without_review_or_export(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    key = create_signing_key(tmp_path / "report.key")
    report_path = tmp_path / "report.json"
    write_json_report(sample_report(), report_path, signing_key=key)

    result = main(["verify-report", str(report_path), "--signing-key", str(key)])
    assert result == 0
    assert "Report integrity verified" in capsys.readouterr().out

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    current = payload["integrity_signature"]
    payload["integrity_signature"] = ("0" if current[0] != "0" else "1") + current[1:]
    report_path.write_text(json.dumps(payload), encoding="utf-8")

    result = main(["verify-report", str(report_path), "--signing-key", str(key)])
    assert result == 2
    assert "signature verification failed" in capsys.readouterr().err
