from __future__ import annotations

from pathlib import Path

from skilltether.compare import compare_packages
from skilltether.models import InvariantManifest


def make_package(root: Path, instructions: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "SKILL.md").write_text(
        f"---\nname: {root.name}\ndescription: A token-order test skill.\n---\n\n"
        f"# Instructions\n\n{instructions}\n",
        encoding="utf-8",
    )
    return root


def reviewed_manifest() -> InvariantManifest:
    return InvariantManifest(
        source_locale="en", target_locale="fr",
        manifest_reviewed=True, manifest_reviewer="test-reviewer",
    )


def test_compare_flags_protected_token_reordering_even_when_counts_match(tmp_path: Path) -> None:
    source = make_package(
        tmp_path / "source" / "sample-skill",
        "Run the command with --before then --after.",
    )
    target = make_package(
        tmp_path / "target" / "sample-skill",
        "Run the command with --after then --before.",
    )

    report = compare_packages(source, target, reviewed_manifest(), target_locale="fr")
    order_findings = [item for item in report.findings if item.code == "PROTECTED_TOKEN_ORDER_CHANGED"]

    assert len(order_findings) == 1
    assert order_findings[0].path == "SKILL.md"
    assert order_findings[0].analysis_method == "heuristic"
    assert order_findings[0].uncertainty == "high"
    assert order_findings[0].requires_review is True
    assert "--before" in (order_findings[0].original_context or "")
    assert "--after" in (order_findings[0].target_context or "")


def test_compare_does_not_flag_unchanged_protected_token_order(tmp_path: Path) -> None:
    source = make_package(
        tmp_path / "source" / "sample-skill",
        "Run the command with --before then --after.",
    )
    target = make_package(
        tmp_path / "target" / "sample-skill",
        "Use --before and then --after for the command.",
    )

    report = compare_packages(source, target, reviewed_manifest(), target_locale="fr")

    assert not any(item.code == "PROTECTED_TOKEN_ORDER_CHANGED" for item in report.findings)
