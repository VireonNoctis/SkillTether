# SkillTether

**Translate the words. Preserve the intent.**

SkillTether is a local-first localization and integrity-checking CLI for Agent Skill packages. It treats a skill as a directory of instructions and resources—not merely a text blob—and reports where localization may have changed machine-facing tokens, package structure, mandatory conditions, negation, numeric limits, or decision logic.

> **Safety boundary:** automated checks identify risks; they do not prove semantic equivalence. Critical instructions and uncertain cases require human review.

## Included in this MVP

- Read-only package inventory with SHA-256 hashes, filesystem permission bits, bounded per-file and aggregate sizes, bounded directory/file counts and depth, UTF-8 detection, symlink rejection, and special-file rejection.
- SKILL.md YAML-frontmatter checks: required fields, name syntax and directory identity, description length, compatibility, metadata types, and body presence.
- Local Markdown links and image assets, in-document fragments, and conventional scripts/references/assets/resources path checks. External URLs are not fetched.
- Static syntax checks for Python scripts and JSON/YAML/TOML/XML resources; scripts are parsed, never executed.
- Protected-span detection for fenced/inline code, URLs, environment variables, command flags, paths, plus configurable regexes and explicit identifiers.
- A human-authored YAML invariant manifest with categories for safety constraints, mandatory conditions, negation, numeric limits, preconditions, and decision rules.
- Line-block, protected-token, package-path, file-mode, non-text resource, and invariant findings with stable rule IDs, explicit deterministic/heuristic method labels, uncertainty states, severity rationale, source/target context, and reviewer disposition.
- Chronological review history with mandatory reviewer identifiers and non-empty rationale; approval requires the latest decision to match a consistent audit history.
- A provider-neutral adapter protocol, an identity adapter for local pipeline tests, and an optional generic JSON-over-HTTPS adapter. No provider is called by default.
- Atomic candidate output, separate explicit approval/export, atomic private JSON/Markdown reports, output-path guards that protect source/candidate packages, bounded reads for manifests/policies/reports/history, actual JSON Schema regression checks, and private SQLite run metadata without document text or credentials.
- Redaction of common credential patterns in finding evidence and persisted reports, plus explicit limits explaining that this is not a complete secret scanner.
- pytest and Hypothesis regression fixtures, plus GitHub Actions CI.

The optional Svelte + TypeScript review UI is intentionally deferred until the report contracts are stable.

## Install

Requires Python 3.13 or newer.

~~~sh
python -m pip install -e ".[dev]"
skilltether --version
pytest
~~~

## Typical workflow

### 1. Validate a source skill

~~~sh
skilltether validate ./skills/my-skill
~~~

The package root basename must match the SKILL.md frontmatter name. The source is read-only; scripts are never executed.

### 2. Draft an invariant manifest

~~~sh
skilltether init-manifest ./skills/my-skill \
  --out ./skills/my-skill/.skilltether-invariants.yaml \
  --source-locale en --target-locale fr
~~~

Suggestions are heuristic candidates, not policy. Edit them and have an appropriate human reviewer confirm every invariant, populate locale-specific negation/mandatory markers where useful, then set manifest_reviewed and each invariant's reviewed fields to true with reviewer identifiers.

### 3. Translate to a separate candidate directory

For local pipeline checks with no translation, use the identity adapter:

~~~sh
skilltether translate ./skills/my-skill /tmp/candidate/my-skill \
  --source-locale en --target-locale fr --adapter identity \
  --invariants ./skills/my-skill/.skilltether-invariants.yaml \
  --policy config/protected-tokens.yaml
~~~

For a remote service, configure a JSON endpoint matching the contract below. Remote transmission requires the explicit --allow-remote flag and an HTTPS endpoint (HTTP is permitted only on loopback):

~~~sh
skilltether translate ./skills/my-skill /tmp/candidate/my-skill \
  --source-locale en --target-locale fr --adapter http-json \
  --endpoint https://your-approved-translation-gateway.example/translate \
  --allow-remote --invariants ./skills/my-skill/.skilltether-invariants.yaml \
  --policy config/protected-tokens.yaml
~~~

The HTTP bridge sends only eligible prose segments as JSON: source text, source locale, and target locale. It expects JSON with a string text field. It has no built-in credentials or vendor assumption. Review the endpoint's data handling before granting consent.

Candidate output and its JSON report are separate from the original package. Translation failures do not publish a partial candidate. The default SQLite history at ~/.skilltether/history.sqlite3 records timestamps, locales, provider name, status, and fingerprints only—not raw source/target text, secrets, or credentials.

### 4. Compare or regenerate a report

~~~sh
skilltether compare ./skills/my-skill /tmp/candidate/my-skill \
  --invariants ./skills/my-skill/.skilltether-invariants.yaml \
  --target-locale fr --policy config/protected-tokens.yaml \
  --out ./review/report.json --markdown ./review/report.md
~~~

The JSON report is the machine-readable review record. It records source and target fingerprints, the canonical human-reviewed manifest fingerprint, the protected-policy fingerprint, locale tags, and (for translate runs) the adapter name. Each finding has a stable ID derived from its evidence and fields for disposition, reviewer, and note.

### 5. Record human decisions and export an approved package

For every finding that requires review (and every critical finding), record a disposition:

~~~sh
skilltether review ./review/report.json FINDING_ID \
  --disposition approved --reviewer "reviewer-id" \
  --note "Compared source and target context; approved."
~~~

Findings with rejected/deferred/pending status remain blockers. Missing or unreviewed manifests are blockers and cannot be approved away: update the manifest and rerun compare. Then export to a new directory with the same skill basename:

~~~sh
skilltether approve ./skills/my-skill /tmp/candidate/my-skill \
  --report ./review/report.json --output ./approved/my-skill \
  --invariants ./skills/my-skill/.skilltether-invariants.yaml \
  --policy config/protected-tokens.yaml
~~~

Approval checks source/candidate/manifest/policy fingerprints against the reviewed report, rejects structural failures and unresolved critical/review findings, and copies only to a separate, previously nonexistent output directory. It never overwrites an existing package.

## Commands

| Command | Purpose |
|---|---|
| skilltether validate PACKAGE | Validate SKILL.md metadata, package safety, and local links |
| skilltether init-manifest SOURCE --out FILE | Suggest human-reviewable invariant candidates |
| skilltether translate SOURCE OUTPUT | Generate a candidate and an initial comparison report |
| skilltether compare SOURCE TARGET --out REPORT | Compare packages and build a review queue |
| skilltether review REPORT FINDING_ID ... | Record approved/rejected/deferred human disposition |
| skilltether approve SOURCE TARGET --report REPORT --output OUTPUT | Export only a reviewed, fingerprint-matched candidate |

Run skilltether COMMAND --help for flags. For CI runs that should fail when human review remains necessary, use `compare --fail-on-review` or `translate --fail-on-review`; without the flag, reports can be generated while preserving the existing structural exit-code behavior.

## Integrity model

| Content | Default handling |
|---|---|
| Names, identifiers, commands, paths, variables, URLs | Protect exact spans or flag mismatches |
| Frontmatter and machine-readable values | Preserve during translation and validate after |
| Code blocks and scripts | Never execute; code blocks are preserved and compared exactly |
| Safety constraints, negation, limits, preconditions | Record in the invariant manifest and require review for critical cases |
| Ordinary prose | Eligible for configured adapters after Markdown/opaque-span masking |
| Unknown or ambiguous meaning | Report uncertainty; do not silently mark semantically safe |

## Limits

- Heuristic invariant suggestions are incomplete and can be wrong. Human-review the manifest.
- Negation/modal-marker detection is locale-specific and does not understand full linguistic context.
- Changed protected tokens require explicit review; this MVP does not implement automatic rename mappings.
- External URLs are not fetched, so network reachability and remote content are outside the default offline check.
- Source hashes and the candidate are checked, but this is not a sandbox for hostile operating-system-level inputs.
- The generic HTTP adapter is a bridge contract, not a translation service. Configure a service you trust.
- Credential redaction is a high-confidence guardrail, not a complete secret scanner. Do not put credentials into skill content, policy files, or reviewer notes; unfamiliar token formats may not be detected.
- The report is reproducible from fingerprints (including filesystem mode), versioned rules, and stable finding IDs; generated timestamps naturally vary.
- Review history is a local audit aid, not a cryptographic signature: it cannot authenticate reviewer identity or prevent deliberate report-file edits.

## Documentation

- [Quick start and workflow](docs/usage.md)
- [Invariant manifest guidance](docs/invariants.md)
- [Architecture research](docs/architecture-research.md)
- [Mitigation strategy](docs/mitigation-strategy.md)
- [Validation matrix](docs/validation-matrix.md)
- [Implementation status and limits](docs/implementation-status.md)
- [Review evidence and approval gates](docs/review-audit.md)

## Research references

- [Agent Skills specification](https://agentskills.io/specification)
- [Agent Skills reference implementation](https://github.com/agentskills/agentskills)
- [RFC 5646 — Tags for Identifying Languages](https://www.rfc-editor.org/rfc/rfc5646)
- [JSON Schema](https://json-schema.org/)

## License

GPL-3.0-only. See LICENSE.
