from __future__ import annotations

import re

import pytest

from skilltether.regex_safety import (
    _has_unbounded_repeat,
    _repeated_group_is_risky,
    validate_policy_regex,
)


@pytest.mark.parametrize("pattern", [None, 17, ["a+"]])
def test_regex_validator_requires_string_input(pattern: object) -> None:
    with pytest.raises(ValueError, match="must be a string"):
        validate_policy_regex(pattern)  # type: ignore[arg-type]


def test_regex_validator_enforces_pattern_length_before_compilation() -> None:
    with pytest.raises(ValueError, match="1000-character limit"):
        validate_policy_regex("a" * 1001)


def test_regex_validator_wraps_compile_errors() -> None:
    with pytest.raises(ValueError, match="Invalid protected-token regular expression") as error:
        validate_policy_regex("(")

    assert isinstance(error.value.__cause__, re.error)


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        (r"\*", False),
        (r"[a-z*+]", False),
        (r"a{2,3}", False),
        (r"a{2,}", True),
        ("a+", True),
        ("b*", True),
    ],
)
def test_unbounded_repeat_scanner_distinguishes_escaped_classes_and_bounds(
    pattern: str, expected: bool,
) -> None:
    assert _has_unbounded_repeat(pattern) is expected


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        (r"(?:abc)+", False),
        (r"(\([a-z]+\))", False),
        (r"([a-z]+)+", True),
        (r"(?:one|two)+", True),
        (r"[()]++", False),
        (r"(?:one|two){2,3}", False),
        (r"(?:one|two){2,}", True),
    ],
)
def test_quantified_group_scanner_handles_escapes_classes_and_alternation(
    pattern: str, expected: bool,
) -> None:
    assert _repeated_group_is_risky(pattern) is expected


def test_safe_compiled_pattern_is_returned_unchanged() -> None:
    compiled = validate_policy_regex(r"(?:[A-Z]{2,5}_)+TOKEN")

    assert isinstance(compiled, re.Pattern)
    assert compiled.pattern == r"(?:[A-Z]{2,5}_)+TOKEN"
