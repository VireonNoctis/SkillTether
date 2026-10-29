# SkillTether

**Translate the words. Preserve the intent.**

SkillTether is a local-first CLI for validating and localizing Agent Skill packages. It treats a skill as a package of instructions, metadata, scripts, references, and assets—not just a Markdown string—and highlights changes that may affect operational meaning.

> **Important:** structural validation and semantic checks can identify risks, but they cannot prove a translation is equivalent or safe. Ambiguous and critical changes need human review.

## What it does

- **Validates packages:** checks `SKILL.md` frontmatter, optional metadata types, local links and fragments, referenced resources, UTF-8 expectations, package limits, symlinks, special files, and file permissions.
- **Protects machine-facing content:** identifies commands, paths, URLs, environment variables, code, and configured literals or patterns.
- **Compares source and candidate packages:** reports missing or added resources, text changes, protected-token drift, changed binary assets, permission changes, and human-authored invariant findings.
- **Guards translation structure:** preserves opaque content and Markdown syntax, validates provider output, bounds provider I/O, and refuses to publish incomplete or structurally altered candidates.
- **Supports human review:** stores findings with stable IDs, evidence, analysis method, uncertainty, severity rationale, and an auditable disposition history.
- **Keeps processing local by default:** the identity adapter makes no network calls. Remote translation requires an explicitly configured endpoint and `--allow-remote`.
- **Supports report integrity:** optional HMAC-SHA256 seals detect report edits when the signing key remains private.

The optional Svelte + TypeScript reviewer UI is deferred. The CLI and report contracts are the current interface.

## Install

Requires Python 3.13 or newer.

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

The package directory basename must match the `name` in `SKILL.md` frontmatter. Validation is read-only; bundled scripts are parsed where supported but never executed.

### 2. Create a draft invariant manifest

Keep the generated manifest **outside** the source package. The output must be a new path.

~~~sh
skilltether init-manifest ./skills/my-skill \
  --out ./review/my-skill.invariants.yaml \
  --source-locale en --target-locale fr
~~~

Suggestions are heuristic candidates, not policy. The generator skips common code examples and some likely false positives, but it can miss real constraints or misclassify prose. Review every candidate, add missing invariants, verify source references and locale-specific markers, and explicitly mark the manifest and each accepted invariant as reviewed with accountable reviewer identifiers. A generated manifest is never marked reviewed automatically.

### 3. Generate a separate candidate

The identity adapter exercises the safe pipeline without translating prose:

~~~sh
skilltether translate ./skills/my-skill ./candidate/my-skill \
  --source-locale en --target-locale fr --adapter identity \
  --invariants ./review/my-skill.invariants.yaml \
  --policy config/protected-tokens.yaml \
  --report ./review/translation-report.json
~~~

For a configured translation gateway, use the provider-neutral JSON adapter:

~~~sh
skilltether translate ./skills/my-skill ./candidate/my-skill \
  --source-locale en --target-locale fr --adapter http-json \
  --endpoint https://your-approved-gateway.example/translate \
  --allow-remote \
  --invariants ./review/my-skill.invariants.yaml \
  --policy config/protected-tokens.yaml \
  --report ./review/translation-report.json
~~~

Remote use requires both a configured endpoint and explicit consent via `--allow-remote`. Production endpoints must use HTTPS; plain HTTP is permitted only for loopback addresses. The request contains eligible prose and locale tags, not package paths, scripts, invariant manifests, or binary assets. Eligible prose can still contain confidential information, so use only an endpoint whose data handling you have approved.

The HTTP bridge expects a JSON object with a string field named `text`. It is not itself a translation service and includes no vendor SDK or built-in credentials. Translation preflight runs locally before the first provider request. Per-line request and response payloads are capped at 2 MiB; package-wide request and response budgets are also enforced. Output from custom adapters is bounded too.

The candidate must be a new, non-overlapping directory with the same basename as the source package. Translation failures do not publish a partial candidate. A JSON report and local SQLite history are written separately; history stores fingerprints and bounded run metadata, not source or target document text. The default history path is `~/.skilltether/history.sqlite3`.

### 4. Compare or regenerate a report

Use `compare` after manually editing a candidate or when you need a fresh report:

~~~sh
skilltether compare ./skills/my-skill ./candidate/my-skill \
  --invariants ./review/my-skill.invariants.yaml \
  --target-locale fr --policy config/protected-tokens.yaml \
  --out ./review/comparison.json \
  --markdown ./review/comparison.md
~~~

Reports capture source/candidate fingerprints, invariant-manifest and policy fingerprints, locale tags, and stable finding IDs. Findings distinguish deterministic checks from heuristic analysis and carry explicit uncertainty; a “no issue detected” status is not a semantic-equivalence guarantee.

### 5. Record review decisions

Record a decision for each finding that requires review and each critical finding:

~~~sh
skilltether review ./review/comparison.json FINDING_ID \
  --disposition approved --reviewer "reviewer-id" \
  --note "Compared the source and target context; approved."
~~~

The allowed dispositions are `approved`, `rejected`, and `deferred`. A non-empty rationale is required. Approval evidence must be present in the review history; a manually edited `approved` field is not sufficient. Rejected, deferred, pending, unreviewed-manifest, and invalid-source-reference blockers cannot be overridden by a bare approval.

### 6. Export an approved package

~~~sh
skilltether approve ./skills/my-skill ./candidate/my-skill \
  --report ./review/comparison.json \
  --output ./approved/my-skill \
  --invariants ./review/my-skill.invariants.yaml \
  --policy config/protected-tokens.yaml
~~~

Approval verifies that the source, candidate, manifest, and policy still match the reviewed report; it rejects structural failures and unresolved review-required findings. The output must be separate and must not already exist. Existing packages are never overwritten.

## Commands

| Command | Purpose |
|---|---|
| `skilltether validate PACKAGE` | Validate package metadata, structure, and local links |
| `skilltether init-manifest SOURCE --out FILE` | Draft invariant candidates for human review |
| `skilltether translate SOURCE OUTPUT` | Create a candidate, comparison report, and metadata history |
| `skilltether compare SOURCE TARGET --out REPORT` | Compare packages and write a review report |
| `skilltether review REPORT FINDING_ID ...` | Append a human review decision |
| `skilltether approve SOURCE TARGET ...` | Export a reviewed, fingerprint-matched candidate |
| `skilltether init-signing-key --out KEY` | Create a new private HMAC key |
| `skilltether verify-report REPORT --signing-key KEY` | Verify a report's HMAC seal without changing it |

Run `skilltether COMMAND --help` for all options. For automation that should return exit code 1 when review remains necessary, use `compare --fail-on-review` or `translate --fail-on-review`.

## Integrity model

| Content or change | Handling |
|---|---|
| Names, commands, identifiers, paths, variables, and URLs | Protect exact spans where recognized, then flag changed protected tokens |
| Frontmatter and machine-readable values | Preserve during translation and validate after |
| Code fences, inline code, script files, and opaque HTML blocks | Never send opaque content for translation; never execute scripts during inspection |
| Markdown formatting and links | Mask syntax and compare parser-visible structure; abort candidate creation on detected structural drift |
| Safety constraints, negation, limits, and prerequisites | Record as human-reviewed invariants; require review for critical or uncertain cases |
| Binary assets and filesystem modes | Fingerprint and compare as package integrity data |
| Unknown or ambiguous meaning | Report uncertainty rather than silently marking it safe |

## Limits and safety boundaries

- **No semantic-equivalence proof.** Heuristic invariant suggestions are incomplete; negation and modal-marker checks are locale-specific and do not understand full linguistic context.
- **No full Markdown/MDX AST rewriting.** Syntax masking and parser-visible checks reduce structural drift but unusual nested constructs and extension-specific syntax still need review.
- **No registry-backed locale validation.** Language tags receive dependency-free BCP 47 structural checks, but are not checked against the versioned [IANA Language Subtag Registry](https://www.iana.org/assignments/language-subtag-registry/language-subtag-registry) and are not canonicalized. See [RFC 5646](https://www.rfc-editor.org/rfc/rfc5646).
- **No external URL fetching.** Remote links are preserved but their reachability or content is not checked.
- **No complete secret scanner.** Common credential patterns are redacted in reports, but unfamiliar token formats may be missed. Do not place credentials in skill content, policy files, or reviewer notes.
- **No script execution or OS sandbox.** Inspection is static and bounded; it is not a sandbox against hostile operating-system-level inputs.
- **HMAC is an integrity seal, not identity proof.** A symmetric key can detect report edits only while it stays private; it does not authenticate a reviewer or provide non-repudiation.
- **Human-labelled corpus is limited.** CI uses a small English-language invariant-suggestion regression fixture. It is not a representative multilingual benchmark and does not yet establish category-level precision or recall.

## CI and compatibility checks

GitHub Actions runs the regression suite on Python 3.13 and 3.14 across Ubuntu, macOS, and Windows. Coverage is reported on every combination, and the aggregate 80% coverage floor is enforced on Linux only; per-module floors are not enforced.

A separate Ubuntu job runs the pinned `skills-ref@v0.0.1` reference CLI against valid, optional-metadata, and intentionally invalid fixtures. This is a compatibility smoke check, not a runtime dependency or a guarantee of complete specification conformance; upstream describes the tool as a reference implementation.

## Documentation

- [CLI workflow](docs/usage.md)
- [Invariant manifest guidance](docs/invariants.md)
- [Architecture research](docs/architecture-research.md)
- [Mitigation strategy](docs/mitigation-strategy.md)
- [Validation matrix](docs/validation-matrix.md)
- [Implementation status and limits](docs/implementation-status.md)
- [Requirements-to-code readiness audit](docs/readiness-audit.md)
- [Agent Skills specification boundary](docs/spec-compatibility.md)
- [Review evidence and approval gates](docs/review-audit.md)

## References

- [Official Agent Skills specification](https://agentskills.io/specification)
- [Agent Skills reference implementation](https://github.com/agentskills/agentskills)
- [RFC 5646 — Tags for Identifying Languages](https://www.rfc-editor.org/rfc/rfc5646)
- [JSON Schema](https://json-schema.org/)

## License

GPL-3.0-only. See [LICENSE](LICENSE).
