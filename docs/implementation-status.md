# Implementation status

## Implemented in the CLI MVP

- Read-only inventory and SHA-256 package fingerprints.
- Bounded file and directory counts, directory depth, per-file size, aggregate package bytes, race-resistant regular-file opens, symlink/special-file rejection, and script non-execution.
- SKILL.md frontmatter type/required-field/name/length checks.
- Local Markdown links and image assets, file targets, conventional script/reference/asset path mentions, and detected heading/HTML fragments.
- Static syntax parsing of Python, JSON, YAML, TOML, and XML resources without executing scripts.
- Protected spans for code fences, inline code, URLs, command flags, environment variables, common paths, and configured literals/regular expressions.
- Provider-neutral translation protocol, identity adapter, and explicit-consent JSON HTTP bridge.
- Markdown prose masking for frontmatter, code fences, inline code, URLs, link destinations, HTML tags, and basic line-prefix syntax.
- Line-block, token, file-path, non-text resource hash, and human-authored invariant findings.
- Atomically written mode-0600 (POSIX) JSON/Markdown reports; output-path guards to preserve source/candidate packages; stable IDs and fingerprints; explicit rule/method/uncertainty/severity rationale; chronological review history; approval gates requiring consistent reviewer decisions with rationale; JSON Schema validation tests; and optional fail-on-review CI exit semantics.
- Optional local SQLite metadata history, pytest/Hypothesis tests, and GitHub Actions CI.

## Deliberately not claimed

- The system does not prove semantic equivalence, fluency, or safety.
- Draft invariant suggestions are not authoritative or complete.
- Locale shape validation is lightweight BCP 47 syntax checking, not full registry validation.
- External URLs and remote targets are not checked for reachability.
- No bundled vendor SDK, API key management, hosted translation service, or built-in credentials.
- No automatic protected-token rename mapping, full Markdown AST translation, complete shell/JavaScript/PowerShell parser, or optional Svelte review UI yet.
- Semantic inference remains a human-reviewed workflow, not an automatic safe/unsafe classifier.
- Review history improves accountability but is not a cryptographic signature or protection against deliberate edits to a report file.

## Current specification assumptions

The base Agent Skills contract requires a SKILL.md with YAML frontmatter containing non-empty name and description. Name syntax and description length are checked; common optional fields are recognized. Unknown frontmatter fields are flagged at low severity to allow client extensions. Check the upstream specification when updating the validator contract.
