"""Read-only package inventory, SKILL.md validation, and protected-span extraction."""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import stat
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import yaml
from markdown_it import MarkdownIt

from .yamlio import safe_load_unique

from .models import FileFingerprint, ProtectedToken, new_finding

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_PACKAGE_FILES = 5000
MAX_PACKAGE_DIRECTORIES = 5000
MAX_PACKAGE_BYTES = 100 * 1024 * 1024
MAX_POLICY_PATTERNS = 128
MAX_EXPLICIT_TOKENS = 2048
MAX_POLICY_REGEX_CHARS = 1000
MAX_EXPLICIT_TOKEN_CHARS = 2048
TEXT_SUFFIXES = {".md", ".mdx", ".txt", ".rst"}
SCRIPT_SUFFIXES = {".py", ".sh", ".bash", ".js", ".ts", ".ps1", ".bat"}
RESOURCE_REFERENCE = re.compile(r"(?<![A-Za-z0-9/:])(?P<path>(?:\.\.?/)*(?:scripts|references|assets|resources)/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*)")
READABLE_SUFFIXES = TEXT_SUFFIXES | {
    ".py", ".sh", ".bash", ".js", ".ts", ".json", ".yaml", ".yml",
    ".toml", ".xml", ".html", ".css", ".sql", ".ps1", ".bat", ".env",
}
NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FRONTMATTER_START = re.compile(r"^---\s*$")
FENCE_START = re.compile(r"^\s{0,3}(\x60{3,}|~{3,})")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def package_fingerprint(files: dict[str, FileFingerprint]) -> str:
    """Fingerprint path names and file hashes in stable lexical order."""
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(files[path].sha256.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def inspect_package(root: str | Path) -> tuple[dict[str, FileFingerprint], list, dict[str, str]]:
    """Inspect files without executing scripts or following symlinks."""
    root_path = Path(root).expanduser().resolve(strict=True)
    if not root_path.is_dir():
        raise ValueError(f"Package root is not a directory: {root_path}")

    inventory: dict[str, FileFingerprint] = {}
    findings = []
    texts: dict[str, str] = {}
    count = 0
    directory_count = 0
    total_bytes = 0

    for current, dirs, names in os.walk(root_path, followlinks=False):
        current_path = Path(current)
        safe_dirs = []
        for dirname in sorted(dirs):
            directory_count += 1
            if directory_count > MAX_PACKAGE_DIRECTORIES:
                raise ValueError(f"Package exceeds the {MAX_PACKAGE_DIRECTORIES}-directory safety limit")
            item = current_path / dirname
            if len(item.relative_to(root_path).parts) > 128:
                raise ValueError("Package directory depth exceeds the 128-level safety limit")
            if item.is_symlink():
                findings.append(new_finding(
                    "SYMLINK_NOT_ALLOWED", "critical", "package_integrity",
                    "Package contains a symbolic-link directory.",
                    "Symbolic links can escape the package boundary or change between inspection and export.",
                    path=item.relative_to(root_path).as_posix(),
                    proposed_change="Replace the symlink with a regular in-package resource.",
                ))
            else:
                safe_dirs.append(dirname)
        dirs[:] = safe_dirs

        for filename in sorted(names):
            path = current_path / filename
            rel = path.relative_to(root_path).as_posix()
            count += 1
            if count > MAX_PACKAGE_FILES:
                raise ValueError(f"Package exceeds the {MAX_PACKAGE_FILES}-file safety limit")
            if path.is_symlink():
                findings.append(new_finding(
                    "SYMLINK_NOT_ALLOWED", "critical", "package_integrity",
                    "Package contains a symbolic-link file.",
                    "The package must be deterministic and confined to its root.",
                    path=rel, proposed_change="Replace the symlink with a regular in-package resource.",
                ))
                continue
            # Reject special entries before open to avoid invoking device-specific
            # open behavior. Recheck the descriptor after opening to narrow the race
            # between lstat and open; O_NOFOLLOW and O_NONBLOCK add platform safeguards.
            try:
                entry_stat = path.lstat()
            except OSError as exc:
                findings.append(new_finding(
                    "FILE_STAT_ERROR", "high", "package_integrity",
                    f"Unable to lstat package entry: {exc.__class__.__name__}.",
                    "An unreadable entry cannot be safely classified or fingerprinted.",
                    path=rel,
                ))
                continue
            if not stat.S_ISREG(entry_stat.st_mode):
                findings.append(new_finding(
                    "SPECIAL_FILE_NOT_ALLOWED", "critical", "package_integrity",
                    "Package contains a non-regular filesystem entry.",
                    "Devices, sockets, and named pipes are not ordinary skill resources and must not be opened or read.",
                    path=rel, proposed_change="Replace this entry with a regular file or directory.",
                ))
                continue

            # Open without following a final-component symlink and without blocking on
            # FIFOs. fstat the opened descriptor (not the path) to narrow TOCTOU risk.
            # Read at most MAX_FILE_BYTES + 1 bytes so a growing file remains bounded.
            descriptor = None
            try:
                flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
                descriptor = os.open(path, flags)
                opened = os.fstat(descriptor)
                if not stat.S_ISREG(opened.st_mode):
                    findings.append(new_finding(
                        "SPECIAL_FILE_NOT_ALLOWED", "critical", "package_integrity",
                        "Package contains a non-regular filesystem entry.",
                        "Devices, sockets, and named pipes can block reads or expose behavior outside a static package inventory.",
                        path=rel, proposed_change="Replace this entry with a regular file or directory.",
                    ))
                    continue
                if opened.st_size > MAX_FILE_BYTES:
                    findings.append(new_finding(
                        "FILE_TOO_LARGE", "high", "package_integrity",
                        f"File exceeds the {MAX_FILE_BYTES}-byte safety limit.",
                        "Large inputs are bounded to reduce resource-exhaustion risk.",
                        path=rel, proposed_change="Review and split or explicitly handle this resource.",
                    ))
                    continue
                if total_bytes + opened.st_size > MAX_PACKAGE_BYTES:
                    findings.append(new_finding(
                        "PACKAGE_TOO_LARGE", "critical", "package_integrity",
                        f"Package content exceeds the {MAX_PACKAGE_BYTES}-byte aggregate safety limit.",
                        "Per-file bounds do not prevent a package containing thousands of individually valid but collectively excessive files.",
                        path=rel, proposed_change="Reduce the package to the supported aggregate size and rerun validation.",
                    ))
                    continue
                chunks: list[bytes] = []
                total = 0
                while total <= MAX_FILE_BYTES:
                    chunk = os.read(descriptor, min(64 * 1024, MAX_FILE_BYTES + 1 - total))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    total += len(chunk)
                data = b"".join(chunks)
                if len(data) > MAX_FILE_BYTES:
                    findings.append(new_finding(
                        "FILE_TOO_LARGE", "high", "package_integrity",
                        f"File grew beyond the {MAX_FILE_BYTES}-byte safety limit while being read.",
                        "The file size changed during inspection and exceeded the bounded read limit.",
                        path=rel, proposed_change="Stabilize the resource and rerun validation.",
                    ))
                    continue
                if total_bytes + len(data) > MAX_PACKAGE_BYTES:
                    findings.append(new_finding(
                        "PACKAGE_TOO_LARGE", "critical", "package_integrity",
                        f"Package content exceeds the {MAX_PACKAGE_BYTES}-byte aggregate safety limit while being read.",
                        "A resource changed after the initial size check and exceeded the aggregate read budget.",
                        path=rel, proposed_change="Stabilize and reduce the package, then rerun validation.",
                    ))
                    continue
            except OSError as exc:
                findings.append(new_finding(
                    "FILE_READ_ERROR", "high", "package_integrity",
                    f"Unable to safely open or read package file: {exc.__class__.__name__}.",
                    "An unreadable or concurrently replaced file cannot be fingerprinted reliably.",
                    path=rel,
                ))
                continue
            finally:
                if descriptor is not None:
                    os.close(descriptor)
            total_bytes += len(data)
            encoding = None
            try:
                text = data.decode("utf-8")
                encoding = "utf-8"
                if path.suffix.lower() in READABLE_SUFFIXES:
                    texts[rel] = text
            except UnicodeDecodeError:
                if path.suffix.lower() in SCRIPT_SUFFIXES:
                    findings.append(new_finding(
                        "SCRIPT_NOT_UTF8", "high", "script_validation",
                        "Script-like resource is not valid UTF-8 text.",
                        "Static syntax checks and safe preservation require readable script text.",
                        path=rel, proposed_change="Restore the intended encoding or explicitly mark this as a binary asset.",
                        requires_review=True,
                    ))
            inventory[rel] = FileFingerprint(
                path=rel, size_bytes=len(data), sha256=sha256_bytes(data),
                encoding=encoding, kind=path.suffix.lower().lstrip(".") or "file",
            )

    if "SKILL.md" not in inventory:
        findings.append(new_finding(
            "SKILL_MD_MISSING", "critical", "structure",
            "Required SKILL.md file is missing.",
            "An Agent Skill package requires a SKILL.md entry point.",
            path="SKILL.md", proposed_change="Add SKILL.md with valid YAML frontmatter and instructions.",
        ))
    elif "SKILL.md" in texts:
        findings.extend(validate_skill_markdown(root_path, texts["SKILL.md"]))
    elif "SKILL.md" in inventory:
        findings.append(new_finding(
            "SKILL_MD_NOT_UTF8", "critical", "structure",
            "SKILL.md is not valid UTF-8 text.",
            "Frontmatter and Markdown cannot be parsed from this encoding.", path="SKILL.md",
        ))

    for rel, text in sorted(texts.items()):
        findings.extend(validate_resource_syntax(rel, text))
        if Path(rel).suffix.lower() in TEXT_SUFFIXES:
            findings.extend(validate_local_links(root_path, rel, text))
        findings.extend(validate_referenced_resources(root_path, rel, text, findings))
    return inventory, findings, texts


def _frontmatter(text: str) -> tuple[dict[str, Any] | None, str, int, str | None]:
    lines = text.splitlines()
    if not lines or not FRONTMATTER_START.fullmatch(lines[0]):
        return None, "", 0, "SKILL.md must begin with a YAML frontmatter block delimited by ---."
    close = next((i for i in range(1, len(lines)) if FRONTMATTER_START.fullmatch(lines[i])), None)
    if close is None:
        return None, "", 0, "YAML frontmatter opening delimiter has no closing ---."
    raw = "\n".join(lines[1:close])
    try:
        parsed = safe_load_unique(raw)
    except yaml.YAMLError as exc:
        return None, "", close + 1, f"Malformed YAML frontmatter: {exc.__class__.__name__}."
    if not isinstance(parsed, dict):
        return None, "", close + 1, "YAML frontmatter must be a mapping of field names to values."
    return parsed, "\n".join(lines[close + 1:]), close + 1, None


def validate_skill_markdown(root: Path, text: str) -> list:
    findings = []
    metadata, body, _body_start_line, error = _frontmatter(text)
    if error:
        findings.append(new_finding(
            "FRONTMATTER_INVALID", "critical", "frontmatter", error,
            "SKILL.md requires a closed, parseable YAML frontmatter mapping.",
            path="SKILL.md", proposed_change="Repair the YAML frontmatter without translating machine-readable fields.",
        ))
        return findings

    assert metadata is not None
    allowed = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
    for key in ("name", "description"):
        value = metadata.get(key)
        if not isinstance(value, str) or not value.strip():
            findings.append(new_finding(
                "FRONTMATTER_REQUIRED_FIELD", "critical", "frontmatter",
                f"Required frontmatter field {key!r} must be a non-empty string.",
                "The Agent Skills specification requires name and description.",
                path="SKILL.md", proposed_change=f"Set a valid {key} field.",
            ))
    name = metadata.get("name")
    if isinstance(name, str):
        if len(name) > 64 or not NAME_PATTERN.fullmatch(name):
            findings.append(new_finding(
                "SKILL_NAME_INVALID", "high", "frontmatter",
                "Skill name must be 1–64 lowercase letters, digits, and single hyphen-separated groups.",
                "The name is a machine-facing identifier and must not be localized as prose.",
                path="SKILL.md", proposed_change="Restore a valid kebab-case name.",
            ))
        if name != root.name:
            findings.append(new_finding(
                "SKILL_NAME_DIRECTORY_MISMATCH", "high", "frontmatter",
                "Frontmatter name does not match the skill directory basename.",
                "Consumers use the directory and metadata name as a package identity.",
                path="SKILL.md", proposed_change=f"Use the directory identity {root.name!r}, or rename the package explicitly.",
            ))
    description = metadata.get("description")
    if isinstance(description, str):
        if len(description) > 1024:
            findings.append(new_finding(
                "DESCRIPTION_TOO_LONG", "high", "frontmatter",
                "Skill description exceeds 1024 characters.",
                "The specification limits discovery metadata to 1024 characters.",
                path="SKILL.md", proposed_change="Shorten the description while preserving its activation conditions.",
            ))
        if not description.strip():
            findings.append(new_finding(
                "DESCRIPTION_EMPTY", "critical", "frontmatter",
                "Skill description is empty.", "A skill needs a description for discovery.",
                path="SKILL.md",
            ))
    if "license" in metadata and not isinstance(metadata["license"], str):
        findings.append(new_finding(
            "LICENSE_INVALID", "high", "frontmatter",
            "license must be a string when present.",
            "License metadata is machine-readable package metadata and must retain its declared type.",
            path="SKILL.md",
        ))
    compatibility = metadata.get("compatibility")
    if compatibility is not None and (
        not isinstance(compatibility, str) or not compatibility.strip() or len(compatibility) > 500
    ):
        findings.append(new_finding(
            "COMPATIBILITY_INVALID", "high", "frontmatter",
            "compatibility must be a string of at most 500 characters.",
            "Compatibility metadata has a defined field type and length limit.", path="SKILL.md",
        ))
    if "allowed-tools" in metadata and not isinstance(metadata["allowed-tools"], str):
        findings.append(new_finding(
            "ALLOWED_TOOLS_INVALID", "high", "frontmatter",
            "allowed-tools must be a space-delimited string.",
            "Tool declarations are identifiers and must be preserved literally.", path="SKILL.md",
        ))
    if "metadata" in metadata:
        extra = metadata["metadata"]
        if not isinstance(extra, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in extra.items()):
            findings.append(new_finding(
                "METADATA_INVALID", "high", "frontmatter",
                "metadata must be a mapping with string keys and string values.",
                "Metadata values are machine-readable and must remain parseable.", path="SKILL.md",
            ))
    unknown = sorted(set(metadata) - allowed)
    if unknown:
        findings.append(new_finding(
            "FRONTMATTER_UNKNOWN_FIELDS", "low", "frontmatter",
            "Frontmatter contains fields not defined by the current base specification: " + ", ".join(unknown),
            "Unknown fields may be intentional extensions; validate them against the target client.",
            path="SKILL.md", proposed_change="Keep only intentional extension fields and document the client requirement.",
        ))
    if len(text.splitlines()) > 500:
        findings.append(new_finding(
            "SKILL_MD_LONG", "low", "structure",
            "SKILL.md exceeds the recommended 500-line progressive-disclosure guideline.",
            "Long reference material may be better placed in references/.", path="SKILL.md",
        ))
    if not body.strip():
        findings.append(new_finding(
            "SKILL_BODY_EMPTY", "high", "structure",
            "SKILL.md has no instruction body after frontmatter.",
            "Metadata alone does not provide the skill instructions.",
            path="SKILL.md", proposed_change="Add the intended instruction content after the closing delimiter.",
        ))
    return findings


def validate_local_links(root: Path, rel_path: str, text: str) -> list:
    findings = []
    parsed = MarkdownIt("commonmark", {"html": False}).parse(text)
    for token in parsed:
        for child in token.children or []:
            if child.type not in {"link_open", "image"}:
                continue
            attrs = dict(child.attrs or [])
            href = attrs.get("href") if child.type == "link_open" else attrs.get("src")
            if not href:
                continue
            parsed_url = urlsplit(href)
            if parsed_url.scheme or href.startswith("//"):
                continue
            decoded = unquote(parsed_url.path)
            if not decoded and parsed_url.fragment:
                decoded = Path(rel_path).name
            destination = (root / Path(rel_path).parent / decoded).resolve()
            if not destination.is_relative_to(root.resolve()):
                findings.append(new_finding(
                    "PATH_TRAVERSAL_LINK", "high", "links",
                    "Local link resolves outside the package root.",
                    "A translated or hostile path must not escape the package boundary.",
                    path=rel_path, proposed_change="Use a relative link that resolves within the package.",
                ))
                continue
            if not destination.exists():
                findings.append(new_finding(
                    "BROKEN_LOCAL_LINK", "high", "links",
                    f"Local link target does not exist: {href}",
                    "Broken links can make required reference material or assets unavailable.",
                    path=rel_path, proposed_change="Restore the resource or correct the link while preserving the intended path.",
                ))
                continue
            if parsed_url.fragment and destination.is_file():
                try:
                    target_text = destination.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                fragments = set(re.findall(r"\bid\s*=\s*['\"]([^'\"]+)", target_text, re.I))
                fragments.update(re.findall(r"\bname\s*=\s*['\"]([^'\"]+)", target_text, re.I))
                for heading in re.finditer(r"^#{1,6}\s+(.+?)\s*#*\s*$", target_text, re.M):
                    slug = re.sub(r"[^\w -]", "", heading.group(1).lower()).strip().replace(" ", "-")
                    fragments.add(slug)
                if parsed_url.fragment not in fragments and target_text:
                    findings.append(new_finding(
                        "BROKEN_LINK_FRAGMENT", "medium", "links",
                        f"Local link fragment does not match a detected heading or HTML anchor: {href}",
                        "A path can exist while its in-document reference is broken.",
                        path=rel_path, proposed_change="Update the fragment or restore the referenced heading/anchor.",
                    ))
    return findings



def validate_resource_syntax(rel_path: str, text: str) -> list:
    """Statically parse selected text resources without executing any package code."""
    findings = []
    suffix = Path(rel_path).suffix.lower()
    try:
        if suffix == ".py":
            ast.parse(text, filename=rel_path)
        elif suffix == ".json":
            json.loads(text)
        elif suffix == ".toml":
            tomllib.loads(text)
        elif suffix in {".yaml", ".yml"}:
            safe_load_unique(text)
        elif suffix == ".xml":
            ET.fromstring(text)
    except (SyntaxError, json.JSONDecodeError, tomllib.TOMLDecodeError, yaml.YAMLError, ET.ParseError) as exc:
        line = getattr(exc, "lineno", None) or getattr(exc, "position", (None,))[0]
        text_lines = text.splitlines()
        excerpt = text_lines[line - 1] if isinstance(line, int) and 1 <= line <= len(text_lines) else None
        findings.append(new_finding(
            "RESOURCE_SYNTAX_INVALID", "high", "resource_validation",
            f"Static syntax validation failed for {rel_path!r} ({exc.__class__.__name__}).",
            "Malformed scripts or structured resource files may fail at runtime or break the localized package.",
            path=rel_path, source_line=line if isinstance(line, int) and line > 0 else None,
            original_context=excerpt,
            proposed_change="Repair the syntax or confirm the file type/format is intentionally different.",
            requires_review=True,
        ))
    return findings


def validate_referenced_resources(
    root: Path, rel_path: str, text: str, existing_findings: list,
) -> list:
    """Resolve conventional skill resource paths in prose and code without running scripts."""
    findings = []
    seen: set[str] = set()
    lines = text.splitlines()
    for line_no, line in enumerate(lines, start=1):
        for match in RESOURCE_REFERENCE.finditer(line):
            raw = match.group("path")
            value = raw.rstrip(".,;:!?")
            if not value or value in seen:
                continue
            seen.add(value)
            if any(
                finding.path == rel_path
                and finding.code in {"BROKEN_LOCAL_LINK", "PATH_TRAVERSAL_LINK"}
                and value in finding.message
                for finding in existing_findings
            ):
                continue
            candidate_paths = [
                (root / value).resolve(),
                (root / Path(rel_path).parent / value).resolve(),
            ]
            in_package = [item for item in candidate_paths if item.is_relative_to(root.resolve())]
            if not in_package:
                findings.append(new_finding(
                    "PATH_TRAVERSAL_RESOURCE", "critical", "resource_validation",
                    f"Referenced resource path escapes the package root: {value!r}.",
                    "Resource paths must remain inside the skill package.",
                    path=rel_path, source_line=line_no, original_context=line,
                    proposed_change="Use a resource path contained within the package root.",
                    requires_review=True,
                ))
                continue
            if not any(item.exists() for item in in_package):
                findings.append(new_finding(
                    "MISSING_REFERENCED_RESOURCE", "high", "resource_validation",
                    f"Referenced skill resource does not exist: {value!r}.",
                    "Scripts, references, and assets named in instructions should be present in the package.",
                    path=rel_path, source_line=line_no, original_context=line,
                    proposed_change="Restore the resource or correct the reference after confirming the intended path.",
                    requires_review=True,
                ))
    return findings

def extract_protected_tokens(
    text: str, path: str, extra_patterns: list[dict[str, str]] | None = None,
    explicit_tokens: list[str] | None = None,
) -> list[ProtectedToken]:
    """Extract code blocks and high-confidence literal tokens; never execute content."""
    patterns = [
        ("url", re.compile(r"https?://[^\s<>)]+")),
        ("environment_variable", re.compile(r"(?<![A-Za-z0-9_])\$[A-Z][A-Z0-9_]*")),
        ("environment_variable", re.compile(r"%[A-Z][A-Z0-9_]*%")),
        ("command_flag", re.compile(r"(?<![A-Za-z0-9_-])--[A-Za-z][A-Za-z0-9-]*")),
        ("windows_path", re.compile(r"[A-Za-z]:\\[^\s]+")),
        ("file_path", re.compile(r"(?:\.\.?/|(?:[A-Za-z0-9_.-]+/)+)[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*")),
        ("inline_code", re.compile(r"(\x60+).*?\1")),
    ]
    for item in extra_patterns or []:
        try:
            patterns.append((item["category"], re.compile(item["regex"])))
        except (KeyError, re.error):
            continue
    result: list[ProtectedToken] = []
    fence_marker: str | None = None
    fence_start = 0
    fence_lines: list[str] = []

    def add(category: str, value: str, line_no: int) -> None:
        if value:
            result.append(ProtectedToken(path=path, category=category, value=value, line=line_no))

    for line_no, line in enumerate(text.splitlines(), start=1):
        opening = FENCE_START.match(line)
        if fence_marker is not None:
            fence_lines.append(line)
            if opening and opening.group(1)[0] == fence_marker[0] and len(opening.group(1)) >= len(fence_marker):
                add("code_block", "\n".join(fence_lines), fence_start)
                fence_marker = None
                fence_lines = []
            continue
        if opening:
            fence_marker = opening.group(1)
            fence_start = line_no
            fence_lines = [line]
            continue
        for category, pattern in patterns:
            for match in pattern.finditer(line):
                add(category, match.group(0), line_no)
        for token in explicit_tokens or []:
            if token and token in line:
                add("explicit_identifier", token, line_no)
    if fence_marker is not None:
        add("code_block", "\n".join(fence_lines), fence_start)
    return result


def load_policy(path: str | Path | None) -> tuple[list[dict[str, str]], list[str]]:
    if path is None:
        return [], []
    data = safe_load_unique(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Protected-token policy must be a YAML or JSON mapping")
    patterns = data.get("patterns", [])
    tokens = data.get("explicit_tokens", [])
    if not isinstance(patterns, list) or not isinstance(tokens, list):
        raise ValueError("Policy patterns and explicit_tokens must be lists")
    if len(patterns) > MAX_POLICY_PATTERNS:
        raise ValueError(f"Protected-token policy exceeds {MAX_POLICY_PATTERNS} patterns")
    if len(tokens) > MAX_EXPLICIT_TOKENS:
        raise ValueError(f"Protected-token policy exceeds {MAX_EXPLICIT_TOKENS} explicit tokens")
    for index, item in enumerate(patterns):
        if not isinstance(item, dict) or not isinstance(item.get("category"), str) or not isinstance(item.get("regex"), str):
            raise ValueError(f"Protected-token pattern {index} needs string category and regex fields")
        if len(item["regex"]) > MAX_POLICY_REGEX_CHARS:
            raise ValueError(f"Protected-token regex at index {index} exceeds {MAX_POLICY_REGEX_CHARS} characters")
        try:
            compiled = re.compile(item["regex"])
        except re.error as exc:
            raise ValueError(f"Invalid protected-token regex at index {index}") from exc
        samples = ("", "x", "1", "A", "/", "-", "$", "x1", "sample")
        if any(
            (match := compiled.search(sample)) is not None and match.start() == match.end()
            for sample in samples
        ):
            raise ValueError(f"Protected-token regex at index {index} may match an empty span")
    if not all(isinstance(token, str) and token for token in tokens):
        raise ValueError("explicit_tokens must contain non-empty strings")
    if any(len(token) > MAX_EXPLICIT_TOKEN_CHARS for token in tokens):
        raise ValueError(f"Explicit protected tokens must be at most {MAX_EXPLICIT_TOKEN_CHARS} characters")
    return patterns, tokens
