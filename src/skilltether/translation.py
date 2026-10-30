"""Provider-neutral translation interfaces and atomic candidate-package generation."""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Protocol

from .markdown_support import create_markdown_parser

from .analysis import (
    MAX_EXPLICIT_TOKEN_CHARS, MAX_EXPLICIT_TOKENS, MAX_POLICY_PATTERNS,
    MAX_POLICY_REGEX_CHARS, inspect_package, normalize_package_root, package_fingerprint,
)
from .models import FileFingerprint
from .regex_safety import validate_policy_regex

ELIGIBLE_SUFFIXES = {".md", ".mdx", ".txt", ".rst"}
MAX_TRANSLATION_REQUEST_BYTES = 2 * 1024 * 1024
MAX_TRANSLATION_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_TRANSLATION_REQUESTS = 10_000
MAX_TRANSLATION_TOTAL_REQUEST_BYTES = 10 * 1024 * 1024
MAX_TRANSLATION_TOTAL_RESPONSE_BYTES = 10 * 1024 * 1024
MAX_TRANSLATION_TIMEOUT_SECONDS = 300.0
FENCE = re.compile(r"^\s{0,3}(\x60{3,}|~{3,})")
HTML_OPAQUE_OPEN = re.compile(r"^\s*<(script|style|pre|code|textarea)\b", re.I)
PREFIX = re.compile(r"^(\s*(?:(?:#{1,6}|>)\s+|[-*+]\s+|\d+[.)]\s+)?)(.*?)(\r?\n?)$")
MASK_SPAN = re.compile(
    r"\x60+.*?\x60+|https?://[^ <>)]+|<[^>]+>|(?<=\]\()[^)]*(?=\))"
    r"|(?<![A-Za-z0-9_])[$][A-Z][A-Z0-9_]*|%[A-Z][A-Z0-9_]*%"
    r"|(?<![A-Za-z0-9_-])--[A-Za-z][A-Za-z0-9-]*"
    r"|[A-Za-z]:\x5c[^ ]+"
    r"|(?:[.][.]/|[.]/|(?:[A-Za-z0-9_.-]+/)+)[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*"
)
# Keep Markdown punctuation opaque while allowing text between delimiters to
# translate. These are lexical safeguards, not a complete CommonMark parser.
MARKDOWN_SYNTAX = re.compile(
    r"\\[\\\\\\x60*{}\[\]()#+.!_|>~-]"
    r"|\[ xX\]"
    r"|\[\^[^\]\r\n]+\]"
    r"|\]\[[^\]\r\n]*\]"
    r"|!\[|\]\(|\*\*|__|~~|\x60|\[|\]|\(|\)|\*|_|~|\|| {2,}$"
)

FOOTNOTE_DEFINITION = re.compile(r"^(\s{0,3}\[\^[^\]\r\n]+\]:\s*)(.*?)(\r?\n?)$")
GFM_ALERT_PREFIX = re.compile(
    r"^(\s{0,3}>\s*\[!(?:NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s+)(.*?)(\r?\n?)$",
    re.I,
)
DEFINITION_LIST_MARKER = re.compile(r"^(\s{0,3}[:~]\s+)(.*?)(\r?\n?)$")


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
        if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 0 < timeout <= MAX_TRANSLATION_TIMEOUT_SECONDS:
            raise ValueError(f"Translation timeout must be greater than 0 and at most {MAX_TRANSLATION_TIMEOUT_SECONDS:g} seconds")
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
        # The adapter also enforces aggregate limits when used directly outside
        # translate_package's whole-package preflight.
        self._request_count = 0
        self._total_request_bytes = 0
        self._total_response_bytes = 0

    def translate(self, text: str, source_locale: str, target_locale: str) -> str:
        body = json.dumps({
            "text": text, "source_locale": source_locale, "target_locale": target_locale,
        }, ensure_ascii=False).encode("utf-8")
        if len(body) > MAX_TRANSLATION_REQUEST_BYTES:
            raise RuntimeError(
                f"Translation provider request exceeds the {MAX_TRANSLATION_REQUEST_BYTES}-byte per-request safety limit"
            )
        if self._request_count + 1 > MAX_TRANSLATION_REQUESTS:
            raise RuntimeError(
                f"Translation provider request count exceeds the {MAX_TRANSLATION_REQUESTS}-request total safety limit"
            )
        if self._total_request_bytes + len(body) > MAX_TRANSLATION_TOTAL_REQUEST_BYTES:
            raise RuntimeError(
                f"Translation provider aggregate request bytes exceed the {MAX_TRANSLATION_TOTAL_REQUEST_BYTES}-byte safety limit"
            )
        remaining_response_bytes = MAX_TRANSLATION_TOTAL_RESPONSE_BYTES - self._total_response_bytes
        if remaining_response_bytes <= 0:
            raise RuntimeError(
                f"Translation provider aggregate response bytes exceed the {MAX_TRANSLATION_TOTAL_RESPONSE_BYTES}-byte safety limit"
            )
        response_limit = min(MAX_TRANSLATION_RESPONSE_BYTES, remaining_response_bytes)
        self._request_count += 1
        self._total_request_bytes += len(body)
        request = urllib.request.Request(
            self.endpoint, data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            opener = urllib.request.build_opener(_NoRedirect())
            with opener.open(request, timeout=self.timeout) as response:
                raw = response.read(response_limit + 1)
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"Translation provider request failed: {exc.__class__.__name__}") from exc
        self._total_response_bytes += len(raw)
        if len(raw) > response_limit:
            raise RuntimeError(
                "Translation provider response exceeds the remaining per-request or aggregate response-byte safety limit"
            )
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Translation provider returned invalid UTF-8 JSON") from exc
        result = payload.get("text") if isinstance(payload, dict) else None
        if not isinstance(result, str):
            raise RuntimeError("Translation provider response must be a JSON object with a string 'text' field")
        return result


def _validate_translation_output(value: object) -> tuple[str, int]:
    """Bound and validate adapter text before it can affect a candidate package."""
    if not isinstance(value, str):
        raise RuntimeError("Translation adapter returned a non-string result")
    if len(value) > MAX_TRANSLATION_RESPONSE_BYTES:
        raise RuntimeError(
            f"Translation adapter response exceeds the {MAX_TRANSLATION_RESPONSE_BYTES}-byte per-line safety limit"
        )
    if any(char in value for char in ("\r", "\n", "\v", "\f", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029")):
        raise RuntimeError(
            "Translation adapter returned a multiline result for a single Markdown line; no output was published"
        )
    if any((ord(char) < 32 and char != "\t") or ord(char) == 127 for char in value):
        raise RuntimeError("Translation adapter returned unsupported control characters")
    try:
        encoded_size = len(value.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise RuntimeError("Translation adapter returned invalid Unicode text") from exc
    if encoded_size > MAX_TRANSLATION_RESPONSE_BYTES:
        raise RuntimeError(
            f"Translation adapter response exceeds the {MAX_TRANSLATION_RESPONSE_BYTES}-byte per-line safety limit"
        )
    return value, encoded_size


class _TranslationOutputBudgetAdapter:
    """Apply the aggregate response budget to every adapter, including custom ones."""

    def __init__(self, adapter: TranslationAdapter) -> None:
        self.adapter = adapter
        self.name = adapter.name
        self.remote = adapter.remote
        self.total_response_bytes = 0

    def translate(self, text: str, source_locale: str, target_locale: str) -> str:
        result, size = _validate_translation_output(
            self.adapter.translate(text, source_locale, target_locale)
        )
        if self.total_response_bytes + size > MAX_TRANSLATION_TOTAL_RESPONSE_BYTES:
            raise RuntimeError(
                f"Translation adapter aggregate response bytes exceed the {MAX_TRANSLATION_TOTAL_RESPONSE_BYTES}-byte safety limit"
            )
        self.total_response_bytes += size
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
    html_comment_open = False
    html_opaque_tag: str | None = None
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
        # HTML comments and code-bearing/raw-text elements can span multiple
        # lines. Preserve their full contents instead of translating a line
        # that happens to fall after the opening marker.
        if html_comment_open:
            output.append(line)
            if "-->" in line:
                html_comment_open = False
            continue
        if html_opaque_tag is not None:
            output.append(line)
            if re.search(rf"</{re.escape(html_opaque_tag)}\s*>", line, re.I):
                html_opaque_tag = None
            continue
        if "<!--" in line:
            output.append(line)
            comment_start = line.find("<!--")
            if "-->" not in line[comment_start + 4:]:
                html_comment_open = True
            continue
        opaque_open = HTML_OPAQUE_OPEN.match(line)
        if opaque_open:
            tag = opaque_open.group(1)
            output.append(line)
            if not re.search(rf"</{re.escape(tag)}\s*>", line, re.I):
                html_opaque_tag = tag
            continue
        is_footnote_definition = FOOTNOTE_DEFINITION.match(line) is not None
        if (
            not stripped or line.startswith("    ") or line.startswith("\t")
            or (re.match(r"^\s{0,3}\[[^\]]+\]:", line) and not is_footnote_definition)
            or stripped.startswith("<!--") or stripped.startswith("<!DOCTYPE")
            or re.match(r"^\s*</?[A-Za-z][^>]*>\s*$", line)
        ):
            output.append(line)
            continue

        matched = (
            FOOTNOTE_DEFINITION.match(line)
            or GFM_ALERT_PREFIX.match(line)
            or DEFINITION_LIST_MARKER.match(line)
            or PREFIX.match(line)
        )
        if not matched:
            output.append(line)
            continue
        prefix, prose, ending = matched.groups()
        if not re.search(r"[A-Za-zÀ-ɏΑ-ϿЀ-ӿ]", prose):
            output.append(line)
            continue
        masked, protected_replacements = _mask_protected_spans(prose, extra_patterns, explicit_tokens)
        if not masked.strip():
            output.append(line)
            continue
        masked, syntax_replacements = _mask_markdown_syntax(masked)
        replacements = protected_replacements + syntax_replacements
        translated, _translated_size = _validate_translation_output(
            adapter.translate(masked, source_locale, target_locale)
        )
        for marker, _original in replacements:
            if translated.count(marker) != 1:
                raise RuntimeError("Translation adapter altered or duplicated a protected placeholder; no output was published")
        # Syntax delimiters are order-sensitive (for example the opening and
        # closing markers around emphasis). Providers may not reorder them.
        syntax_markers = [marker for marker, _original in syntax_replacements]
        syntax_positions = [translated.find(marker) for marker in syntax_markers]
        if syntax_positions != sorted(syntax_positions):
            raise RuntimeError("Translation adapter reordered Markdown syntax placeholders; no output was published")
        for marker, original in replacements:
            translated = translated.replace(marker, original)
        output.append(prefix + translated + ending)
    if in_frontmatter and not frontmatter_closed:
        raise ValueError("Unclosed SKILL.md frontmatter; refusing to translate malformed input")
    if html_comment_open or html_opaque_tag is not None:
        raise ValueError("Unclosed HTML comment or opaque HTML block; refusing to translate malformed input")
    translated_document = "".join(output)
    if _markdown_structure_signature(text) != _markdown_structure_signature(translated_document):
        raise RuntimeError(
            "Translation changed parser-visible Markdown structure; no output was published"
        )
    return translated_document


def _markdown_structure_signature(text: str) -> tuple[tuple[object, ...], ...]:
    """Describe parser-visible Markdown structure without ordinary prose content.

    This catches providers that insert new links/emphasis/block syntax even when
    every source placeholder is retained. It is a structural guard, not semantic
    analysis, and intentionally does not compare ordinary text tokens.
    """
    parser = create_markdown_parser()
    signature: list[tuple[object, ...]] = []

    def visit(token: object) -> None:
        token_type = getattr(token, "type")
        children = getattr(token, "children", None)
        if token_type == "inline":
            for child in children or []:
                visit(child)
            return
        # The number and boundaries of text tokens are parser implementation
        # details and can differ harmlessly after translation.
        if token_type == "text":
            return
        attrs = getattr(token, "attrs", None) or {}
        stable_attrs = tuple(sorted((str(key), str(value)) for key, value in attrs.items()))
        opaque_content = (
            getattr(token, "content", None)
            if token_type in {"code_inline", "code_block", "fence", "html_inline", "html_block"}
            else None
        )
        signature.append((
            token_type,
            getattr(token, "tag", ""),
            getattr(token, "nesting", 0),
            getattr(token, "markup", ""),
            getattr(token, "info", ""),
            stable_attrs,
            opaque_content,
        ))
        for child in children or []:
            visit(child)

    for item in parser.parse(text):
        visit(item)
    return tuple(signature)


def _mask_markdown_syntax(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Replace Markdown delimiters with exact-once, order-checked placeholders.

    Text between delimiters remains translatable. Reference-link identifiers and
    task-list checkbox tokens are preserved as a whole. The caller verifies both
    exact-once occurrence and source order before restoring the original tokens.
    """
    # Do not re-mask punctuation inside opaque placeholders created by
    # _mask_protected_spans (which may start with underscores on collisions).
    opaque_iter = iter(re.finditer(r"_*SKTETHEROPAQUE\d{5}END", text))
    current_opaque = next(opaque_iter, None)
    matches = []
    for match in MARKDOWN_SYNTAX.finditer(text):
        while current_opaque is not None and current_opaque.end() <= match.start():
            current_opaque = next(opaque_iter, None)
        if current_opaque is not None and current_opaque.start() <= match.start() < current_opaque.end():
            continue
        matches.append(match)
    if not matches:
        return text, []

    prefix = "SKTETHERSYNTAX"
    while prefix in text:
        prefix += "X"

    replacements: list[tuple[str, str]] = []
    output: list[str] = []
    cursor = 0
    for index, match in enumerate(matches):
        output.append(text[cursor:match.start()])
        marker = f"{prefix}{index:05d}END"
        original = match.group(0)
        replacements.append((marker, original))
        output.append(marker)
        cursor = match.end()
    output.append(text[cursor:])
    return "".join(output), replacements


def _mask_protected_spans(
    prose: str, extra_patterns: list[dict[str, str]] | None,
    explicit_tokens: list[str] | None,
) -> tuple[str, list[tuple[str, str]]]:
    # Collect matches independently, then resolve overlaps by earliest start and
    # longest span. Regex alternation is left-biased, so a single combined pattern
    # can accidentally protect only a prefix when configured identifiers overlap.
    if extra_patterns is not None and (
        not isinstance(extra_patterns, list) or any(not isinstance(item, dict) for item in extra_patterns)
    ):
        raise ValueError("Protected-token patterns must be a list of mappings")
    tokens = explicit_tokens or []
    if not isinstance(tokens, list) or any(not isinstance(token, str) for token in tokens):
        raise ValueError("Explicit protected tokens must be a list of strings")
    if len(extra_patterns or []) > MAX_POLICY_PATTERNS:
        raise ValueError(f"Protected-token policy exceeds {MAX_POLICY_PATTERNS} patterns")
    if len([token for token in tokens if token]) > MAX_EXPLICIT_TOKENS:
        raise ValueError(f"Protected-token policy exceeds {MAX_EXPLICIT_TOKENS} explicit tokens")
    if any(len(token) > MAX_EXPLICIT_TOKEN_CHARS for token in tokens if token):
        raise ValueError(f"Explicit protected tokens must be at most {MAX_EXPLICIT_TOKEN_CHARS} characters")
    patterns: list[re.Pattern[str]] = [re.compile(MASK_SPAN.pattern)]
    for item in extra_patterns or []:
        regex = item.get("regex")
        if not isinstance(regex, str):
            raise ValueError("Every protected-token policy entry needs a regex string")
        if len(regex) > MAX_POLICY_REGEX_CHARS:
            raise ValueError(f"Protected-token policy regex exceeds the {MAX_POLICY_REGEX_CHARS}-character limit")
        custom = validate_policy_regex(regex, max_chars=MAX_POLICY_REGEX_CHARS)
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
    for token in sorted((token for token in tokens if token), key=lambda value: (-len(value), value)):
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


class _TranslationBudgetPreflight:
    """Identity adapter that counts the exact masked JSON requests without networking."""

    name = "local-budget-preflight"
    remote = False

    def __init__(self) -> None:
        self.request_count = 0
        self.total_request_bytes = 0

    def translate(self, text: str, source_locale: str, target_locale: str) -> str:
        body = json.dumps({
            "text": text, "source_locale": source_locale, "target_locale": target_locale,
        }, ensure_ascii=False).encode("utf-8")
        if len(body) > MAX_TRANSLATION_REQUEST_BYTES:
            raise RuntimeError(
                f"Translation package has a single request exceeding the {MAX_TRANSLATION_REQUEST_BYTES}-byte limit; no provider request was sent"
            )
        if self.request_count + 1 > MAX_TRANSLATION_REQUESTS:
            raise RuntimeError(
                f"Translation package exceeds the {MAX_TRANSLATION_REQUESTS}-request safety limit; no provider request was sent"
            )
        if self.total_request_bytes + len(body) > MAX_TRANSLATION_TOTAL_REQUEST_BYTES:
            raise RuntimeError(
                f"Translation package exceeds the {MAX_TRANSLATION_TOTAL_REQUEST_BYTES}-byte aggregate request budget; no provider request was sent"
            )
        self.request_count += 1
        self.total_request_bytes += len(body)
        return text


def translate_package(
    source: str | Path, output: str | Path, adapter: TranslationAdapter,
    source_locale: str, target_locale: str,
    protected_patterns: list[dict[str, str]] | None = None,
    explicit_tokens: list[str] | None = None,
) -> tuple[dict[str, FileFingerprint], dict[str, FileFingerprint], int]:
    """Generate a candidate atomically; never mutate source or overwrite an existing output."""
    source_root = normalize_package_root(source)
    output_root = Path(os.path.abspath(Path(output).expanduser()))
    if output_root.is_symlink():
        raise ValueError("Candidate output must not be a symbolic link")
    resolved_output = output_root.resolve()
    if not source_root.is_dir():
        raise ValueError("Source package must be a directory")
    if output_root.name != source_root.name:
        raise ValueError(
            "Candidate directory basename must match the source skill package name; "
            "choose a separate parent directory with the same leaf name."
        )
    for candidate in (output_root, resolved_output):
        if (
            candidate == source_root
            or source_root in candidate.parents
            or candidate in source_root.parents
        ):
            raise ValueError("Source and output directories must be separate and non-overlapping")
    if output_root.exists():
        raise FileExistsError(f"Candidate output already exists: {output_root}")

    source_inventory, validation_findings, source_text = inspect_package(source_root)
    severe = [f for f in validation_findings if f.severity in ("high", "critical")]
    if severe:
        codes = ", ".join(sorted({f.code for f in severe}))
        raise ValueError(f"Source package has blocking validation findings: {codes}")
    before = package_fingerprint(source_inventory)

    # Preflight the complete translation workload with a no-network adapter. This
    # catches per-request, aggregate-byte, and call-count limits before the first
    # provider receives any portion of a large package.
    budget_probe = _TranslationBudgetPreflight()
    for rel, original_text in sorted(source_text.items()):
        if Path(rel).suffix.lower() not in ELIGIBLE_SUFFIXES:
            continue
        translate_markdown(
            original_text, budget_probe, source_locale, target_locale,
            extra_patterns=protected_patterns, explicit_tokens=explicit_tokens,
        )

    output_root.parent.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix=f".{output_root.name}.candidate-", dir=output_root.parent))
    temp_package = temp_root / output_root.name
    try:
        # Preserve a symlink that appears after the initial inventory instead of
        # dereferencing it while staging. Verify the staged bytes and metadata before
        # any translated content is written into the temporary package.
        shutil.copytree(source_root, temp_package, symlinks=True)
        copied_inventory, copied_findings, _copied_text = inspect_package(temp_package)
        copied_blocking = [f for f in copied_findings if f.severity in ("high", "critical")]
        if copied_blocking:
            codes = ", ".join(sorted({f.code for f in copied_blocking}))
            raise RuntimeError(f"Source package changed or became unsafe while staging: {codes}")
        if package_fingerprint(copied_inventory) != before:
            raise RuntimeError("Source package changed while staging; candidate discarded")

        translated_count = 0
        output_budget_adapter = _TranslationOutputBudgetAdapter(adapter)
        for rel, original_text in sorted(source_text.items()):
            if Path(rel).suffix.lower() not in ELIGIBLE_SUFFIXES:
                continue
            translated = translate_markdown(
                original_text, output_budget_adapter, source_locale, target_locale,
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
