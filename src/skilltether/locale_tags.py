"""IANA-backed RFC 5646 validation and explicit canonicalization.

Validation uses the locally bundled IANA registry snapshot from iana-bcp47.
Canonicalization is separate so callers do not silently rewrite supplied tags.
"""
from __future__ import annotations

from iana_bcp47 import validate_bcp47
from iana_bcp47._registry import get_registry


def registry_file_date() -> str:
    """Return the bundled registry date, not the live IANA registry date."""
    return get_registry().file_date.isoformat()


def validate_bcp47_tag(tag: str) -> str:
    """Return tag unchanged when its RFC 5646 syntax and IANA membership are valid."""
    if not isinstance(tag, str) or not tag:
        raise ValueError("language tag must be a non-empty string")
    try:
        valid, message = validate_bcp47(tag)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"tag is not valid against the bundled IANA registry: {exc}") from None
    if not valid:
        raise ValueError(f"{tag!r} is not a valid BCP 47 tag in the bundled IANA registry: {message}")
    return tag


def canonicalize_bcp47_tag(tag: str) -> str:
    """Return canonical form using registry Preferred-Value and Suppress-Script fields.

    Extension-specific payloads are not interpreted. The operation never mutates
    manifests/reports; callers must opt in and handle the returned value explicitly.
    """
    validate_bcp47_tag(tag)
    registry = get_registry()

    for kind in ("grandfathered", "redundant"):
        special = registry.lookup(kind, tag)
        if special is not None:
            if special.preferred_value:
                return canonicalize_bcp47_tag(special.preferred_value)
            return special.identifier

    parts = tag.split("-")
    if parts[0].lower() == "x":
        return "-".join(part.lower() for part in parts)

    language_entry = registry.lookup("language", parts[0])
    if language_entry and language_entry.preferred_value:
        parts = language_entry.preferred_value.split("-") + parts[1:]
        language_entry = registry.lookup("language", parts[0])
    parts[0] = parts[0].lower()
    index = 1

    # Promote a deprecated extlang to its registry Preferred-Value when present.
    if len(parts[0]) in {2, 3}:
        while index < len(parts) and len(parts[index]) == 3 and parts[index].isalpha():
            extlang = registry.lookup("extlang", parts[index])
            if extlang is None:
                break
            if extlang.preferred_value:
                parts = extlang.preferred_value.split("-") + parts[index + 1:]
                parts[0] = parts[0].lower()
                index = 1
                language_entry = registry.lookup("language", parts[0])
                break
            parts[index] = parts[index].lower()
            index += 1

    script_index = None
    if index < len(parts) and len(parts[index]) == 4 and parts[index].isalpha():
        script_index = index
        script = registry.lookup("script", parts[index])
        parts[index] = (
            script.preferred_value.title()
            if script and script.preferred_value
            else parts[index].title()
        )
        index += 1

    if index < len(parts) and (
        (len(parts[index]) == 2 and parts[index].isalpha())
        or (len(parts[index]) == 3 and parts[index].isdigit())
    ):
        region = registry.lookup("region", parts[index])
        parts[index] = (
            region.preferred_value.upper()
            if region and region.preferred_value
            else parts[index].upper()
        )
        index += 1

    while index < len(parts) and (
        5 <= len(parts[index]) <= 8
        or (len(parts[index]) == 4 and parts[index][0].isdigit())
    ):
        variant = registry.lookup("variant", parts[index])
        if variant and variant.preferred_value:
            replacement = variant.preferred_value.split("-")
            parts[index:index + 1] = replacement
            index += len(replacement)
        else:
            parts[index] = parts[index].lower()
            index += 1

    # Remove only the exact Suppress-Script registered for the primary language.
    if script_index is not None and language_entry and language_entry.suppress_script:
        if parts[script_index].casefold() == language_entry.suppress_script.casefold():
            del parts[script_index]

    # Extension payloads are opaque; only lowercase casing and singleton order
    # are normalized. Keep private-use material as a trailing opaque sequence.
    extension_start = next(
        (i for i, part in enumerate(parts) if len(part) == 1 and part.lower() != "x"),
        len(parts),
    )
    private_start = next(
        (i for i in range(extension_start, len(parts)) if parts[i].lower() == "x"),
        len(parts),
    )
    if extension_start < private_start:
        prefix = parts[:extension_start]
        extension_parts = parts[extension_start:private_start]
        groups: list[tuple[str, list[str]]] = []
        cursor = 0
        while cursor < len(extension_parts):
            singleton = extension_parts[cursor].lower()
            cursor += 1
            payload: list[str] = []
            while cursor < len(extension_parts) and len(extension_parts[cursor]) != 1:
                payload.append(extension_parts[cursor].lower())
                cursor += 1
            groups.append((singleton, payload))
        groups.sort(key=lambda item: item[0])
        parts = prefix + [
            part for singleton, payload in groups for part in [singleton, *payload]
        ] + parts[private_start:]

    private_index = next(
        (i for i, part in enumerate(parts) if part.lower() == "x"),
        len(parts),
    )
    parts[private_index:] = [part.lower() for part in parts[private_index:]]
    return "-".join(parts)


def is_canonical_bcp47_tag(tag: str) -> bool:
    """Return whether a valid tag is already in canonical form."""
    return canonicalize_bcp47_tag(tag) == tag
