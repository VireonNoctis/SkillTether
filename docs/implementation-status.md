# Implementation status

This page describes the repository implementation, not the entire long-term SkillTether vision. For traceability by requirement and test evidence, see [the readiness audit](readiness-audit.md). For CLI examples, see [the usage guide](usage.md).

## Implemented and regression-tested

### Package inspection and structural validation

- Read-only package inventory with SHA-256 fingerprints that include file mode/permission metadata.
- Bounded traversal, directory depth/count limits, per-file and aggregate byte budgets, non-following regular-file reads, and rejection of package-root symlink aliases, in-package symlinks, and special filesystem entries.
- Source packages are inspected but never intentionally rewritten. Candidate and approval output are staged separately, staged content and metadata are rechecked, and failed translation/approval does not publish a partial package.
- UTF-8 validation for expected text/script resources; arbitrary binary assets remain byte-oriented rather than being misclassified as malformed text.
- YAML frontmatter and required `SKILL.md` metadata checks, including required non-empty `name` and `description`, name syntax/length/directory identity, description length, and types for supported optional fields.
- Optional `license`, `compatibility`, `metadata`, and experimental `allowed-tools` are validated when present but are not required. Unknown frontmatter fields receive a low-severity notice rather than an automatic blocking failure.
- Local Markdown links and images, table-cell links, percent-decoded fragments, malformed local-link URL findings, conventional resource references, heading/HTML fragments, and referenced package resources are checked within bounded reads. External URLs are not fetched.
- Static syntax parsing is applied to supported Python, JSON, YAML, TOML, and XML resources. Referenced scripts are never executed.
- Protected-token policies support configured literals and regular expressions, bounded token/pattern inputs, overlap handling, and conservative screening for common risky regex shapes. This screening does not prove all patterns computationally safe.

### Protected content, translation, and comparison

- Protected spans cover common machine-facing material such as code fences, inline code, URLs, command flags, environment variables, paths, and configured identifiers/literals.
- Translation is provider-neutral through the `TranslationAdapter` interface. The default identity adapter makes no network request and leaves prose unchanged; it is a pipeline test, not a translator. The generic JSON HTTP adapter requires an endpoint and explicit `--allow-remote` consent.
- Translation performs a local whole-package preflight before the first provider call. The workload is capped at 10,000 translation requests and 10 MiB of aggregate outbound request bodies. The HTTP adapter also enforces request-count/byte budgets, a 2 MiB per-line request/response cap, a 10 MiB aggregate response cap, positive timeouts no longer than five minutes, and endpoint URL restrictions. Production endpoints must use HTTPS; plain HTTP is limited to loopback.
- Markdown translation masks/restores supported syntax and opaque regions: frontmatter, fenced/indented code, inline-code spans, URLs and link/image/reference-link delimiters, emphasis delimiters, task-list checkboxes, escaped punctuation, hard line breaks, HTML tags, and table pipes. Table-cell prose can be translated while separators stay intact. Multiline HTML comments and recognized code-bearing HTML blocks remain opaque.
- Translation fails closed on deleted/duplicated/reordered syntax placeholders, provider-injected line breaks or unsupported controls, invalid response values, exceeded budgets, or a changed parser-visible Markdown structure signature. All adapters, including custom adapters, are subject to shared output validation. This is not a full CommonMark/MDX AST transformation.
- Package comparison covers line-block/content differences, protected tokens and their order, file paths, non-text resource hashes/modes, and human-authored invariants. Added/omitted-content findings are alignment evidence, not a complete classification of new operational instructions.
- Invariant source paths, line ranges, and quoted source excerpts are checked against the current source. Stale or invalid anchors create deterministic critical findings and cannot be bypassed by an approval disposition; fix the manifest and rerun comparison.
- Count-preserving reordering of protected machine-facing tokens can be flagged as a high-uncertainty heuristic finding.

### Invariants, reports, approval, and local history

- `init-manifest` creates an unreviewed YAML draft. Heuristic suggestions skip fenced/indented code examples, recognized HTML `<pre>`/`<code>` examples, headings, table rows, descriptive numeric facts without operational cues, and candidate lines over 1,200 characters. Candidates can still be missed or misclassified and require human curation.
- Invariant manifests and comparison reports use versioned Pydantic contracts and JSON Schemas. Locale fields share dependency-free BCP 47 structural validation, including subtag ordering, extlang structure, variant uniqueness, extension singleton uniqueness, and private-use forms. IANA registry membership checks and canonicalization are not implemented.
- Findings record evidence/locations where available, a rule identifier, detection method, explicit uncertainty, severity rationale, review disposition, reviewer details, and timestamped review history.
- Review decisions append to history; changing a decision does not silently erase prior dispositions. Approval/export requires structural success, matching source/target/manifest/policy fingerprints, a reviewed invariant manifest, current evidence, and approved decisions for critical or review-required findings.
- JSON/Markdown reports are written atomically, use restricted POSIX permissions where supported, and are guarded against unsafe package-overlapping output paths. Markdown reports fence untrusted contexts and notes.
- Common credential-shaped values are redacted or rejected in selected report/review fields. This is a limited guardrail, not a complete secret scanner.
- Optional HMAC-SHA256 sealing can verify report integrity before review/export. It is symmetric integrity protection, not reviewer authentication or non-repudiation.
- Optional SQLite history keeps run metadata, locale/provider/status values, and package fingerprints, not source/target document text or credentials. Local history improves traceability but is not itself cryptographically tamper-evident.

## Verification and CI

The most recent verified `main` run before this documentation branch is [GitHub Actions run 40873536059](https://github.com/VireonNoctis/SkillTether/actions/runs/40873536059), on commit `90f1b922c7d93971638631ad95db7fb4f547914e` (2026-10-29). It passed **215 tests in each of six combinations**: Ubuntu, macOS, and Windows with Python 3.13 and 3.14. Measured coverage was 86% on Linux/macOS and 85% on Windows. CI also validates schema syntax, loads the protected-token policy, validates bundled fixtures, and runs a separate pinned `skills-ref@v0.0.1` reference-conformance smoke check. Only the Linux job enforces the 80% aggregate coverage floor; coverage is not proof of correctness.

## Explicit limitations and non-claims

- No automated guarantee of translation fluency, semantic equivalence, completeness, or safety. Human review is required for critical or ambiguous meaning.
- Invariant candidate generation and token/order/context heuristics are incomplete, language-dependent, and not a calibrated semantic classifier.
- Markdown safeguards are lexical masking plus parser-visible structure comparison, not a complete CommonMark/MDX AST transformation. Unusual extensions and nested constructs require review.
- External URL reachability, IANA registry validation/canonicalization, and full shell/JavaScript/PowerShell semantic parsing are unsupported.
- No automatic protected-token rename mapping; changed identifiers must be reviewed rather than silently renamed.
- No bundled vendor SDK, hosted translation service, API-key management service, or built-in credentials. Provider privacy/retention remains the user's responsibility after explicit consent.
- No comprehensive secret scanner, cryptographic reviewer identity, or tamper-proof local history.
- The optional Svelte/TypeScript reviewer interface is not implemented; the CLI and report contracts are the current interface.

## Specification boundary

The normative format reference is the [official Agent Skills specification](https://agentskills.io/specification). SkillTether keeps base-format validation separate from additional package-integrity and localization safeguards. See [spec-compatibility.md](spec-compatibility.md) for the boundary and the limitations of the pinned reference validator.
