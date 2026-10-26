# SkillTether Validation Matrix

## Required fixtures

| Test class | Example | Expected result |
|---|---|---|
| Package structure | Valid package with references and assets | All declared resources resolve |
| Frontmatter | Missing required field, invalid YAML, wrong field type | Explicit validation failure |
| Exact identifiers | Command, path, tool name changed | Protected-token finding |
| Negation | “Do” changed to “do not”, or negation removed | Critical review warning |
| Modal strength | “Must” weakened to “may” | Invariant review warning |
| Threshold | Number, time, or limit changed | Difference and rationale shown |
| Conditional logic | “Only if” or prerequisite removed | Review finding |
| Harmless rephrase | Non-critical prose rewritten with same invariant | No structural false alarm where rules can determine equivalence |
| Omitted sections | Paragraph, list item, or reference file removed | Missing-content finding |
| Added instructions | Target contains new imperative not in source | Unexpected addition warning |
| Provider privacy | Provider disabled or mock provider configured | No network call without explicit setup |
| Hostile content | HTML-like text, huge Markdown, path traversal strings | Safe parsing and rendering |

## Evaluation protocol
Create labelled source/target pairs with human-reviewed invariants. Measure precision and recall separately for each finding category. Include difficult negatives: synonyms that preserve meaning, quoted commands, example-only instructions, language-specific grammatical changes, and ambiguous sentences. Do not use a model's own confidence score as the sole ground truth.

## Acceptance criteria
- Original package hashes remain unchanged.
- Structural validity and semantic review are separate outputs.
- Exact protected tokens remain stable unless a reviewer-approved mapping exists.
- Critical invariants have clear source and target references.
- Uncertain meaning triggers review, not an automatic pass.
- Translation provider use is explicit and privacy-tested.
- Exported package structure passes the target specification's checks.

## Regression policy
Every confirmed defect becomes a fixture. Every rule update records whether it changes past findings. Reports identify the rule-set version and provider/model identity where relevant.
