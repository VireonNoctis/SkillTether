from __future__ import annotations

from pathlib import Path

import pytest

from skilltether.analysis import inspect_package


def make_skill(tmp_path: Path, extra_frontmatter: str = "") -> Path:
    package = tmp_path / "sample-skill"
    package.mkdir()
    (package / "SKILL.md").write_text(
        "---\n"
        "name: sample-skill\n"
        "description: A frontmatter edge-case fixture.\n"
        f"{extra_frontmatter}"
        "---\n\n"
        "# Instructions\n\n"
        "Follow the documented workflow.\n",
        encoding="utf-8",
    )
    return package


def test_null_compatibility_is_invalid_when_optional_field_is_present(tmp_path: Path) -> None:
    package = make_skill(tmp_path, "compatibility: null\n")

    _inventory, findings, _texts = inspect_package(package)

    compatibility = [finding for finding in findings if finding.code == "COMPATIBILITY_INVALID"]
    assert len(compatibility) == 1
    assert compatibility[0].severity == "high"


def test_omitted_compatibility_remains_valid(tmp_path: Path) -> None:
    package = make_skill(tmp_path)

    _inventory, findings, _texts = inspect_package(package)

    assert not [finding for finding in findings if finding.code == "COMPATIBILITY_INVALID"]


@pytest.mark.parametrize("skill_name", ["café-tool", "δοκιμή-εργαλείο", "资料-处理"])
def test_unicode_lowercase_skill_names_are_accepted(tmp_path: Path, skill_name: str) -> None:
    package = tmp_path / skill_name
    package.mkdir()
    (package / "SKILL.md").write_text(
        f"---\nname: {skill_name}\ndescription: A Unicode skill name fixture.\n---\n\n"
        "# Instructions\n\nFollow the documented workflow.\n",
        encoding="utf-8",
    )

    _inventory, findings, _texts = inspect_package(package)

    assert not [finding for finding in findings if finding.code in {
        "SKILL_NAME_INVALID", "SKILL_NAME_DIRECTORY_MISMATCH",
    }]


def test_nfkc_equivalent_unicode_directory_name_is_compared_without_rewriting(
    tmp_path: Path,
) -> None:
    directory_name = "cafe\u0301-tool"
    metadata_name = "café-tool"
    package = tmp_path / directory_name
    package.mkdir()
    skill_md = (
        f"---\nname: {metadata_name}\ndescription: Canonical Unicode name fixture.\n---\n\n"
        "# Instructions\n\nFollow the documented workflow.\n"
    )
    (package / "SKILL.md").write_text(skill_md, encoding="utf-8")

    _inventory, findings, _texts = inspect_package(package)

    assert (package / "SKILL.md").read_text(encoding="utf-8") == skill_md
    assert not [finding for finding in findings if finding.code in {
        "SKILL_NAME_INVALID", "SKILL_NAME_DIRECTORY_MISMATCH",
    }]


def test_uppercase_unicode_skill_name_remains_invalid(tmp_path: Path) -> None:
    package = tmp_path / "Café-tool"
    package.mkdir()
    (package / "SKILL.md").write_text(
        "---\nname: Café-tool\ndescription: Uppercase Unicode name fixture.\n---\n\n"
        "# Instructions\n\nFollow the documented workflow.\n",
        encoding="utf-8",
    )

    _inventory, findings, _texts = inspect_package(package)

    assert any(finding.code == "SKILL_NAME_INVALID" for finding in findings)


def test_non_string_frontmatter_key_is_reported_without_crashing(tmp_path: Path) -> None:
    package = make_skill(tmp_path, "7: unexpected\n")

    _inventory, findings, _texts = inspect_package(package)

    invalid_keys = [finding for finding in findings if finding.code == "FRONTMATTER_KEY_INVALID"]
    assert len(invalid_keys) == 1
    assert invalid_keys[0].severity == "high"
    assert not [finding for finding in findings if finding.code == "FRONTMATTER_UNKNOWN_FIELDS"]
