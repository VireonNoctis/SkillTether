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
