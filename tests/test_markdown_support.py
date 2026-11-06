from __future__ import annotations

from pathlib import Path

from skilltether.markdown_support import (
    create_markdown_parser,
    markdown_heading_anchors,
    markdown_inline_line_numbers,
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


def test_heading_anchor_suffixes_do_not_collide_with_literal_headings() -> None:
    anchors = markdown_heading_anchors(
        "# Setup\n\n# Setup\n\n# Setup-1\n\n# Setup\n\n# Setup-1\n"
    )

    assert anchors == {"setup", "setup-1", "setup-1-1", "setup-2", "setup-1-2"}


def test_crlf_frontmatter_is_opaque_to_translation_and_preserves_line_endings() -> None:
    source = (
        "---\r\n"
        "name: sample-skill\r\n"
        'description: "Keep this notice in metadata."\r\n'
        "---\r\n"
        "Keep this notice in the body.\r\n"
    )

    translated = translate_markdown(source, ReplaceAdapter(), "en", "fr")

    assert 'description: "Keep this notice in metadata."' in translated
    assert "Conservez cet avis in the body." in translated
    assert translated.count("\r\n") == source.count("\r\n")
    assert translated.replace("\r\n", "").find("\n") == -1


def test_bom_frontmatter_is_opaque_to_translation_and_mdx_detection() -> None:
    source = (
        "\ufeff---\n"
        "name: sample-skill\n"
        'description: "{user.name}"\n'
        "---\n\n"
        "Keep this notice in the body.\n"
    )

    translated = translate_markdown(source, ReplaceAdapter(), "en", "fr")

    assert translated.startswith("\ufeff---\n")
    assert 'description: "{user.name}"' in translated
    assert "Conservez cet avis in the body." in translated

    mdx = (
        "\ufeff---\n"
        "name: sample-skill\n"
        'description: "{user.name}"\n'
        "---\n"
        "import RealComponent from './RealComponent.jsx'\n"
    )
    locations = mdx_syntax_locations(mdx)

    assert locations == [(5, "MDX module import/export syntax")]


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


def test_markdown_ast_maps_nested_container_prose_but_not_code_or_frontmatter() -> None:
    source = (
        "\\ufeff---\\n"
        "name: sample-skill\\n"
        'description: "Do not translate this metadata."\\n'
        "---\\n"
        "> - Keep the quoted item safe.\\n"
        ">   - Keep the nested item safe.\\n"
        "- Keep the parent item safe.\\n"
        "  - Keep the child item safe.\\n"
        "\\n"
        "~~~text\\n"
        "Keep this code unchanged.\\n"
        "~~~\\n"
    )

    mapped = markdown_inline_line_numbers(source)

    assert {5, 6, 7, 8} <= mapped
    assert 1 not in mapped
    assert 3 not in mapped
    assert 11 not in mapped


def test_nested_blockquote_and_list_prose_is_translated_without_changing_containers() -> None:
    class NestedAdapter:
        name = "nested-adapter"
        remote = False

        def translate(self, text: str, source_locale: str, target_locale: str) -> str:
            return (
                text.replace("Keep the quoted item safe.", "Gardez l'élément cité en sécurité.")
                .replace("Keep the nested item safe.", "Gardez l'élément imbriqué en sécurité.")
                .replace("Keep the parent item safe.", "Gardez l'élément parent en sécurité.")
                .replace("Keep the child item safe.", "Gardez l'élément enfant en sécurité.")
            )

    source = (
        "> - Keep the quoted item safe.\\n"
        ">   - Keep the nested item safe.\\n"
        "- Keep the parent item safe.\\n"
        "  - Keep the child item safe.\\n"
    )

    translated = translate_markdown(source, NestedAdapter(), "en", "fr")

    assert translated.startswith(
        "> - Gardez l'élément cité en sécurité.\\n"
        ">   - Gardez l'élément imbriqué en sécurité.\\n"
    )
    assert "- Gardez l'élément parent en sécurité." in translated
    assert "  - Gardez l'élément enfant en sécurité." in translated


def test_mdx_syntax_fails_closed_in_direct_markdown_translation() -> None:
    import pytest

    source = "import Panel from './Panel.jsx'\\n\\n<Panel />\\n"
    with pytest.raises(RuntimeError, match="MDX-only syntax is not supported"):
        translate_markdown(source, ReplaceAdapter(), "en", "fr")


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



def test_mdx_package_resource_is_flagged_without_execution(tmp_path: Path) -> None:
    from skilltether.analysis import inspect_package

    package = tmp_path / "sample-skill"
    package.mkdir()
    (package / "SKILL.md").write_text(
        "---\nname: sample-skill\ndescription: A package with an MDX reference.\n---\n\n"
        "See [the interactive panel](references/panel.mdx).\n",
        encoding="utf-8",
    )
    references = package / "references"
    references.mkdir()
    (references / "panel.mdx").write_text(
        "import Panel from './Panel.jsx'\n\n<Panel />\n",
        encoding="utf-8",
    )

    _inventory, findings, _texts = inspect_package(package)
    mdx_finding = next(f for f in findings if f.code == "MDX_SYNTAX_UNSUPPORTED")
    assert mdx_finding.path == "references/panel.mdx"
    assert mdx_finding.severity == "high"
    assert mdx_finding.requires_review is True
