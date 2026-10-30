# SkillTether Research Notes

## Research question

How can an Agent Skill be localized while preserving operational constraints, identifiers, decision logic, package integrity, and safety-relevant meaning without presenting heuristic analysis as proof?

## Specification and package model

The Agent Skills format uses a directory package whose core file is `SKILL.md`, with metadata and optional scripts, references, and assets. The public specification is maintained at [agentskills.io](https://agentskills.io/specification) and [the Agent Skills repository](https://github.com/agentskills/agentskills).

**Design implication:** localization must operate on the package, not only on a text blob. Metadata, references, relative paths, scripts, permission bits, binary resources, and resource names require integrity checks before and after translation.

## Why ordinary translation checks are insufficient

- A negation can disappear or reverse.
- “Must” can become “should”.
- A prerequisite or threshold can be moved, weakened, or lost.
- A command, tool identifier, environment variable, path, or URL can be mistranslated.
- An example may be mistaken for an instruction or vice versa.
- A translated Markdown file may be fluent but have broken structure or missing resources.
- Translation systems may invent unsupported details or normalize text in ways that change operational meaning.
- A structurally valid package may still contain a semantically unsafe translation.

## Current implementation approach

### Structural and package invariants

The CLI validates `SKILL.md` frontmatter, supported metadata types, local links/fragments and conventional resource references. It fingerprints the bounded package, includes file-mode information, validates expected text encodings, rejects symlink/special-file cases, and inspects supported data/script formats statically. It does not execute package scripts or fetch external URLs.

### Protected spans

Built-in detection and a reviewed policy protect common code, commands, flags, identifiers, environment variables, paths, URLs, and other configured literals. Detection is pattern-driven and incomplete; unrecognized operational literals can be missed.

### Human-reviewed operational invariants

Versioned YAML manifests record reviewer-maintained expectations about requirements, negation, limits, prerequisites, and decision rules. Draft cue profiles now cover six primary languages (English, French, Spanish, German, Portuguese, and Italian) and are measured against a small human-labelled positive/negative corpus. Exact precision/recall on that corpus is regression evidence only, not a representative multilingual benchmark. Source anchors are checked against current source content. Target comparison uses exact-token/numeric/marker checks, Unicode-normalized marker matching, word overlap, and a labelled line-position fallback when source and target line counts are identical. Every non-deterministic context location remains heuristic; positional alignment cannot establish equivalent meaning. Critical and ambiguous instructions need qualified human review and scenario testing.

### Translation and provider boundary

The identity adapter enables a no-network pipeline exercise but does not translate. The generic JSON HTTP adapter is used only when an endpoint is configured and remote consent is explicit. Whole-package preflight and adapter-level budgets constrain requests and output. The shared parser supports CommonMark plus GFM-like tables, strikethrough, task lists, alerts, footnotes, and definition lists. Parser-visible structure comparison detects some structural drift. Common MDX-only constructs are flagged as unsupported instead of being treated as plain Markdown; there is still no complete MDX AST transformer.

### Locale metadata and audit evidence

BCP 47 tag structure is validated consistently across CLI/model/history surfaces without registry-backed canonicalization. Versioned report contracts, evidence locations, method/uncertainty fields, reviewer history, optional local SQLite metadata history, and optional HMAC report seals support review traceability. HMAC is a shared-key integrity check, not reviewer authentication; history itself is not cryptographically tamper-evident.

## Threats to validity

| Risk | Why it matters | Current response and remaining limit |
|---|---|---|
| Fluent mistranslation | Surface quality hides a changed instruction | Human-reviewed invariants and contextual findings; semantic equivalence is not proven |
| Lost negation or threshold | A safety condition can be reversed | Marker, token, number and heuristic checks; locale grammar and morphology can cause false positives/negatives |
| Identifier mutation | Tools and commands may stop working | Protected spans and exact-token tests; unrecognized literals may be missed |
| Broken package structure | Agent may fail to load the skill or miss resources | Bounded inventory, metadata/link/resource checks, structural comparisons; external links are not checked online |
| Hallucinated instruction | Translation may add unsupported steps | Line/content diffs, added-content findings, and review gates; new imperative classification is incomplete |
| Different client behaviours | Consumers may interpret extensions differently | Normative specification boundary and a pinned reference-validator smoke test, not a guarantee for all clients |
| Confidential skill disclosure | Provider receives private operational content | Local default/identity path, explicit remote opt-in and budget checks; provider retention remains external |
| Hostile files or model output | Inputs may trigger resource exhaustion or unsafe publication | Bounded reads, symlink/special-file checks, staging and output validation; platform/filesystem behavior remains a residual risk |

## Open research and engineering gaps

1. Expand the multilingual labelled corpus beyond the six current profiles. Current exact-match metrics are reported by language and rule family on 30 curated positive examples, but dialect, regional, script, and real-world package coverage remain limited.
2. Replace word-overlap and positional context heuristics with stronger evidence-linked multilingual alignment while preserving explicit uncertainty and reviewer control.
3. Evaluate fuller MDX support only with a parser that can safely model JSX/JavaScript syntax without executing it; current behavior flags obvious constructs and refuses to localize those files.
4. Expand portability testing to additional normalization variants, network/removable filesystems, and platform-specific path semantics; the current path check covers common Windows name hazards and casefold/NFC collisions.
5. Consider a typed component-based reviewer UI if the offline HTML workbench grows beyond its intentionally small scope.
6. Define a documented differential compatibility corpus for the pinned reference validator and selected optional/unknown metadata fields.
7. Improve evidence-linked drift analysis without treating language-model confidence as ground truth or an approval guarantee.

## Limits

Natural-language meaning is context-dependent. The same phrase can be a safety constraint in one section and an illustrative example in another. Automated checks can identify suspicious differences but cannot certify complete semantic equivalence. Critical instructions require human review and scenario testing. See [implementation status](implementation-status.md), [the readiness audit](readiness-audit.md), and [the validation matrix](validation-matrix.md) for current evidence and supported scope.
