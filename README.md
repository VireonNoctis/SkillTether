# SkillTether

<!-- REPOSITORY-HEALTH:START -->
[![Code quality](https://github.com/VireonNoctis/SkillTether/actions/workflows/repository-health.yml/badge.svg?branch=main)](https://github.com/VireonNoctis/SkillTether/actions/workflows/repository-health.yml)
[![Top language](https://img.shields.io/github/languages/top/VireonNoctis/SkillTether?style=flat-square)](https://github.com/VireonNoctis/SkillTether)
[![Languages](https://img.shields.io/github/languages/count/VireonNoctis/SkillTether?style=flat-square)](https://github.com/VireonNoctis/SkillTether)
[![Automated tech stack](https://img.shields.io/badge/tech_stack-auto--detected-64748b?style=flat-square)](TECH_STACK.md)
<!-- REPOSITORY-HEALTH:END -->


**Translate the words. Preserve the intent.**

SkillTether is a local-first CLI for validating and localizing [Agent Skills](https://agentskills.io/specification). It treats a skill as a package—`SKILL.md`, metadata, scripts, references, assets, and relative paths—not just a block of prose.

> **Safety boundary:** automated checks can reveal suspicious changes; they cannot prove semantic equivalence or certify a translation as safe. Critical and ambiguous instructions require human review.

## What it does

- **Validate the package:** check frontmatter, metadata types, Unicode lowercase skill names, local links and fragments, referenced resources, path safety, file modes, encodings, and bounded package size. Unicode name comparison trims surrounding whitespace and uses NFKC without rewriting package identifiers; unreadable directories fail closed. Python and supported structured resources receive static syntax checks. Bash/sh, JavaScript, and PowerShell use bounded parse-only checks when local parsers exist; TypeScript-family scripts use the installed TypeScript compiler's parser; Windows batch files receive only a conservative delimiter scan. No package script is executed and no parser is downloaded.
- **Protect machine-facing content:** identify commands, code, URLs, paths, environment variables, and configured identifiers; flag token changes and package-resource drift. Explicit one-to-one token renames can be recorded only with a reviewed, path/category-scoped manifest mapping; stale, incomplete, or unreviewed mappings never suppress findings.
- **Track operational invariants:** create a draft YAML manifest for requirements, negations, numeric limits, prerequisites, and decision rules. Draft suggestions include conservative cue profiles for English, French, Spanish, German, Portuguese, Italian, Arabic, Hindi, Russian, Japanese, and Chinese, with an eleven-language primary-tag fixture and a separate document-like regional-tag fixture (en-GB, fr-CA, es-MX, de-AT, pt-BR, it-CH); both report finite-corpus precision/recall and hard negatives, and neither is a representative dialect benchmark. The cues remain heuristic and unreviewed until a person curates them. Human reviewers can also pin an invariant to an exact target-language `target_lines`/`target_text` excerpt when source/target word overlap is unavailable; stale anchors block approval, and a valid anchor identifies context without proving semantic equivalence.
- **Localize Markdown carefully:** use the shared GFM-like parser and its inline source maps to restrict translation to parser-owned prose lines, including nested list/blockquote content. Preserve syntax with protected placeholders, enforce provider budgets, and reject detected structure drift. Obvious MDX-only module/JSX/expression constructs fail closed and are not translated. This is AST-informed line gating, not a complete source-preserving CommonMark/MDX AST round-trip.
- **Keep decisions auditable:** generate JSON/Markdown reports, retain review history and rationale, and require fingerprint-matched evidence before exporting an approved candidate.
- **Review reports offline:** open the dependency-free local workbench in reviewer/index.html to inspect evidence, filter findings, record decisions on unsigned reports, and export the updated JSON. HMAC-signed reports remain read-only in the browser.
- **Make remote translation opt-in:** the default identity adapter sends no content. The generic JSON adapter requires an endpoint and explicit `--allow-remote` consent; per-line and aggregate limits bound provider output.
- **Audit credential indicators locally:** `skilltether scan-secrets` and `validate --scan-secrets` check readable UTF-8 resources for common provider tokens, private-key headers, bearer/basic credentials, URL user-info, cloud access-key identifiers, and suspicious credential assignments. Findings never include matched values.
- **Keep local run metadata minimal:** optional SQLite history stores fingerprints and run metadata, not source/target document text.
- **Support report integrity:** optionally seal JSON reports using a local HMAC-SHA256 key and verify the seal before review or approval.

- **Diagnose the local CLI environment:** `skilltether doctor` reports the Python requirement, bundled locale-registry snapshot, and optional local parser availability in text or JSON. It does not access the network, install tools, or execute package scripts.

See the [requirements-to-code readiness audit](docs/readiness-audit.md) for the traceability matrix and known gaps.

## Install

Requires Python 3.13 or newer. CI tests Python 3.13 and 3.14 on Ubuntu, macOS, and Windows.

~~~sh
python -m pip install -e ".[dev]"
skilltether --version
pytest
~~~

## Typical workflow

### 1. Validate and audit the source package

~~~sh
skilltether validate ./skills/my-skill
skilltether scan-secrets ./skills/my-skill
~~~

Run the local credential-indicator scan before choosing a remote translation provider. It does not send data anywhere; it reports file/line locations and redacted rule explanations only.

The package directory basename must match the `name` field in `SKILL.md`. Inspection is read-only; scripts and external URLs are not executed or fetched.

### 2. Draft an invariant manifest

Write the manifest **outside the source package**. The CLI refuses to write into the package or overwrite an existing manifest.

~~~sh
skilltether init-manifest ./skills/my-skill \
  --out ./review/my-skill.invariants.yaml \
  --source-locale en --target-locale fr
~~~

The suggestions are heuristic candidates, not policy. Review every entry, add missed constraints, correct categories and source references, and set `manifest_reviewed: true` plus each approved invariant's `reviewed: true` and reviewer identifier. Add locale-specific negation or mandatory markers where helpful. Do not treat an automatically generated manifest as reviewed evidence.

### 3. Translate into a separate candidate

For a no-network pipeline check, use the identity adapter. It leaves prose unchanged; it does **not** translate a skill.

~~~sh
skilltether translate ./skills/my-skill ./candidate/my-skill \
  --source-locale en --target-locale fr --adapter identity \
  --invariants ./review/my-skill.invariants.yaml \
  --policy config/protected-tokens.yaml \
  --report ./review/candidate-report.json
~~~

For an approved remote gateway, use the provider-neutral JSON bridge. Add `--scan-secrets` to stop locally when supported credential indicators are found or the source inventory cannot be fully scanned:

~~~sh
skilltether translate ./skills/my-skill ./candidate/my-skill \
  --source-locale en --target-locale fr --adapter http-json \
  --endpoint https://your-approved-gateway.example/translate \
  --allow-remote --scan-secrets \
  --invariants ./review/my-skill.invariants.yaml \
  --policy config/protected-tokens.yaml \
  --report ./review/candidate-report.json
~~~

The gateway accepts a JSON request containing eligible prose and the source/target locale tags, and must return a JSON object with a string `text` field. Production endpoints must use HTTPS; plain HTTP is restricted to loopback. No vendor SDK or credentials are bundled. Review the gateway's retention and data-handling terms before consenting to transmit private content.

Translation writes to a new candidate directory and does not intentionally modify the source. Response limits and a whole-package preflight constrain requests and output; failures must not publish a partial candidate.

### 4. Compare the current candidate

Run comparison after any candidate edits. Use the same manifest and policy that you intend to rely on during approval.

~~~sh
skilltether compare ./skills/my-skill ./candidate/my-skill \
  --invariants ./review/my-skill.invariants.yaml \
  --target-locale fr --policy config/protected-tokens.yaml \
  --out ./review/report.json --markdown ./review/report.md
~~~

Reports include source, target, manifest, and policy fingerprints, finding locations and evidence, analysis method, uncertainty, severity rationale, and reviewer disposition. A report describes detected differences; a clean structural result does not prove meaning is preserved.

### 5. Record decisions and approve explicitly

For every review-required or critical finding, record the decision and a meaningful rationale:

~~~sh
skilltether review ./review/report.json FINDING_ID \
  --disposition approved --reviewer "reviewer-id" \
  --note "Compared the full source and target context; approval rationale."
~~~

`rejected` and `deferred` findings remain blockers. Missing or unreviewed manifests and invalid source or target excerpt anchors cannot be approved away; correct them and rerun comparison. Export to a new directory:

~~~sh
skilltether approve ./skills/my-skill ./candidate/my-skill \
  --report ./review/report.json --output ./approved/my-skill \
  --invariants ./review/my-skill.invariants.yaml \
  --policy config/protected-tokens.yaml
~~~

Approval checks the current fingerprints and review evidence, then regenerates the comparison from the current source, candidate, invariant manifest, and protected-token policy. Machine-produced findings, statuses, and evidence must match that fresh result; only reviewer disposition/history fields may differ. Structural failures and unresolved blockers cannot be approved away, and existing or unsafe output paths are refused. It never overwrites an existing approved package. Unsigned review history remains editable by anyone who can edit the report; use HMAC signing when report tamper detection is required.

### Optional: seal review reports

Create a private key once in the user's configuration directory, outside the repository and skill package:

~~~sh
skilltether init-signing-key --out ~/.skilltether/report-signing.key
~~~

Pass `--signing-key ~/.skilltether/report-signing.key` when creating the comparison report, then verify it with:

~~~sh
skilltether verify-report ./review/report.json \
  --signing-key ~/.skilltether/report-signing.key
~~~

Use the same key with `review` and `approve` for a signed report. HMAC detects report edits only while the key remains private; it does not authenticate reviewer identity or provide non-repudiation.

## Command reference

| Command | Purpose |
|---|---|
| `skilltether validate PACKAGE [--fail-on SEVERITY] [--scan-secrets]` | Validate a package; optionally include local credential-indicator checks |
| `skilltether scan-secrets PACKAGE [--json]` | Scan readable UTF-8 package resources for common credential indicators; values are omitted |
| `skilltether doctor [--json]` | Diagnose Python compatibility, locale registry snapshot, and optional local parser availability |
| `skilltether init-manifest SOURCE --out FILE` | Generate unreviewed invariant candidates |
| `skilltether translate SOURCE OUTPUT` | Create a candidate and initial report |
| `skilltether compare SOURCE TARGET --out REPORT` | Compare packages and create a review queue |
| `skilltether review REPORT FINDING_ID ...` | Append a human decision and rationale |
| `skilltether approve SOURCE TARGET --report REPORT --output OUTPUT` | Export a fingerprint-matched, approved candidate |
| `skilltether init-signing-key --out FILE` | Create a private report-signing key |
| `skilltether verify-report REPORT --signing-key KEY` | Verify a signed report without modifying it |

Use `skilltether COMMAND --help` for available options. `validate --fail-on` accepts `info`, `low`, `medium`, `high`, or `critical`; its default is `high` to preserve existing exit semantics. For automation that should fail when semantic review is still required, `compare` and `translate` support `--fail-on-review`.

## Integrity model

| Content | Handling |
|---|---|
| Commands, identifiers, paths, variables, and URLs | Protect exact spans where recognized; flag suspicious changes |
| Frontmatter and machine-readable values | Preserve during translation and validate after |
| Code blocks and scripts | Never execute; keep protected and compare for changes |
| Safety constraints, negation, limits, and prerequisites | Capture as reviewable invariants; require explicit review for critical findings |
| Ordinary prose | Eligible for configured adapters after masking and structural checks |
| Uncertain or ambiguous meaning | Report uncertainty instead of silently marking the result safe |

## CI and specification compatibility

GitHub Actions tests the suite on **Python 3.13 and 3.14 × Ubuntu, macOS, and Windows** for pull requests and pushes to `main`. A per-PR concurrency group cancels superseded runs instead of duplicating every feature-branch push. It reports line and branch coverage on all six combinations and enforces the **80% aggregate coverage floor on Linux**. A separate Ubuntu job checks valid Unicode and maximum-length metadata fixtures, invalid name/compatibility boundaries, and expected unknown-extension divergence with the pinned `skills-ref@v0.0.1` validator. This is a small, version-pinned differential corpus—not exhaustive compatibility proof—and the reference tool is not a runtime dependency.

## Limits

- **No semantic-equivalence guarantee.** Invariants and marker comparisons are heuristic and context-sensitive. Critical operational instructions need human review.
- **Locale validation uses a bundled IANA snapshot.** BCP 47 syntax and subtag membership are checked against the `iana-bcp47` registry snapshot dated 2026-09-17. Validation preserves the supplied tag and does not automatically canonicalize it; explicit canonicalization is a separate opt-in helper. The bundled snapshot is not a live registry query.
- **Reference and syntax coverage is bounded.** External URLs are not fetched. The parser supports a documented GFM-like/Pandoc subset; heading fragments and MDX detection have known limits. JSX and JavaScript constructs are flagged as unsupported, not parsed or translated. AST source maps gate eligible Markdown prose lines, but this is not a complete AST transformation.
- **Script syntax support is bounded.** Bash/sh, JavaScript, and PowerShell parsing is syntax-only and depends on trusted local parsers. TypeScript/TSX/MTS/CTS use an already-installed TypeScript compiler AST parser without type-checking or execution. Windows batch files receive a conservative delimiter scan only, never a full syntax-validity claim. Checks are limited to 16 files per package and eight seconds per parser process. Missing parsers, timeouts, partial checks, and skipped scripts are reported; package scripts are never executed.
- **Protected-token detection is incomplete.** Unknown identifiers may be missed. Human-reviewed path/category-scoped exact token mappings are supported; SkillTether does not generate or approve rename mappings automatically.
- **Secret scanning is heuristic and bounded.** `scan-secrets` recognizes selected provider token formats, private-key headers, bearer/basic credentials, URL user-info, cloud access-key identifiers, and non-placeholder credential assignments. It scans readable UTF-8 resources only and does not validate whether credentials are active. Binary/unsupported encodings, unknown token formats, and arbitrary high-entropy values can be missed; a clean scan is not proof of no secrets.
- **Filesystem portability is checked, not guaranteed.** Common Windows-invalid path components and case/Unicode-normalization collisions are reported. This does not model every filesystem, Unicode equivalence rule, or race condition.
- **Hostile-system isolation is not provided.** File and path protections reduce common risks, but SkillTether is not a sandbox for malicious operating-system inputs.
- **Coverage is not a correctness proof.** Per-module coverage floors are not enforced, and platform-specific filesystem behavior still requires care.

## Documentation

- [Quick start and CLI workflow](docs/usage.md)
- [Invariant manifest guidance](docs/invariants.md)
- [Review evidence and approval gates](docs/review-audit.md)
- [Specification boundary and reference-validator check](docs/spec-compatibility.md)
- [Validation matrix](docs/validation-matrix.md)
- [Implementation status and limits](docs/implementation-status.md)
- [Offline reviewer workbench](docs/reviewer-workbench.md)
- [Requirements-to-code readiness audit](docs/readiness-audit.md)
- [Architecture research](docs/architecture-research.md)
- [Mitigation strategy](docs/mitigation-strategy.md)
- [Research notes](docs/research-notes.md)

## References

- [Official Agent Skills specification](https://agentskills.io/specification)
- [Agent Skills reference implementation](https://github.com/agentskills/agentskills)
- [RFC 5646 — Tags for Identifying Languages](https://www.rfc-editor.org/rfc/rfc5646)
- [IANA Language Subtag Registry](https://www.iana.org/assignments/language-subtag-registry/language-subtag-registry)
- [JSON Schema](https://json-schema.org/)

## License

GPL-3.0-only. See [LICENSE](LICENSE).
