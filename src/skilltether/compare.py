"""Line-, token-, and invariant-level comparison with reviewer-oriented evidence."""
from __future__ import annotations

import difflib
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import yaml

from .analysis import extract_protected_tokens, inspect_package, load_policy, package_fingerprint
from .models import ComparisonReport, InvariantManifest, new_finding
from .yamlio import safe_load_unique
from . import __version__

FATAL_STRUCTURE_CODES = {
    "SKILL_MD_MISSING", "SKILL_MD_NOT_UTF8", "FRONTMATTER_INVALID",
    "FRONTMATTER_REQUIRED_FIELD", "SKILL_NAME_INVALID", "SKILL_NAME_DIRECTORY_MISMATCH",
    "DESCRIPTION_TOO_LONG", "COMPATIBILITY_INVALID", "ALLOWED_TOOLS_INVALID",
    "METADATA_INVALID", "SKILL_BODY_EMPTY", "SYMLINK_NOT_ALLOWED", "FILE_TOO_LARGE",
    "FILE_STAT_ERROR", "FILE_READ_ERROR", "PATH_TRAVERSAL_LINK", "BROKEN_LOCAL_LINK",
    "SCRIPT_NOT_UTF8", "SPECIAL_FILE_NOT_ALLOWED", "RESOURCE_SYNTAX_INVALID", "MISSING_REFERENCED_RESOURCE",
    "PATH_TRAVERSAL_RESOURCE",
}
CODE_CATEGORIES = {
    "code_block", "inline_code", "command_flag", "file_path", "windows_path",
    "environment_variable", "explicit_identifier",
}


def load_invariant_manifest(path: str | Path) -> InvariantManifest:
    raw = safe_load_unique(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Invariant manifest must be a YAML mapping")
    return InvariantManifest.model_validate(raw)



def fingerprint_manifest(manifest: InvariantManifest | None) -> str | None:
    """Stable fingerprint of normalized manifest contracts and reviewer decisions."""
    if manifest is None:
        return None
    payload = json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def fingerprint_policy(policy_path: str | Path | None) -> str:
    """Fingerprint explicit policy bytes or the versioned built-in policy."""
    if policy_path is None:
        raw = b"skilltether-builtin-protected-policy-v1"
    else:
        raw = Path(policy_path).read_bytes()
    return hashlib.sha256(raw).hexdigest()

def compare_packages(
    source: str | Path,
    target: str | Path,
    manifest: InvariantManifest | None = None,
    *,
    target_locale: str | None = None,
    policy_path: str | Path | None = None,
) -> ComparisonReport:
    """Compare packages without executing their scripts or making network calls."""
    source_root = Path(source).expanduser().resolve(strict=True)
    target_root = Path(target).expanduser().resolve(strict=True)
    source_inventory, source_findings, source_text = inspect_package(source_root)
    target_inventory, target_findings, target_text = inspect_package(target_root)
    findings = [*source_findings, *target_findings]
    patterns, explicit_tokens = load_policy(policy_path)
    policy_fingerprint = fingerprint_policy(policy_path)
    manifest_fingerprint = fingerprint_manifest(manifest)

    source_paths, target_paths = set(source_inventory), set(target_inventory)
    for missing in sorted(source_paths - target_paths):
        severity = "critical" if missing == "SKILL.md" else "high"
        findings.append(new_finding(
            "PACKAGE_FILE_MISSING", severity, "package_integrity",
            f"Target package omits source file {missing!r}.",
            "Package resources and relative paths should survive localization unless an explicit reviewed mapping says otherwise.",
            path=missing, proposed_change="Restore this file at its original relative path or document and approve its intentional removal.",
            requires_review=True,
        ))
    for added in sorted(target_paths - source_paths):
        findings.append(new_finding(
            "PACKAGE_FILE_ADDED", "medium", "package_integrity",
            f"Target package adds file {added!r} that is not present in the source.",
            "Unexpected resources may introduce unsupported instructions or executable content.",
            path=added, proposed_change="Confirm the new file is required and review its content.",
            requires_review=True,
        ))

    # Byte-only resources (including images and unknown binary formats) are
    # part of package integrity too. They do not appear in source_text/target_text,
    # so compare their hashes explicitly instead of silently overlooking edits.
    for path in sorted(source_paths & target_paths):
        source_file = source_inventory[path]
        target_file = target_inventory[path]
        if source_file.sha256 == target_file.sha256:
            continue
        if path in source_text and path in target_text:
            continue
        normalized = path.lower()
        executable_suffixes = {".exe", ".dll", ".so", ".dylib", ".bin", ".com"}
        is_executable_area = normalized.startswith("scripts/") or Path(path).suffix.lower() in executable_suffixes
        severity = "high" if is_executable_area else "medium"
        findings.append(new_finding(
            "PACKAGE_RESOURCE_CHANGED", severity, "package_integrity",
            f"Target changes bytes of a resource that is not compared as decoded text: {path!r}.",
            "Binary assets and unsupported text formats are part of the skill package; a byte change may alter behavior or user-visible output even when ordinary line comparison cannot inspect it.",
            path=path,
            original_context=f"sha256:{source_file.sha256}",
            target_context=f"sha256:{target_file.sha256}",
            proposed_change="Restore the original bytes or explicitly review and document why this non-text resource must change.",
            requires_review=True,
        ))

    for path in sorted(source_paths & target_paths):
        left, right = source_text.get(path), target_text.get(path)
        if left is None or right is None or left == right:
            continue
        left_lines, right_lines = left.splitlines(), right.splitlines()
        matcher = difflib.SequenceMatcher(a=left_lines, b=right_lines, autojunk=False)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                continue
            old = "\n".join(left_lines[i1:i2])
            new = "\n".join(right_lines[j1:j2])
            source_line = i1 + 1 if i1 < len(left_lines) else max(1, len(left_lines))
            target_line = j1 + 1 if j1 < len(right_lines) else max(1, len(right_lines))
            if tag == "delete":
                code, severity, category, requires = "CONTENT_OMITTED", "high", "content_diff", True
                message = "Target omits source content."
                rationale = "Omissions can remove a prerequisite, exception, safety constraint, or reference."
                proposed = "Restore the omitted content or record a reviewed rationale for its removal."
            elif tag == "insert":
                code, severity, category, requires = "CONTENT_ADDED", "medium", "content_diff", True
                message = "Target adds content not aligned to a source line."
                rationale = "Unexpected additions can create new operational instructions."
                proposed = "Confirm the addition is intentional and consistent with the reviewed invariant manifest."
            else:
                code, severity, category, requires = "LINE_CHANGED", "info", "line_diff", False
                message = "Source and target lines differ."
                rationale = "This line-level difference is evidence for review, not by itself proof of semantic drift."
                proposed = "Review the target wording against the source instruction and its invariants."
            findings.append(new_finding(
                code, severity, category, message, rationale, path=path,
                source_line=source_line, target_line=target_line,
                original_context=old[:2000], target_context=new[:2000],
                proposed_change=proposed, requires_review=requires,
            ))

    source_counter: Counter[tuple[str, str, str]] = Counter()
    target_counter: Counter[tuple[str, str, str]] = Counter()
    source_token_objects = []
    target_token_objects = []
    for path, text in source_text.items():
        source_token_objects.extend(extract_protected_tokens(text, path, patterns, explicit_tokens))
    for path, text in target_text.items():
        target_token_objects.extend(extract_protected_tokens(text, path, patterns, explicit_tokens))
    source_counter.update((item.path, item.category, item.value) for item in source_token_objects)
    target_counter.update((item.path, item.category, item.value) for item in target_token_objects)

    source_index = {(item.path, item.category, item.value): item for item in source_token_objects}
    target_index = {(item.path, item.category, item.value): item for item in target_token_objects}
    for token_key, source_count in sorted(source_counter.items()):
        if target_counter[token_key] >= source_count:
            continue
        path, category, value = token_key
        severity = "critical" if category in CODE_CATEGORIES else "high"
        findings.append(new_finding(
            "PROTECTED_TOKEN_CHANGED", severity, "protected_token",
            f"Protected {category} is missing or changed in the target ({value[:160]!r}).",
            "Machine-facing tokens must remain exact unless an explicit reviewed mapping permits a change.",
            path=path, source_line=source_index[token_key].line,
            target_line=target_index[token_key].line if token_key in target_index else None,
            original_context=value[:1000],
            proposed_change="Restore the exact token or document and approve an explicit token mapping.",
            requires_review=True,
        ))
    for token_key, target_count in sorted(target_counter.items()):
        if source_counter[token_key] >= target_count:
            continue
        path, category, value = token_key
        findings.append(new_finding(
            "PROTECTED_TOKEN_ADDED", "medium", "protected_token",
            f"Target adds a protected-looking {category} ({value[:160]!r}).",
            "A new command, path, URL, or identifier may indicate invented operational detail.",
            path=path, target_line=target_index[token_key].line, target_context=value[:1000],
            proposed_change="Confirm the new literal is required and does not add unrequested behavior.",
            requires_review=True,
        ))

    if manifest is None:
        findings.append(new_finding(
            "INVARIANT_MANIFEST_MISSING", "critical", "semantic_invariant",
            "No human-reviewed invariant manifest was supplied.",
            "A structural or token match cannot establish that safety conditions and decision rules survived translation.",
            path="SKILL.md", proposed_change="Create and review an invariant manifest, then rerun comparison.",
            requires_review=True,
        ))
    else:
        if manifest.target_locale and target_locale and manifest.target_locale.lower() != target_locale.lower():
            findings.append(new_finding(
                "INVARIANT_LOCALE_MISMATCH", "high", "semantic_invariant",
                "The manifest target locale differs from the requested comparison locale.",
                "Locale-specific negation and mandatory markers are meaningful only for the intended language.",
                path="SKILL.md", proposed_change="Update the manifest locale or compare against the declared target.",
                requires_review=True,
            ))
        if not manifest.manifest_reviewed:
            findings.append(new_finding(
                "INVARIANT_MANIFEST_UNREVIEWED", "critical", "semantic_invariant",
                "Invariant manifest has not been marked as human-reviewed.",
                "Automatically suggested invariants are candidate prompts, not approved safety policy.",
                path="SKILL.md", proposed_change="Review the manifest and set manifest_reviewed=true with a reviewer.",
                requires_review=True,
            ))
        for invariant in manifest.invariants:
            if not invariant.reviewed:
                findings.append(new_finding(
                    "INVARIANT_NOT_HUMAN_REVIEWED", "critical", "semantic_invariant",
                    f"Invariant {invariant.id!r} has not been human-reviewed.",
                    "Only human-confirmed invariant statements should gate translation approval.",
                    path=invariant.source_path,
                    source_line=invariant.source_lines[0] if invariant.source_lines else None,
                    original_context=invariant.source_text or invariant.statement,
                    proposed_change="Confirm the invariant statement and mark it reviewed with the reviewer's identifier.",
                    requires_review=True,
                ))
            target_doc = target_text.get(invariant.source_path)
            if target_doc is None:
                findings.append(new_finding(
                    "INVARIANT_RESOURCE_MISSING", "critical", "semantic_invariant",
                    f"Invariant {invariant.id!r} references a missing target file.",
                    "The instruction being checked is absent from the localized package.",
                    path=invariant.source_path, original_context=invariant.statement,
                    proposed_change="Restore the target resource at the original path.",
                    requires_review=True,
                ))
                continue
            target_context = _find_invariant_context(target_doc, invariant.source_text or invariant.statement)
            if invariant.severity == "high" and target_context is None:
                findings.append(new_finding(
                    "INVARIANT_TARGET_CONTEXT_UNCERTAIN", "high", "semantic_invariant",
                    f"Invariant {invariant.id!r} could not be aligned confidently to a target-language context.",
                    "Word-overlap matching is not multilingual semantic alignment; review is required when the target sentence cannot be located.",
                    path=invariant.source_path,
                    source_line=invariant.source_lines[0] if invariant.source_lines else None,
                    original_context=invariant.source_text or invariant.statement,
                    proposed_change="Locate the corresponding target sentence manually and review it against this invariant.",
                    requires_review=True,
                ))
            for expected in dict.fromkeys(invariant.required_tokens + invariant.expected_numbers):
                needs_context_match = expected in invariant.expected_numbers
                missing = expected not in target_doc or (
                    needs_context_match and (not target_context or expected not in target_context)
                )
                if expected and missing:
                    findings.append(new_finding(
                        "INVARIANT_REQUIRED_TOKEN_MISSING", invariant.severity, "semantic_invariant",
                        f"Invariant {invariant.id!r} requires {expected!r}, which is absent from the document or matched target context.",
                        "A required literal or numeric bound must be present in the appropriate instruction, not merely elsewhere in the package.",
                        path=invariant.source_path,
                        source_line=invariant.source_lines[0] if invariant.source_lines else None,
                        original_context=invariant.source_text or invariant.statement,
                        target_context=target_context,
                        proposed_change=f"Restore {expected!r} in the corresponding target instruction if required, or revise the manifest after human review.",
                        requires_review=True,
                    ))
            for forbidden in invariant.forbidden_tokens:
                if forbidden and forbidden in target_doc:
                    findings.append(new_finding(
                        "INVARIANT_FORBIDDEN_TOKEN_PRESENT", invariant.severity, "semantic_invariant",
                        f"Invariant {invariant.id!r} forbids a token present in the target ({forbidden!r}).",
                        "The target contains a value that this reviewed invariant says must not appear.",
                        path=invariant.source_path, original_context=invariant.source_text or invariant.statement,
                        proposed_change="Remove the forbidden value or revise the invariant after human review.",
                        requires_review=True,
                    ))
            unconfigured_marker_types = []
            if invariant.negation_required and not invariant.negation_markers:
                unconfigured_marker_types.append("negation")
            if invariant.mandatory_required and not invariant.mandatory_markers:
                unconfigured_marker_types.append("mandatory-modality")
            if unconfigured_marker_types:
                findings.append(new_finding(
                    "INVARIANT_MARKERS_UNCONFIGURED", "critical", "semantic_invariant",
                    f"Invariant {invariant.id!r} requires locale-specific marker configuration for {', '.join(unconfigured_marker_types)}.",
                    "Marker checks cannot run until appropriate target-language negation/mandatory markers are explicitly configured.",
                    path=invariant.source_path, original_context=invariant.source_text or invariant.statement,
                    target_context=target_context,
                    proposed_change="Configure locale-specific markers with a qualified reviewer, then rerun comparison.",
                    requires_review=True,
                ))
            if invariant.negation_required and invariant.negation_markers and (
                not target_context or not any(marker in target_context for marker in invariant.negation_markers)
            ):
                findings.append(new_finding(
                    "INVARIANT_NEGATION_UNCERTAIN", "critical", "semantic_invariant",
                    f"Invariant {invariant.id!r} requires a target-language negation marker in the matched instruction, but none was detected confidently.",
                    "Negation loss or reversal can invert a safety instruction; global marker presence elsewhere in the package is not sufficient.",
                    path=invariant.source_path, original_context=invariant.source_text or invariant.statement,
                    target_context=target_context,
                    proposed_change="Inspect the corresponding target sentence manually and update locale-specific markers only after review.",
                    requires_review=True,
                ))
            if invariant.mandatory_required and invariant.mandatory_markers and (
                not target_context or not any(marker in target_context for marker in invariant.mandatory_markers)
            ):
                findings.append(new_finding(
                    "INVARIANT_MODALITY_UNCERTAIN", "critical", "semantic_invariant",
                    f"Invariant {invariant.id!r} requires a mandatory marker in the matched target instruction, but none was detected confidently.",
                    "A mandatory instruction may have been weakened; global marker presence elsewhere in the package is not enough to establish modality.",
                    path=invariant.source_path, original_context=invariant.source_text or invariant.statement,
                    target_context=target_context,
                    proposed_change="Review modal strength in context and configure target-language markers deliberately.",
                    requires_review=True,
                ))
            if invariant.severity == "critical":
                findings.append(new_finding(
                    "CRITICAL_INVARIANT_REVIEW_REQUIRED", "critical", "semantic_invariant",
                    f"Critical invariant {invariant.id!r} requires explicit target-language sign-off.",
                    "Automated checks cannot guarantee semantic equivalence for a safety-critical instruction.",
                    path=invariant.source_path,
                    source_line=invariant.source_lines[0] if invariant.source_lines else None,
                    original_context=invariant.source_text or invariant.statement,
                    target_context=target_context,
                    proposed_change="Have a qualified human compare the complete source and target contexts, then disposition this finding.",
                    requires_review=True,
                ))

    structural_bad = any(finding.code in FATAL_STRUCTURE_CODES for finding in findings)
    semantic_review = any(f.requires_review or f.severity in ("medium", "high", "critical") for f in findings)
    return ComparisonReport.create(
        tool_version=__version__,
        source_locale=manifest.source_locale if manifest else None,
        target_locale=target_locale or (manifest.target_locale if manifest else None),
        invariant_manifest_fingerprint=manifest_fingerprint,
        protected_policy_fingerprint=policy_fingerprint,
        source_fingerprint=package_fingerprint(source_inventory),
        target_fingerprint=package_fingerprint(target_inventory),
        source_files={key: item.sha256 for key, item in sorted(source_inventory.items())},
        target_files={key: item.sha256 for key, item in sorted(target_inventory.items())},
        structural_status="fail" if structural_bad else "pass",
        semantic_status="review_recommended" if semantic_review else "no_issue_detected",
        limitations=[
            "Semantic similarity is heuristic; this report does not prove equivalence or safety.",
            "External URLs are not fetched. Only local paths and detected in-document fragments are checked.",
            "The invariant manifest must be reviewed by a human; suggested invariants are not authoritative.",
        ],
        findings=findings,
    )


def _find_invariant_context(text: str, statement: str) -> str | None:
    """Return a small target excerpt by approximate word overlap, not a semantic verdict."""
    words = {word.lower() for word in re.findall(r"[A-Za-z0-9_-]{4,}", statement)}
    if not words:
        return None
    lines = text.splitlines()
    scored = [
        (len(words & {w.lower() for w in re.findall(r"[A-Za-z0-9_-]{4,}", line)}), i, line)
        for i, line in enumerate(lines)
    ]
    score, _index, line = max(scored, default=(0, 0, ""))
    return line[:1000] if score > 0 else None
