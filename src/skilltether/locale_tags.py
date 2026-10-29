"""Dependency-free checks for BCP 47 language-tag structure.

This validates syntax and duplicate variant/extension-singleton constraints. It
intentionally does not consult the versioned IANA Language Subtag Registry.
"""
from __future__ import annotations

import re

_ALPHA = re.compile(r"^[A-Za-z]+$")
_ALNUM = re.compile(r"^[A-Za-z0-9]+$")
_SINGLETON = re.compile(r"^[0-9A-WY-Za-wy-z]$", re.I)

# RFC 5646 §2.1's fixed grandfathered list. Values are case-insensitive.
_GRANDFATHERED = frozenset({
    "en-gb-oed",
    "i-ami", "i-bnn", "i-default", "i-enochian", "i-hak", "i-klingon",
    "i-lux", "i-mingo", "i-navajo", "i-pwn", "i-tao", "i-tay", "i-tsu",
    "sgn-be-fr", "sgn-be-nl", "sgn-ch-de",
    "art-lojban", "cel-gaulish", "no-bok", "no-nyn", "zh-guoyu",
    "zh-hakka", "zh-min", "zh-min-nan", "zh-xiang",
})


def _is_variant(subtag: str) -> bool:
    return (
        5 <= len(subtag) <= 8 and bool(_ALNUM.fullmatch(subtag))
    ) or (
        len(subtag) == 4 and subtag[0].isdigit() and bool(_ALNUM.fullmatch(subtag))
    )


def validate_bcp47_tag(tag: str) -> str:
    """Return *tag* unchanged when it is structurally well-formed.

    Registry membership and canonicalization are deliberately out of scope:
    a syntactically valid but unfamiliar subtag is not rejected merely because
    no IANA registry snapshot is bundled with SkillTether.
    """
    if not isinstance(tag, str) or not tag or not tag.isascii():
        raise ValueError("language tag must be a non-empty ASCII string")

    normalized = tag.lower()
    if normalized in _GRANDFATHERED:
        return tag

    parts = tag.split("-")
    if any(not part or len(part) > 8 or not _ALNUM.fullmatch(part) for part in parts):
        raise ValueError("language tag contains an empty, non-alphanumeric, or overlong subtag")

    # Private-use-only tags are valid BCP 47 syntax: x- followed by one or more
    # subtags of 1–8 alphanumeric characters.
    if parts[0].lower() == "x":
        if len(parts) < 2:
            raise ValueError("private-use language tags need at least one subtag after x")
        return tag

    language = parts[0]
    if not _ALPHA.fullmatch(language) or not (
        2 <= len(language) <= 3 or len(language) == 4 or 5 <= len(language) <= 8
    ):
        raise ValueError("invalid primary language subtag")

    index = 1
    # RFC 5646's extlang shape is three alpha characters after a 2–3 character
    # language. Current validity constraints permit at most one extlang subtag.
    if len(language) <= 3 and index < len(parts):
        candidate = parts[index]
        if len(candidate) == 3 and _ALPHA.fullmatch(candidate):
            index += 1

    if index < len(parts) and len(parts[index]) == 4 and _ALPHA.fullmatch(parts[index]):
        index += 1

    if index < len(parts):
        region = parts[index]
        if (len(region) == 2 and _ALPHA.fullmatch(region)) or (
            len(region) == 3 and region.isdigit()
        ):
            index += 1

    variants: set[str] = set()
    while index < len(parts) and _is_variant(parts[index]):
        variant = parts[index].lower()
        if variant in variants:
            raise ValueError(f"duplicate variant subtag: {parts[index]}")
        variants.add(variant)
        index += 1

    singletons: set[str] = set()
    while index < len(parts) and _SINGLETON.fullmatch(parts[index]):
        singleton = parts[index].lower()
        if singleton in singletons:
            raise ValueError(f"duplicate extension singleton: {parts[index]}")
        singletons.add(singleton)
        index += 1
        extension_values = 0
        while index < len(parts) and 2 <= len(parts[index]) <= 8:
            extension_values += 1
            index += 1
        if extension_values == 0:
            raise ValueError(f"extension singleton {singleton!r} needs at least one 2–8 character subtag")

    if index < len(parts) and parts[index].lower() == "x":
        index += 1
        if index >= len(parts):
            raise ValueError("private-use sequence x needs at least one following subtag")
        while index < len(parts) and 1 <= len(parts[index]) <= 8:
            index += 1

    if index != len(parts):
        raise ValueError(f"subtag {parts[index]!r} appears in an invalid position")
    return tag
