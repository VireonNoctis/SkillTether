# SkillTether

**Translate the words. Preserve the intent.**

SkillTether is a local-first CLI for validating and localizing [Agent Skills](https://agentskills.io/specification). It treats a skill as a package—`SKILL.md`, metadata, scripts, references, assets, and relative paths—not just a block of prose.

> **Safety boundary:** automated checks can reveal suspicious changes; they cannot prove semantic equivalence or certify a translation as safe. Critical and ambiguous instructions require human review.

## What it does

- **Validate the package:** check frontmatter, metadata types, local links and fragments, referenced resources, path safety, file modes, encodings, and bounded package size. Scripts are inspected statically and **never executed**.
- **Protect machine-facing content:** identify commands, code, URLs, paths, environment variables, and configured identifiers; flag token changes and package-resource drift.
- **Track operational invariants:** create a draft YAML manifest for requirements, negations, numeric limits, prerequisites, and decision rules. Draft suggestions include explicit cue profiles for English, French, Spanish, German, Portuguese, and Italian, with a curated evaluation fixture that reports precision/recall by language and rule family; the cues remain heuristic and unreviewed until a person curates them.
- **Localize Markdown carefully:** use a shared GFM-like parser with tables, task lists, alerts, strikethrough, footnotes, and definition lists. Protect syntax, enforce provider budgets, and reject detected structure drift; obvious MDX-only constructs are flagged rather than translated. This is not a complete CommonMark/MDX AST transformation.
- **Keep decisions auditable:** generate JSON/Markdown reports, retain review history and rationale, and require fingerprint-matched evidence before exporting an approved candidate.
- **Review reports offline:** open the dependency-free local workbench in reviewer/index.html to inspect evidence, filter findings, record decisions on unsigned reports, and export the updated JSON. HMAC-signed reports remain read-only in the browser.
- **Make remote translation opt-in:** the default identity adapter sends no content. The generic JSON adapter requires an endpoint and explicit `--allow-remote` consent; per-line and aggregate limits bound provider output.
- **Keep local run metadata minimal:** optional SQLite history stores fingerprints and run metadata, not source/target document text.
- **Support report integrity:** optionally seal JSON reports using a local HMAC-SHA256 key and verify the seal before review or approval.

See the [requirements-to-code readiness audit](docs/readiness-audit.md) for the traceability matrix and known gaps.

## Install

Requires Python 3.13 or newer. CI tests Python 3.13 and 3.14 on Ubuntu, macOS, and Windows.

~~~sh
python -m pip install -e ".[dev]"
skilltether --version
pytest
~~~

## Typical workflow

### 1. Validate the source package

~~~sh
skilltether validate ./skills/my-skill
~~~

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

For an approved remote gateway, use the provider-neutral JSON bridge:

~~~sh
skilltether translate ./skills/my-skill ./candidate/my-skill \
  --source-locale en --target-locale fr --adapter http-json \
  --endpoint https://your-approved-gateway.example/translate \
  --allow-remote \
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

`rejected` and `deferred` findings remain blockers. Missing or unreviewed manifests and invalid source references cannot be approved away; correct them and rerun comparison. Export to a new directory:

~~~sh
skilltether approve ./skills/my-skill ./candidate/my-skill \
  --report ./review/report.json --output ./approved/my-skill \
  --invariants ./review/my-skill.invariants.yaml \
  --policy config/protected-tokens.yaml
~~~

Approval checks the current fingerprints and review evidence, rejects structural failures and unresolved blockers, and refuses existing or unsafe output paths. It never overwrites an existing approved package.

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
| `skilltether validate PACKAGE` | Validate package metadata, structure, and local links |
| `skilltether init-manifest SOURCE --out FILE` | Generate unreviewed invariant candidates |
| `skilltether translate SOURCE OUTPUT` | Create a candidate and initial report |
| `skilltether compare SOURCE TARGET --out REPORT` | Compare packages and create a review queue |
| `skilltether review REPORT FINDING_ID ...` | Append a human decision and rationale |
| `skilltether approve SOURCE TARGET --report REPORT --output OUTPUT` | Export a fingerprint-matched, approved candidate |
| `skilltether init-signing-key --out FILE` | Create a private report-signing key |
| `skilltether verify-report REPORT --signing-key KEY` | Verify a signed report without modifying it |

Use `skilltether COMMAND --help` for available options. For automation that should fail when semantic review is still required, `compare` and `translate` support `--fail-on-review`.

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

GitHub Actions tests the suite on **Python 3.13 and 3.14 × Ubuntu, macOS, and Windows**. It reports line and branch coverage on all six combinations and enforces the **80% aggregate coverage floor on Linux**. A separate Ubuntu job checks valid and invalid fixtures with the pinned `skills-ref@v0.0.1` reference validator, including a valid fixture with optional metadata. That smoke test is compatibility evidence, not a full differential benchmark; the reference tool is not a runtime dependency.

## Limits

- **No semantic-equivalence guarantee.** Invariants and marker comparisons are heuristic and context-sensitive. Critical operational instructions need human review.
- **Locale validation is structural.** BCP 47 formatting and ordering are checked, but IANA registry membership and canonicalization are not.
- **Reference and syntax coverage is bounded.** External URLs are not fetched. The parser supports a documented GFM-like/Pandoc subset; heading fragments and MDX detection have known limits. JSX and JavaScript constructs are flagged as unsupported, not parsed or translated. Shell, JavaScript, and PowerShell resources are not fully semantically parsed.
- **Protected-token detection is incomplete.** Unknown identifiers may be missed. Automatic renamed-token mappings are not implemented.
- **Secret redaction is not a secret scanner.** Common credential shapes are redacted, but unfamiliar formats may pass through. Do not store credentials in skill content, policy files, or review notes.
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
