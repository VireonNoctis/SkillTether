"""Conservative guardrails against obvious catastrophic-backtracking regex shapes.

Python's stdlib regular-expression engine has no per-match timeout. This checker
rejects common nested-unbounded-repeat and repeated-alternation forms. It is a
heuristic guardrail, not a proof that arbitrary regular expressions are linear-time.
"""
from __future__ import annotations

import re


def _has_unbounded_repeat(expression: str) -> bool:
    escaped = False
    in_class = False
    index = 0
    while index < len(expression):
        char = expression[index]
        if escaped:
            escaped = False
            index += 1
            continue
        if char == "\\":
            escaped = True
            index += 1
            continue
        if char == "[" and not in_class:
            in_class = True
            index += 1
            continue
        if char == "]" and in_class:
            in_class = False
            index += 1
            continue
        if not in_class and char in "*+":
            return True
        if not in_class and char == "{":
            match = re.match(r"\{\d+,\s*\}", expression[index:])
            if match:
                return True
        index += 1
    return False


def _repeated_group_is_risky(pattern: str) -> bool:
    """Return true for obvious quantified groups with nested repetition/alternation."""
    stack: list[tuple[int, bool]] = []
    escaped = False
    in_class = False
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if escaped:
            escaped = False
            index += 1
            continue
        if char == "\\":
            escaped = True
            index += 1
            continue
        if char == "[" and not in_class:
            in_class = True
            index += 1
            continue
        if char == "]" and in_class:
            in_class = False
            index += 1
            continue
        if in_class:
            index += 1
            continue
        if char == "(":
            stack.append((index, False))
        elif char == "|" and stack:
            group_start, _ = stack[-1]
            stack[-1] = (group_start, True)
        elif char == ")" and stack:
            group_start, has_alternation = stack.pop()
            end = index + 1
            if end < len(pattern) and pattern[end] in "*+":
                body = pattern[group_start + 1:index]
                if _has_unbounded_repeat(body) or (has_alternation and pattern[end] in "*+"):
                    return True
            elif end < len(pattern) and pattern[end] == "{":
                quantifier = re.match(r"\{\d+,\s*\}", pattern[end:])
                if quantifier and (_has_unbounded_repeat(pattern[group_start + 1:index]) or has_alternation):
                    return True
            # Propagate a nested alternation flag upward conservatively.
            if stack and has_alternation:
                parent_start, _ = stack[-1]
                stack[-1] = (parent_start, True)
        index += 1
    return False


def validate_policy_regex(pattern: str, *, max_chars: int = 1000) -> re.Pattern[str]:
    """Compile a regex and reject common high-risk backtracking shapes."""
    if not isinstance(pattern, str):
        raise ValueError("Protected-token regex must be a string")
    if len(pattern) > max_chars:
        raise ValueError(f"Protected-token regex exceeds the {max_chars}-character limit")
    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        raise ValueError("Invalid protected-token regular expression") from exc
    if _repeated_group_is_risky(pattern):
        raise ValueError(
            "Protected-token regex contains nested unbounded repetition or a repeated alternation; "
            "simplify the pattern to avoid excessive backtracking"
        )
    return compiled
