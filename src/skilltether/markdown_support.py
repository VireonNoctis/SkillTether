"""Shared, explicit Markdown dialect configuration and safe structural helpers.

Supported parser extensions are CommonMark plus the GFM-like preset, footnotes,
and definition lists. MDX JavaScript/JSX is not parsed as Markdown; callers can
surface explicit unsupported-syntax findings instead of silently treating it as
ordinary prose.
"""
from __future__ import annotations

import html
import re
import unicodedata
from collections.abc import Iterable, Iterator
from typing import Any

from markdown_it import MarkdownIt
from mdit_py_plugins.deflist import deflist_plugin
from mdit_py_plugins.footnote import footnote_plugin


def create_markdown_parser() -> MarkdownIt:
    """Create the single parser configuration used by inspection and translation."""
    parser = MarkdownIt("gfm-like2", {"html": False})
    parser.use(footnote_plugin)
    parser.use(deflist_plugin)
    return parser


def walk_tokens(tokens: Iterable[Any]) -> Iterator[Any]:
    """Yield a token tree depth-first, including nested inline children."""
    for token in tokens:
        yield token
        children = getattr(token, "children", None)
        if children:
            yield from walk_tokens(children)


def markdown_link_targets(text: str) -> list[tuple[str, str]]:
    """Return parsed link/image destinations, including nested/list/table content."""
    result: list[tuple[str, str]] = []
    for token in walk_tokens(create_markdown_parser().parse(text)):
        token_type = getattr(token, "type", "")
        if token_type not in {"link_open", "image"}:
            continue
        attrs = getattr(token, "attrs", None) or {}
        value = attrs.get("href") if token_type == "link_open" else attrs.get("src")
        if isinstance(value, str) and value:
            result.append((token_type, value))
    return result


def _inline_plain_text(children: Iterable[Any] | None) -> str:
    chunks: list[str] = []
    for token in children or []:
        token_type = getattr(token, "type", "")
        if token_type in {"text", "code_inline"}:
            chunks.append(getattr(token, "content", ""))
        elif token_type == "image":
            chunks.append(getattr(token, "content", ""))
        elif token_type in {"softbreak", "hardbreak"}:
            chunks.append(" ")
        elif token_type in {"html_inline", "html_block"}:
            continue
        else:
            nested = getattr(token, "children", None)
            if nested:
                chunks.append(_inline_plain_text(nested))
    return html.unescape("".join(chunks))


def _heading_slug(value: str) -> str:
    value = unicodedata.normalize("NFC", html.unescape(value)).casefold()
    value = re.sub(r"<[^>]*>", "", value)
    kept = "".join(
        character
        for character in value
        if character.isalnum() or character in {"-", "_", " ", "\t"}
    )
    return re.sub(r"\s+", "-", kept.strip())


def markdown_heading_anchors(text: str) -> set[str]:
    """Return GitHub-style heading slugs, including duplicate-heading suffixes."""
    tokens = create_markdown_parser().parse(text)
    seen: dict[str, int] = {}
    anchors: set[str] = set()
    for index, token in enumerate(tokens[:-1]):
        if getattr(token, "type", "") != "heading_open":
            continue
        inline = tokens[index + 1]
        if getattr(inline, "type", "") != "inline":
            continue
        slug = _heading_slug(_inline_plain_text(getattr(inline, "children", None)))
        if not slug:
            continue
        duplicate = seen.get(slug, 0)
        seen[slug] = duplicate + 1
        anchors.add(slug if duplicate == 0 else f"{slug}-{duplicate}")
    return anchors


_FENCE = re.compile(r"^\s{0,3}(\x60{3,}|~{3,})")
_MDX_IMPORT_EXPORT = re.compile(
    r"^\s*(?:import\s+(?:[\w*$,\s{}]+\s+from\s+|['\"])|"
    r"export\s+(?:default|const|function|class|let|var)\b)"
)
_MDX_JSX = re.compile(r"</?[A-Z][A-Za-z0-9_.:-]*(?:\s|/?>)")
_MDX_EXPRESSION = re.compile(
    r"\{\s*[A-Za-z_$][A-Za-z0-9_$]*(?:\s*(?:\.|\(|\[|===|!==|=>|\?|\+|-|\*|/|,))"
)


def mdx_syntax_locations(text: str) -> list[tuple[int, str]]:
    """Find obvious MDX-only constructs outside fenced/indented code examples.

    This is a conservative unsupported-syntax detector, not a complete MDX parser.
    """
    lines = text.splitlines()
    frontmatter_open = bool(lines and lines[0].strip() == "---")
    frontmatter_closed = not frontmatter_open
    fence_marker: str | None = None
    fence_length = 0
    findings: list[tuple[int, str]] = []
    for line_no, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not frontmatter_closed:
            if line_no > 1 and stripped == "---":
                frontmatter_closed = True
            continue
        fence = _FENCE.match(line)
        if fence_marker is not None:
            if (
                fence
                and fence.group(1)[0] == fence_marker
                and len(fence.group(1)) >= fence_length
                and not line[fence.end():].strip()
            ):
                fence_marker = None
                fence_length = 0
            continue
        if fence:
            fence_marker = fence.group(1)[0]
            fence_length = len(fence.group(1))
            continue
        if line.startswith("    ") or line.startswith("\t") or not stripped:
            continue
        if _MDX_IMPORT_EXPORT.search(line):
            findings.append((line_no, "MDX module import/export syntax"))
        elif _MDX_JSX.search(line):
            findings.append((line_no, "JSX component syntax"))
        elif _MDX_EXPRESSION.search(line):
            findings.append((line_no, "embedded JavaScript expression syntax"))
    return findings
