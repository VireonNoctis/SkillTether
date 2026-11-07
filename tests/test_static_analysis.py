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
        "pwsh": "pwsh",
    }[executable]
    assert len(calls) == 1
    command, kwargs = calls[0]
    assert command[:len(expected_prefix)] == expected_prefix
    assert source not in " ".join(command)
    assert kwargs["input"] == source.encode("utf-8")
    assert kwargs["shell"] is False
    assert kwargs["timeout"] == 8.0
    assert kwargs["stdout"] is subprocess.DEVNULL
    assert kwargs["stderr"] is subprocess.DEVNULL
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


def test_new_script_extensions_are_read_and_checked_by_package_inspection(
    tmp_path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from skilltether.static_analysis import ScriptSyntaxResult

    package = tmp_path / "sample-skill"
    package.mkdir()
    (package / "SKILL.md").write_text(
        "---\nname: sample-skill\ndescription: A script validation fixture.\n---\n\nInstructions.\n",
        encoding="utf-8",
    )
    scripts = package / "scripts"
    scripts.mkdir()
    extensions = [".cjs", ".mjs", ".psm1", ".psd1"]
    for suffix in extensions:
        (scripts / f"tool{suffix}").write_text("syntactically checked source\n", encoding="utf-8")

    checked: list[str] = []
    def valid(path: str, _source: str) -> ScriptSyntaxResult:
        checked.append(path)
        return ScriptSyntaxResult(parser="test-parser", status="valid")

    monkeypatch.setattr(analysis, "check_script_syntax", valid)
    inventory, findings, _texts = analysis.inspect_package(package)

    assert {f"scripts/tool{suffix}" for suffix in extensions} <= set(inventory)
    assert set(checked) == {f"scripts/tool{suffix}" for suffix in extensions}
    assert not any(
        finding.code in {"SCRIPT_NOT_UTF8", "TEXT_RESOURCE_NOT_UTF8", "SCRIPT_SYNTAX_INVALID"}
        for finding in findings
    )


def test_script_parser_budget_caps_process_invocations_and_reports_unchecked_scripts(
    tmp_path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from skilltether.static_analysis import ScriptSyntaxResult

    package = tmp_path / "sample-skill"
    package.mkdir()
    (package / "SKILL.md").write_text(
        "---\nname: sample-skill\ndescription: A bounded script validation fixture.\n---\n\nInstructions.\n",
        encoding="utf-8",
    )
    scripts = package / "scripts"
    scripts.mkdir()
    for index in range(analysis.MAX_STATIC_SCRIPT_CHECKS + 3):
        (scripts / f"script-{index:02d}.js").write_text("const ready = true;\n", encoding="utf-8")

    checked: list[str] = []
    def valid(path: str, _source: str) -> ScriptSyntaxResult:
        checked.append(path)
        return ScriptSyntaxResult(parser="node", status="valid")

    monkeypatch.setattr(analysis, "check_script_syntax", valid)
    _inventory, findings, _texts = analysis.inspect_package(package)

    assert len(checked) == analysis.MAX_STATIC_SCRIPT_CHECKS
    budget = [item for item in findings if item.code == "SCRIPT_SYNTAX_CHECK_BUDGET_EXCEEDED"]
    assert len(budget) == 1
    assert budget[0].requires_review is True
    assert budget[0].uncertainty == "high"


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



def test_typescript_uses_compiler_ast_parser_with_source_on_stdin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []
    monkeypatch.setattr(
        static_analysis.shutil,
        "which",
        lambda name: {"node": "/trusted/node", "tsc": "/trusted/tsc"}.get(name),
    )
    monkeypatch.setattr(
        static_analysis,
        "_typescript_module_path",
        lambda _tsc: "/trusted/node_modules/typescript",
    )

    def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(static_analysis.subprocess, "run", fake_run)
    source = "export const answer: number = 42;\n"
    result = static_analysis.check_script_syntax("scripts/check.ts", source)

    assert result is not None and result.status == "valid"
    assert result.parser == "typescript"
    assert len(calls) == 1
    command, kwargs = calls[0]
    assert command[:2] == ["/trusted/node", "-e"]
    assert "/trusted/node_modules/typescript" in command
    assert ".ts" in command
    assert source not in " ".join(command)
    assert kwargs["input"] == source.encode("utf-8")
    assert kwargs["shell"] is False
    assert kwargs["timeout"] == 8.0
    assert kwargs["env"] is not None


def test_typescript_requires_an_already_installed_local_parser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launches: list[object] = []
    monkeypatch.setattr(static_analysis.shutil, "which", lambda _name: None)
    monkeypatch.setattr(
        static_analysis.subprocess,
        "run",
        lambda *args, **kwargs: launches.append(args),
    )

    result = static_analysis.check_script_syntax("scripts/check.ts", "const answer = 42;")

    assert result is not None
    assert result.parser == "typescript"
    assert result.status == "unavailable"
    assert launches == []


@pytest.mark.parametrize(
    ("source", "status"),
    [
        ('@echo off\nif defined FLAG (\n  echo "open paren ("\n)\n', "partial"),
        ("@echo off\nif defined FLAG (\n  echo missing close\n", "invalid"),
        ("@echo off\necho unmatched )\n", "invalid"),
        ("@echo off\necho ^(literal^)\n", "partial"),
        ('@echo off\necho "unterminated\n', "invalid"),
    ],
)
def test_batch_file_uses_only_conservative_delimiter_scan(source: str, status: str) -> None:
    result = static_analysis.check_script_syntax("scripts/tool.bat", source)

    assert result is not None
    assert result.parser == "batch-delimiter-check"
    assert result.status == status


def test_batch_balanced_scan_never_claims_full_syntax_validity() -> None:
    result = static_analysis.check_script_syntax("scripts/tool.bat", "@echo off\necho ready\n")

    assert result is not None
    assert result.status == "partial"


def test_batch_delimiter_findings_are_heuristic_and_incomplete_results_are_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suspicious = analysis.validate_script_syntax("scripts/bad.bat", "if defined FLAG (\necho no close")
    finding = next(item for item in suspicious if item.code == "SCRIPT_BATCH_DELIMITER_SUSPECTED")
    assert finding.analysis_method == "heuristic"
    assert finding.uncertainty == "high"
    assert finding.requires_review is True

    balanced = analysis.validate_script_syntax("scripts/good.bat", "@echo off\necho ready\n")
    incomplete = next(item for item in balanced if item.code == "SCRIPT_SYNTAX_CHECK_INCOMPLETE")
    assert incomplete.analysis_method == "deterministic"
    assert incomplete.uncertainty == "high"
    assert incomplete.requires_review is True


def test_typescript_and_batch_extensions_are_classified_as_readable_scripts() -> None:
    assert {".ts", ".tsx", ".mts", ".cts", ".bat"} <= analysis.SCRIPT_SUFFIXES
    assert {".ts", ".tsx", ".mts", ".cts", ".bat"} <= analysis.READABLE_SUFFIXES
    assert {".ts", ".tsx", ".mts", ".cts", ".bat"} <= analysis.PARSE_ONLY_SCRIPT_SUFFIXES
