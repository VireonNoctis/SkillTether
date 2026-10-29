from __future__ import annotations

import pytest

from skilltether.locale_tags import validate_bcp47_tag
from skilltether.cli import _validate_locale_tag


@pytest.mark.parametrize(
    "tag",
    [
        "en",
        "fr-CA",
        "zh-Hans-CN",
        "de-CH-1901",
        "sl-rozaj-biske",
        "en-u-ca-gregory",
        "en-t-en-US",
        "en-x-custom",
        "x-private",
        "es-419",
        "zh-cmn-Hans",
        "i-klingon",
        "en-GB-oed",
        "sgn-BE-FR",
        "qaa-Qaaa-001-abcde",
    ],
)
def test_well_formed_bcp47_tags_are_preserved_without_canonicalization(tag: str) -> None:
    assert validate_bcp47_tag(tag) == tag


@pytest.mark.parametrize(
    "tag",
    [
        "",
        "en--US",
        "-en",
        "en-",
        "a",
        "a-value",
        "x",
        "en-u",
        "en-a-b",
        "en-a-bbb-a-ccc",
        "de-DE-1901-1901",
        "en-abc-def-ghi",
        "en-GB-US",
        "en-x-",
        "en_US",
        "en-123456789",
        "fré",
    ],
)
def test_malformed_bcp47_tags_are_rejected(tag: str) -> None:
    with pytest.raises(ValueError):
        validate_bcp47_tag(tag)


def test_well_formed_unknown_subtags_are_not_rejected_as_registry_unknown() -> None:
    # Syntax validation is deliberately independent of a live/versioned IANA
    # registry. Valid structure is not the same as registry validity.
    assert validate_bcp47_tag("qaa-Qaaa-001") == "qaa-Qaaa-001"


def test_case_insensitive_duplicate_singletons_and_variants_are_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate extension singleton"):
        validate_bcp47_tag("en-a-foo-A-bar")
    with pytest.raises(ValueError, match="duplicate variant"):
        validate_bcp47_tag("de-1901-1901")


def test_cli_uses_bcp47_validator_and_returns_original_case() -> None:
    assert _validate_locale_tag("zh-Hans-CN") == "zh-Hans-CN"
    with pytest.raises(ValueError, match="IANA registry membership"):
        _validate_locale_tag("en-u")


def test_invariant_manifest_enforces_bcp47_structure_but_keeps_target_optional() -> None:
    from pydantic import ValidationError
    from skilltether.models import InvariantManifest

    manifest = InvariantManifest(source_locale="x-private")
    assert manifest.source_locale == "x-private"
    assert manifest.target_locale is None

    with pytest.raises(ValidationError, match="well-formed BCP 47"):
        InvariantManifest(source_locale="en-u")
    with pytest.raises(ValidationError, match="well-formed BCP 47"):
        InvariantManifest(source_locale="en", target_locale="fr-a")


def test_comparison_report_rejects_malformed_locale_tags() -> None:
    from pydantic import ValidationError
    from skilltether.models import ComparisonReport

    base = {
        "tool_version": "0.1.0",
        "generated_at": "2026-01-01T00:00:00Z",
        "protected_policy_fingerprint": "a" * 64,
        "source_fingerprint": "b" * 64,
        "target_fingerprint": "c" * 64,
        "source_files": {},
        "target_files": {},
        "structural_status": "pass",
        "semantic_status": "unknown",
    }
    with pytest.raises(ValidationError, match="well-formed BCP 47"):
        ComparisonReport(**base, source_locale="en-u")
    report = ComparisonReport(**base, source_locale="x-private")
    assert report.source_locale == "x-private"


@pytest.mark.parametrize(
    "tag",
    ["en", "zh-Hans-CN", "en-u-ca-gregory", "x-private", "i-klingon", "en-GB-oed"],
)
def test_valid_bcp47_tags_pass_manifest_model_and_json_schema(tag: str) -> None:
    import json
    from pathlib import Path

    from jsonschema import Draft202012Validator
    from skilltether.models import InvariantManifest

    root = Path(__file__).resolve().parents[1]
    schema = json.loads((root / "schemas" / "invariant-manifest.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)

    manifest = InvariantManifest(source_locale=tag, invariants=[])
    assert manifest.source_locale == tag
    assert validator.is_valid({
        "manifest_version": "1.0",
        "source_locale": tag,
        "invariants": [],
    })
