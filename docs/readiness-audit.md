# Requirements-to-code readiness audit

**Audit date:** 2026-10-29  
**Scope:** the repository state on `feat/review-audit-hardening`, including README, research/architecture notes, current parser and CLI, Pydantic models, schemas, comparison and translation paths, test fixtures, and CI.  
**Normative reference:** [official Agent Skills specification](https://agentskills.io/specification), checked on the audit date; [RFC 5646 / BCP 47](https://www.rfc-editor.org/rfc/rfc5646).

This is a traceability audit, not a semantic-safety certification. “Implemented” means the behavior exists and has regression coverage; it does not mean all possible inputs or operating systems are proven safe. “Partial” identifies heuristic, client-dependent, or deliberately bounded support.

## Status key

- **Implemented / tested:** behavior is present with focused regression evidence.
- **Partial:** supported only for a defined subset, or dependent on heuristics/human review.
- **Deferred / not claimed:** intentionally absent or not supported by evidence yet.
- **Fixed in this audit:** concrete reliability issue corrected here; current-head CI must pass before treating the correction as release-verified.

## Requirements traceability

| Requirement | Implementation evidence | Test/evaluation evidence | Status and remaining limit |
|---|---|---|---|
| Treat a skill as a directory/package, not a single string | `src/skilltether/analysis.py:inspect_package`, `translation.py:translate_package`, `cli.py:cmd_approve` | `tests/test_copy_race.py`, `tests/test_root_symlink.py`, `tests/test_safeio.py`, package fingerprint tests in `tests/test_core.py` | **Implemented / tested.** Inventory is bounded and source/candidate/output are kept separate. OS/filesystem race behavior remains platform-dependent. |
| Validate expected text encodings | `analysis.py:inspect_package` | `test_non_utf8_expected_text_resources_are_reported`; `test_binary_asset_is_not_misclassified_as_invalid_text` | **Implemented / tested.** Known text/script suffixes that are not UTF-8 produce findings; other binary assets remain fingerprinted as binary. Suffix classification is conventional rather than content-type proof. |
| Validate required `SKILL.md` frontmatter and Agent Skills name rules | `analysis.py:_frontmatter`, `validate_skill_markdown`; `docs/spec-compatibility.md` | `tests/test_core.py`: malformed/duplicate YAML, missing fields, wrong types, optional fields and unknown fields | **Implemented / tested** for documented fields and name/directory identity. Compare periodically with the normative spec and reference validator. |
| Preserve optional-field compatibility and unknown extensions | `analysis.py:validate_skill_markdown` | valid optional-field and unknown-field tests in `tests/test_core.py` | **Implemented / tested.** Unknown fields warn rather than block; client-specific meanings are not inferred. |
| Check local links, fragments, images, and conventional resource references | `analysis.py:validate_local_links`, `validate_referenced_resources` | broken-link and missing-resource tests in `tests/test_core.py` | **Partial.** External URLs are not fetched; Markdown heading slug recognition is heuristic. This audit adds table parsing, percent-decoded fragments, malformed-URL findings, and bounded snapshot reuse. |
| Parse Markdown while preserving content structure | `translation.py:translate_markdown`, `_markdown_structure_signature`; `compare.py` line diff | syntax, tables, placeholders, HTML blocks and injected-link regressions in `tests/test_core.py` | **Partial.** Lexical masking plus parser-visible structure signature, not a complete CommonMark/MDX AST transformer. Extension-specific syntax still needs review. |
| Preserve scripts, assets, relative paths, and permissions | `analysis.py:inspect_package`, `compare.py` | `tests/test_copy_race.py`, asset/mode tests in `tests/test_core.py` | **Implemented / tested** for inventory, hashes, modes, path integrity, and non-execution. Static parser coverage is limited to selected formats; shell/JS/PowerShell semantics are not fully parsed. |
| Protect commands, identifiers, paths, URLs, environment variables, and code | `analysis.py:extract_protected_tokens`, `translation.py:_mask_protected_spans`, `config/protected-tokens.yaml` | token mutation, overlap, placeholder collision, token order tests | **Partial.** Detection depends on built-in and configured patterns; unrecognized operational literals may be missed. |
| Compare text, omitted/added sections, and protected token differences | `compare.py:compare_packages` | `tests/test_core.py`, `tests/test_token_order.py` | **Implemented / tested** for line-level/token-level changes under resource budgets. “Added/omitted” findings are textual alignment evidence, not reliable classification of newly introduced imperatives. |
| Draft invariant suggestions | `cli.py:_suggest_invariants` | `tests/fixtures/invariant-suggestion-corpus.json`, `test_human_labeled_invariant_suggestion_corpus`, code-example regression in `tests/test_review_audit.py` | **Partial.** Fenced, indented, and recognized HTML `<pre>/<code>` examples, headings, table rows, lines over 1,200 characters, and descriptive numeric facts without operational cues are excluded. This curated English corpus is not a representative benchmark; suggestions remain heuristic and unreviewed by default. |
| Maintain human-reviewed invariants for negation, modality, thresholds, prerequisites, and decision rules | `models.py:Invariant`, `compare.py` invariant checks, `reviewing.py` | `tests/test_invariant_source_refs.py`, `tests/test_core.py`, `tests/test_review_audit.py` | **Partial by design.** Candidate generation is heuristic and now skips fenced, indented, and recognized HTML code examples; nested-list indentation can be skipped, and prose inside unusual code/MDX constructs may still be misclassified. Manifest quality and locale-specific markers are human-authored. Word overlap and marker checks do not prove semantic equivalence. |
| Keep structural status separate from semantic-review status | `models.py:ComparisonReport`, `compare.py`, CLI output and approval gate | comparison/review audit tests | **Implemented / tested.** The semantic status is a workflow signal, not a confidence-calibrated semantic score. |
| Provider adapters behind a narrow interface; no provider enabled by default | `translation.py:TranslationAdapter`, `IdentityAdapter`, `HttpJsonAdapter`; `cli.py:cmd_translate` | HTTP adapter, no-network preflight, timeout, redirect and budget tests | **Implemented / tested** for the identity adapter and generic JSON bridge. There is no bundled vendor SDK or automatic provider discovery. |
| Do not send private package text without explicit opt-in; bound provider I/O | `cli.py`, `translation.py:HttpJsonAdapter`, whole-package preflight and shared adapter output validation | `tests/test_translation_budget.py`, provider failure and injection tests | **Implemented / tested** for configured adapters and declared budgets. Provider retention/data handling remains the user's responsibility; transport-level timeouts do not guarantee remote deletion. |
| Reject malformed/injected provider output and avoid partial candidates | `translation.py:translate_markdown`, parser signature, response validator, staging and final replace | line injection, structure injection, control characters, size caps, provider failure tests | **Implemented / tested** for covered checks. Parsing and output checks reduce structural drift but cannot detect every meaningful rewrite. |
| Validate source/target locale tags consistently | `locale_tags.py`, CLI, Pydantic validators, and SQLite history | `tests/test_locale_tags.py`, `tests/test_history.py` | **Partial.** BCP 47 structure including one to three extlang subtags is checked consistently, not live IANA registry membership or canonicalization. JSON Schema provides a lexical envelope; Pydantic performs the complete implemented structural checks. |
| Produce versioned reports, require auditable approval, protect reports optionally with HMAC | `models.py`, `report.py`, `reviewing.py`, `signing.py`, `cli.py` | `tests/test_review_audit.py`, `tests/test_signing.py` | **Implemented / tested.** HMAC is a symmetric integrity seal, not reviewer identity or non-repudiation. |
| Redact secrets and keep history local/minimal | `redaction.py`, `report.py`, `history.py`, `safeio.py` | redaction/history/safe-I/O test modules | **Partial.** Patterns catch common credential shapes; redaction is not a complete secret scanner. |
| Exercise deterministic and heuristic checks with negative cases | `tests/fixtures/invariant-suggestion-corpus.json`, `tests/`, Hypothesis and JSON Schema dependencies, `.github/workflows/ci.yml` | A human-labeled English corpus asserts expected invariant candidates and difficult exclusions; CI also runs schema/policy checks and bundled fixture validation | **Partial.** The curated corpus is small and is an exact-match regression fixture, not a representative benchmark. Precision/recall by rule family and multilingual evaluation remain future work. CI enforces an 80% aggregate coverage floor on Linux; per-module floors are not enforced. |
| Compare base-format metadata with the official reference CLI | Separate Ubuntu CI job installs pinned `skills-ref@v0.0.1` | Valid and deliberately invalid fixture exit-status checks | **Compatibility smoke test only.** Upstream documents `skills-ref` as a demonstration/reference tool, not production software; the result is version-pinned evidence, not a runtime dependency or sole authority. |
| Optional reviewer UI | no production UI in current tree | none | **Deferred.** CLI/report contracts are the current interface. |
| Provider-specific renamed-token mapping | no approved mapping schema/workflow yet | none | **Deferred.** Tokens are preserved or flagged; there is no silent automatic rename mechanism. |

## Findings fixed during the audit

1. **Unbounded link-target reopen:** fragment validation uses the bounded inventory snapshot or a bounded, non-following fallback.
2. **Malformed URL exception:** malformed URL syntax yields a `LOCAL_LINK_URL_INVALID` finding instead of crashing inspection.
3. **Markdown table links:** local-link validation enables table parsing so links in table cells are checked.
4. **Percent-encoded fragments:** URL fragments are decoded before comparison with detected IDs/headings.
5. **Invariant manifest output path:** `init-manifest` refuses destinations inside the source package and existing destinations; it stages YAML beside the output before atomic create-only publication.
6. **Approval/translation output paths:** final-component symlinks are rejected for approval and translation candidate destinations, including broken symlinks.
7. **Coverage visibility and gate:** CI prints line/branch coverage on three operating systems and fails below the 80% aggregate floor on Linux only.
8. **Invariant suggestion scope:** suggestions skip fenced, indented, and recognized HTML `<pre>/<code>` examples; headings, table rows, descriptive numeric facts without action/limit cues, and candidate lines over 1,200 characters are excluded. Suggestions are still unreviewed heuristics.
9. **Invalid text encoding:** expected text/script resources with invalid UTF-8 produce findings; arbitrary binary assets are not misclassified as malformed text.
10. **Windows byte preservation:** raw package/file reads and signing-key reads use binary mode so CRLF and Ctrl-Z bytes do not corrupt hashes, aggregate-budget accounting, or HMAC key length.
11. **History locale parity:** SQLite history uses the same BCP 47 structural validator as CLI/manifests/reports instead of a looser shape regex.
12. **Reference-validator check:** CI runs a separately pinned `skills-ref` valid/invalid fixture smoke test without adding it to SkillTether's runtime dependencies.

Each item has or is receiving a regression fixture in the same pull request. These fixes count as release-verified only when CI passes on the resulting head.

## Highest-priority remaining work

### P1 — Release correctness
- Keep the Linux/macOS/Windows suite and pinned reference-validator smoke job green; continue expanding branch coverage around filesystem error handling, CLI approval gates, and Markdown/parser edge cases.
- Expand `tests/fixtures/invariant-suggestion-corpus.json` with more human-reviewed positive/negative examples, other Markdown constructs and languages; report precision/recall by rule family rather than treating the current small exact-match fixture as a benchmark.
- Review approval/export behavior against adversarial source/target/manifest/report path changes; retain the existing symlink-race and fingerprint gates.

### P2 — Stronger evidence
- Expand the pinned skills-ref v0.0.1 smoke check into a documented differential corpus covering optional fields, unknown extensions, naming edge cases, and expected differences. Keep the reference tool CI-only and non-mandatory at runtime.
- Continue targeted branch coverage in the CLI (83%) and package analysis (80%) modules; these are now the lowest-covered high-risk areas in the latest measured snapshot. An aggregate floor does not guarantee that every risky branch is exercised.
- CI now runs the suite on Ubuntu, macOS, and Windows with Python 3.13. Expand the matrix to supported Python minor versions and test additional filesystem configurations before claiming broad platform coverage.
- Improve Markdown reference/link/slug edge cases and specify exactly which Markdown dialects are supported.

### P3 — Deliberately not a release promise
- Full semantic-equivalence detection, automatic approval, complete shell/JavaScript/PowerShell parsing, full MDX AST transformation, registry-backed locale canonicalization, online URL reachability, automatic protected-token rename mappings, and the optional Svelte reviewer UI remain unsupported or deferred.

## Latest verification snapshot

- Verified PR head: `e82b627986c3bed40b426aebd7e67a01b09e60d6`.
- GitHub Actions matrix and reference-conformance run: [40870699582](https://github.com/VireonNoctis/SkillTether/actions/runs/40870699582).
- Regression/property-based suite: **214 passed on each of Ubuntu, macOS, and Windows**.
- Linux aggregate measured coverage: **86%** across 2,072 statements and 844 branches (237 statements missed; 157 partial branches); macOS measured 86% and Windows 85%.
- Module coverage highlights from the Linux run: CLI 83%, package analysis 80%, comparison 84%, translation 85%, report writing 96%, safe I/O 96%, locale-tag validation 97%.
- JSON Schema syntax/protected-token policy checks and bundled valid-skill validation passed on the matrix. The pinned `skills-ref@v0.0.1` reference-conformance smoke job also passed against the valid and invalid fixtures.
- CI reports line/branch coverage on all three operating systems and enforces an 80% aggregate floor on Linux only. It does not enforce per-module floors. Coverage is evidence of exercised code, not proof of correctness; branch-specific review remains necessary.

This run validates the current PR head, byte-exact file reads/key loading, the human-labeled invariant-suggestion corpus, output-symlink guards, and the pinned reference-validator smoke test. Any later source/test change still needs its own passing CI run before release.
## Acceptance gate

A release candidate should pass the current CI suite; include traceable tests for each newly implemented rule plus a hard negative; preserve source-package fingerprints; validate schemas and bundled fixtures; document coverage and cross-platform limits; and leave critical or ambiguous semantic changes for explicit human review. No single score should be presented as a “safe translation” certificate.
