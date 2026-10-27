# Review evidence and approval gates

## Why approval evidence is stricter

A report disposition alone is not enough to export a package. Earlier report files could be edited so that a finding said `approved` without preserving who made the decision or why. That undermines reviewability even when source, target, manifest, and policy fingerprints still match.

For every finding that requires review or is critical, the current disposition must be `approved` and match the final review-history event. The history must be internally consistent: the first event records the report's disposition when tracking began (which may be a legacy value), and each later event's prior disposition matches the preceding event. Each event carries a timezone-aware ISO-8601 timestamp, reviewer identifier, decision, and non-empty rationale.

The `skilltether review` command appends a decision instead of discarding earlier decisions. Changing a decision creates another event. Rejected and deferred decisions remain blockers until a later explicit approval is recorded.

## What the metadata means

New findings include:

- `rule_id`: stable rule identifier; initially the finding code.
- `analysis_method`: `deterministic`, `heuristic`, `human_review`, or `unknown`.
- `uncertainty`: an explicit `none`, `low`, `medium`, `high`, or `unknown` signal about the rule's finding.
- `severity_rationale`: why the chosen severity merits its level of attention.
- `review_history`: a chronological series of reviewer actions.

These fields explain how a finding was produced; they do not score semantic equivalence. A deterministic mismatch is evidence that a particular condition was detected, not proof that the translation is unsafe. A heuristic warning is not a semantic verdict. Human review remains necessary for critical instructions.

## Privacy and trust boundary

Reviewer notes must be non-empty and are capped at 4,000 characters. The CLI rejects several high-confidence credential forms, including common API-key/password assignments, bearer tokens, GitHub-style tokens, and private-key headers. This is a narrow guardrail, not a secret scanner: do not paste private skill content, credentials, or unrelated sensitive data into reviewer notes.

Review history is **not cryptographically signed or tamper-evident**. It improves traceability and blocks accidental/unattributed approval in the normal CLI workflow, but it cannot authenticate reviewer identity or protect against deliberate edits to the JSON file. Use trusted version control and organizational review controls for stronger accountability.

## Backward compatibility

The new finding fields are additive to report version 1.0 and have defaults when older reports are loaded. An older report that contains an `approved` disposition but no matching review-history event is intentionally not sufficient for export: re-record the decision with `skilltether review`, including a reviewer and reason. Changing source/target packages, manifest, or policy still requires a fresh comparison as documented in the main workflow.
