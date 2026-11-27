from __future__ import annotations

import json
from pathlib import Path

from skilltether.cli import main
from skilltether.redaction import redact_sensitive_text
from skilltether.secret_scan import scan_secret_indicators


def _make_skill(path: Path, body: str = "Use the documented workflow.") -> Path:
    path.mkdir(parents=True)
    (path / "SKILL.md").write_text(
        f"---\nname: {path.name}\ndescription: A local secret-scan fixture.\n---\n\n"
        f"# Instructions\n\n{body}\n",
        encoding="utf-8",
    )
    return path


def test_known_credential_indicators_are_reported_without_values() -> None:
    github_token = "ghp_" + "A" * 36
    google_key = "AIza" + "B" * 35
    aws_key_id = "AKIA" + "C" * 16
    assigned_secret = "local-development-secret-value-123456"
    bearer_secret = "Bearer " + "D" * 32
    url_password = "url-passphrase-123456"

    findings = scan_secret_indicators({
        "SKILL.md": (
            f"API_KEY={assigned_secret}\n"
            f"Authorization: {bearer_secret}\n"
            f"Cloud access: {aws_key_id}\n"
            f"Provider A: {github_token}\n"
            f"Provider B: {google_key}\n"
            f"Database: https://alice:{url_password}@db.example.test/app\n"
            "-----BEGIN PRIVATE KEY-----\n"
        )
    })
    serialized = json.dumps([item.model_dump(mode="json") for item in findings])

    codes = {item.code for item in findings}
    assert {
        "SECRET_CREDENTIAL_ASSIGNMENT",
        "SECRET_BEARER_TOKEN",
        "SECRET_CLOUD_ACCESS_KEY_ID",
        "SECRET_PROVIDER_TOKEN",
        "SECRET_URL_CREDENTIALS",
        "SECRET_PRIVATE_KEY",
    } <= codes
    assert all(item.original_context is None and item.target_context is None for item in findings)
    assert all(item.requires_review for item in findings)
    assert all(item.analysis_method == "heuristic" for item in findings)
    for value in (github_token, google_key, aws_key_id, assigned_secret, bearer_secret, url_password):
        assert value not in serialized


def test_documented_placeholders_and_normal_prose_are_not_reported() -> None:
    findings = scan_secret_indicators({
        "SKILL.md": (
            "API_KEY=your-api-key-here\n"
            "password: " + "$" + "{DATABASE_PASSWORD}\n"
            "access_token: <set-at-deploy-time>\n"
            "Use the bearer authorization scheme with a token from your provider.\n"
            "This is an example of a credential field, not a credential.\n"
        )
    })

    assert findings == []


def test_redaction_covers_common_provider_tokens_and_url_credentials() -> None:
    github_token = "github_pat_" + "Z" * 48
    google_key = "AIza" + "Y" * 35
    stripe_key = "sk_live_" + "X" * 24
    url_password = "password-in-url-1234"
    source = (
        f"{github_token} {google_key} {stripe_key} "
        f"https://alice:{url_password}@example.test/resource"
    )

    redacted = redact_sensitive_text(source)
    assert all(value not in redacted for value in (github_token, google_key, stripe_key, url_password))
    assert "[REDACTED_CREDENTIAL]" in redacted


def test_cli_scans_secret_files_and_never_mutates_or_echoes_values(tmp_path: Path, capsys) -> None:
    package = _make_skill(tmp_path / "secret-skill")
    github_token = "ghp_" + "Q" * 36
    private_key_header = "-----BEGIN OPENSSH PRIVATE KEY-----"
    env_path = package / ".env"
    local_env_path = package / ".env.local"
    key_path = package / "id_ed25519"
    env_path.write_text(f"GITHUB_TOKEN={github_token}\n", encoding="utf-8")
    local_env_path.write_text("GITHUB_TOKEN=opaque-development-token-123456\n", encoding="utf-8")
    key_path.write_text(private_key_header + "\n", encoding="utf-8")
    before = {item.name: item.read_bytes() for item in package.iterdir()}

    status = main(["scan-secrets", str(package), "--json"])
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert status == 1
    assert {item["code"] for item in payload} >= {
        "SECRET_PROVIDER_TOKEN", "SECRET_PRIVATE_KEY", "SECRET_CREDENTIAL_ASSIGNMENT",
    }
    assert any(item["path"] == ".env.local" for item in payload)
    assert github_token not in output
    assert private_key_header not in output
    assert {item.name: item.read_bytes() for item in package.iterdir()} == before
    assert main(["validate", str(package)]) == 0
    assert main(["validate", str(package), "--scan-secrets"]) == 1


def test_cli_secret_scan_ignores_placeholder_values(tmp_path: Path, capsys) -> None:
    package = _make_skill(tmp_path / "placeholder-skill")
    (package / ".env").write_text(
        "API_KEY=your-api-key-here\nPASSWORD=" + "$" + "{DATABASE_PASSWORD}\n",
        encoding="utf-8",
    )

    assert main(["scan-secrets", str(package), "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_cli_secret_scan_reports_incomplete_readable_resource(tmp_path: Path, capsys) -> None:
    package = _make_skill(tmp_path / "unreadable-secret-skill")
    (package / "private.pem").write_bytes(b"\xff\xfe\xfa")

    assert main(["scan-secrets", str(package), "--json"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert any(item["code"] == "SECRET_SCAN_INCOMPLETE" for item in payload)
    assert main(["validate", str(package), "--scan-secrets", "--fail-on", "critical"]) == 2


def test_scanner_reports_output_truncation_as_incomplete() -> None:
    token = "ghp_" + "R" * 36
    findings = scan_secret_indicators({
        "SKILL.md": "\n".join(f"token {token} line {index}" for index in range(1005))
    })

    assert len(findings) == 1001
    assert findings[-1].code == "SECRET_SCAN_FINDINGS_TRUNCATED"


def test_translate_secret_preflight_stops_before_provider_or_output(
    tmp_path: Path, monkeypatch, capsys,
) -> None:
    from skilltether import cli as cli_module

    package = _make_skill(tmp_path / "source" / "secret-skill", "Use token ghp_" + "S" * 36)
    output = tmp_path / "candidate" / "secret-skill"
    report = tmp_path / "review" / "report.json"
    history = tmp_path / "review" / "history.sqlite3"
    calls: list[bool] = []

    def unexpected_translate(self, text: str, source_locale: str, target_locale: str) -> str:
        calls.append(True)
        raise AssertionError("provider must not be called after a secret-scan finding")

    monkeypatch.setattr(cli_module.HttpJsonAdapter, "translate", unexpected_translate)

    status = main([
        "translate", str(package), str(output),
        "--source-locale", "en", "--target-locale", "fr",
        "--adapter", "http-json", "--endpoint", "https://translator.example/translate",
        "--allow-remote", "--scan-secrets",
        "--report", str(report), "--history-db", str(history),
    ])

    captured = capsys.readouterr()
    assert status == 2
    assert "Credential indicators found" in captured.err
    assert calls == []
    assert not output.exists()
    assert not report.exists()
    assert not history.exists()


def test_service_specific_token_assignment_is_detected_and_redacted() -> None:
    opaque_token = "internal-token-material-123456789"
    findings = scan_secret_indicators({
        ".env.local": f"GITHUB_TOKEN={opaque_token}",
    })
    assert len(findings) == 1
    assert findings[0].code == "SECRET_CREDENTIAL_ASSIGNMENT"
    assert findings[0].path == ".env.local"
    assert opaque_token not in json.dumps([item.model_dump(mode="json") for item in findings])

    redacted = redact_sensitive_text(f"GITHUB_TOKEN={opaque_token}")
    assert opaque_token not in redacted
    assert "[REDACTED]" in redacted


def test_translate_secret_preflight_stops_on_incomplete_inventory(
    tmp_path: Path, monkeypatch, capsys,
) -> None:
    from skilltether import cli as cli_module

    package = _make_skill(tmp_path / "source" / "incomplete-skill")
    (package / "private.pem").write_bytes(b"\\xff\\xfe\\xfa")
    output = tmp_path / "candidate" / "incomplete-skill"
    report = tmp_path / "review" / "report.json"
    history = tmp_path / "review" / "history.sqlite3"
    calls: list[bool] = []

    def unexpected_translate(self, text: str, source_locale: str, target_locale: str) -> str:
        calls.append(True)
        raise AssertionError("provider must not be called when the local scan is incomplete")

    monkeypatch.setattr(cli_module.HttpJsonAdapter, "translate", unexpected_translate)

    status = main([
        "translate", str(package), str(output),
        "--source-locale", "en", "--target-locale", "fr",
        "--adapter", "http-json", "--endpoint", "https://translator.example/translate",
        "--allow-remote", "--scan-secrets",
        "--report", str(report), "--history-db", str(history),
    ])

    captured = capsys.readouterr()
    assert status == 2
    assert "Secret scan was incomplete" in captured.err
    assert calls == []
    assert not output.exists()
    assert not report.exists()
    assert not history.exists()


def test_provider_token_families_are_recognized_without_echoing_values() -> None:
    tokens = [
        "gho_" + "A" * 24,
        "github_pat_" + "B" * 48,
        "sk-proj-" + "C" * 28,
        "xoxb-" + "D" * 24,
        "AIza" + "E" * 35,
        "sk_live_" + "F" * 24,
        "SK" + "a" * 32,
        "SG." + "G" * 20 + "." + "H" * 20,
    ]
    text_by_path = {
        f"references/token-{index}.md": token
        for index, token in enumerate(tokens)
    }
    findings = scan_secret_indicators(text_by_path)
    serialized = json.dumps([item.model_dump(mode="json") for item in findings])

    assert len(findings) == len(tokens)
    assert all(item.code == "SECRET_PROVIDER_TOKEN" for item in findings)
    assert all(token not in serialized for token in tokens)


def test_multisegment_secret_assignment_names_are_detected_and_redacted() -> None:
    value = "opaque-cloud-session-secret-value-987654"
    findings = scan_secret_indicators({
        ".env.production": f"AWS_SESSION_TOKEN={value}"
    })
    assert len(findings) == 1
    assert findings[0].code == "SECRET_CREDENTIAL_ASSIGNMENT"
    assert value not in json.dumps([item.model_dump(mode="json") for item in findings])
    assert value not in redact_sensitive_text(f"AWS_SESSION_TOKEN={value}")
