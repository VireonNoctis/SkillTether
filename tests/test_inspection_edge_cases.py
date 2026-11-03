from __future__ import annotations

import os
from pathlib import Path

import pytest

import skilltether.analysis as analysis


def make_skill(path: Path) -> Path:
    path.mkdir(parents=True)
    (path / "SKILL.md").write_text(
        f"---\nname: {path.name}\ndescription: Inspection boundary fixture.\n---\n\n"
        "# Instructions\n\nFollow the documented workflow.\n",
        encoding="utf-8",
    )
    return path


def test_regular_file_cannot_be_used_as_package_root(tmp_path: Path) -> None:
    root = tmp_path / "not-a-directory"
    root.write_text("not a package", encoding="utf-8")

    with pytest.raises(ValueError, match="not a directory"):
        analysis.inspect_package(root)


def test_symlinked_directory_is_reported_and_not_traversed(tmp_path: Path) -> None:
    package = make_skill(tmp_path / "sample-skill")
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "do-not-inventory.md"
    secret.write_text("External content must not be followed.", encoding="utf-8")
    alias = package / "references"
    try:
        alias.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlink creation is not permitted")

    inventory, findings, _texts = analysis.inspect_package(package)

    assert "references/do-not-inventory.md" not in inventory
    assert any(
        finding.code == "SYMLINK_NOT_ALLOWED" and finding.path == "references"
        for finding in findings
    )
    assert secret.read_text(encoding="utf-8") == "External content must not be followed."


def test_package_file_count_limit_is_enforced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = make_skill(tmp_path / "sample-skill")
    (package / "extra.txt").write_text("extra", encoding="utf-8")
    monkeypatch.setattr(analysis, "MAX_PACKAGE_FILES", 1)

    with pytest.raises(ValueError, match="file safety limit"):
        analysis.inspect_package(package)
