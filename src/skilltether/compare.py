"""Line-, token-, and invariant-level comparison with reviewer-oriented evidence."""
from __future__ import annotations

import difflib
import hashlib
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

from .analysis import (
    MAX_MANIFEST_FILE_BYTES, MAX_POLICY_FILE_BYTES, extract_protected_tokens,
    inspect_package, load_policy, normalize_package_root, package_fingerprint,
)
from .models import ComparisonReport, InvariantManifest, new_finding
from .yamlio import safe_load_unique
from .safeio import read_bounded_regular_file
from . import __version__

FATAL_STRUCTURE_CODES = {
    "SKILL_MD_MISSING", "SKILL_MD_NOT_UTF8", "PACKAGE_TOO_LARGE", "FRONTMATTER_INVALID",
    "FRONTMATTER_REQUIRED_FIELD", "SKILL_NAME_INVALID", "SKILL_NAME_DIRECTORY_MISMATCH",
    "DESCRIPTION_TOO_LONG", "COMPATIBILITY_INVALID", "ALLOWED_TOOLS_INVALID",
    "METADATA_INVALID", "SKILL_BODY_EMPTY", "SYMLINK_NOT_ALLOWED", "FILE_TOO_LARGE",
    "FILE_STAT_ERROR", "FILE_READ_ERROR", "PATH_TRAVERSAL_LINK", "BROKEN_LOCAL_LINK",
    "SCRIPT_NOT_UTF8", "SPECIAL_FILE_NOT_ALLOWED", "RESOURCE_SYNTAX_INVALID", "MISSING_REFERENCED_RESOURCE",
    "PATH_TRAVERSAL_RESOURCE", "MDX_SYNTAX_UNSUPPORTED",
    "PACKAGE_PATH_NOT_PORTABLE", "PACKAGE_PATH_NORMALIZATION_COLLISION",
}
MAX_DIFF_LINE_CELLS = 4_000_000

CODE_CATEGORIES = {
    "code_block", "inline_code", "command_flag", "file_path", "windows_path",
    "environment_variable", "explicit_identifier",
}


def load_invariant_manifest(path: str | Path) -> InvariantManifest:
    source = read_bounded_regular_file(
        path, max_bytes=MAX_MANIFEST_FILE_BYTES, purpose="Invariant manifest",
    )
    raw = safe_load_unique(source.decode("utf-8"))
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
        raw = read_bounded_regular_file(
            policy_path, max_bytes=MAX_POLICY_FILE_BYTES, purpose="Protected-token policy",
        )
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
    source_root = normalize_package_root(source)
    target_root = normalize_package_root(target)
    source_inventory, source_findings, source_text = inspect_package(source_root)
    target_inventory, target_findings, target_text = inspect_package(target_root)
    findings = [*source_findings, *target_findings]
    patterns, explicit_tokens = load_policy(policy_path)
    policy_fingerprint = fingerprint_policy(policy_path)
    manifest_fingerprint = fingerprint_manifest(manifest)

    source_paths, target_paths = set(source_inventory), set(target_inventory)
    for path in sorted(source_paths & target_paths):
        source_mode = source_inventory[path].mode
        target_mode = target_inventory[path].mode
        if source_mode is None or target_mode is None or source_mode == target_mode:
            continue
        executable_changed = bool((source_mode ^ target_mode) & 0o111)
        findings.append(new_finding(
            "PACKAGE_FILE_MODE_CHANGED",
            "high" if executable_changed else "medium",
            "package_integrity",
            f"Target changes filesystem permission bits for {path!r}.",
            "Executable bits and read/write permissions can affect how scripts are launched or which package content is accessible.",
            path=path,
            original_context=f"mode:{source_mode:04o}",
            target_context=f"mode:{target_mode:04o}",
            proposed_change="Restore the original mode or explicitly review and document the intended permission change.",
            requires_review=True,
        ))

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
        if len(left_lines) * len(right_lines) > MAX_DIFF_LINE_CELLS:
            findings.append(new_finding(
                "TEXT_DIFF_COMPLEXITY_LIMIT", "high", "line_diff",
                f"Line-by-line comparison was skipped for {path!r} because the source/target line-pair budget was exceeded.",
                "Sequence matching can take quadratic time on adversarial repeated-line inputs. Skipping the detailed diff is explicit uncertainty, not a pass.",
                path=path,
                original_context=f"source_lines:{len(left_lines)}",
                target_context=f"target_lines:{len(right_lines)}",
                proposed_change="Review this resource manually or split long reference material into smaller resources, then rerun comparison.",
                requires_review=True,
                analysis_method="deterministic",
                uncertainty="high",
                severity_rationale="The report intentionally skipped a bounded comparison; missing findings must not be interpreted as semantic equivalence.",
            ))
            continue
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
            # Human review metadata is only useful when its source evidence still
            # anchors to this exact source package. Stale paths, line ranges, or
            # excerpts are deterministic integrity issues, not semantic guesses.
            source_reference_problem: str | None = None
            source_doc = source_text.get(invariant.source_path)
            if invariant.source_path not in source_inventory:
                source_reference_problem = "source path does not exist in the current source package"
            elif source_doc is None:
                source_reference_problem = "source path is not available as decoded UTF-8 text"
            elif invariant.source_lines:
                source_lines = source_doc.splitlines()
                start_line, end_line = invariant.source_lines
                if end_line > len(source_lines):
                    source_reference_problem = (
                        f"source line range {start_line}-{end_line} exceeds the current "
                        f"{len(source_lines)}-line resource"
                    )
                elif invariant.source_text is not None:
                    actual_excerpt = "\n".join(
                        line.strip() for line in source_lines[start_line - 1:end_line]
                    )
                    declared_excerpt = "\n".join(
                        line.strip() for line in invariant.source_text.splitlines()
                    )
                    if actual_excerpt != declared_excerpt:
                        source_reference_problem = (
                            "source_text no longer matches the declared source_lines range"
                        )
            elif invariant.source_text and invariant.source_text not in source_doc:
                source_reference_problem = (
                    "source_text is not present in the current source resource"
                )

            if source_reference_problem:
                findings.append(new_finding(
                    "INVARIANT_SOURCE_REFERENCE_INVALID", "critical", "semantic_invariant",
                    f"Invariant {invariant.id!r} has stale or invalid source evidence: {source_reference_problem}.",
                    "Human-reviewed invariants must remain anchored to the current source package; a stale quote or line range can cause reviewers to approve the wrong instruction.",
                    path=invariant.source_path,
                    source_line=invariant.source_lines[0] if invariant.source_lines else None,
                    original_context=invariant.source_text or invariant.statement,
                    proposed_change="Correct source_path, source_lines, and/or source_text to match the current source, then rerun comparison and review the updated manifest.",
                    requires_review=True,
                    analysis_method="deterministic",
                    uncertainty="none",
                    severity_rationale="The declared source reference can be checked deterministically and does not match the current package; approval must be blocked until corrected.",
                ))
                continue

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

            # For SKILL.md, align against the instruction body rather than allowing
            # metadata values to masquerade as translated instruction context.
            context_doc = target_doc
            context_offset = 1
            if invariant.source_path == "SKILL.md":
                target_lines = target_doc.splitlines()
                closing = next(
                    (index for index in range(1, len(target_lines)) if target_lines[index].strip() == "---"),
                    None,
                ) if target_lines and target_lines[0].strip() == "---" else None
                if closing is not None:
                    context_doc = "\n".join(target_lines[closing + 1:])
                    context_offset = closing + 2
            source_context_offset = 1
            if invariant.source_path == "SKILL.md":
                source_lines_for_alignment = source_doc.splitlines()
                if source_lines_for_alignment and source_lines_for_alignment[0].strip() == "---":
                    source_close = next(
                        (index for index in range(1, len(source_lines_for_alignment))
                         if source_lines_for_alignment[index].strip() == "---"),
                        None,
                    )
                    if source_close is not None:
                        source_context_offset = source_close + 2
            preferred_target_line = None
            if (
                invariant.source_lines
                and len(source_doc.splitlines()) == len(target_doc.splitlines())
            ):
                candidate_line = invariant.source_lines[0] - source_context_offset + 1
                if candidate_line > 0:
                    preferred_target_line = candidate_line
            alignment = _find_invariant_context(
                context_doc,
                invariant.source_text or invariant.statement,
                preferred_line=preferred_target_line,
            )
            if alignment is None:
                target_line, target_context = None, None
                alignment_method = None
            else:
                relative_line, target_context, alignment_method = alignment
                target_line = context_offset + relative_line - 1
            if alignment_method == "positional":
                findings.append(new_finding(
                    "INVARIANT_TARGET_CONTEXT_POSITIONAL", "info", "semantic_invariant",
                    f"Invariant {invariant.id!r} was aligned by preserved source/target line position, not by shared vocabulary.",
                    "This fallback supports translated languages with no shared words, but unchanged line counts do not prove that the target sentence has the same meaning.",
                    path=invariant.source_path,
                    source_line=invariant.source_lines[0] if invariant.source_lines else None,
                    target_line=target_line,
                    original_context=invariant.source_text or invariant.statement,
                    target_context=target_context,
                    proposed_change="Review this target line against the complete source instruction and its surrounding conditions.",
                    requires_review=False,
                    analysis_method="heuristic",
                    uncertainty="high",
                    severity_rationale="The context location is approximate; the report records the method so it cannot be mistaken for semantic confirmation.",
                ))

            if invariant.severity in {"high", "critical"} and target_context is None:
                findings.append(new_finding(
                    "INVARIANT_TARGET_CONTEXT_UNCERTAIN", "high", "semantic_invariant",
                    f"Invariant {invariant.id!r} could not be aligned confidently to a target-language context.",
                    "Word-overlap matching is not multilingual semantic alignment; review is required when the target sentence cannot be located.",
                    path=invariant.source_path,
                    source_line=invariant.source_lines[0] if invariant.source_lines else None,
                    target_line=target_line,
                    original_context=invariant.source_text or invariant.statement,
                    proposed_change="Locate the corresponding target sentence manually and review it against this invariant.",
                    requires_review=True,
                    analysis_method="heuristic",
                    uncertainty="high",
                ))

            for expected in dict.fromkeys(invariant.required_tokens + invariant.expected_numbers):
                missing_from_document = expected not in target_doc
                missing_from_context = not target_context or expected not in target_context
                if expected and (missing_from_document or missing_from_context):
                    findings.append(new_finding(
                        "INVARIANT_REQUIRED_TOKEN_MISSING", invariant.severity, "semantic_invariant",
                        f"Invariant {invariant.id!r} requires {expected!r}, which is absent from the document or matched target context.",
                        "A required literal or numeric bound must be present in the appropriate instruction, not merely elsewhere in the package.",
                        path=invariant.source_path,
                        source_line=invariant.source_lines[0] if invariant.source_lines else None,
                        target_line=target_line,
                        original_context=invariant.source_text or invariant.statement,
                        target_context=target_context,
                        proposed_change=f"Restore {expected!r} in the corresponding target instruction if required, or revise the manifest after human review.",
                        requires_review=True,
                        analysis_method="deterministic" if missing_from_document else "heuristic",
                        uncertainty="none" if missing_from_document else "high",
                    ))

            for forbidden in invariant.forbidden_tokens:
                if not forbidden or forbidden not in target_doc:
                    continue
                if target_context and forbidden in target_context:
                    findings.append(new_finding(
                        "INVARIANT_FORBIDDEN_TOKEN_PRESENT", invariant.severity, "semantic_invariant",
                        f"Invariant {invariant.id!r} forbids a token found in the aligned target context ({forbidden!r}).",
                        "The approximate context matcher located the forbidden literal in the instruction excerpt; confirm surrounding linguistic and example context.",
                        path=invariant.source_path,
                        source_line=invariant.source_lines[0] if invariant.source_lines else None,
                        target_line=target_line,
                        original_context=invariant.source_text or invariant.statement,
                        target_context=target_context,
                        proposed_change="Review the aligned instruction and remove the forbidden value if the invariant applies in this context.",
                        requires_review=True,
                        analysis_method="heuristic",
                        uncertainty="high",
                    ))
                else:
                    findings.append(new_finding(
                        "INVARIANT_FORBIDDEN_TOKEN_CONTEXT_UNCERTAIN", invariant.severity, "semantic_invariant",
                        f"Invariant {invariant.id!r} forbids {forbidden!r}, which occurs in the target file but was not found in the aligned instruction context.",
                        "A document-wide match may be an unrelated example or another instruction; do not treat it as a confirmed invariant violation without contextual review.",
                        path=invariant.source_path,
                        source_line=invariant.source_lines[0] if invariant.source_lines else None,
                        target_line=target_line,
                        original_context=invariant.source_text or invariant.statement,
                        target_context=target_context,
                        proposed_change="Locate the corresponding target instruction and confirm whether the forbidden literal violates this invariant.",
                        requires_review=True,
                        analysis_method="heuristic",
                        uncertainty="high",
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
                    path=invariant.source_path,
                    source_line=invariant.source_lines[0] if invariant.source_lines else None,
                    target_line=target_line,
                    original_context=invariant.source_text or invariant.statement,
                    target_context=target_context,
                    proposed_change="Configure locale-specific markers with a qualified reviewer, then rerun comparison.",
                    requires_review=True,
                ))
            if invariant.negation_required and invariant.negation_markers and (
                not target_context or not _contains_any_marker(target_context, invariant.negation_markers)
            ):
                findings.append(new_finding(
                    "INVARIANT_NEGATION_UNCERTAIN", "critical", "semantic_invariant",
                    f"Invariant {invariant.id!r} requires a target-language negation marker in the matched instruction, but none was detected confidently.",
                    "Negation loss or reversal can invert a safety instruction; global marker presence elsewhere in the package is not sufficient.",
                    path=invariant.source_path,
                    source_line=invariant.source_lines[0] if invariant.source_lines else None,
                    target_line=target_line,
                    original_context=invariant.source_text or invariant.statement,
                    target_context=target_context,
                    proposed_change="Inspect the corresponding target sentence manually and update locale-specific markers only after review.",
                    requires_review=True,
                ))
            if invariant.mandatory_required and invariant.mandatory_markers and (
                not target_context or not _contains_any_marker(target_context, invariant.mandatory_markers)
            ):
                findings.append(new_finding(
                    "INVARIANT_MODALITY_UNCERTAIN", "critical", "semantic_invariant",
                    f"Invariant {invariant.id!r} requires a mandatory marker in the matched target instruction, but none was detected confidently.",
                    "A mandatory instruction may have been weakened; global marker presence elsewhere in the package is not enough to establish modality.",
                    path=invariant.source_path,
                    source_line=invariant.source_lines[0] if invariant.source_lines else None,
                    target_line=target_line,
                    original_context=invariant.source_text or invariant.statement,
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
                    target_line=target_line,
                    original_context=invariant.source_text or invariant.statement,
                    target_context=target_context,
                    proposed_change="Have a qualified human compare the complete source and target contexts, then disposition this finding.",
                    requires_review=True,
                ))

    # Count-preserving reordering is a distinct risk from token deletion. A
    # changed sequence can alter CLI option/operand relationships even when every
    # token is still present, so ask for review without claiming semantic certainty.
    source_machine: dict[str, list] = {}
    target_machine: dict[str, list] = {}
    for item in source_token_objects:
        if item.category in CODE_CATEGORIES:
            source_machine.setdefault(item.path, []).append(item)
    for item in target_token_objects:
        if item.category in CODE_CATEGORIES:
            target_machine.setdefault(item.path, []).append(item)
    for path in sorted(set(source_machine) & set(target_machine)):
        left_tokens = sorted(
            source_machine[path],
            key=lambda item: (item.line, item.column if item.column is not None else 0, item.category, item.value),
        )
        right_tokens = sorted(
            target_machine[path],
            key=lambda item: (item.line, item.column if item.column is not None else 0, item.category, item.value),
        )
        left_sequence = [(item.category, item.value) for item in left_tokens]
        right_sequence = [(item.category, item.value) for item in right_tokens]
        if Counter(left_sequence) != Counter(right_sequence) or left_sequence == right_sequence:
            continue
        first_difference = next(
            (index for index, (left_item, right_item) in enumerate(zip(left_sequence, right_sequence, strict=True))
             if left_item != right_item),
            None,
        )
        if first_difference is None:
            continue
        left_item = left_tokens[first_difference]
        right_item = right_tokens[first_difference]
        source_lines = source_text[path].splitlines()
        target_lines = target_text[path].splitlines()
        original_context = source_lines[left_item.line - 1][:1000] if left_item.line <= len(source_lines) else left_item.value
        target_context = target_lines[right_item.line - 1][:1000] if right_item.line <= len(target_lines) else right_item.value
        findings.append(new_finding(
            "PROTECTED_TOKEN_ORDER_CHANGED", "high", "protected_token",
            "The target changes the order of protected machine-facing tokens while retaining the same token multiset.",
            "Counts alone do not preserve order-sensitive command arguments or operand relationships. This heuristic cannot determine whether the reordering is harmless in context.",
            path=path, source_line=left_item.line, target_line=right_item.line,
            original_context=original_context, target_context=target_context,
            proposed_change="Restore source order or document and approve the intended reordering after reviewing the full instruction.",
            requires_review=True, analysis_method="heuristic", uncertainty="high",
            severity_rationale="A reordered command flag, identifier, or path can change operational behavior; the heuristic requires human review rather than asserting semantic failure.",
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


def _normalized_marker_text(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", value).casefold()).strip()


def _contains_any_marker(text: str, markers: list[str]) -> bool:
    normalized_text = _normalized_marker_text(text)
    return any(
        (normalized := _normalized_marker_text(marker)) and normalized in normalized_text
        for marker in markers
    )


def _find_invariant_context(
    text: str,
    statement: str,
    *,
    preferred_line: int | None = None,
) -> tuple[int, str, str] | None:
    """Locate likely target context by token overlap or a clearly labelled positional fallback."""
    words = {
        word.casefold()
        for word in re.findall(r"[\w-]{3,}", unicodedata.normalize("NFC", statement))
    }
    lines = text.splitlines()
    scored = [
        (
            len(words & {
                word.casefold()
                for word in re.findall(r"[\w-]{3,}", unicodedata.normalize("NFC", line))
            }),
            index,
            line,
        )
        for index, line in enumerate(lines, start=1)
    ]
    score, line_number, line = max(scored, default=(0, 1, ""))
    # A weak one-word collision must not beat a known line-preserving mapping.
    threshold = max(2, min(3, (len(words) + 3) // 4))
    if score >= threshold:
        return line_number, line[:1000], "word-overlap"
    if preferred_line is not None and 1 <= preferred_line <= len(lines):
        positional = lines[preferred_line - 1]
        if positional.strip():
            return preferred_line, positional[:1000], "positional"
    return None
