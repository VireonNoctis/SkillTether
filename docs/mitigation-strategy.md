# SkillTether Mitigation Strategy

SkillTether reduces localization defects in Agent Skill packages, especially changes that affect execution, safety, or decision-making. The table distinguishes controls implemented today from controls that remain heuristic. All tests named below are regression evidence, not proof of completeness.

| Risk | Current control and maturity | Validation evidence | Residual risk |
|---|---|---|---|
| Constraint weakened | **Partial:** reviewed invariant manifests, exact tokens/numbers, six explicit language cue profiles, configured modality/negation markers, and word-overlap/positional context findings | Multilingual labelled corpus with exact precision/recall on curated examples, modal-strength, threshold, precondition and source-anchor tests | The corpus is small; language/dialect variation, paraphrase and pragmatic meaning can evade rules |
| Negation reversed or omitted | **Partial:** target-locale negation markers plus human review gates for critical/review-required findings | Negation, marker, double-negative and negative-case fixtures | Marker absence can be grammatical, and no general polarity model proves correctness |
| Tool/command/path altered | **Implemented for detected spans:** extract/protect built-in and configured exact literals, compare tokens/resources, validate local references | Exact-token mutation, token-order, resource-integrity and path-resolution tests | Detection is pattern-driven; legitimate renames require explicit human handling; no automatic mapping is supported |
| Package structure broken | **Implemented within bounded formats:** frontmatter/resource checks, shared GFM-like/Pandoc Markdown parser, explicit MDX unsupported-syntax findings, common Windows path portability checks, normalization/case-collision detection, package inventory, size/depth limits and symlink/special-file rejection | GFM/footnote/definition-list/alert fixtures, MDX-positive/code-negative fixtures, Windows-reserved path and Unicode/case-collision tests | MDX is flagged, not parsed; the path check does not reproduce every filesystem rule; external links are not fetched and races remain platform-dependent |
| Unrequested details added | **Partial:** line/content diffs, protected-token differences, resource hashes and context-linked invariant findings | Unexpected-instruction, binary-asset and context-misalignment fixtures | Added imperative classification and multilingual context alignment are not complete |
| Translation provider receives confidential text | **Implemented consent boundary:** identity adapter is local; remote JSON bridge requires an endpoint and `--allow-remote`; local workload preflight runs before requests | Mock/provider privacy, opt-in, timeout, redirect and request-budget tests | User must assess endpoint approval, retention and data-handling terms |
| Malformed or hostile provider output | **Implemented structural/output guards:** placeholders, one-line validation, control-character rejection, per-line and aggregate budgets, Markdown structure comparison and staged publication | Injected links/formatting/newlines, oversized custom-adapter, control-character and failure/no-partial-publication fixtures | Lexical/structure checks do not detect every semantic rewrite; unusual Markdown/MDX still needs review |
| Machine score mistaken for guarantee | **Implemented evidence model:** findings separate deterministic/heuristic methods, uncertainty, severity rationale, and reviewer disposition/history; offline workbench keeps signed reports read-only | Report-schema, finding-method, workbench XSS/offline, review-audit and approval-gate tests | Reviewers may still over-trust warnings or clean results; browser review does not authenticate identity or validate the full report contract |
| Source overwritten or outputs leaked into packages | **Implemented path/integrity guards:** source kept separate, bounded safe reads, staging/fingerprint checks, report/history path containment, atomic restricted report writes | Source immutability, copy-race, symlink-alias, approval-output and safe-I/O tests | Concurrent external changes and OS/filesystem differences remain residual risks |
| Report edited after review | **Optional HMAC integrity seal:** verify sealed reports before review/export when signing is requested; history tracks decisions in the normal CLI workflow | Valid/tampered HMAC, signed review update, key hygiene and review-audit tests | HMAC is symmetric, not reviewer identity/non-repudiation; unsigned reports remain possible unless signing is required |
| Credentials appear in reports/notes | **Partial redaction/guardrail:** selected credential patterns are redacted or rejected in defined fields | API-key/bearer/provider-token/PEM and reviewer-note negative fixtures | It is not a complete secret scanner and cannot promise that sensitive information has been removed |

## Operating safeguards

- Preserve the original skill package and compare fingerprints before publishing a transformed or approved copy.
- Keep source and target language tags explicit; do not silently canonicalize tags or rewrite identifiers.
- Treat invariant suggestions as unreviewed candidates; validate source anchors and rerun comparison after changing the manifest.
- Keep structural findings, heuristic warnings, uncertainty, and human approval as separate signals.
- Require explicit consent before sending package prose to a remote provider; never execute referenced scripts as part of inspection or translation.
- Treat binary assets as package content: same-path byte changes require review rather than being silently ignored.
- Treat generated context alignment as heuristic and avoid presenting unrelated document-wide token matches as confirmed violations.
- Keep reports and local history outside source/candidate directories. Report files are written atomically and use restricted POSIX permissions where supported.

## Release gates

A release should pass the current CI matrix, include a fixture for each new rule plus a meaningful negative case, preserve source-package fingerprints, validate schemas and bundled fixtures, and document coverage/platform limits. Critical or ambiguous semantic changes remain subject to explicit human review. Avoid claims such as “meaning guaranteed” or “safe translation.”
