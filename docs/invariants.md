# Human-reviewed invariant manifest

## Why it exists

A package can pass Markdown/frontmatter checks while a translated instruction has lost negation, weakened a requirement, altered a numeric limit, removed a prerequisite, or added a step. Invariant manifests encode human-reviewed expectations that can be compared against the target package.

The manifest is not itself a proof. The reviewer should inspect complete context and use scenario tests for high-impact workflows.

## Manifest lifecycle

1. Run init-manifest to produce draft candidates, or author a YAML manifest directly.
2. Confirm or remove each suggested rule. Add constraints missed by the heuristic.
3. Assign a stable ID and the source path/line range. After a candidate translation exists, optionally add the exact target line range and excerpt as `target_lines` and `target_text`.
4. Choose category and severity: safety_constraint, mandatory_condition, negation, numeric_limit, precondition, decision_rule, or other.
5. Populate required_tokens, forbidden_tokens, and expected_numbers only for exact target expectations that are valid in the target locale.
6. For negation_required and mandatory_required, configure locale-specific negation_markers and mandatory_markers deliberately. Marker absence is a review warning—not a semantic verdict.
7. Set reviewed and reviewer on each confirmed invariant, and manifest_reviewed and manifest_reviewer on the manifest.
8. Rerun comparison whenever the source, target, manifest, policy, or protected mapping changes.

## Example

~~~yaml
manifest_version: "1.0"
source_locale: en
target_locale: fr
manifest_reviewer: "safety-reviewer"
manifest_reviewed: true
invariants:
  - id: SAFE-RETRIES-01
    statement: "The retry count must not exceed three."
    category: numeric_limit
    severity: critical
    source_path: SKILL.md
    source_lines: [42, 42]
    source_text: "Do not retry more than 3 times."
    required_tokens: ["3"]
    expected_numbers: ["3"]
    negation_required: true
    negation_markers: ["ne pas", "jamais"]
    mandatory_required: true
    mandatory_markers: ["doit"]
    reviewed: true
    reviewer: "safety-reviewer"
~~~

The example's language markers are illustrative. Confirm natural target-language grammar and morphology with a qualified reviewer rather than copying markers blindly.

## Human-verified target context anchors

When word overlap cannot locate a translated passage (for example, when the target uses a different script or substantially different vocabulary), a reviewer can anchor the invariant directly to the candidate:

~~~yaml
target_lines: [61, 61]
target_text: "Exact target-language text copied from line 61"
reviewed: true
reviewer: "safety-reviewer"
~~~

`target_lines` is a one-based inclusive line range in the same relative resource named by `source_path`; `target_text` must contain the exact trimmed text across that range. Supply both fields or neither, and set `reviewed: true` with a reviewer identifier; an unreviewed invariant cannot carry a target anchor. The CLI verifies the excerpt against the current target package on every comparison. A missing range, a line moved beyond the resource, or an excerpt mismatch produces a deterministic critical finding that cannot be approved away; update the manifest and rerun comparison.

A valid anchor replaces word-overlap/positional location guessing for that invariant and gives the reviewer an exact target excerpt. It does not establish that the source and target passages are semantically equivalent. Critical invariants still require explicit human sign-off. If the candidate changes, refresh the target anchor before approval.

## Findings and disposition

A comparison finding includes:
- Stable ID, code, and rule ID, with severity and an explicit severity rationale.
- Analysis method (deterministic, heuristic, human review, or unknown) and an explicit uncertainty state.
- Source/target path and line when available, plus original and target context.
- Rationale and proposed change.
- requires_review, current disposition, reviewer, and note, plus a timestamped history of review decisions.

Critical findings and findings marked for review must be explicitly approved before export. Rejected or deferred findings remain blockers. Missing/unreviewed manifests are permanent blockers until the manifest is corrected and comparison rerun. Structural failures are also blockers.

## Interpretation cautions

- Required token checks are exact-string assertions and can be unsuitable for translated numbers or inflectional languages unless the manifest is configured thoughtfully.
- Numeric text may use locale-specific separators and units; encode the intended rule, not an accidental textual form.
- An absence of a negation marker may be a grammar difference rather than a translation failure.
- Source-line locations may shift after editing; refresh evidence and compare again.
- A critical invariant always requires a target-language human sign-off, even when deterministic checks do not detect drift.
