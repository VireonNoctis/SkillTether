from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

import skilltether.analysis as analysis
import skilltether.static_analysis as static_analysis


@pytest.mark.parametrize(
    ("path", "executable", "expected_prefix"),
    [
        ("scripts/check.sh", "bash", ["bash", "-n"]),
        ("scripts/check.mjs", "node", ["node", "--check", "--input-type=module", "-"]),
        ("scripts/check.js", "node", ["node", "--check", "--input-type=commonjs", "-"]),
        ("scripts/check.ps1", "pwsh", ["pwsh", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command"]),
    ],
)
def test_static_script_parsers_receive_only_stdin_and_parse_only_flags(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    executable: str,
    expected_prefix: list[str],
) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []
    source = 'Write-Output "$(touch SHOULD_NOT_EXIST)"\n'

    monkeypatch.setattr(
        static_analysis.shutil,
        "which",
        lambda candidate: candidate if candidate == executable else None,
    )

    def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(static_analysis.subprocess, "run", fake_run)

    result = static_analysis.check_script_syntax(path, source)

    assert result is not None
    assert result.status == "valid"
    assert result.parser == {
        "bash": "bash",
        "node": "node",
        "pwsh": "powershell",
    }[executable]
    assert len(calls) == 1
    command, kwargs = calls[0]
    assert command[:len(expected_prefix)] == expected_prefix
    assert source not in " ".join(command)
    assert kwargs["input"] == source.encode("utf-8")
    assert kwargs["shell"] is False
    assert kwargs["timeout"] == 3.0
    assert kwargs["close_fds"] is True
    environment = kwargs["env"]
    assert isinstance(environment, dict)
    assert "API_TOKEN" not in environment
    assert "GITHUB_TOKEN" not in environment


def test_shell_fallback_reports_the_actual_parser_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(
        static_analysis.shutil,
        "which",
        lambda name: "/bin/sh" if name == "sh" else None,
    )
    monkeypatch.setattr(
        static_analysis.subprocess,
        "run",
        lambda command, **kwargs: (
            calls.append(command),
            SimpleNamespace(returncode=0, stdout=b"", stderr=b""),
        )[1],
    )

    result = static_analysis.check_script_syntax("scripts/tool.sh", "echo safe")

    assert result is not None
    assert result.parser == "sh"
    assert calls == [["/bin/sh", "-n"]]


def test_missing_local_parser_is_reported_without_network_or_process_launch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_run(*args: object, **kwargs: object) -> None:
        pytest.fail("no process should launch when a parser is unavailable")

    monkeypatch.setattr(static_analysis.shutil, "which", lambda _name: None)
    monkeypatch.setattr(static_analysis.subprocess, "run", unexpected_run)

    result = static_analysis.check_script_syntax("scripts/automation.ps1", "Write-Output safe")

    assert result is not None
    assert result.parser == "pwsh"
    assert result.status == "unavailable"


def test_parser_timeout_is_bounded_and_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        static_analysis.shutil,
        "which",
        lambda name: f"/trusted-tools/{name}" if name == "bash" else None,
    )

    def timeout(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(args[0], kwargs.get("timeout"))

    monkeypatch.setattr(static_analysis.subprocess, "run", timeout)

    result = static_analysis.check_script_syntax("scripts/check.sh", "echo safe")

    assert result is not None
    assert result.status == "timeout"
    assert result.parser == "bash"


@pytest.mark.parametrize(
    ("suffix", "status", "expected_code"),
    [
        (".js", "invalid", "SCRIPT_SYNTAX_INVALID"),
        (".ps1", "timeout", "SCRIPT_SYNTAX_CHECK_INCOMPLETE"),
        (".sh", "unavailable", "SCRIPT_SYNTAX_CHECK_UNAVAILABLE"),
    ],
)
def test_inspection_maps_script_parser_status_to_review_evidence(
    monkeypatch: pytest.MonkeyPatch,
    suffix: str,
    status: str,
    expected_code: str,
) -> None:
    from skilltether.static_analysis import ScriptSyntaxResult

    parser = {"js": "node", "ps1": "powershell", "sh": "bash"}[suffix.removeprefix(".")]
    monkeypatch.setattr(
        analysis,
        "check_script_syntax",
        lambda _path, _source: ScriptSyntaxResult(parser=parser, status=status),  # type: ignore[arg-type]
    )

    findings = analysis.validate_script_syntax(f"scripts/tool{suffix}", "source")

    finding = next(item for item in findings if item.code == expected_code)
    assert finding.path == f"scripts/tool{suffix}"
    assert finding.analysis_method == "deterministic"
    assert finding.requires_review is (status != "unavailable")
    if status == "invalid":
        assert finding.severity == "high"
        assert finding.uncertainty == "low"
    if status == "timeout":
        assert finding.severity == "medium"
        assert finding.uncertainty == "high"


def test_non_script_resources_do_not_request_a_parser() -> None:
    assert static_analysis.check_script_syntax("references/guide.md", "A paragraph.") is None


@pytest.mark.parametrize(
    ("suffix", "valid_source", "invalid_source"),
    [
        (".sh", "set -eu\necho safe\n", "if then\n"),
        (".js", "const answer = 42;\n", "const = ;\n"),
        (".mjs", "export const answer = 42;\n", "export const = ;\n"),
    ],
)
def test_installed_system_parsers_check_syntax_without_executing_sources(
    suffix: str,
    valid_source: str,
    invalid_source: str,
) -> None:
    path = {
        ".sh": "bash",
        ".js": "node",
        ".mjs": "node",
    }[suffix]
    if static_analysis.shutil.which(path) is None:
        pytest.skip(f"{path} parser is not installed on this host")

    valid = static_analysis.check_script_syntax(f"scripts/check{suffix}", valid_source)
    invalid = static_analysis.check_script_syntax(f"scripts/check{suffix}", invalid_source)

    assert valid is not None and valid.status == "valid"
    assert invalid is not None and invalid.status == "invalid"
