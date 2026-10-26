# SkillTether Architecture Research

## Pipeline
Inventory package → parse structure → identify protected spans → apply configured translation adapter → re-parse output → compare invariants → human review → export to a separate directory.

## Intended stack
- Python 3.13+ for CLI, parsing, diffing, rules, and translation-provider interfaces.
- YAML parser and Markdown parser selected with strict modes and well-defined error handling.
- Pydantic and JSON Schema for manifests and report contracts.
- BCP 47 language tags for source and target locale identifiers.
- SQLite only if local review history proves valuable.
- Svelte + TypeScript as a later optional review interface.
- pytest, property-based tests, and GitHub Actions for regressions and adversarial fixtures.

## Package inventory
Record original file path, type, size, hash, encoding where detectable, frontmatter metadata, link targets, and referenced resources. Avoid reading or executing a script merely to translate its surrounding documentation.

## Protected-span model
Each span has path, source range, category, exact literal or matching rule, criticality, and policy. Categories may include tool names, commands, file paths, environment variables, URLs, code, safety constraints, numeric limits, and identifiers. A rule must be able to distinguish a literal code example from narrative prose.

## Invariant model
Represent an invariant as a stable ID, source text or reference, category, condition, required/forbidden action, threshold or limit if relevant, criticality, reviewer, and status. Findings must point back to the relevant source and target ranges.

## Translation adapters
Define a narrow adapter interface with source locale, target locale, provider identity, configuration, and data-handling declaration. Provider use should require explicit configuration. Store neither API keys nor raw credentials in reports. A failed provider call must not create partially translated output that appears complete.

## Trust boundaries
Source packages, scripts, links, model outputs, and imported manifests are untrusted. Parse safely, bound file sizes, never execute scripts during analysis, and write output to a new path. Reports should escape arbitrary source text when rendered.

## Status semantics
Structural check outcomes: pass, fail, unsupported, or error. Semantic check outcomes: no issue detected, review recommended, reviewer approved, reviewer rejected, or unknown. Do not merge these states into one “safe” bit.
