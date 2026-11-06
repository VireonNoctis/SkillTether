"""Parse-only checks for script resources using local system parsers.

No package script is executed. Source is supplied on stdin to syntax-check/parser
modes so a path race cannot redirect a parser to a different package file.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ParserStatus = Literal["valid", "invalid", "unavailable", "timeout", "error"]


@dataclass(frozen=True)
class ScriptSyntaxResult:
    parser: str
    status: ParserStatus
    returncode: int | None = None


_POWERSHELL_PARSE_COMMAND = (
    "$source = [Console]::In.ReadToEnd(); "
    "$tokens = $null; $parseErrors = $null; "
    "[System.Management.Automation.Language.Parser]::ParseInput("
    "$source, [ref]$tokens, [ref]$parseErrors) | Out-Null; "
    "if ($parseErrors.Count -gt 0) { exit 1 }"
)

# Every command is a fixed parse-only invocation. User-controlled source never
# enters argv, a command string, a filename, or a shell interpolation.
def _parser_invocation(
    suffix: str, executable: str, parser_name: str,
) -> tuple[list[str], str] | None:
    normalized = suffix.lower()
    if normalized in {".sh", ".bash"}:
        return [executable, "-n"], parser_name
    if normalized in {".js", ".cjs", ".mjs"}:
        input_type = "module" if normalized == ".mjs" else "commonjs"
        return [executable, "--check", f"--input-type={input_type}", "-"], "node"
    if normalized in {".ps1", ".psm1", ".psd1"}:
        return [
            executable, "-NoLogo", "-NoProfile", "-NonInteractive",
            "-Command", _POWERSHELL_PARSE_COMMAND,
        ], parser_name
    return None


def _minimal_parser_environment() -> dict[str, str]:
    """Pass only launch-critical environment keys, never provider/agent secrets."""
    allowed = {"PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"}
    return {key: value for key, value in os.environ.items() if key.upper() in allowed}


def check_script_syntax(
    path: str | Path,
    source: str,
    *,
    timeout_seconds: float = 8.0,
) -> ScriptSyntaxResult | None:
    """Return static syntax status for supported script suffixes, or None otherwise."""
    suffix = Path(path).suffix.lower()
    if suffix in {".sh", ".bash"}:
        candidates = ("bash",) if suffix == ".bash" else ("bash", "sh")
    elif suffix in {".js", ".cjs", ".mjs"}:
        candidates = ("node",)
    elif suffix in {".ps1", ".psm1", ".psd1"}:
        candidates = ("pwsh", "powershell")
    else:
        return None

    executable = None
    selected_parser = candidates[0]
    for candidate in candidates:
        executable = shutil.which(candidate)
        if executable:
            selected_parser = candidate
            break
    if executable is None:
        return ScriptSyntaxResult(parser=candidates[0], status="unavailable")

    invocation = _parser_invocation(suffix, executable, selected_parser)
    if invocation is None:
        return None
    command, parser_name = invocation
    try:
        encoded = source.encode("utf-8")
        completed = subprocess.run(
            command,
            input=encoded,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            shell=False,
            cwd=tempfile.gettempdir(),
            env=_minimal_parser_environment(),
            timeout=timeout_seconds,
            close_fds=True,
        )
    except subprocess.TimeoutExpired:
        return ScriptSyntaxResult(parser=parser_name, status="timeout")
    except (OSError, UnicodeEncodeError, ValueError):
        return ScriptSyntaxResult(parser=parser_name, status="error")

    return ScriptSyntaxResult(
        parser=parser_name,
        status="valid" if completed.returncode == 0 else "invalid",
        returncode=completed.returncode,
    )
