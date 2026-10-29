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
| Validate required `SKILL.md` frontmatter and Agent Skills name rules | `analysis.py:_frontmatter`, `validate_skill_markdown`; `docs/spec-compatibility.md` | `tests/test_core.py`: malformed/duplicate YAML, missing fields, wrong types, optional fields and unknown fields | **Implemented / tested** for documented fields and name/directory identity. Compare periodically with the normative spec and reference validator. |
| Preserve optional-field compatibility and unknown extensions | `analysis.py:validate_skill_markdown` | valid optional-field and unknown-field tests in `tests/test_core.py` | **Implemented / tested.** Unknown fields warn rather than block; client-specific meanings are not inferred. |
| Check local links, fragments, images, and conventional resource references | `analysis.py:validate_local_links`, `validate_referenced_resources` | broken-link and missing-resource tests in `tests/test_core.py` | **Partial.** External URLs are not fetched; Markdown heading slug recognition is heuristic. This audit adds table parsing, percent-decoded fragments, malformed-URL findings, and bounded snapshot reuse. |
| Parse Markdown while preserving content structure | `translation.py:translate_markdown`, `_markdown_structure_signature`; `compare.py` line diff | syntax, tables, placeholders, HTML blocks and injected-link regressions in `tests/test_core.py` | **Partial.** Lexical masking plus parser-visible structure signature, not a complete CommonMark/MDX AST transformer. Extension-specific syntax still needs review. |
| Preserve scripts, assets, relative paths, and permissions | `analysis.py:inspect_package`, `compare.py` | `tests/test_copy_race.py`, asset/mode tests in `tests/test_core.py` | **Implemented / tested** for inventory, hashes, modes, path integrity, and non-execution. Static parser coverage is limited to selected formats; shell/JS/PowerShell semantics are not fully parsed. |
| Protect commands, identifiers, paths, URLs, environment variables, and code | `analysis.py:extract_protected_tokens`, `translation.py:_mask_protected_spans`, `config/protected-tokens.yaml` | token mutation, overlap, placeholder collision, token order tests | **Partial.** Detection depends on built-in and configured patterns; unrecognized operational literals may be missed. |
| Compare text, omitted/added sections, and protected token differences | `compare.py:compare_packages` | `tests/test_core.py`, `tests/test_token_order.py` | **Implemented / tested** for line-level/token-level changes under resource budgets. “Added/omitted” findings are textual alignment evidence, not reliable classification of newly introduced imperatives. |
| Maintain human-reviewed invariants for negation, modality, thresholds, prerequisites, and decision rules | `models.py:Invariant`, `compare.py` invariant checks, `reviewing.py` | `tests/test_invariant_source_refs.py`, `tests/test_core.py`, `tests/test_review_audit.py` | **Partial by design.** Manifest quality and locale-specific markers are human-authored. Word overlap and marker checks do not prove semantic equivalence. |
| Keep structural status separate from semantic-review status | `models.py:ComparisonReport`, `compare.py`, CLI output and approval gate | comparison/review audit tests | **Implemented / tested.** The semantic status is a workflow signal, not a confidence-calibrated semantic score. |
| Provider adapters behind a narrow interface; no provider enabled by default | `translation.py:TranslationAdapter`, `IdentityAdapter`, `HttpJsonAdapter`; `cli.py:cmd_translate` | HTTP adapter, no-network preflight, timeout, redirect and budget tests | **Implemented / tested** for the identity adapter and generic JSON bridge. There is no bundled vendor SDK or automatic provider discovery. |
| Do not send private package text without explicit opt-in; bound provider I/O | `cli.py`, `translation.py:HttpJsonAdapter`, whole-package preflight and shared adapter output validation | `tests/test_translation_budget.py`, provider failure and injection tests | **Implemented / tested** for configured adapters and declared budgets. Provider retention/data handling remains the user's responsibility; transport-level timeouts do not guarantee remote deletion. |
| Reject malformed/injected provider output and avoid partial candidates | `translation.py:translate_markdown`, parser signature, response validator, staging and final replace | line injection, structure injection, control characters, size caps, provider failure tests | **Implemented / tested** for covered checks. Parsing and output checks reduce structural drift but cannot detect every meaningful rewrite. |
| Validate source/target locale tags consistently | `locale_tags.py`, CLI and Pydantic validators, schemas | `tests/test_locale_tags.py` | **Partial.** BCP 47 structure including one to three extlang subtags is checked, not live IANA registry membership or canonicalization. JSON Schema provides a lexical envelope; Pydantic performs the complete implemented structural checks. |
| Produce versioned reports, require auditable approval, protect reports optionally with HMAC | `models.py`, `report.py`, `reviewing.py`, `signing.py`, `cli.py` | `tests/test_review_audit.py`, `tests/test_signing.py` | **Implemented / tested.** HMAC is a symmetric integrity seal, not reviewer identity or non-repudiation. |
| Redact secrets and keep history local/minimal | `redaction.py`, `report.py`, `history.py`, `safeio.py` | redaction/history/safe-I/O test modules | **Partial.** Patterns catch common credential shapes; redaction is not a complete secret scanner. |
| Exercise deterministic and heuristic checks with negative cases | `tests/`, Hypothesis and JSON Schema dependencies, `.github/workflows/ci.yml` | CI runs pytest, schema/policy checks and bundled fixture validation; this audit enables coverage reporting | **Partial.** There is not yet a separately versioned, human-labelled evaluation corpus with precision/recall by finding category. CI enforces an 80% aggregate coverage floor; per-module floors are not enforced. |
| Optional reviewer UI | no production UI in current tree | none | **Deferred.** CLI/report contracts are the current interface. |
| Provider-specific renamed-token mapping | no approved mapping schema/workflow yet | none | **Deferred.** Tokens are preserved or flagged; there is no silent automatic rename mechanism. |

## Findings fixed during the audit

1. **Unbounded link-target reopen:** fragment validation used `Path.read_text()` after package inventory. It now prefers the already bounded text snapshot and uses `read_bounded_regular_file()` as a bounded, non-following fallback.
2. **Malformed URL exception:** malformed URL syntax now yields a `LOCAL_LINK_URL_INVALID` finding instead of crashing inspection.
3. **Markdown table links:** local-link validation enables table parsing so links in table cells are checked.
4. **Percent-encoded fragments:** URL fragments are decoded before comparison with detected IDs/headings.
5. **Invariant manifest output path:** `init-manifest` now refuses destinations inside the source package and existing destinations, and stages the YAML beside the output before atomic create-only publication. This avoids following or clobbering a final-component symlink, including a symlink introduced during publication.
6. **Coverage visibility and gate:** CI prints line/branch coverage and fails below the measured 80% aggregate floor. The latest run measures 85%; no per-module floor is enforced.

Each item has or is receiving a regression fixture in the same pull request. These fixes count as release-verified only when CI passes on the resulting head.

## Highest-priority remaining work

### P1 — Release correctness
- Pass current-head CI with the audit fixtures and inspect the measured coverage output.
- Add a stable, human-reviewed evaluation corpus with both hard positives and difficult negatives; report precision/recall per rule family rather than one blended score.
- Review approval/export behavior against adversarial source/target/manifest/report path changes; retain the existing symlink-race and fingerprint gates.

### P2 — Stronger evidence
- Establish a documented comparison against the official `skills-ref validate` reference implementation, with the tool version and expected differences recorded. Do not silently make the reference tool a mandatory network dependency.
- Expand coverage in the CLI (67%) and package analysis (79%) modules; an aggregate floor does not guarantee that every risky branch is exercised.
- Expand cross-platform CI beyond the current Ubuntu/Python 3.13 job before claiming cross-platform release readiness.
- Improve Markdown reference/link/slug edge cases and specify exactly which Markdown dialects are supported.

### P3 — Deliberately not a release promise
- Full semantic-equivalence detection, automatic approval, complete shell/JavaScript/PowerShell parsing, full MDX AST transformation, registry-backed locale canonicalization, online URL reachability, automatic protected-token rename mappings, and the optional Svelte reviewer UI remain unsupported or deferred.

## Latest verification snapshot

- Verified source/test commit: `4f4280beea116362aa36b01d8dcb80999c2a1ad9`.
- GitHub Actions run: [40868180566](https://github.com/VireonNoctis/SkillTether/actions/runs/40868180566).
- Regression/property-based suite: **199 passed**.
- Aggregate measured coverage: **85%** across 2,039 statements and 824 branches (244 statements missed; 158 partial branches).
- Module coverage highlights: CLI 82%, package analysis 80%, comparison 84%, translation 85%, report writing 96%, safe I/O 96%, locale-tag validation 97%.
- JSON Schema syntax/protected-token policy checks and bundled valid-skill validation passed.
- CI reports line/branch coverage and enforces an 80% aggregate floor. It does not enforce per-module floors. Coverage is evidence of exercised code, not proof of correctness; branch-specific review remains necessary.

This run validates the manifest-publication fix and its tests as well as the coverage gate. This audit text is a documentation-only follow-up; any later source/test change still needs its own passing CI run before release.

## Acceptance gate

A release candidate should pass the current CI suite; include traceable tests for each newly implemented rule plus a hard negative; preserve source-package fingerprints; validate schemas and bundled fixtures; document coverage and cross-platform limits; and leave critical or ambiguous semantic changes for explicit human review. No single score should be presented as a “safe translation” certificate.
