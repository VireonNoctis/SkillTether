"""Command-line interface for validation, translation, comparison, review, and approval."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

import yaml
from pydantic import ValidationError

from . import __version__
from .analysis import inspect_package, load_policy, normalize_package_root, package_fingerprint
from .compare import compare_packages, fingerprint_manifest, fingerprint_policy, load_invariant_manifest
from .history import default_history_path, record_event
from .models import Invariant, InvariantManifest
from .report import read_json_report, verify_report_signature, write_json_report, write_markdown_report
from .signing import create_signing_key
from .translation import HttpJsonAdapter, IdentityAdapter, translate_package
from .reviewing import has_audited_approval, record_review

CUE_PATTERN = re.compile(
    r"\b(must|must not|mustn't|never|do not|don't|only if|unless|at least|at most|no more than|required|before|after|if)\b|\d",
    re.I,
)
NEGATION_PATTERN = re.compile(r"\b(not|never|no|without|don't|doesn't|mustn't|cannot|can't)\b", re.I)
MANDATORY_PATTERN = re.compile(r"\b(must|required|shall|mandatory)\b", re.I)
NUMBER_PATTERN = re.compile(r"(?<![A-Za-z])(?:[<>]=?\s*)?\d+(?:[.,]\d+)?(?:\s*(?:%|seconds?|minutes?|hours?|days?|files?|tokens?))?", re.I)


def _manifest_arg(path_value: str | None, source: Path) -> InvariantManifest | None:
    if path_value:
        return load_invariant_manifest(path_value)
    fallback = source / ".skilltether-invariants.yaml"
    if fallback.exists():
        return load_invariant_manifest(fallback)
    return None


def _terminal_safe(value: object) -> str:
    """Collapse control characters so untrusted paths and excerpts cannot alter the terminal."""
    return re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", str(value))


def _show_findings(findings) -> None:
    if not findings:
        print("No findings.")
        return
    for finding in findings:
        location = finding.path or "(package)"
        if finding.source_line:
            location += f":{finding.source_line}"
        print(f"[{finding.severity.upper():8}] {_terminal_safe(finding.code)} {_terminal_safe(location)} — {_terminal_safe(finding.message)}")
    counts = {}
    for finding in findings:
        counts[finding.severity] = counts.get(finding.severity, 0) + 1
    print("Finding counts: " + ", ".join(f"{level}={counts[level]}" for level in sorted(counts)))


def _fingerprint_path(root: Path) -> str:
    inventory, _findings, _texts = inspect_package(root)
    return package_fingerprint(inventory)


def _ensure_outputs_outside_packages(
    outputs: list[Path], packages: list[Path], *, label: str,
) -> list[Path]:
    """Prevent report/history outputs from overwriting or polluting skill packages."""
    raw_outputs = [Path(item).expanduser() for item in outputs]
    # Compare both normalized lexical paths and resolved paths: resolving only the
    # final component could hide an output symlink located inside a protected package.
    lexical_outputs = [Path(os.path.abspath(item)) for item in raw_outputs]
    resolved_outputs = [item.resolve() for item in raw_outputs]
    if len(set(resolved_outputs)) != len(resolved_outputs):
        raise ValueError(f"{label} output paths must be distinct")
    resolved_packages = [Path(item).expanduser().resolve() for item in packages]
    for lexical, resolved in zip(lexical_outputs, resolved_outputs, strict=True):
        for candidate in (lexical, resolved):
            for package in resolved_packages:
                if candidate == package or candidate in package.parents or package in candidate.parents:
                    raise ValueError(
                        f"{label} output must be outside source/candidate package directories: {lexical}"
                    )
    # Return the lexical path so atomic report writing replaces a final-component
    # symlink instead of following it to an unrelated external file.
    return lexical_outputs


def cmd_validate(args: argparse.Namespace) -> int:
    _inventory, findings, _texts = inspect_package(args.package)
    if args.json:
        print(json.dumps([item.model_dump(mode="json") for item in findings], indent=2, ensure_ascii=False))
    else:
        _show_findings(findings)
    return 1 if any(item.severity in ("high", "critical") for item in findings) else 0


def _suggest_invariants(source_root: Path, source_locale: str, target_locale: str | None) -> InvariantManifest:
    inventory, findings, texts = inspect_package(source_root)
    if "SKILL.md" not in texts:
        raise ValueError("Cannot suggest invariants without a readable SKILL.md")
    suggestions: list[Invariant] = []
    for line_no, line in enumerate(texts["SKILL.md"].splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("|") or stripped.startswith("~~~"):
            continue
        if not CUE_PATTERN.search(stripped):
            continue
        if len(stripped) > 1200:
            continue
        lower = stripped.lower()
        if NEGATION_PATTERN.search(lower):
            category = "negation"
            severity = "critical"
        elif NUMBER_PATTERN.search(stripped):
            category = "numeric_limit"
            severity = "critical"
        elif MANDATORY_PATTERN.search(lower):
            category = "mandatory_condition"
            severity = "high"
        elif re.search(r"\b(if|unless|before|after|only if)\b", lower):
            category = "precondition"
            severity = "high"
        else:
            category = "decision_rule"
            severity = "high"
        numbers = NUMBER_PATTERN.findall(stripped)
        # A single line is a draft candidate. Review and refine before marking it trusted.
        suggestions.append(Invariant(
            id=f"INV-{len(suggestions)+1:04d}",
            statement=stripped.lstrip("-*0123456789. "),
            category=category,
            severity=severity,
            source_path="SKILL.md",
            source_lines=(line_no, line_no),
            source_text=stripped,
            expected_numbers=sorted(set(n.strip() for n in numbers if n.strip())),
            negation_required=category == "negation",
            mandatory_required=category == "mandatory_condition",
            reviewed=False,
        ))
    return InvariantManifest(
        source_locale=source_locale, target_locale=target_locale, invariants=suggestions,
        manifest_reviewed=False,
    )


def cmd_init_signing_key(args: argparse.Namespace) -> int:
    path = create_signing_key(args.out)
    print(f"Created private report signing key: {_terminal_safe(path)}")
    print("Keep this key private and backed up; losing it prevents verification or updates to signed reports.")
    return 0


def cmd_init_manifest(args: argparse.Namespace) -> int:
    source = normalize_package_root(args.source)
    manifest = _suggest_invariants(source, args.source_locale, args.target_locale)
    output = Path(args.out).expanduser()
    if output.exists():
        raise FileExistsError(f"Manifest output already exists: {output}; choose a new path so reviewed rules are not overwritten")
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = manifest.model_dump(mode="json", exclude_none=True)
    output.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"Wrote {len(manifest.invariants)} draft invariant candidates to {output}")
    print("Review every candidate and its locale-specific markers before setting manifest_reviewed=true.")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    if args.target_locale:
        _validate_locale_tag(args.target_locale)
    source = normalize_package_root(args.source)
    target = normalize_package_root(args.target)
    requested_outputs = [Path(args.out).expanduser()]
    if args.markdown:
        requested_outputs.append(Path(args.markdown).expanduser())
    guarded_paths = list(requested_outputs)
    if args.signing_key:
        guarded_paths.append(Path(args.signing_key).expanduser())
    checked_paths = _ensure_outputs_outside_packages(
        guarded_paths, [source, target], label="Report/signing-key",
    )
    report_outputs = checked_paths[:len(requested_outputs)]
    manifest = _manifest_arg(args.invariants, source)
    report = compare_packages(
        source, target, manifest, target_locale=args.target_locale,
        policy_path=args.policy,
    )
    write_json_report(report, report_outputs[0], signing_key=args.signing_key)
    if args.markdown:
        write_markdown_report(report, report_outputs[1])
    _show_findings(report.findings)
    print(f"Report: {args.out}")
    print(f"Structural status: {report.structural_status}; semantic status: {report.semantic_status}")
    review_gate = args.fail_on_review and report.semantic_status in ("review_recommended", "unknown")
    return 1 if report.structural_status in ("fail", "error") or review_gate else 0


def _validate_locale_tag(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*", value):
        raise ValueError(f"Locale {value!r} is not a valid-looking BCP 47 language tag")
    return value


def cmd_translate(args: argparse.Namespace) -> int:
    _validate_locale_tag(args.source_locale)
    _validate_locale_tag(args.target_locale)
    source = normalize_package_root(args.source)
    output = Path(args.output).expanduser().resolve()
    report_requested = Path(args.report).expanduser() if args.report else output.with_name(output.name + ".report.json")
    history_requested = Path(args.history_db).expanduser() if args.history_db else default_history_path()
    guarded_paths = [report_requested, history_requested]
    if args.signing_key:
        guarded_paths.append(Path(args.signing_key).expanduser())
    output_paths = _ensure_outputs_outside_packages(
        guarded_paths, [source, output], label="Report/history/signing-key",
    )
    report_path, history_path = output_paths[:2]
    if args.adapter == "identity":
        adapter = IdentityAdapter()
        print("Using the identity adapter: no prose will be translated; this exercises the safe pipeline only.")
    else:
        if not args.allow_remote:
            raise ValueError("Remote translation requires --allow-remote after reviewing the endpoint's data handling.")
        if not args.endpoint:
            raise ValueError("--endpoint is required with --adapter http-json")
        adapter = HttpJsonAdapter(args.endpoint)

    protected_patterns, explicit_tokens = load_policy(args.policy)
    source_inventory, target_inventory, changed = translate_package(
        source, output, adapter, args.source_locale, args.target_locale,
        protected_patterns=protected_patterns, explicit_tokens=explicit_tokens,
    )
    manifest = _manifest_arg(args.invariants, source)
    report = compare_packages(
        source, output, manifest, target_locale=args.target_locale, policy_path=args.policy,
    )
    report.translation_provider = adapter.name
    write_json_report(report, report_path, signing_key=args.signing_key)
    history_path = record_event(
        source_fingerprint=package_fingerprint(source_inventory),
        target_fingerprint=package_fingerprint(target_inventory),
        source_locale=args.source_locale, target_locale=args.target_locale,
        provider=adapter.name, status="candidate_written",
        database=history_path,
    )
    print(f"Candidate package: {output}")
    print(f"Translated text files changed: {changed}")
    print(f"Comparison report: {report_path}")
    print(f"Local run metadata: {history_path}")
    print("This is an unapproved candidate. Run review decisions and skilltether approve before distributing it.")
    review_gate = args.fail_on_review and report.semantic_status in ("review_recommended", "unknown")
    return 1 if report.structural_status in ("fail", "error") or review_gate else 0


def cmd_verify_report(args: argparse.Namespace) -> int:
    report = read_json_report(args.report)
    verify_report_signature(report, args.signing_key, require_signature=True)
    print("Report integrity verified (HMAC-SHA256).")
    print(f"Structural status: {report.structural_status}; semantic status: {report.semantic_status}")
    print(f"Findings: {len(report.findings)}")
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    report = read_json_report(args.report)
    verify_report_signature(report, args.signing_key)
    matched = [finding for finding in report.findings if finding.id == args.finding_id]
    if len(matched) != 1:
        raise ValueError(f"Finding ID not found or not unique: {args.finding_id}")
    finding = matched[0]
    record_review(
        finding, disposition=args.disposition, reviewer=args.reviewer, note=args.note,
    )
    write_json_report(report, args.report, signing_key=args.signing_key)
    print(f"Recorded {args.disposition} disposition for {_terminal_safe(finding.id)} by {_terminal_safe(finding.reviewer)}; prior decisions were retained.")
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    source = normalize_package_root(args.source)
    target = normalize_package_root(args.target)
    report_path = Path(args.report).expanduser().resolve(strict=True)
    output = Path(args.output).expanduser().resolve()
    if args.signing_key:
        _ensure_outputs_outside_packages(
            [Path(args.signing_key).expanduser()], [source, target, output],
            label="Signing key",
        )
    report = read_json_report(report_path)
    verify_report_signature(
        report, args.signing_key, require_signature=bool(args.signing_key),
    )
    current_manifest = _manifest_arg(args.invariants, source)
    if fingerprint_manifest(current_manifest) != report.invariant_manifest_fingerprint:
        raise ValueError("Invariant manifest fingerprint differs from the reviewed report; rerun compare")
    if fingerprint_policy(args.policy) != report.protected_policy_fingerprint:
        raise ValueError("Protected-token policy fingerprint differs from the reviewed report; rerun compare with the same policy")
    if output.exists():
        raise FileExistsError(f"Approved output already exists: {output}")
    if output.name != target.name:
        raise ValueError("Approved output directory basename must match the skill package directory name")
    if source == target or source in target.parents or target in source.parents:
        raise ValueError("Source and candidate directories must be separate and non-overlapping")
    if output == source or output == target or source in output.parents or target in output.parents or output in source.parents or output in target.parents:
        raise ValueError("Approved output must be a separate, non-overlapping directory")

    if _fingerprint_path(source) != report.source_fingerprint:
        raise ValueError("Source package changed after comparison; rerun compare before approval")
    if _fingerprint_path(target) != report.target_fingerprint:
        raise ValueError("Candidate package changed after comparison; rerun compare before approval")
    if report.structural_status != "pass":
        raise ValueError("Structural validation failed. Fix the package and rerun comparison before approval.")
    permanently_blocked = {
        "INVARIANT_MANIFEST_MISSING", "INVARIANT_MANIFEST_UNREVIEWED", "INVARIANT_NOT_HUMAN_REVIEWED",
        "INVARIANT_SOURCE_REFERENCE_INVALID",
    }
    blocked = [finding for finding in report.findings if finding.code in permanently_blocked]
    if blocked:
        raise ValueError("The invariant manifest is missing, unreviewed, or contains invalid source references; correct it and rerun comparison before approval.")
    unresolved = [
        finding for finding in report.findings
        if (finding.requires_review or finding.severity == "critical")
        and not has_audited_approval(finding)
    ]
    if unresolved:
        preview = ", ".join(f.id for f in unresolved[:8])
        raise ValueError(
            f"{len(unresolved)} review-required finding(s) lack a current, audited approval "
            f"with a reviewer and non-empty rationale: {preview}"
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    import tempfile

    temp_parent = Path(tempfile.mkdtemp(prefix=f".{output.name}.approved-", dir=output.parent))
    temp_package = temp_parent / output.name
    try:
        # Preserve a late-arriving symlink in the private staging tree. The
        # post-copy fingerprint check then rejects it without reading through it.
        shutil.copytree(target, temp_package, symlinks=True)
        if _fingerprint_path(temp_package) != report.target_fingerprint:
            raise RuntimeError("Approved output fingerprint mismatch; nothing was published")
        os.replace(temp_package, output)
    finally:
        shutil.rmtree(temp_parent, ignore_errors=True)
    print(f"Approved package written to: {output}")
    print(f"Approval evidence: {report_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skilltether",
        description="Local-first localization integrity checks for Agent Skill packages.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    init_key = sub.add_parser("init-signing-key", help="create a private local key for signed report integrity")
    init_key.add_argument("--out", required=True, help="new key file path; existing files are never overwritten")
    init_key.set_defaults(func=cmd_init_signing_key)

    validate = sub.add_parser("validate", help="validate SKILL.md metadata, structure, and local links")
    validate.add_argument("package")
    validate.add_argument("--json", action="store_true", help="print findings as JSON")
    validate.set_defaults(func=cmd_validate)

    init_manifest = sub.add_parser("init-manifest", help="suggest invariant candidates for human review")
    init_manifest.add_argument("source")
    init_manifest.add_argument("--out", required=True)
    init_manifest.add_argument("--source-locale", required=True)
    init_manifest.add_argument("--target-locale")
    init_manifest.set_defaults(func=cmd_init_manifest)

    compare = sub.add_parser("compare", help="compare source and localized package")
    compare.add_argument("source")
    compare.add_argument("target")
    compare.add_argument("--invariants", help="human-reviewed YAML invariant manifest")
    compare.add_argument("--target-locale")
    compare.add_argument("--policy", help="protected-token policy YAML")
    compare.add_argument("--out", required=True, help="JSON report path")
    compare.add_argument("--markdown", help="optional Markdown report path")
    compare.add_argument("--signing-key", help="optional private HMAC key; seals the JSON report")
    compare.add_argument(
        "--fail-on-review", action="store_true",
        help="return exit code 1 when semantic findings require human review or meaning is unknown",
    )
    compare.set_defaults(func=cmd_compare)

    translate = sub.add_parser("translate", help="create a separate candidate package and comparison report")
    translate.add_argument("source")
    translate.add_argument("output", help="new candidate directory, with the same basename as the skill root")
    translate.add_argument("--source-locale", required=True)
    translate.add_argument("--target-locale", required=True)
    translate.add_argument("--adapter", choices=["identity", "http-json"], default="identity")
    translate.add_argument("--endpoint", help="provider-neutral JSON translation endpoint")
    translate.add_argument("--allow-remote", action="store_true", help="explicit consent to transmit eligible prose")
    translate.add_argument("--invariants")
    translate.add_argument("--policy")
    translate.add_argument("--report")
    translate.add_argument("--signing-key", help="optional private HMAC key; seals the JSON report")
    translate.add_argument("--history-db", help="optional local SQLite path (default: ~/.skilltether/history.sqlite3)")
    translate.add_argument(
        "--fail-on-review", action="store_true",
        help="return exit code 1 when the generated report requires human review or meaning is unknown",
    )
    translate.set_defaults(func=cmd_translate)

    verify_report = sub.add_parser(
        "verify-report", help="verify the HMAC integrity seal on a signed JSON report",
    )
    verify_report.add_argument("report")
    verify_report.add_argument("--signing-key", required=True, help="private HMAC key used to seal the report")
    verify_report.set_defaults(func=cmd_verify_report)

    review = sub.add_parser("review", help="record a human disposition for a report finding")
    review.add_argument("report")
    review.add_argument("finding_id")
    review.add_argument("--disposition", choices=["approved", "rejected", "deferred"], required=True)
    review.add_argument("--reviewer", required=True)
    review.add_argument("--note", required=True, help="non-empty rationale; obvious credential material is rejected")
    review.add_argument("--signing-key", help="key required to verify/re-sign a sealed report")
    review.set_defaults(func=cmd_review)

    approve = sub.add_parser("approve", help="copy a reviewed candidate to a new approved output directory")
    approve.add_argument("source")
    approve.add_argument("target")
    approve.add_argument("--report", required=True)
    approve.add_argument("--output", required=True)
    approve.add_argument("--invariants", help="same invariant manifest used for comparison")
    approve.add_argument("--policy", help="same protected-token policy used for comparison")
    approve.add_argument("--signing-key", help="verify HMAC-sealed approval evidence; requires a signed report")
    approve.set_defaults(func=cmd_approve)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError, ValidationError, yaml.YAMLError, RuntimeError) as exc:
        print(f"skilltether: error: {_terminal_safe(exc)}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
