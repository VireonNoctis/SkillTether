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

Versioned YAML manifests record reviewer-maintained expectations about requirements, negation, limits, prerequisites, and decision rules. The manifest generator suggests candidates using heuristics. Source anchors are checked against current source content, while target comparison uses exact-token/numeric/marker checks and contextual heuristics. These checks inform review; they do not establish semantic equivalence. Critical and ambiguous instructions need qualified human review and scenario testing.

### Translation and provider boundary

The identity adapter enables a no-network pipeline exercise but does not translate. The generic JSON HTTP adapter is used only when an endpoint is configured and remote consent is explicit. Whole-package preflight and adapter-level budgets constrain requests and output. Markdown syntax masking and parser-visible structure checks detect some structural drift; they are not a complete Markdown/MDX transformation.

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

1. Expand the human-reviewed positive/negative invariant corpus across languages and Markdown constructs, then measure precision/recall by rule family.
2. Improve Markdown reference/slug and extension handling without claiming a complete CommonMark/MDX AST.
3. Define a documented differential compatibility corpus for the pinned reference validator and selected optional/unknown metadata fields.
4. Explore better evidence-linked semantic review methods with explicit calibration and reviewer control; do not turn model confidence into an approval guarantee.
5. Decide how provider-specific configuration and provenance should be represented without coupling the core to one vendor.
6. Evaluate extra filesystem configurations and new Python minors before claiming support outside the currently tested CI matrix.

## Limits

Natural-language meaning is context-dependent. The same phrase can be a safety constraint in one section and an illustrative example in another. Automated checks can identify suspicious differences but cannot certify complete semantic equivalence. Critical instructions require human review and scenario testing. See [implementation status](implementation-status.md), [the readiness audit](readiness-audit.md), and [the validation matrix](validation-matrix.md) for current evidence and supported scope.
