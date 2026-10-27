# SkillTether Validation Matrix

## Required fixtures

| Test class | Example | Expected result |
|---|---|---|
| Package structure | Valid package with references and assets | All declared resources resolve |
| Package resource integrity | Same-path binary asset differs by byte hash | Review-required resource-change finding |
| Package permission integrity | Script executable bit changes while bytes remain equal | Package fingerprint changes and review-required file-mode finding |
| Resource exhaustion | Aggregate package bytes or directory count exceeds limit | Inspection fails closed without unbounded reads |
| Special filesystem entry | Named pipe, socket, device, or symlink is present | Critical structural finding; special files are never read |
| Output path integrity | Report path inside package or reached through a symlink alias | Command refuses before writing; package remains unchanged |
| Frontmatter | Missing required field, invalid YAML, wrong field type | Explicit validation failure |
| Exact identifiers | Command, path, tool name changed | Protected-token finding |
| Negation | “Do” changed to “do not”, or negation removed | Critical review warning |
| Modal strength | “Must” weakened to “may” | Invariant review warning |
| Threshold | Number, time, or limit changed | Difference and rationale shown |
| Conditional logic | “Only if” or prerequisite removed | Review finding |
| Harmless rephrase | Non-critical prose rewritten with same invariant | No structural false alarm where rules can determine equivalence |
| Omitted sections | Paragraph, list item, or reference file removed | Missing-content finding |
| Comparison complexity | Repeated-line source/target exceeds diff-pair budget | Explicit high-uncertainty finding; no silent semantic pass |
| Added instructions | Target contains new imperative not in source | Unexpected addition warning |
| Provider privacy | Provider disabled or mock provider configured | No network call without explicit setup |
| Review evidence | Critical finding approved, then deferred | Approval is blocked until a newer consistent approval event exists |
| Signed report integrity | Signed report field is edited before export | HMAC verification rejects the report and no output package is published |
| Signed review update | Existing signed report is reviewed with the matching key | Decision is appended and the new report payload receives a valid updated seal |
| Key hygiene | Key is symlinked, too short, or group/world accessible on POSIX | Key is rejected before signing or verification |
| Review audit | Bare approved disposition without history or rationale | Approval gate rejects missing review evidence |
| Review input privacy | Note contains obvious credential material | Note is rejected without echoing the credential |
| Review rendering | Note contains HTML/Markdown control syntax | Markdown report fences the untrusted note |
| Report compatibility | Existing v1.0 finding omits additive evidence fields | Legacy report still parses; bare approval is not treated as an audited approval |
| Local history privacy | History record is written to SQLite | Only fingerprints, locales, provider/status and timestamp are stored; DB mode is 0600 on POSIX |
| Credential redaction | Report context or a path contains common API-key, bearer, provider-token, or PEM patterns | JSON/Markdown report omits the raw credential-like value; truncated key blocks are covered |
| Redaction limitation | Unknown credential shape appears in report evidence | Documentation states redaction is not a complete secret scanner |
| Hostile content | HTML-like text, huge Markdown, path traversal strings | Safe parsing and rendering |
| Policy complexity | Too many protected patterns/tokens or oversized regex | Policy is rejected before analysis |
| Config input safety | Oversized policy/manifest/report, symlink, FIFO, or special file | Bounded read rejects it without blocking or following the link |
| Protected-token overlap | `TOOL` and `TOOL_NAME` both protected | Longest matching span is masked once |
| Placeholder collision | Source prose contains a reserved-looking placeholder | Placeholder namespace is chosen without colliding with the prose |
| Terminal output | Finding contains ANSI/control characters and newlines | CLI output collapses control characters |
| Schema conformance | Serialized report and negative enum payload are checked against Draft 2020-12 schema | Valid report passes, unsupported severity fails |

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
