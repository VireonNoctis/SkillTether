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

## Specification boundary

The normative format reference is the [official Agent Skills specification](https://agentskills.io/specification). Keep required frontmatter and optional-field rules aligned with that source. See [specification boundary and additional safeguards](spec-compatibility.md) for the distinction between base-format requirements and SkillTether operational checks.

## Package inventory
Record original file path, type, size, hash, filesystem mode, encoding where detectable, frontmatter metadata, link targets, and referenced resources. Bound per-file/aggregate bytes and directory traversal. Avoid reading or executing a script merely to translate its surrounding documentation.

## Protected-span model
Each span has path, source range, category, exact literal or matching rule, criticality, and policy. Categories may include tool names, commands, file paths, environment variables, URLs, code, safety constraints, numeric limits, and identifiers. A rule must be able to distinguish a literal code example from narrative prose. Policy regexes are size/count bounded and screened for common catastrophic-backtracking shapes; this heuristic is not a proof of safe complexity.

## Invariant model
Represent an invariant as a stable ID, source text or reference, category, condition, required/forbidden action, threshold or limit if relevant, criticality, reviewer, and status. Findings must point back to the relevant source and target ranges.

## Translation adapters
Define a narrow adapter interface with source locale, target locale, provider identity, configuration, and data-handling declaration. Provider use should require explicit configuration. Enforce per-line and aggregate response budgets at the adapter boundary, not only in the built-in HTTP implementation; reject line separators, unsupported control characters, and invalid Unicode before writing a candidate. Store neither API keys nor raw credentials in reports. A failed provider call must not create partially translated output that appears complete.

After prose translation and placeholder restoration, compare parser-visible Markdown structure while ignoring ordinary text tokens. This catches accidental or malicious insertion/removal of links, emphasis, lists, headings, code blocks, and tables even when the original placeholders remain present. Keep this structural signature deterministic and separate from multilingual semantic heuristics; it is not a semantic-equivalence score or a complete parser for MDX extensions.

## Trust boundaries
Source packages, scripts, links, model outputs, and imported manifests are untrusted. Parse safely, bound file sizes, never execute scripts during analysis, and write output to a new path. Reports should escape arbitrary source text when rendered.

## Status semantics
Structural check outcomes: pass, fail, unsupported, or error. Semantic check outcomes: no issue detected, review recommended, reviewer approved, reviewer rejected, or unknown. Do not merge these states into one “safe” bit.
