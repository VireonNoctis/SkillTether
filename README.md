# SkillTether

<p align="center">
  <strong>Translate the words. Preserve the intent.</strong><br/>
  A localization and integrity-testing toolkit for AI Agent Skills.
</p>

---

## The problem

A Skill package is more than prose. A translated instruction set can accidentally weaken a constraint, change a command or tool identifier, break a path, alter a condition, or turn a mandatory requirement into a suggestion. Ordinary translation quality checks do not reliably catch these failures.

SkillTether is planned to translate and validate Agent Skill packages while protecting critical invariants. It compares the source and localized package, finds risky changes, and presents evidence for a human reviewer.

> **No automatic checker can guarantee semantic equivalence for every instruction.** SkillTether is a risk detector and review aid, not a substitute for testing or human approval.

## Planned capabilities

- Parse a skill directory and validate SKILL.md metadata and structure.
- Identify protected tokens such as tool names, commands, paths, environment variables, URLs, identifiers, and code blocks.
- Maintain a human-reviewed invariant manifest for safety constraints, mandatory conditions, negations, limits, and decision rules.
- Support translation-provider adapters without coupling the core to one vendor.
- Compare source and target language documents with line-level, token-level, and invariant-level findings.
- Detect omitted sections, broken links, malformed frontmatter, missing resources, and altered file paths.
- Build a review queue with severity rationale, original context, proposed change, and human disposition.
- Export a reproducible report and keep translation history local by default.

## Workflow

1. Load a package as read-only input and fingerprint its files.
2. Parse frontmatter, Markdown structure, links, scripts, references, and assets.
3. Extract protected spans and explicit invariants.
4. Translate only eligible prose using a configured adapter.
5. Validate structure and protected tokens after translation.
6. Run invariant checks and flag likely semantic drift.
7. Require review for critical findings and uncertain cases.
8. Export a report and write an approved output to a separate directory.

## Planned technology stack

| Component | Planned technology | Purpose |
|---|---|---|
| Core CLI and package analysis | Python 3.13+ | Markdown/frontmatter parsing, diffing, rules, adapters |
| Contract validation | Pydantic + JSON Schema | Validate project manifests and findings |
| Locale metadata | BCP 47 language tags | Identify language/region consistently |
| Rule configuration | YAML and JSON | Explicit invariants and protected-token policies |
| Local case history | SQLite, if persistence proves useful | Review state and report metadata |
| Optional review interface | Svelte + TypeScript | Source/target diff and reviewer decisions |
| Tests and CI | pytest, property-based tests, GitHub Actions | Adversarial skill fixtures and regression testing |

Translation engines are adapters, not built-in truth sources. Any external provider must be configured deliberately; sending skill content outside the machine should require explicit consent and a clear data-handling explanation.

## Documentation

- [Research notes](docs/research-notes.md)
- [Mitigation strategy](docs/mitigation-strategy.md)
- [Architecture research](docs/architecture-research.md)
- [Validation matrix](docs/validation-matrix.md)

## Integrity model

| Content type | Default handling |
|---|---|
| Tool names, commands, API identifiers, paths, variables | Protect or flag for explicit review |
| Code blocks and machine-readable frontmatter | Preserve unless a declared schema-aware transform is enabled |
| Safety constraints, negations, limits, preconditions | Treat as critical invariants with human review |
| Natural-language explanatory prose | Eligible for translation and semantic checks |
| Unknown or ambiguous content | Flag; do not silently guess |

A valid package can still contain a wrong translation. Structural validity and semantic fidelity are separate outcomes.

## Principles

- Preserve the original source and write targets to a separate output.
- Version protected-token and invariant rules.
- Keep machine findings distinct from human decisions.
- Never remove a warning merely because the translated text is fluent.
- Do not claim that an invariant checker proves intent was preserved.
- Avoid sending private skills to external services without explicit approval.
- Treat executable scripts and referenced resources as untrusted content.

## Project status

**Research / early planning.** The README and documentation set the intended architecture and safety criteria; implementation claims must be based on code and passing tests.

## Roadmap

- [ ] Define a versioned skill-package inventory schema.
- [ ] Validate SKILL.md frontmatter and required fields against the current Agent Skills specification.
- [ ] Build protected-token and structural-diff checks.
- [ ] Add invariant manifests and omission/negation checks.
- [ ] Add translation adapters behind an explicit privacy boundary.
- [ ] Build a human-reviewable report and regression fixture library.
- [ ] Add a review UI only after result contracts stabilize.

## Research references

- Agent Skills specification and project: https://agentskills.io/ and https://github.com/agentskills/agentskills
- RFC 5646, language tags: https://www.rfc-editor.org/rfc/rfc5646
- JSON Schema: https://json-schema.org/
- NIST Generative AI Profile: https://doi.org/10.6028/NIST.AI.600-1

## Contributing

Include a minimal skill fixture, expected invariants, an example of the failure being prevented, and both positive and negative tests. Do not include private instructions or secrets in fixtures.

## License

Add an explicit licence before treating this repository as licensed for reuse.
