from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from skilltether.cli import main


def test_multilingual_invariant_suggestions_match_curated_corpus(tmp_path: Path) -> None:
    corpus = json.loads(
        Path("tests/fixtures/invariant-suggestion-multilingual.json").read_text(encoding="utf-8")
    )
    aggregate = {"tp": 0, "fp": 0, "fn": 0}

    for case in corpus["cases"]:
        source = tmp_path / case["locale"] / f"skill-{case['locale']}"
        source.mkdir(parents=True)
        (source / "SKILL.md").write_text(
            f"---\nname: skill-{case['locale']}\ndescription: Multilingual test fixture.\n---\n\n"
            + case["body"],
            encoding="utf-8",
        )
        output = tmp_path / "review" / f"{case['locale']}.yaml"
        status = main([
            "init-manifest", str(source), "--out", str(output),
            "--source-locale", case["locale"], "--target-locale", "en",
        ])
        assert status == 0

        payload = yaml.safe_load(output.read_text(encoding="utf-8"))
        observed = [
            {"source_text": item["source_text"], "category": item["category"]}
            for item in payload["invariants"]
        ]
        assert observed == case["expected_candidates"], case["locale"]
        expected = {
            (item["source_text"], item["category"])
            for item in case["expected_candidates"]
        }
        actual = {(item["source_text"], item["category"]) for item in observed}
        true_positive = len(expected & actual)
        false_positive = len(actual - expected)
        false_negative = len(expected - actual)
        aggregate["tp"] += true_positive
        aggregate["fp"] += false_positive
        aggregate["fn"] += false_negative

        observed_text = {item["source_text"] for item in payload["invariants"]}
        for excluded in case["expected_exclusions"]:
            assert excluded not in observed_text, f"{case['locale']}: {excluded}"
        assert payload["manifest_reviewed"] is False
        assert all(item["reviewed"] is False for item in payload["invariants"])

        negation = next(
            (item for item in payload["invariants"] if item["category"] == "negation"),
            None,
        )
        if negation is not None:
            assert negation["negation_markers"] == ["not", "never", "without", "cannot", "can't", "mustn't", "don't"]

    assert aggregate == {"tp": 25, "fp": 0, "fn": 0}
    precision = aggregate["tp"] / (aggregate["tp"] + aggregate["fp"])
    recall = aggregate["tp"] / (aggregate["tp"] + aggregate["fn"])
    assert precision == 1.0
    assert recall == 1.0


@pytest.mark.parametrize(
    ("locale", "text", "category"),
    [
        ("fr", "Ne supprimez jamais le fichier.", "negation"),
        ("es", "Debes conservar el archivo.", "mandatory_condition"),
        ("de", "Du musst die Datei erhalten.", "mandatory_condition"),
        ("pt", "Não exclua o arquivo.", "negation"),
        ("it", "Devi conservare il file.", "mandatory_condition"),
    ],
)
def test_language_profiles_are_selected_by_primary_bcp47_subtag(
    locale: str, text: str, category: str,
) -> None:
    from skilltether.invariant_language import classify_candidate, language_profile

    profile = language_profile(locale + "-Latn")
    assert profile is not None
    assert classify_candidate(text, profile) == category


def test_unknown_language_profile_does_not_guess_invariant_candidates() -> None:
    from skilltether.invariant_language import classify_candidate, language_profile

    assert language_profile("ja") is None
    assert classify_candidate("Never delete the source.", language_profile("en")) == "negation"
