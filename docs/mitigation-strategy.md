# SkillTether Mitigation Strategy

SkillTether aims to reduce localization defects in Agent Skill packages, especially changes that affect execution, safety, or decision-making.

| Risk | Planned mitigation | Validation | Residual risk |
|---|---|---|---|
| Constraint weakened | Protected invariant manifest for must/must-not, preconditions, thresholds, and escalation rules | Pairs differing only in modal strength or condition | Language models may miss subtle pragmatic shifts |
| Negation reversed or omitted | Detect polarity and condition changes; require human review on critical invariants | Negation and double-negative fixtures | Natural language can remain ambiguous |
| Tool/command/path altered | Extract and protect exact spans; validate referenced resources | Exact-token and path-resolution tests | A legitimate rename requires explicit mapping |
| Package structure broken | Parse YAML frontmatter and Markdown; verify files and links; cap per-file/aggregate bytes, entry counts, and directory depth; reject symlinks and non-regular files | Missing file, invalid YAML, broken-link, named-pipe, and aggregate-limit fixtures | Client extensions differ; filesystem races cannot be eliminated on every platform |
| Unrequested details added | Diff content and protected tokens; compare non-text resources by hash; scope invariant literals to an approximate matched context | Unexpected-instruction, binary asset, and context-misalignment fixtures | Approximate multilingual context alignment can be wrong and remains review-only |
| Translation provider receives confidential text | Provider adapters off by default; clear disclosure and explicit consent before remote processing | Mock provider verifies no network call by default | User may approve a provider without understanding its retention policy |
| Machine score mistaken for guarantee | Distinguish deterministic, heuristic, and human-review signals; attach uncertainty and severity rationale | Schema-validated report fixtures and finding-method assertions | Reviewers can still over-trust scores |
| Source overwritten | Read-only source, separate target output, report/history path containment checks, and atomic mode-restricted report writes | Source hashes remain unchanged; symlink-alias report-path tests | External processes can still mutate shared files; output alias handling varies by OS |

## Operating safeguards

- Preserve the original skill package and calculate a manifest before transformation.
- Keep source and target languages explicit.
- Protect identifiers and machine-readable values by default.
- Never silently resolve an ambiguous instruction.
- Critical safety invariants must be reviewed before export.
- Keep automated warnings and human approval as different fields.
- Do not transmit package contents to remote services without explicit consent.
- Do not execute referenced scripts as part of translation or validation.
- Treat binary assets as package content: same-path byte changes require review rather than being silently ignored.
- Keep machine-generated context alignment explicitly heuristic; never present an unrelated document-wide token as a confirmed contextual invariant violation.
- Do not write reports or local history into source/candidate directories; report outputs are written atomically and made user-private on POSIX systems.

## Release gates
A release needs structural validation, a fixture suite for semantic invariants, evidence-linked warnings, clear uncertainty labels, and privacy tests for translation adapters. Avoid claims such as “meaning guaranteed” or “safe translation”.
