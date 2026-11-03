from __future__ import annotations

from pathlib import Path

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


def test_non_string_frontmatter_key_is_reported_without_crashing(tmp_path: Path) -> None:
    package = make_skill(tmp_path, "7: unexpected\n")

    _inventory, findings, _texts = inspect_package(package)

    invalid_keys = [finding for finding in findings if finding.code == "FRONTMATTER_KEY_INVALID"]
    assert len(invalid_keys) == 1
    assert invalid_keys[0].severity == "high"
    assert not [finding for finding in findings if finding.code == "FRONTMATTER_UNKNOWN_FIELDS"]
