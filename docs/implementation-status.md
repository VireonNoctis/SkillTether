# Implementation status

## Implemented in the CLI MVP

- Read-only inventory and SHA-256 package fingerprints that include file permission bits, with explicit permission-drift findings.
- Bounded file and directory counts, directory depth, per-file size, aggregate package bytes, race-resistant regular-file opens, symlink/special-file rejection, and script non-execution.
- Reject package-root symlink aliases; stage candidate and approved copies without intentionally dereferencing symlinks, then compare staged package fingerprints before modifying or publishing the copy.
- Bounded regular-file reads for manifests, protected-token policies, reports, and local-history databases; reject symlink/special-file inputs and cap report/policy/manifest sizes.
- SKILL.md frontmatter type/required-field/name/length checks.
- Local Markdown links and image assets, file targets, conventional script/reference/asset path mentions, and detected heading/HTML fragments.
- Static syntax parsing of Python, JSON, YAML, TOML, and XML resources without executing scripts.
- Protected spans for code fences, inline code, URLs, command flags, environment variables, common paths, and configured literals/regular expressions.
- Provider-neutral translation protocol, identity adapter, and explicit-consent JSON HTTP bridge.
- Whole-package no-network preflight caps translation at 10,000 requests and 10 MiB of aggregate outbound JSON; HTTP adapter independently limits aggregate request count/bytes and response bytes.
- Markdown prose masking for frontmatter, code fences, inline code, URLs/destinations, emphasis and link/image/reference-link delimiters, task-list checkboxes, escaped punctuation, hard line breaks, HTML tags, and table pipes. Table-cell prose can be translated while separator rows remain unchanged; multiline HTML comments and code-bearing HTML blocks remain opaque. Missing, duplicated, or reordered Markdown syntax placeholders, provider-injected line breaks/control characters, response-budget overruns, and parser-visible Markdown structure changes abort publication. The parser signature ignores ordinary prose text and is a structural guard, not a semantic equivalence check or full Markdown AST translator.
- Line-block, token, file-path, non-text resource hash, and human-authored invariant findings.
- Validate optional invariant source paths, line ranges, and source excerpts against current source text; invalid anchors produce deterministic critical findings and cannot be overridden during approval until the manifest is corrected and comparison rerun.
- Detect count-preserving reordering of protected machine-facing tokens as a high-uncertainty heuristic finding that requires human review.
- Atomically written mode-0600 (POSIX) JSON/Markdown reports; bounded regular-file reads; output-path guards; file-mode-aware fingerprints; explicit rule/method/uncertainty/severity rationale; chronological review history; common-credential redaction; and optional HMAC-SHA256 report integrity with verification before review/export.
- Optional local SQLite metadata history with fingerprint/locale/metadata validation, private file permissions, and no text payload columns; pytest/Hypothesis/JSON Schema tests and GitHub Actions CI.

## Deliberately not claimed

- The system does not prove semantic equivalence, fluency, or safety.
- Draft invariant suggestions are not authoritative or complete.
- Locale shape validation is lightweight BCP 47 syntax checking, not full registry validation.
- External URLs and remote targets are not checked for reachability.
- No bundled vendor SDK, API key management, hosted translation service, or built-in credentials.
- No automatic protected-token rename mapping, full Markdown AST translation, complete shell/JavaScript/PowerShell parser, or optional Svelte review UI yet.
- Semantic inference remains a human-reviewed workflow, not an automatic safe/unsafe classifier.
- Review history improves accountability but is not a cryptographic signature or protection against deliberate edits to a report file.
- Credential redaction covers selected common patterns only; it is not a secret scanner and cannot guarantee sensitive material has been removed.
- HMAC seals detect accidental/unauthorized report edits while the key remains private, but do not authenticate reviewers or provide non-repudiation.

## Current specification assumptions

The validator contract is cross-referenced in [docs/spec-compatibility.md](spec-compatibility.md) and the [official Agent Skills specification](https://agentskills.io/specification). Base-format rules are kept distinct from additional SkillTether operational safeguards; optional fields stay optional, and unknown frontmatter fields receive low-severity review notices rather than automatic blocking failures.
