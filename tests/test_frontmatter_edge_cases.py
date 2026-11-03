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


def test_crlf_frontmatter_is_accepted_without_normalizing_source(tmp_path: Path) -> None:
    package = tmp_path / "crlf-frontmatter"
    package.mkdir()
    source = Path("tests/fixtures/crlf-frontmatter/SKILL.md").read_bytes()
    path = package / "SKILL.md"
    path.write_bytes(source)

    _inventory, findings, _texts = inspect_package(package)

    assert source.startswith(b"---\r\n")
    assert b"\r\n" in source
    assert b"\n" not in source.replace(b"\r\n", b"")
    assert path.read_bytes() == source
    assert not [finding for finding in findings if finding.code == "FRONTMATTER_INVALID"]


def test_utf8_bom_before_frontmatter_is_accepted_without_rewriting_source(tmp_path: Path) -> None:
    package = tmp_path / "utf8-bom"
    package.mkdir()
    fixture = Path("tests/fixtures/utf8-bom/SKILL.md")
    source = fixture.read_bytes()
    path = package / "SKILL.md"
    path.write_bytes(source)

    _inventory, findings, _texts = inspect_package(package)

    assert source.startswith(b"\xef\xbb\xbf---")
    assert path.read_bytes() == source
    assert not [finding for finding in findings if finding.code == "FRONTMATTER_INVALID"]


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


def test_nfkc_compatibility_form_name_matches_ascii_directory_without_rewriting(
    tmp_path: Path,
) -> None:
    package = tmp_path / "skill-tool"
    package.mkdir()
    path = package / "SKILL.md"
    original = Path("tests/fixtures/skill-tool/SKILL.md").read_text(encoding="utf-8")
    path.write_text(original, encoding="utf-8")

    _inventory, findings, _texts = inspect_package(package)

    assert path.read_text(encoding="utf-8") == original
    assert not [finding for finding in findings if finding.code in {
        "SKILL_NAME_INVALID", "SKILL_NAME_DIRECTORY_MISMATCH",
    }]


def test_unicode_skill_name_limit_counts_characters_not_utf8_bytes(tmp_path: Path) -> None:
    for length, expected_invalid in ((64, False), (65, True)):
        skill_name = "é" * length
        package = tmp_path / skill_name
        package.mkdir()
        (package / "SKILL.md").write_text(
            f"---\nname: {skill_name}\ndescription: Unicode length fixture.\n---\n\n"
            "# Instructions\n\nFollow the documented workflow.\n",
            encoding="utf-8",
        )

        _inventory, findings, _texts = inspect_package(package)
        invalid = any(finding.code == "SKILL_NAME_INVALID" for finding in findings)
        assert invalid is expected_invalid


def test_skill_name_comparison_trims_surrounding_space_without_rewriting_source(
    tmp_path: Path,
) -> None:
    package = tmp_path / "café-tool"
    package.mkdir()
    source = (
        '---\nname: " café-tool "\ndescription: Whitespace comparison fixture.\n---\n\n'
        "# Instructions\n\nFollow the documented workflow.\n"
    )
    path = package / "SKILL.md"
    path.write_text(source, encoding="utf-8")

    _inventory, findings, _texts = inspect_package(package)

    assert not [finding for finding in findings if finding.code in {
        "SKILL_NAME_INVALID", "SKILL_NAME_DIRECTORY_MISMATCH",
    }]
    assert path.read_text(encoding="utf-8") == source


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


@pytest.mark.parametrize(
    "skill_name",
    ["-leading", "trailing-", "double--hyphen", "Uppercase", "with_underscore", "contains.dot"],
)
def test_invalid_skill_name_separators_and_characters_are_rejected(
    tmp_path: Path, skill_name: str,
) -> None:
    package = tmp_path / skill_name
    package.mkdir()
    (package / "SKILL.md").write_text(
        f"---\nname: {skill_name}\ndescription: Invalid name fixture.\n---\n\n"
        "# Instructions\n\nFollow the documented workflow.\n",
        encoding="utf-8",
    )

    _inventory, findings, _texts = inspect_package(package)

    assert any(finding.code == "SKILL_NAME_INVALID" for finding in findings)


def test_skill_name_over_64_characters_is_rejected(tmp_path: Path) -> None:
    skill_name = "a" * 65
    package = tmp_path / skill_name
    package.mkdir()
    (package / "SKILL.md").write_text(
        f"---\nname: {skill_name}\ndescription: Long name fixture.\n---\n\n"
        "# Instructions\n\nFollow the documented workflow.\n",
        encoding="utf-8",
    )

    _inventory, findings, _texts = inspect_package(package)

    assert any(finding.code == "SKILL_NAME_INVALID" for finding in findings)


def test_specification_maximum_frontmatter_boundaries_are_accepted() -> None:
    from skilltether.analysis import validate_skill_markdown

    skill_name = "a" * 64
    text = (
        f"---\nname: {skill_name}\n"
        f"description: {'d' * 1024}\n"
        f"compatibility: {'c' * 500}\n"
        "---\n\n"
        "# Instructions\n\nFollow the documented workflow.\n"
    )

    findings = validate_skill_markdown(Path(skill_name), text)

    assert not {
        "SKILL_NAME_INVALID", "DESCRIPTION_TOO_LONG", "COMPATIBILITY_INVALID",
    } & {finding.code for finding in findings}


def test_description_over_1024_characters_is_rejected() -> None:
    from skilltether.analysis import validate_skill_markdown

    text = (
        "---\nname: sample-skill\n"
        f"description: {'d' * 1025}\n"
        "---\n\n"
        "# Instructions\n\nFollow the documented workflow.\n"
    )

    findings = validate_skill_markdown(Path("sample-skill"), text)

    assert any(finding.code == "DESCRIPTION_TOO_LONG" for finding in findings)


def test_reference_boundary_fixtures_exercise_limits_and_invalid_name() -> None:
    from skilltether.analysis import validate_skill_markdown

    valid_text = Path("tests/fixtures/" + "a" * 64 + "/SKILL.md").read_text(encoding="utf-8")
    invalid_text = Path("tests/fixtures/bad--name/SKILL.md").read_text(encoding="utf-8")

    valid_findings = validate_skill_markdown(Path("a" * 64), valid_text)
    invalid_findings = validate_skill_markdown(Path("bad--name"), invalid_text)

    assert not {
        "SKILL_NAME_INVALID", "DESCRIPTION_TOO_LONG", "COMPATIBILITY_INVALID",
    } & {finding.code for finding in valid_findings}
    assert {
        "SKILL_NAME_INVALID", "COMPATIBILITY_INVALID",
    } <= {finding.code for finding in invalid_findings}


def test_unknown_extension_fixture_is_warning_not_blocking() -> None:
    package = Path("tests/fixtures/extension-skill")
    _inventory, findings, _texts = inspect_package(package)

    extension = next(
        finding for finding in findings if finding.code == "FRONTMATTER_UNKNOWN_FIELDS"
    )
    assert extension.severity == "low"
    assert not [finding for finding in findings if finding.severity in ("high", "critical")]

    from skilltether.cli import main

    assert main(["validate", str(package)]) == 0


def test_numeric_metadata_keys_and_values_are_rejected_without_coercion(
    tmp_path: Path,
) -> None:
    package = tmp_path / "numeric-metadata-scalar"
    package.mkdir()
    fixture = Path("tests/fixtures/numeric-metadata-scalar/SKILL.md")
    original = fixture.read_text(encoding="utf-8")
    path = package / "SKILL.md"
    path.write_text(original, encoding="utf-8")

    _inventory, findings, _texts = inspect_package(package)

    metadata = [finding for finding in findings if finding.code == "METADATA_INVALID"]
    assert len(metadata) == 1
    assert metadata[0].severity == "high"
    assert path.read_text(encoding="utf-8") == original


def test_non_string_frontmatter_key_is_reported_without_crashing(tmp_path: Path) -> None:
    package = make_skill(tmp_path, "7: unexpected\n")

    _inventory, findings, _texts = inspect_package(package)

    invalid_keys = [finding for finding in findings if finding.code == "FRONTMATTER_KEY_INVALID"]
    assert len(invalid_keys) == 1
    assert invalid_keys[0].severity == "high"
    assert not [finding for finding in findings if finding.code == "FRONTMATTER_UNKNOWN_FIELDS"]
