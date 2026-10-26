# SkillTether Research Notes

## Research question
How can an Agent Skill be localized while preserving operational constraints, identifiers, decision logic, and safety-relevant meaning?

## Relevant specification
The Agent Skills format packages instructions in a directory whose core file is SKILL.md, with metadata and optional scripts, references, and assets. The public specification is maintained at https://agentskills.io/ and https://github.com/agentskills/agentskills.

**Design implication:** localization must operate on the package, not only on a text blob. Metadata, references, relative paths, scripts, and resource names must be validated after translation.

## Why ordinary translation checks are insufficient

- A negation can disappear or reverse.
- “Must” can become “should”.
- A prerequisite can be moved or lost.
- A command, tool identifier, environment variable, path, or URL can be mistranslated.
- An example may be mistaken for an instruction or vice versa.
- A translated Markdown file may be fluent but have broken structure or missing resources.
- Translation systems may invent details or normalize text in a way that changes operational meaning.

## Core research approach

### Structural invariants
Parse frontmatter and Markdown; compare headings, lists, links, code fences, referenced files, and package paths. Validate metadata against the current Agent Skills specification.

### Protected spans
Track code blocks, literal commands, identifiers, URLs, paths, environment variable names, and explicitly protected names. Do not rely solely on token heuristics; allow a reviewed configuration.

### Semantic invariants
Represent critical instructions as reviewable statements: required action, forbidden action, precondition, condition, limit, negation, and escalation path. Compare source and target claims and flag likely omission or polarity change. Treat semantic comparison as a warning system, not proof.

### Locale metadata
Use established language tags and record source/target locale explicitly. RFC 5646 describes language tags: https://www.rfc-editor.org/rfc/rfc5646

## Threats to validity

| Risk | Why it matters | Research response |
|---|---|---|
| Fluent mistranslation | Surface quality hides a changed instruction | Invariant review and back-to-source comparison |
| Lost negation or threshold | A safety condition can be reversed | Dedicated condition/negation checks plus human approval |
| Identifier mutation | Tools and commands may stop working | Protected spans and exact-token tests |
| Broken package structure | Agent may fail to load the skill or miss resources | Parse and validate complete package |
| Hallucinated instruction | Translation engine may add unsupported steps | Detect new imperative content and require review |
| Different client behaviours | Skill consumers may interpret metadata differently | Follow the shared specification and test target clients |
| Confidential skill disclosure | Translation service receives private operational content | Local processing where possible; explicit consent before remote providers |

## Limits
Natural-language meaning is context-dependent. The same phrase can be a safety constraint in one section and an illustrative example in another. Automated checks can identify suspicious differences but cannot certify complete semantic equivalence. Critical instructions require human review and scenario tests.

## Open questions
1. Which structural fields are invariant in the current specification?
2. How should invariants be authored and versioned with a skill?
3. Which classes of instruction can be checked reliably without an LLM?
4. How can a semantic model be evaluated without allowing its score to become a false guarantee?
5. How should provider-specific behaviour and translation provenance be recorded?

## Research exit criteria
A prototype should pass fixtures covering negation loss, modal weakening, changed command names, missing resources, malformed frontmatter, added content, and harmless rephrasing. Evaluation should report false positives as well as missed changes.
