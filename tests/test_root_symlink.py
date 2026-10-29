from __future__ import annotations

import os
from pathlib import Path

import pytest

from skilltether.analysis import inspect_package
from skilltether.cli import main
from skilltether.compare import compare_packages
from skilltether.models import InvariantManifest
from skilltether.translation import IdentityAdapter, translate_package


def make_package(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "SKILL.md").write_text(
        f"---\nname: {root.name}\ndescription: A root-symlink test skill.\n---\n\n"
        "# Instructions\n\nKeep the package local.\n",
        encoding="utf-8",
    )
    return root


def test_package_root_symlink_is_rejected_across_entry_points(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    if not hasattr(os, "symlink"):
        pytest.skip("symlink creation is unavailable")
    package = make_package(tmp_path / "real" / "sample-skill")
    alias = tmp_path / "sample-skill-alias"
    try:
        alias.symlink_to(package, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is not permitted")

    expected = "Package root must not be a symbolic link"
    with pytest.raises(ValueError, match="symbolic link"):
        inspect_package(alias)
    with pytest.raises(ValueError, match="symbolic link"):
        compare_packages(alias, package, InvariantManifest(source_locale="en"))
    with pytest.raises(ValueError, match="symbolic link"):
        translate_package(
            alias, tmp_path / "candidate" / "sample-skill", IdentityAdapter(), "en", "fr",
        )

    result = main(["validate", str(alias)])
    assert result == 2
    assert expected in capsys.readouterr().err
