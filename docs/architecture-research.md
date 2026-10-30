# SkillTether Architecture and Research Notes

This document records the architecture behind the current CLI implementation and separates shipped behavior from longer-term proposals. The [implementation-status page](implementation-status.md) and [readiness audit](readiness-audit.md) are the source of truth for implemented scope.

## Pipeline

Inventory package → validate metadata/resources → identify protected spans → apply the selected adapter to eligible prose → validate adapter output and Markdown structure → compare source/target packages and invariants → record human review → export to a separate directory.

## Architecture status

- **Implemented:** Python 3.13+ CLI; PyYAML and markdown-it-py parsing; Pydantic models and JSON Schema contracts; provider-neutral translation adapters; dependency-free BCP 47 structural checks; pytest/Hypothesis regression tests; GitHub Actions CI.
- **Implemented, optional:** SQLite run history stores metadata and package fingerprints without document-text columns.
- **Implemented, deliberately bounded:** local package inventory, safe I/O/output guards, Windows/case/Unicode path-portability findings, protected-token policy, GFM-like/Pandoc Markdown parsing, MDX unsupported-syntax detection, Markdown syntax masking, structural comparison, six-language heuristic invariant suggestions, positional context fallback, audit reports, optional HMAC-SHA256 sealing, and an offline HTML review workbench.
- **Deferred:** Svelte + TypeScript review UI, vendor-specific SDK integrations, automatic protected-token rename mappings, and full semantic-equivalence analysis.
- **Not claimed:** canonicalization or IANA registry membership for language tags, online link reachability, complete shell/JavaScript/PowerShell parsing, or full CommonMark/MDX AST transformation.

## Specification boundary

The normative format reference is the [official Agent Skills specification](https://agentskills.io/specification). Keep required frontmatter and optional-field rules aligned with that source. See [specification boundary and additional safeguards](spec-compatibility.md) for the distinction between base-format requirements and SkillTether operational checks.

## Package inventory

The package scanner now reports common Windows-reserved file names/characters, trailing spaces/periods, and collisions after Unicode NFC normalization plus case-folding. These deterministic portability findings improve cross-platform review, but do not model every filesystem's comparison rules or eliminate concurrent mutation races.

The validator inspects a bounded package snapshot including file paths, file types, sizes, hashes, filesystem modes, expected text encodings, frontmatter metadata, local link targets, and conventional resource references. The local-link validator parses links in table cells, decodes percent-encoded fragments, and reports malformed URL syntax instead of crashing. Fragment validation reuses the bounded inventory where possible; fallback reads are bounded and refuse a final-component symlink. External URLs are not fetched and referenced scripts are never executed.

## Protected-span model

Protected spans cover categories such as tool names, commands, file paths, environment variables, URLs, code, safety constraints, numeric limits, and identifiers. Sources include built-in patterns and the reviewed `config/protected-tokens.yaml` policy. The patterns are bounded and screened for common catastrophic-backtracking shapes; that screening is conservative and does not prove safe complexity or detect every operational literal.

## Invariant model

The suggestion layer has explicit cue profiles for English, French, Spanish, German, Portuguese, and Italian. Its 30-positive labelled corpus computes exact precision/recall by primary language and four rule families; it is not representative of naturalistic text or language varieties. Target context uses NFC/casefold, stopword-filtered overlap, and then a preserved-line-position fallback when line counts match; positional mapping is explicitly high-uncertainty. Neither cue profiles nor positional location establish equivalent meaning.

Each invariant can carry a stable ID, statement, category, source file and line range, source excerpt, tokens/numbers, criticality/severity, reviewer, and review status. Source anchors are checked against the current source text. Manifest suggestion generation is heuristic: it avoids several common code/example regions and unactionable numeric facts, but it is neither complete nor authoritative. Findings preserve locations and evidence where available.

## Translation adapters and Markdown boundaries

The parser profile covers CommonMark plus GFM-like tables, strikethrough, task lists and alerts, and Pandoc-style footnotes and definition lists. Obvious MDX module, JSX, and embedded-expression syntax is reported as unsupported and is not executed or translated by the pipeline. This is a bounded supported subset, not full Markdown/MDX compatibility.

The core uses a narrow `TranslationAdapter` interface. The identity adapter is local and does not translate. The generic JSON HTTP adapter requires an explicit endpoint and `--allow-remote`; the CLI performs a whole-package preflight before the first request and enforces request/response budgets. Provider failures, malformed results, control characters, placeholder violations, and detected Markdown structure changes must not publish a partial candidate.

The Markdown transformer uses lexical masks and placeholders for supported syntax and keeps selected opaque regions unchanged. A parser-visible structure signature detects many inserted or removed links, emphasis, lists, headings, code blocks, and tables. It intentionally ignores ordinary prose text. This is a structural guard, not a full CommonMark/MDX AST transformer and not a semantic-equivalence score.

## Trust boundaries

The static reviewer workbench loads user-selected JSON locally, does not make network requests or use browser storage, and renders report content as text. It may append decisions to unsigned reports; signed reports are read-only and must be reviewed through the CLI with the HMAC key. Browser review does not authenticate identity or replace model/schema validation and CLI approval gates.

Source packages, scripts, link targets, imported manifests, configured regular expressions, and provider outputs are untrusted. Reads and traversal are bounded; special files and symlink cases are guarded; scripts are inspected statically and never executed; outputs are staged separately. Reports escape/fence untrusted content before rendering. Credential redaction recognizes selected common patterns only and is not a complete secret scanner.

Remote services can receive eligible prose only after the user explicitly configures and consents to the remote adapter. The user's provider agreement, retention choices, and access controls remain outside SkillTether's control.

## Status semantics

Structural check outcomes and semantic-review outcomes are kept distinct. Deterministic findings report a specific detected mismatch; heuristic findings can be false positives or misses; the absence of a finding is not proof of equivalence. Human review and scenario testing remain necessary for critical or ambiguous instructions. Never collapse these signals into a single “safe translation” bit.
