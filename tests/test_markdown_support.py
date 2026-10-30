from __future__ import annotations

from pathlib import Path

from skilltether.markdown_support import (
    create_markdown_parser,
    markdown_heading_anchors,
    markdown_link_targets,
    mdx_syntax_locations,
    walk_tokens,
)
from skilltether.translation import translate_markdown


class ReplaceAdapter:
    name = "replace-test"
    remote = False

    def translate(self, text: str, source_locale: str, target_locale: str) -> str:
        return (
            text.replace("an old note", "une ancienne note")
            .replace("Keep this notice", "Conservez cet avis")
            .replace("a definition", "une définition")
        )


def test_extended_parser_handles_gfm_alerts_tables_tasks_and_footnotes() -> None:
    text = """# Guide

> [!WARNING] Keep this notice.

| Item | Reference |
| --- | --- |
| One | [guide](references/guide.md) |

- [x] Done
- [ ] Pending

Read this note[^memo].

[^memo]: an old note.
"""
    types = [token.type for token in walk_tokens(create_markdown_parser().parse(text))]
    assert "table_open" in types
    assert "footnote_ref" in types
    assert "footnote_block_open" in types
    targets = markdown_link_targets(text)
    assert ("link_open", "references/guide.md") in targets


def test_heading_anchor_slugs_include_unicode_and_duplicate_suffixes() -> None:
    anchors = markdown_heading_anchors(
        "## Setup\n\n## Setup\n\n## Über Café\n\n## **Nested title**\n"
    )
    assert {"setup", "setup-1", "über-café", "nested-title"} <= anchors


def test_mdx_syntax_is_detected_but_code_examples_are_ignored() -> None:
    text = """---
name: sample-skill
description: Test package.
---

~~~mdx
import Demo from './Demo.jsx'
<Demo />
{user.name}
~~~

import Alert from './Alert.jsx'

<Alert kind="warning" />

{user.name}
"""
    locations = mdx_syntax_locations(text)
    reasons = [reason for _line, reason in locations]
    assert reasons == [
        "MDX module import/export syntax",
        "JSX component syntax",
        "embedded JavaScript expression syntax",
    ]
    assert all(line >= 10 for line, _reason in locations)


def test_translation_preserves_footnotes_alerts_and_definition_lists() -> None:
    text = """# Guide

> [!WARNING] Keep this notice.

Term

: a definition.

Read this note[^memo].

[^memo]: an old note.
"""
    translated = translate_markdown(text, ReplaceAdapter(), "en", "fr")
    assert "> [!WARNING] Conservez cet avis." in translated
    assert ": une définition." in translated
    assert "Read this note[^memo]." in translated
    assert "[^memo]: une ancienne note." in translated


def test_parser_structure_rejects_added_footnote_or_table_structure() -> None:
    from skilltether.translation import _markdown_structure_signature

    source = "# Guide\n\nThis is a simple paragraph.\n"
    changed = "# Guide\n\nThis is a simple paragraph.[^new]\n\n[^new]: Added note.\n"
    assert _markdown_structure_signature(source) != _markdown_structure_signature(changed)
