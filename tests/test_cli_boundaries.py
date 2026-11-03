from __future__ import annotations

from pathlib import Path

import yaml

from skilltether.cli import main


def make_skill(path: Path, body: str = "Use the documented workflow.") -> Path:
    path.mkdir(parents=True)
    (path / "SKILL.md").write_text(
        f"---\nname: {path.name}\ndescription: A CLI boundary fixture.\n---\n\n"
        f"# Instructions\n\n{body}\n",
        encoding="utf-8",
    )
    return path


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
        "--source-locale", "ja",
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
