from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
import yaml

from skilltether.cli import main
from skilltether.compare import compare_packages
from skilltether.models import InvariantManifest
from skilltether.report import write_json_report
from skilltether.translation import IdentityAdapter, translate_package


def make_package(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "SKILL.md").write_text(
        f"---\nname: {root.name}\ndescription: A race-test skill.\n---\n\n"
        "# Instructions\n\nKeep the package local.\n",
        encoding="utf-8",
    )
    return root


def replace_with_symlink(path: Path, destination: Path) -> None:
    if not hasattr(os, "symlink"):
        pytest.skip("symlink creation is unavailable")
    path.unlink()
    try:
        path.symlink_to(destination)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is not permitted")


def test_translation_staging_preserves_raced_symlink_and_fails_before_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = make_package(tmp_path / "source" / "sample-skill")
    output = tmp_path / "candidate" / "sample-skill"
    external = tmp_path / "outside.md"
    external.write_text("outside content must never be overwritten", encoding="utf-8")
    real_copytree = shutil.copytree
    injected = False

    def race_before_copy(src, dst, *args, **kwargs):
        nonlocal injected
        if Path(src).resolve() == source.resolve() and not injected:
            replace_with_symlink(source / "SKILL.md", external)
            injected = True
        assert kwargs.get("symlinks") is True, "staging must not dereference links"
        return real_copytree(src, dst, *args, **kwargs)

    monkeypatch.setattr("skilltether.translation.shutil.copytree", race_before_copy)

    with pytest.raises(RuntimeError, match="changed or became unsafe while staging"):
        translate_package(source, output, IdentityAdapter(), "en", "fr")

    assert injected
    assert not output.exists()
    assert external.read_text(encoding="utf-8") == "outside content must never be overwritten"


def test_approval_staging_preserves_raced_symlink_and_never_exports_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    source = make_package(tmp_path / "source" / "sample-skill")
    target = make_package(tmp_path / "candidate" / "sample-skill")
    output = tmp_path / "approved" / "sample-skill"
    external = tmp_path / "outside.md"
    external.write_text("external approval target remains untouched", encoding="utf-8")
    manifest = InvariantManifest(
        source_locale="en", target_locale="fr",
        manifest_reviewed=True, manifest_reviewer="test-reviewer",
    )
    manifest_path = tmp_path / "invariants.yaml"
    manifest_path.write_text(
        yaml.safe_dump(manifest.model_dump(mode="json", exclude_none=True), sort_keys=False),
        encoding="utf-8",
    )
    report_path = tmp_path / "report.json"
    report = compare_packages(source, target, manifest, target_locale="fr")
    assert report.structural_status == "pass"
    write_json_report(report, report_path)

    real_copytree = shutil.copytree
    injected = False

    def race_before_copy(src, dst, *args, **kwargs):
        nonlocal injected
        if Path(src).resolve() == target.resolve() and not injected:
            replace_with_symlink(target / "SKILL.md", external)
            injected = True
        assert kwargs.get("symlinks") is True, "approval staging must not dereference links"
        return real_copytree(src, dst, *args, **kwargs)

    monkeypatch.setattr("skilltether.cli.shutil.copytree", race_before_copy)
    result = main([
        "approve", str(source), str(target),
        "--report", str(report_path), "--output", str(output),
        "--invariants", str(manifest_path),
    ])

    assert result == 2
    assert "Approved output fingerprint mismatch" in capsys.readouterr().err
    assert injected
    assert not output.exists()
    assert external.read_text(encoding="utf-8") == "external approval target remains untouched"
