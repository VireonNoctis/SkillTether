from __future__ import annotations

from pathlib import Path

import pytest

from skilltether.analysis import inspect_package, path_portability_issue, path_portability_key


def make_skill(path: Path) -> Path:
    path.mkdir(parents=True)
    (path / "SKILL.md").write_text(
        f"---\nname: {path.name}\ndescription: A path portability test.\n---\n\n# Instructions\nFollow the workflow.\n",
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize("path", ["CON.txt", "folder/AUX", "bad:name.md", "trailing.", "trailing "])
def test_windows_nonportable_names_are_detected(path: str) -> None:
    assert path_portability_issue(path) is not None


@pytest.mark.parametrize("path", ["normal/file.md", "references/guide-v2.md", "assets/logo.svg"])
def test_portable_names_are_accepted(path: str) -> None:
    assert path_portability_issue(path) is None


def test_unicode_path_normalization_key_is_canonical() -> None:
    assert path_portability_key("CAFÉ.md") == path_portability_key("cafe\u0301.md")


def test_case_colliding_package_files_are_reported_when_host_supports_them(tmp_path: Path) -> None:
    package = make_skill(tmp_path / "sample-skill")
    (package / "Guide.md").write_text("# Upper\n", encoding="utf-8")
    try:
        (package / "guide.md").write_text("# Lower\n", encoding="utf-8")
    except OSError:
        pytest.skip("Filesystem does not permit case-distinct sibling paths")
    inventory, findings, _texts = inspect_package(package)
    if len([name for name in inventory if name.casefold() == "guide.md"]) < 2:
        pytest.skip("Filesystem aliases case-distinct names")
    collision = next(f for f in findings if f.code == "PACKAGE_PATH_NORMALIZATION_COLLISION")
    assert collision.analysis_method == "deterministic"
    assert collision.uncertainty == "none"
