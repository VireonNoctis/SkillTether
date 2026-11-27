from __future__ import annotations

from pathlib import Path

import json
import pytest
import yaml

from skilltether import cli as cli_module
from skilltether.cli import main


def make_skill(path: Path, body: str = "Use the documented workflow.") -> Path:
    path.mkdir(parents=True)
    (path / "SKILL.md").write_text(
        f"---\nname: {path.name}\ndescription: A CLI boundary fixture.\n---\n\n"
        f"# Instructions\n\n{body}\n",
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize("bom", ["", "\ufeff"])
def test_manifest_suggestions_ignore_frontmatter_instruction_like_metadata(
    tmp_path: Path, bom: str,
) -> None:
    package = tmp_path / ("bom-skill" if bom else "plain-skill")
    package.mkdir()
    (package / "SKILL.md").write_text(
        bom
        + "---\n"
        + f"name: {package.name}\n"
        + 'description: "You must never overwrite the source package."\n'
        + 'compatibility: "Keep at most 3 backup copies."\n'
        + "---\n\n"
        + "# Instructions\n\n"
        + "This paragraph describes the package contents.\n",
        encoding="utf-8",
    )
    output = tmp_path / "review" / f"{package.name}.yaml"

    status = main([
        "init-manifest", str(package), "--out", str(output),
        "--source-locale", "en", "--target-locale", "fr",
    ])

    assert status == 0
    payload = yaml.safe_load(output.read_text(encoding="utf-8"))
    assert payload["invariants"] == []
    assert payload["manifest_reviewed"] is False


def test_manifest_generation_refuses_malformed_frontmatter(
    tmp_path: Path, capsys,
) -> None:
    package = tmp_path / "broken-skill"
    package.mkdir()
    (package / "SKILL.md").write_text(
        "---\nname: broken-skill\ndescription: A broken package.\n\n"
        "You must preserve this instruction.\n",
        encoding="utf-8",
    )
    output = tmp_path / "review" / "broken.yaml"

    status = main([
        "init-manifest", str(package), "--out", str(output),
        "--source-locale", "en",
    ])

    assert status == 2
    assert "malformed SKILL.md frontmatter" in capsys.readouterr().err
    assert not output.exists()


def test_unknown_language_writes_empty_unreviewed_manifest(
    tmp_path: Path, capsys,
) -> None:
    source = make_skill(
        tmp_path / "sample-skill",
        "You must preserve the source package and never overwrite it.",
    )
    output = tmp_path / "review" / "unknown-language.yaml"

    status = main([
        "init-manifest", str(source), "--out", str(output),
        "--source-locale", "eo",
    ])

    assert status == 0
    payload = yaml.safe_load(output.read_text(encoding="utf-8"))
    captured = capsys.readouterr()
    assert "No built-in invariant suggestion profile" in captured.out
    assert payload["invariants"] == []
    assert payload["manifest_reviewed"] is False


def test_http_translation_requires_explicit_consent_before_any_candidate_write(
    tmp_path: Path, capsys,
) -> None:
    source = make_skill(tmp_path / "source" / "sample-skill")
    output = tmp_path / "candidate" / "sample-skill"
    report = tmp_path / "review" / "report.json"
    history = tmp_path / "review" / "history.sqlite3"

    status = main([
        "translate", str(source), str(output),
        "--source-locale", "en", "--target-locale", "fr",
        "--adapter", "http-json", "--endpoint", "https://translator.example/translate",
        "--report", str(report), "--history-db", str(history),
    ])

    assert status == 2
    assert "Remote translation requires --allow-remote" in capsys.readouterr().err
    assert not output.exists()
    assert not report.exists()
    assert not history.exists()



def test_validate_fail_on_threshold_can_include_low_warnings(
    tmp_path: Path,
) -> None:
    package = make_skill(tmp_path / "extension-skill")
    skill_file = package / "SKILL.md"
    content = skill_file.read_text(encoding="utf-8")
    skill_file.write_text(
        content.replace(
            "description: A CLI boundary fixture.",
            "description: A CLI boundary fixture." + chr(10) + "x-client-extension: preserved",
        ),
        encoding="utf-8",
    )

    assert main(["validate", str(package)]) == 0
    assert main(["validate", str(package), "--fail-on", "medium"]) == 0
    assert main(["validate", str(package), "--fail-on", "low"]) == 1


def test_doctor_reports_local_capabilities_without_invoking_parsers(
    monkeypatch: pytest.MonkeyPatch, capsys,
) -> None:
    available = {
        "bash": "/usr/bin/bash",
        "node": "/usr/bin/node",
        "tsc": "/usr/bin/tsc",
        "pwsh": None,
        "powershell": None,
        "sh": None,
    }
    calls: list[str] = []

    def which(name: str) -> str | None:
        calls.append(name)
        return available.get(name)

    monkeypatch.setattr(cli_module.shutil, "which", which)
    monkeypatch.setattr(
        cli_module,
        "_typescript_module_path",
        lambda _path: "/usr/lib/node_modules/typescript",
    )

    assert main(["doctor", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["checks_are_local"] is True
    assert payload["locale_registry"]["provider"] == "iana-bcp47"
    assert payload["locale_registry"]["snapshot_date"]
    assert payload["script_parsers"] == {
        "bash_sh": True,
        "javascript": True,
        "typescript": True,
        "powershell": False,
        "batch": "heuristic-only",
    }
    assert calls
