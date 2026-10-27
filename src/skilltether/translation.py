"""Provider-neutral translation interfaces and atomic candidate-package generation."""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Protocol

from .analysis import inspect_package, package_fingerprint
from .models import FileFingerprint

ELIGIBLE_SUFFIXES = {".md", ".mdx", ".txt", ".rst"}
FENCE = re.compile(r"^\s{0,3}(\x60{3,}|~{3,})")
PREFIX = re.compile(r"^(\s*(?:(?:#{1,6}|>)\s+|[-*+]\s+|\d+[.)]\s+)?)(.*?)(\r?\n?)$")
MASK_SPAN = re.compile(
    r"\x60+.*?\x60+|https?://[^ <>)]+|<[^>]+>|(?<=\]\()[^)]*(?=\))"
    r"|(?<![A-Za-z0-9_])[$][A-Z][A-Z0-9_]*|%[A-Z][A-Z0-9_]*%"
    r"|(?<![A-Za-z0-9_-])--[A-Za-z][A-Za-z0-9-]*"
    r"|[A-Za-z]:\x5c[^ ]+"
    r"|(?:[.][.]/|[.]/|(?:[A-Za-z0-9_.-]+/)+)[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*"
)


class TranslationAdapter(Protocol):
    """Small interface implemented by provider-specific or in-house adapters."""

    name: str
    remote: bool

    def translate(self, text: str, source_locale: str, target_locale: str) -> str:
        """Return translated prose, preserving any supplied opaque placeholders."""


class IdentityAdapter:
    """No-op adapter for local tests, dry runs, and structural pipeline verification."""

    name = "identity"
    remote = False

    def translate(self, text: str, source_locale: str, target_locale: str) -> str:
        return text


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Prevent redirects from forwarding private prose to an unreviewed destination."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(
            newurl, code, "translation redirects are disabled", headers, fp,
        )


class HttpJsonAdapter:
    """Generic JSON HTTP bridge: POST {text, source_locale, target_locale}; expect {text}."""

    name = "http-json"
    remote = True

    def __init__(self, endpoint: str, timeout: float = 60.0) -> None:
        parsed = urllib.parse.urlparse(endpoint)
        local_hosts = {"localhost", "127.0.0.1", "::1"}
        if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in local_hosts):
            raise ValueError("Translation endpoint must use HTTPS (HTTP is allowed only for loopback hosts)")
        if not parsed.hostname:
            raise ValueError("Translation endpoint must include a host")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Do not put credentials, query parameters, or fragments in the translation endpoint URL")
        self.endpoint = endpoint
        self.timeout = timeout

    def translate(self, text: str, source_locale: str, target_locale: str) -> str:
        body = json.dumps({
            "text": text, "source_locale": source_locale, "target_locale": target_locale,
        }, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint, data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            opener = urllib.request.build_opener(_NoRedirect())
            with opener.open(request, timeout=self.timeout) as response:
                raw = response.read(2 * 1024 * 1024 + 1)
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"Translation provider request failed: {exc.__class__.__name__}") from exc
        if len(raw) > 2 * 1024 * 1024:
            raise RuntimeError("Translation provider response exceeds the 2 MiB safety limit")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Translation provider returned invalid UTF-8 JSON") from exc
        result = payload.get("text") if isinstance(payload, dict) else None
        if not isinstance(result, str):
            raise RuntimeError("Translation provider response must be a JSON object with a string 'text' field")
        return result


def translate_markdown(
    text: str, adapter: TranslationAdapter, source_locale: str, target_locale: str,
    extra_patterns: list[dict[str, str]] | None = None,
    explicit_tokens: list[str] | None = None,
) -> str:
    """Translate prose while masking machine-facing literals and preserving Markdown structure."""
    lines = text.splitlines(keepends=True)
    in_frontmatter = bool(lines and lines[0].strip() == "---")
    frontmatter_closed = not in_frontmatter
    fence_marker: str | None = None
    output: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not frontmatter_closed:
            output.append(line)
            if stripped == "---" and len(output) > 1:
                frontmatter_closed = True
            continue
        fence_match = FENCE.match(line)
        if fence_marker is not None:
            output.append(line)
            if fence_match and fence_match.group(1)[0] == fence_marker[0] and len(fence_match.group(1)) >= len(fence_marker):
                fence_marker = None
            continue
        if fence_match:
            fence_marker = fence_match.group(1)
            output.append(line)
            continue
        if (
            not stripped or line.startswith("    ") or line.startswith("\t")
            or stripped.startswith("|") or re.match(r"^\s{0,3}\[[^\]]+\]:", line)
            or stripped.startswith("<!--") or stripped.startswith("<!DOCTYPE")
            or re.match(r"^\s*</?[A-Za-z][^>]*>\s*$", line)
        ):
            output.append(line)
            continue

        matched = PREFIX.match(line)
        if not matched:
            output.append(line)
            continue
        prefix, prose, ending = matched.groups()
        if not re.search(r"[A-Za-zÀ-ɏΑ-ϿЀ-ӿ]", prose):
            output.append(line)
            continue
        masked, replacements = _mask_protected_spans(prose, extra_patterns, explicit_tokens)
        if not masked.strip():
            output.append(line)
            continue
        translated = adapter.translate(masked, source_locale, target_locale)
        if not isinstance(translated, str):
            raise RuntimeError("Translation adapter returned a non-string result")
        for marker, _original in replacements:
            if translated.count(marker) != 1:
                raise RuntimeError("Translation adapter altered or duplicated a protected placeholder; no output was published")
        for marker, original in replacements:
            translated = translated.replace(marker, original)
        output.append(prefix + translated + ending)
    if in_frontmatter and not frontmatter_closed:
        raise ValueError("Unclosed SKILL.md frontmatter; refusing to translate malformed input")
    return "".join(output)


def _mask_protected_spans(
    prose: str, extra_patterns: list[dict[str, str]] | None,
    explicit_tokens: list[str] | None,
) -> tuple[str, list[tuple[str, str]]]:
    # Collect matches independently, then resolve overlaps by earliest start and
    # longest span. Regex alternation is left-biased, so a single combined pattern
    # can accidentally protect only a prefix when configured identifiers overlap.
    patterns: list[re.Pattern[str]] = [re.compile(MASK_SPAN.pattern)]
    for item in extra_patterns or []:
        regex = item.get("regex")
        if not isinstance(regex, str):
            raise ValueError("Every protected-token policy entry needs a regex string")
        if len(regex) > 1000:
            raise ValueError("Protected-token policy regex exceeds the 1000-character limit")
        try:
            custom = re.compile(regex)
        except re.error as exc:
            raise ValueError("Invalid custom protected-token regular expression") from exc
        patterns.append(custom)

    # (start, end, priority, literal). Explicit identifiers are treated as
    # literal substrings; longest-first overlap resolution preserves compound
    # identifiers such as TOOL and TOOL_NAME as one opaque span.
    candidates: list[tuple[int, int, int, str]] = []
    for priority, pattern in enumerate(patterns):
        for match in pattern.finditer(prose):
            if match.start() == match.end():
                raise ValueError("Protected-token policy regex matched an empty span")
            candidates.append((match.start(), match.end(), priority, match.group(0)))

    seen_tokens: set[str] = set()
    for token in sorted((token for token in (explicit_tokens or []) if token), key=lambda value: (-len(value), value)):
        if token in seen_tokens:
            continue
        seen_tokens.add(token)
        for match in re.finditer(re.escape(token), prose):
            candidates.append((match.start(), match.end(), len(patterns), match.group(0)))

    candidates.sort(key=lambda item: (item[0], -(item[1] - item[0]), item[2], item[3]))
    selected: list[tuple[int, int, str]] = []
    cursor = 0
    for start, end, _priority, literal in candidates:
        if start < cursor:
            continue
        selected.append((start, end, literal))
        cursor = end

    replacements: list[tuple[str, str]] = []
    output: list[str] = []
    cursor = 0
    # Never choose a placeholder namespace that already occurs in unmasked prose.
    placeholder_prefix = "SKTETHEROPAQUE"
    while placeholder_prefix in prose:
        placeholder_prefix = "_" + placeholder_prefix
    for index, (start, end, original) in enumerate(selected):
        output.append(prose[cursor:start])
        marker = f"{placeholder_prefix}{index:05d}END"
        replacements.append((marker, original))
        output.append(marker)
        cursor = end
    output.append(prose[cursor:])
    return "".join(output), replacements


def translate_package(
    source: str | Path, output: str | Path, adapter: TranslationAdapter,
    source_locale: str, target_locale: str,
    protected_patterns: list[dict[str, str]] | None = None,
    explicit_tokens: list[str] | None = None,
) -> tuple[dict[str, FileFingerprint], dict[str, FileFingerprint], int]:
    """Generate a candidate atomically; never mutate source or overwrite an existing output."""
    source_root = Path(source).expanduser().resolve(strict=True)
    output_root = Path(output).expanduser().resolve()
    if not source_root.is_dir():
        raise ValueError("Source package must be a directory")
    if output_root.exists():
        raise FileExistsError(f"Candidate output already exists: {output_root}")
    if output_root.name != source_root.name:
        raise ValueError(
            "Candidate directory basename must match the source skill package name; "
            "choose a separate parent directory with the same leaf name."
        )
    if output_root == source_root or source_root in output_root.parents or output_root in source_root.parents:
        raise ValueError("Source and output directories must be separate and non-overlapping")

    source_inventory, validation_findings, source_text = inspect_package(source_root)
    severe = [f for f in validation_findings if f.severity in ("high", "critical")]
    if severe:
        codes = ", ".join(sorted({f.code for f in severe}))
        raise ValueError(f"Source package has blocking validation findings: {codes}")
    before = package_fingerprint(source_inventory)

    output_root.parent.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix=f".{output_root.name}.candidate-", dir=output_root.parent))
    temp_package = temp_root / output_root.name
    try:
        shutil.copytree(source_root, temp_package, symlinks=False)
        translated_count = 0
        for rel, original_text in sorted(source_text.items()):
            if Path(rel).suffix.lower() not in ELIGIBLE_SUFFIXES:
                continue
            translated = translate_markdown(
                original_text, adapter, source_locale, target_locale,
                extra_patterns=protected_patterns, explicit_tokens=explicit_tokens,
            )
            if translated != original_text:
                (temp_package / rel).write_text(translated, encoding="utf-8", newline="")
                translated_count += 1

        after_inventory, _after_findings, _after_text = inspect_package(source_root)
        if package_fingerprint(after_inventory) != before:
            raise RuntimeError("Source package changed during translation; candidate discarded")
        target_inventory, target_findings, _target_text = inspect_package(temp_package)
        blocking = [f for f in target_findings if f.severity in ("high", "critical")]
        if blocking:
            codes = ", ".join(sorted({f.code for f in blocking}))
            raise RuntimeError(f"Translated candidate failed structural validation: {codes}")
        os.replace(temp_package, output_root)
        return source_inventory, target_inventory, translated_count
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
