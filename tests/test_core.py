from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest
from hypothesis import given, strategies as st

from skilltether.analysis import extract_protected_tokens, inspect_package, package_fingerprint
from skilltether.compare import compare_packages
from skilltether.models import FileFingerprint, Invariant, InvariantManifest
from skilltether.translation import IdentityAdapter, translate_markdown, translate_package


def make_package(root: Path, instructions: str = "Follow the documented workflow.") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "SKILL.md").write_text(
        f"---\nname: {root.name}\ndescription: A sample skill for tests.\n---\n\n"
        f"# Sample skill\n\n{instructions}\n",
        encoding="utf-8",
    )
    return root


def reviewed_manifest(*invariants: Invariant) -> InvariantManifest:
    return InvariantManifest(
        source_locale="en", target_locale="fr", manifest_reviewed=True,
        manifest_reviewer="test-reviewer", invariants=list(invariants),
    )


def test_valid_skill_metadata_and_local_link(tmp_path: Path) -> None:
    package = make_package(tmp_path / "sample-skill", "See [guide](references/guide.md).")
    (package / "references").mkdir()
    (package / "references" / "guide.md").write_text("# Guide\n", encoding="utf-8")
    _inventory, findings, _texts = inspect_package(package)
    assert not [item for item in findings if item.severity in ("high", "critical")]


def test_malformed_frontmatter_is_reported(tmp_path: Path) -> None:
    package = tmp_path / "sample-skill"
    package.mkdir()
    (package / "SKILL.md").write_text("---\nname: [oops\n---\n# Broken\n", encoding="utf-8")
    _inventory, findings, _texts = inspect_package(package)
    assert any(item.code == "FRONTMATTER_INVALID" for item in findings)


def test_missing_local_resource_is_reported(tmp_path: Path) -> None:
    package = make_package(tmp_path / "sample-skill", "Read [guide](references/missing.md).")
    _inventory, findings, _texts = inspect_package(package)
    assert any(item.code == "BROKEN_LOCAL_LINK" for item in findings)


def test_protected_tokens_include_code_env_path_and_url() -> None:
    tick = chr(96)
    text = f"Run {tick}skilltether validate{tick} with $API_TOKEN at references/guide.md and https://example.test/path"
    tokens = extract_protected_tokens(text, "SKILL.md")
    observed = {(item.category, item.value) for item in tokens}
    assert ("inline_code", f"{tick}skilltether validate{tick}") in observed
    assert ("environment_variable", "$API_TOKEN") in observed
    assert any(category == "file_path" and value == "references/guide.md" for category, value in observed)
    assert any(category == "url" and value == "https://example.test/path" for category, value in observed)


def test_compare_flags_changed_code_block_and_requires_review(tmp_path: Path) -> None:
    source = make_package(tmp_path / "source" / "sample-skill", "Run the check:\n\n~~~sh\nskilltether validate\n~~~")
    target = make_package(tmp_path / "target" / "sample-skill", "Run the check:\n\n~~~sh\nskilltether compare\n~~~")
    report = compare_packages(source, target, reviewed_manifest())
    assert any(item.code == "PROTECTED_TOKEN_CHANGED" for item in report.findings)
    assert any(item.severity == "critical" and item.requires_review for item in report.findings)
    assert report.structural_status == "pass"


def test_invariant_required_value_and_critical_review(tmp_path: Path) -> None:
    source = make_package(tmp_path / "source" / "sample-skill", "You must not use more than 3 retries.")
    target = make_package(tmp_path / "target" / "sample-skill", "Use 5 retries.")
    invariant = Invariant(
        id="SAFE-1", statement="Do not exceed 3 retries.",
        category="safety_constraint", severity="critical",
        source_text="You must not use more than 3 retries.",
        required_tokens=["3"], expected_numbers=["3"],
        negation_required=True, negation_markers=["not"],
        reviewed=True, reviewer="safety-reviewer",
    )
    report = compare_packages(source, target, reviewed_manifest(invariant), target_locale="fr")
    codes = {item.code for item in report.findings}
    assert "INVARIANT_REQUIRED_TOKEN_MISSING" in codes
    assert "INVARIANT_NEGATION_UNCERTAIN" in codes
    assert "CRITICAL_INVARIANT_REVIEW_REQUIRED" in codes


def test_identity_translation_writes_separate_candidate_and_preserves_source(tmp_path: Path) -> None:
    source = make_package(tmp_path / "source" / "sample-skill", "A plain paragraph.")
    source_before = (source / "SKILL.md").read_bytes()
    output = tmp_path / "candidate" / "sample-skill"
    _source_inventory, target_inventory, changed = translate_package(
        source, output, IdentityAdapter(), "en", "fr",
    )
    assert output.is_dir()
    assert changed == 0
    assert (source / "SKILL.md").read_bytes() == source_before
    assert "SKILL.md" in target_inventory


def test_translate_masks_inline_code_and_urls() -> None:
    class PrefixAdapter:
        name = "prefix"
        remote = False

        def translate(self, text: str, source_locale: str, target_locale: str) -> str:
            return "translated " + text

    tick = chr(96)
    source = "---\nname: sample-skill\ndescription: A skill.\n---\n\nUse " + tick + "tool-call" + tick + " at https://example.test/path.\n"
    result = translate_markdown(source, PrefixAdapter(), "en", "fr")
    assert "name: sample-skill" in result
    assert tick + "tool-call" + tick in result
    assert "https://example.test/path" in result
    assert "translated Use" in result


def test_package_fingerprint_is_order_independent() -> None:
    a = FileFingerprint(path="a.md", size_bytes=1, sha256=hashlib.sha256(b"a").hexdigest(), encoding="utf-8", kind="md")
    b = FileFingerprint(path="b.md", size_bytes=1, sha256=hashlib.sha256(b"b").hexdigest(), encoding="utf-8", kind="md")
    assert package_fingerprint({"a.md": a, "b.md": b}) == package_fingerprint({"b.md": b, "a.md": a})


@given(st.dictionaries(st.text(min_size=1, max_size=12), st.text(max_size=40), max_size=8))
def test_package_fingerprint_is_deterministic_under_generated_inputs(values: dict[str, str]) -> None:
    inventory = {
        key: FileFingerprint(
            path=key, size_bytes=len(value.encode("utf-8")),
            sha256=hashlib.sha256(value.encode("utf-8")).hexdigest(),
            encoding="utf-8", kind="txt",
        )
        for key, value in values.items()
    }
    assert package_fingerprint(inventory) == package_fingerprint(dict(reversed(list(inventory.items()))))


def test_translation_policy_masks_custom_patterns_and_literals() -> None:
    class EchoPrefixAdapter:
        name = "echo-prefix"
        remote = False

        def translate(self, text: str, source_locale: str, target_locale: str) -> str:
            return "translated " + text

    source = "Use WIDGET_TOKEN and ToolZ safely."
    result = translate_markdown(
        source, EchoPrefixAdapter(), "en", "fr",
        extra_patterns=[{"category": "identifier", "regex": r"WIDGET_[A-Z]+"}],
        explicit_tokens=["ToolZ"],
    )
    assert "WIDGET_TOKEN" in result
    assert "ToolZ" in result


def test_report_context_fence_cannot_be_closed_by_untrusted_text() -> None:
    from skilltether.report import _fenced_context
    import re

    hostile_context = "Source text\n~~~text\n# embedded heading\n~~~\n<script>not executable here</script>"
    block = _fenced_context(hostile_context)
    fence = block.split("text\n", 1)[0]
    runs = [len(match.group(0)) for match in re.finditer(re.escape(fence[0]) + "+", hostile_context)]
    assert len(fence) > max(runs, default=0)
    assert block.endswith(fence)
    assert hostile_context in block
def test_remote_adapter_rejects_non_loopback_plain_http() -> None:
    from skilltether.translation import HttpJsonAdapter

    try:
        HttpJsonAdapter("http://translation.example.test/api")
    except ValueError as exc:
        assert "HTTPS" in str(exc)
    else:
        raise AssertionError("Non-loopback HTTP endpoint should be rejected")


def test_duplicate_frontmatter_keys_are_rejected(tmp_path: Path) -> None:
    package = tmp_path / "sample-skill"
    package.mkdir()
    (package / "SKILL.md").write_text(
        "---\nname: sample-skill\nname: different-skill\ndescription: A skill.\n---\nInstructions.\n",
        encoding="utf-8",
    )
    _inventory, findings, _texts = inspect_package(package)
    assert any(item.code == "FRONTMATTER_INVALID" for item in findings)


def test_provider_failure_does_not_publish_partial_candidate(tmp_path: Path) -> None:
    source = make_package(tmp_path / "source" / "sample-skill", "A line that needs translation.")
    original = (source / "SKILL.md").read_bytes()

    class FailingAdapter:
        name = "failing"
        remote = False

        def translate(self, text: str, source_locale: str, target_locale: str) -> str:
            raise RuntimeError("synthetic provider failure")

    output = tmp_path / "candidate" / "sample-skill"
    with pytest.raises(RuntimeError, match="synthetic provider failure"):
        translate_package(source, output, FailingAdapter(), "en", "fr")
    assert not output.exists()
    assert (source / "SKILL.md").read_bytes() == original


def test_report_round_trip_preserves_review_disposition(tmp_path: Path) -> None:
    from skilltether.report import read_json_report, write_json_report

    source = make_package(tmp_path / "source" / "sample-skill", "A plain source sentence.")
    target = make_package(tmp_path / "target" / "sample-skill", "Une phrase localisée.")
    report = compare_packages(source, target, reviewed_manifest())
    report.findings[0].disposition = "approved"
    report.findings[0].reviewer = "qa-reviewer"
    report.findings[0].review_note = "Context reviewed."
    path = tmp_path / "report.json"
    write_json_report(report, path)
    restored = read_json_report(path)
    assert restored.findings[0].disposition == "approved"
    assert restored.findings[0].reviewer == "qa-reviewer"
    assert restored.protected_policy_fingerprint == report.protected_policy_fingerprint


def test_missing_markdown_images_and_literal_script_references_are_reported(tmp_path: Path) -> None:
    package = make_package(
        tmp_path / "sample-skill",
        "Run `python scripts/missing.py` and inspect ![the diagram](assets/missing.png).",
    )
    _inventory, findings, _texts = inspect_package(package)
    codes = {item.code for item in findings}
    assert "MISSING_REFERENCED_RESOURCE" in codes
    assert "BROKEN_LOCAL_LINK" in codes


def test_python_resources_are_parsed_but_never_executed(tmp_path: Path) -> None:
    package = make_package(tmp_path / "sample-skill", "Inspect the scripts folder.")
    scripts = package / "scripts"
    scripts.mkdir()
    marker = tmp_path / "should-not-exist.txt"
    (scripts / "side_effect.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n",
        encoding="utf-8",
    )
    (scripts / "invalid.py").write_text("def broken(:\n    pass\n", encoding="utf-8")
    _inventory, findings, _texts = inspect_package(package)
    assert any(item.code == "RESOURCE_SYNTAX_INVALID" and item.path == "scripts/invalid.py" for item in findings)
    assert not marker.exists()



def test_binary_asset_byte_changes_are_review_findings(tmp_path: Path) -> None:
    source = make_package(tmp_path / "source" / "sample-skill", "A skill with an image.")
    target = make_package(tmp_path / "target" / "sample-skill", "A skill with an image.")
    (source / "assets").mkdir()
    (target / "assets").mkdir()
    (source / "assets" / "icon.png").write_bytes(b"\x89PNG\r\n\x1a\nsource")
    (target / "assets" / "icon.png").write_bytes(b"\x89PNG\r\n\x1a\ntarget")

    report = compare_packages(source, target, reviewed_manifest())
    changed = [item for item in report.findings if item.code == "PACKAGE_RESOURCE_CHANGED"]

    assert len(changed) == 1
    assert changed[0].path == "assets/icon.png"
    assert changed[0].severity == "medium"
    assert changed[0].requires_review
    assert changed[0].original_context != changed[0].target_context


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="named pipes are not available on this platform")
def test_named_pipe_is_rejected_without_blocking_package_inspection(tmp_path: Path) -> None:
    package = make_package(tmp_path / "sample-skill", "A package with a special entry.")
    (package / "assets").mkdir()
    os.mkfifo(package / "assets" / "pipe")

    inventory, findings, _texts = inspect_package(package)

    assert "assets/pipe" not in inventory
    assert any(
        item.code == "SPECIAL_FILE_NOT_ALLOWED" and item.path == "assets/pipe"
        for item in findings
    )
    from skilltether.compare import compare_packages
    report = compare_packages(package, package, reviewed_manifest())
    assert report.structural_status == "fail"



def test_overlapping_explicit_identifiers_choose_the_longest_span() -> None:
    class CapturingAdapter:
        name = "capturing"
        remote = False

        def __init__(self) -> None:
            self.received = ""

        def translate(self, text: str, source_locale: str, target_locale: str) -> str:
            self.received = text
            return text

    adapter = CapturingAdapter()
    source = "Use TOOL_NAME and TOOL."
    translated = translate_markdown(
        source, adapter, "en", "fr",
        explicit_tokens=["TOOL", "TOOL_NAME"],
    )

    assert translated == source
    assert adapter.received.count("SKTETHEROPAQUE") == 2
    assert "TOOL_NAME" not in adapter.received
    assert "TOOL" not in adapter.received


def test_placeholder_namespace_collision_does_not_consume_source_text() -> None:
    class CapturingAdapter:
        name = "capturing"
        remote = False

        def __init__(self) -> None:
            self.received = ""

        def translate(self, text: str, source_locale: str, target_locale: str) -> str:
            self.received = text
            return text

    adapter = CapturingAdapter()
    source = "Literal SKTETHEROPAQUE00000END and API_TOKEN."
    translated = translate_markdown(
        source, adapter, "en", "fr", explicit_tokens=["API_TOKEN"],
    )

    assert translated == source
    assert "_SKTETHEROPAQUE00000END" in adapter.received
    assert "SKTETHEROPAQUE00000END and" in adapter.received


def test_zero_width_policy_regex_on_real_text_is_rejected() -> None:
    class IdentityLikeAdapter:
        name = "identity-like"
        remote = False

        def translate(self, text: str, source_locale: str, target_locale: str) -> str:
            return text

    with pytest.raises(ValueError, match="empty span"):
        translate_markdown(
            "This is a critical instruction.",
            IdentityLikeAdapter(), "en", "fr",
            extra_patterns=[{"category": "lookahead", "regex": r"(?=critical)"}],
        )



def test_aggregate_package_byte_limit_is_enforced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import skilltether.analysis as analysis

    package = make_package(tmp_path / "sample-skill", "A package with a bounded inventory.")
    base_size = (package / "SKILL.md").stat().st_size
    assets = package / "assets"
    assets.mkdir()
    (assets / "a.bin").write_bytes(b"123")
    (assets / "b.bin").write_bytes(b"456")
    monkeypatch.setattr(analysis, "MAX_PACKAGE_BYTES", base_size + 4)

    inventory, findings, _texts = analysis.inspect_package(package)

    assert "assets/a.bin" in inventory
    assert "assets/b.bin" not in inventory
    assert any(item.code == "PACKAGE_TOO_LARGE" for item in findings)
    report = compare_packages(package, package, reviewed_manifest())
    assert report.structural_status == "fail"


def test_directory_count_limit_is_enforced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import skilltether.analysis as analysis

    package = make_package(tmp_path / "sample-skill")
    (package / "assets").mkdir()
    (package / "references").mkdir()
    monkeypatch.setattr(analysis, "MAX_PACKAGE_DIRECTORIES", 1)

    with pytest.raises(ValueError, match="directory safety limit"):
        analysis.inspect_package(package)



def test_invariant_numbers_in_frontmatter_do_not_satisfy_instruction_context(tmp_path: Path) -> None:
    source = make_package(
        tmp_path / "source" / "sample-skill",
        "You must not use more than 3 retries.",
    )
    target = tmp_path / "target" / "sample-skill"
    target.mkdir(parents=True)
    (target / "SKILL.md").write_text(
        "---\nname: sample-skill\ndescription: A 3-step retry workflow.\n---\n\n"
        "# Retry guidance\nUse five retries.\n",
        encoding="utf-8",
    )
    invariant = Invariant(
        id="RETRIES-3", statement="Do not exceed 3 retries.",
        category="numeric_limit", severity="critical",
        source_path="SKILL.md", source_lines=(7, 7),
        source_text="You must not use more than 3 retries.",
        expected_numbers=["3"], reviewed=True, reviewer="qa-reviewer",
    )
    report = compare_packages(source, target, reviewed_manifest(invariant))
    finding = next(
        item for item in report.findings
        if item.code == "INVARIANT_REQUIRED_TOKEN_MISSING" and "3" in item.message
    )

    assert finding.target_line == 7
    assert finding.analysis_method == "heuristic"
    assert finding.uncertainty == "high"
    assert finding.target_context == "Use five retries."


def test_forbidden_token_elsewhere_is_uncertain_not_a_context_confirmed_violation(tmp_path: Path) -> None:
    source = make_package(
        tmp_path / "source" / "sample-skill",
        "Do not include SECRET_TOKEN when describing the public endpoint.",
    )
    target = make_package(
        tmp_path / "target" / "sample-skill",
        "The public endpoint must accept requests only.\n\n"
        "A glossary lists SECRET_TOKEN as a separate identifier.",
    )
    invariant = Invariant(
        id="PUBLIC-ENDPOINT", statement="Do not include SECRET_TOKEN when describing the public endpoint.",
        category="safety_constraint", severity="high",
        source_path="SKILL.md",
        source_text="Do not include SECRET_TOKEN when describing the public endpoint.",
        forbidden_tokens=["SECRET_TOKEN"], reviewed=True, reviewer="qa-reviewer",
    )
    report = compare_packages(source, target, reviewed_manifest(invariant))
    codes = {item.code for item in report.findings}

    assert "INVARIANT_FORBIDDEN_TOKEN_CONTEXT_UNCERTAIN" in codes
    assert "INVARIANT_FORBIDDEN_TOKEN_PRESENT" not in codes
    finding = next(item for item in report.findings if item.code == "INVARIANT_FORBIDDEN_TOKEN_CONTEXT_UNCERTAIN")
    assert finding.analysis_method == "heuristic"
    assert finding.uncertainty == "high"
    assert finding.target_context == "The public endpoint must accept requests only."
    assert finding.target_line == 8



def test_mask_rejects_malformed_direct_policy_inputs() -> None:
    with pytest.raises(ValueError, match="list of mappings"):
        translate_markdown(
            "Translate this sentence.", IdentityAdapter(), "en", "fr",
            extra_patterns=["not-a-pattern-mapping"],  # type: ignore[list-item]
        )
    with pytest.raises(ValueError, match="list of strings"):
        translate_markdown(
            "Translate this sentence.", IdentityAdapter(), "en", "fr",
            explicit_tokens=[object()],  # type: ignore[list-item]
        )


def test_policy_loader_rejects_oversized_regex_and_too_many_patterns(tmp_path: Path) -> None:
    import yaml
    from skilltether.analysis import MAX_POLICY_PATTERNS, load_policy

    too_long = tmp_path / "too-long.yaml"
    too_long.write_text(yaml.safe_dump({
        "policy_version": "1.0",
        "patterns": [{"category": "custom", "regex": "a" * 1001}],
        "explicit_tokens": [],
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="exceeds 1000 characters"):
        load_policy(too_long)

    too_many = tmp_path / "too-many.yaml"
    too_many.write_text(yaml.safe_dump({
        "policy_version": "1.0",
        "patterns": [{"category": "custom", "regex": f"PATTERN_{i}"} for i in range(MAX_POLICY_PATTERNS + 1)],
        "explicit_tokens": [],
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="exceeds 128 patterns"):
        load_policy(too_many)



def test_empty_optional_compatibility_is_rejected_when_present(tmp_path: Path) -> None:
    package = tmp_path / "sample-skill"
    package.mkdir()
    (package / "SKILL.md").write_text(
        "\n".join([
            "---", "name: sample-skill", "description: A skill.",
            'compatibility: ""', "---", "", "Instructions.", "",
        ]),
        encoding="utf-8",
    )

    _inventory, findings, _texts = inspect_package(package)

    assert any(item.code == "COMPATIBILITY_INVALID" for item in findings)