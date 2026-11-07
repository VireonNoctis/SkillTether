"""Bounded parser-only checks for package scripts.

No package script is executed. Source is supplied on stdin to fixed parser APIs.
TypeScript is parsed through the TypeScript compiler API; batch files receive only
a conservative delimiter scan and are never treated as fully parsed.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ParserStatus = Literal["valid", "invalid", "unavailable", "timeout", "error", "partial"]


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

# This fixed helper loads a trusted TypeScript compiler module and only calls
# createSourceFile. It does not evaluate or transpile package code.
_TYPESCRIPT_PARSE_SCRIPT = (
    "const fs = require('node:fs'); "
    "const ts = require(process.argv[1]); "
    "const suffix = process.argv[2]; "
    "const kind = suffix === '.tsx' ? ts.ScriptKind.TSX : ts.ScriptKind.TS; "
    "const source = fs.readFileSync(0, 'utf8'); "
    "const file = ts.createSourceFile('skilltether-input' + suffix, source, "
    "ts.ScriptTarget.Latest, true, kind); "
    "if (file.parseDiagnostics.length > 0) process.exit(1);"
)


def _typescript_module_path(tsc_executable: str) -> str | None:
    """Locate an already-installed TypeScript package; never invoke a downloader."""
    executable = Path(tsc_executable).resolve()
    candidates = [
        executable.parent.parent,
        executable.parent / "node_modules" / "typescript",
        executable.parent.parent / "node_modules" / "typescript",
        Path.cwd() / "node_modules" / "typescript",
        Path.home() / ".npm-global" / "lib" / "node_modules" / "typescript",
        Path.home() / "AppData" / "Roaming" / "npm" / "node_modules" / "typescript",
    ]
    for candidate in candidates:
        if (candidate / "package.json").is_file():
            return str(candidate)
    return None


def _batch_delimiter_status(source: str) -> ScriptSyntaxResult:
    """Conservatively spot unmatched batch quotes/parentheses without running cmd.exe."""
    quoted = False
    depth = 0
    line = 1
    column = 0
    index = 0
    while index < len(source):
        character = source[index]
        if character == "\r":
            if index + 1 < len(source) and source[index + 1] == "\n":
                index += 1
            line += 1
            column = 0
            index += 1
            continue
        if character == "\n":
            line += 1
            column = 0
            index += 1
            continue
        column += 1
        if character == "^":
            if index + 1 >= len(source):
                return ScriptSyntaxResult("batch-delimiter-check", "invalid", 1)
            if source[index + 1] in "\r\n":
                # A trailing caret is the batch line-continuation marker.
                if source[index + 1] == "\r" and index + 2 < len(source) and source[index + 2] == "\n":
                    index += 2
                else:
                    index += 1
                line += 1
                column = 0
                index += 1
                continue
            index += 2
            column += 1
            continue
        if character == '"':
            quoted = not quoted
        elif not quoted and character == "(":
            depth += 1
        elif not quoted and character == ")":
            depth -= 1
            if depth < 0:
                return ScriptSyntaxResult("batch-delimiter-check", "invalid", 1)
        index += 1

    if quoted or depth != 0:
        return ScriptSyntaxResult("batch-delimiter-check", "invalid", 1)
    # Balanced delimiters are not proof of batch syntax validity. cmd.exe's
    # grammar and expansion rules are too complex for this intentionally small scan.
    return ScriptSyntaxResult("batch-delimiter-check", "partial", 0)


# Every external command is fixed. User-controlled source never enters argv,
# a command string, a filename, or a shell interpolation.
def _parser_invocation(
    suffix: str, executable: str, parser_name: str,
    *, typescript_module: str | None = None,
) -> tuple[list[str], str] | None:
    normalized = suffix.lower()
    if normalized in {".sh", ".bash"}:
        return [executable, "-n"], parser_name
    if normalized in {".js", ".cjs", ".mjs"}:
        input_type = "module" if normalized == ".mjs" else "commonjs"
        return [executable, "--check", f"--input-type={input_type}", "-"], "node"
    if normalized in {".ts", ".tsx", ".mts", ".cts"}:
        if typescript_module is None:
            return None
        return [
            executable, "-e", _TYPESCRIPT_PARSE_SCRIPT,
            typescript_module, normalized,
        ], "typescript"
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
    """Run a bounded parser-only check, or a conservative batch delimiter scan."""
    suffix = Path(path).suffix.lower()
    if suffix == ".bat":
        return _batch_delimiter_status(source)
    if suffix in {".sh", ".bash"}:
        candidates = ("bash",) if suffix == ".bash" else ("bash", "sh")
    elif suffix in {".js", ".cjs", ".mjs"}:
        candidates = ("node",)
    elif suffix in {".ts", ".tsx", ".mts", ".cts"}:
        candidates = ("node", "tsc")
    elif suffix in {".ps1", ".psm1", ".psd1"}:
        candidates = ("pwsh", "powershell")
    else:
        return None

    executables = {candidate: shutil.which(candidate) for candidate in candidates}
    if suffix in {".ts", ".tsx", ".mts", ".cts"}:
        node = executables.get("node")
        tsc = executables.get("tsc")
        if node is None or tsc is None:
            return ScriptSyntaxResult(parser="typescript", status="unavailable")
        module_path = _typescript_module_path(tsc)
        if module_path is None:
            return ScriptSyntaxResult(parser="typescript", status="unavailable")
        invocation = _parser_invocation(suffix, node, "node", typescript_module=module_path)
        parser_name = "typescript"
    else:
        executable = None
        selected_parser = candidates[0]
        for candidate in candidates:
            if executables.get(candidate):
                executable = executables[candidate]
                selected_parser = candidate
                break
        if executable is None:
            return ScriptSyntaxResult(parser=candidates[0], status="unavailable")
        invocation = _parser_invocation(suffix, executable, selected_parser)
        parser_name = selected_parser

    if invocation is None:
        return ScriptSyntaxResult(parser=parser_name, status="unavailable")
    command, parser_name = invocation
    try:
        completed = subprocess.run(
            command,
            input=source.encode("utf-8"),
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
