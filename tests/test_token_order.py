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


def test_reviewed_path_scoped_token_mapping_suppresses_only_exact_rename(tmp_path: Path) -> None:
    from skilltether.compare import compare_packages
    from skilltether.models import InvariantManifest, ProtectedTokenMapping

    source = make_package(tmp_path / "source", "Use `--old-mode` for this operation.\n")
    target = make_package(tmp_path / "target", "Use `--new-mode` for this operation.\n")
    manifest = InvariantManifest(
        source_locale="en",
        target_locale="fr",
        manifest_reviewed=True,
        manifest_reviewer="reviewer-1",
        protected_token_mappings=[
            ProtectedTokenMapping(
                id="rename-cli-flag",
                path="SKILL.md",
                category="inline_code",
                source_token="--old-mode",
                target_token="--new-mode",
                rationale="The upstream CLI renamed this flag; verified against the target tool release.",
                reviewed=True,
                reviewer="reviewer-1",
            )
        ],
    )

    report = compare_packages(source, target, manifest)

    assert any(f.code == "PROTECTED_TOKEN_MAPPING_APPLIED" for f in report.findings)
    assert not any(f.code in {"PROTECTED_TOKEN_CHANGED", "PROTECTED_TOKEN_ADDED"} for f in report.findings)


def test_unreviewed_token_mapping_never_suppresses_token_change_findings(tmp_path: Path) -> None:
    from skilltether.compare import compare_packages
    from skilltether.models import InvariantManifest, ProtectedTokenMapping

    source = make_package(tmp_path / "source", "Use `--old-mode`.\n")
    target = make_package(tmp_path / "target", "Use `--new-mode`.\n")
    manifest = InvariantManifest(
        source_locale="en",
        target_locale="fr",
        manifest_reviewed=True,
        manifest_reviewer="reviewer-1",
        protected_token_mappings=[
            ProtectedTokenMapping(
                id="unreviewed-rename",
                path="SKILL.md",
                category="inline_code",
                source_token="--old-mode",
                target_token="--new-mode",
                rationale="Pending review.",
                reviewed=False,
            )
        ],
    )

    report = compare_packages(source, target, manifest)

    codes = {f.code for f in report.findings}
    assert "PROTECTED_TOKEN_MAPPING_UNREVIEWED" in codes
    assert "PROTECTED_TOKEN_CHANGED" in codes
    assert "PROTECTED_TOKEN_ADDED" in codes
    assert "PROTECTED_TOKEN_MAPPING_APPLIED" not in codes


def test_stale_or_incomplete_token_mappings_fail_closed(tmp_path: Path) -> None:
    from skilltether.compare import compare_packages
    from skilltether.models import InvariantManifest, ProtectedTokenMapping

    source = make_package(tmp_path / "source", "Use `--old-mode` twice: `--old-mode`.\n")
    target = make_package(tmp_path / "target", "Use `--new-mode`.\n")
    manifest = InvariantManifest(
        source_locale="en",
        manifest_reviewed=True,
        manifest_reviewer="reviewer-1",
        protected_token_mappings=[
            ProtectedTokenMapping(
                id="not-enough-replacements",
                path="SKILL.md",
                category="inline_code",
                source_token="--old-mode",
                target_token="--new-mode",
                rationale="The replacement is incomplete.",
                reviewed=True,
                reviewer="reviewer-1",
            )
        ],
    )

    report = compare_packages(source, target, manifest)

    codes = {f.code for f in report.findings}
    assert "PROTECTED_TOKEN_MAPPING_TARGET_MISSING" in codes
    assert "PROTECTED_TOKEN_CHANGED" in codes


def test_token_mapping_contract_rejects_duplicates_and_unreviewed_identity() -> None:
    from pydantic import ValidationError
    from skilltether.models import InvariantManifest, ProtectedTokenMapping

    with pytest.raises(ValidationError, match="distinct token"):
        ProtectedTokenMapping(
            id="same",
            category="command_flag",
            source_token="--same",
            target_token="--same",
            rationale="Not a rename.",
        )
    mapping = ProtectedTokenMapping(
        id="pending",
        category="command_flag",
        source_token="--before",
        target_token="--after",
        rationale="Pending human review.",
    )
    assert mapping.reviewed is False
    with pytest.raises(ValidationError, match="unique per path and category"):
        InvariantManifest(
            source_locale="en",
            protected_token_mappings=[
                mapping,
                ProtectedTokenMapping(
                    id="second",
                    category="command_flag",
                    source_token="--before",
                    target_token="--after-2",
                    rationale="A conflicting second mapping.",
                ),
            ],
        )
