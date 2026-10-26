# SkillTether Mitigation Strategy

SkillTether aims to reduce localization defects in Agent Skill packages, especially changes that affect execution, safety, or decision-making.

| Risk | Planned mitigation | Validation | Residual risk |
|---|---|---|---|
| Constraint weakened | Protected invariant manifest for must/must-not, preconditions, thresholds, and escalation rules | Pairs differing only in modal strength or condition | Language models may miss subtle pragmatic shifts |
| Negation reversed or omitted | Detect polarity and condition changes; require human review on critical invariants | Negation and double-negative fixtures | Natural language can remain ambiguous |
| Tool/command/path altered | Extract and protect exact spans; validate referenced resources | Exact-token and path-resolution tests | A legitimate rename requires explicit mapping |
| Package structure broken | Parse YAML frontmatter and Markdown; verify files and links | Missing file, invalid YAML, broken-link fixtures | Some clients implement extensions differently |
| Unrequested details added | Diff imperative statements and flag new operational steps | Compare source and target with unexpected-instruction fixtures | Not all additions are automatically identifiable |
| Translation provider receives confidential text | Provider adapters off by default; clear disclosure and explicit consent before remote processing | Mock provider verifies no network call by default | User may approve a provider without understanding its retention policy |
| Machine score mistaken for guarantee | Distinguish deterministic structural checks from probabilistic semantic warnings | UI/report wording tests | Reviewers can still over-trust scores |
| Source overwritten | Read-only source and separate target output | Source hashes remain unchanged | External tools may change unrelated machine state |

## Operating safeguards

- Preserve the original skill package and calculate a manifest before transformation.
- Keep source and target languages explicit.
- Protect identifiers and machine-readable values by default.
- Never silently resolve an ambiguous instruction.
- Critical safety invariants must be reviewed before export.
- Keep automated warnings and human approval as different fields.
- Do not transmit package contents to remote services without explicit consent.
- Do not execute referenced scripts as part of translation or validation.

## Release gates
A release needs structural validation, a fixture suite for semantic invariants, evidence-linked warnings, clear uncertainty labels, and privacy tests for translation adapters. Avoid claims such as “meaning guaranteed” or “safe translation”.
