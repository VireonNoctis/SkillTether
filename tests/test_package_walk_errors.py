from __future__ import annotations

from pathlib import Path

import pytest

import skilltether.analysis as analysis


def test_directory_enumeration_error_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = tmp_path / "sample-skill"
    package.mkdir()
    (package / "SKILL.md").write_text(
        "---\nname: sample-skill\ndescription: Scan error fixture.\n---\n\n"
        "# Instructions\n\nFollow the workflow.\n",
        encoding="utf-8",
    )

    def walk_with_inaccessible_subtree(root, *, followlinks, onerror):
        assert Path(root) == package
        assert followlinks is False
        assert callable(onerror)
        onerror(PermissionError("synthetic directory enumeration denial"))
        return iter(())

    monkeypatch.setattr(analysis.os, "walk", walk_with_inaccessible_subtree)

    with pytest.raises(ValueError, match="incomplete package inventory"):
        analysis.inspect_package(package)
