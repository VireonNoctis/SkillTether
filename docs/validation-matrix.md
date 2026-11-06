# SkillTether Validation Matrix

## Current CI baseline

The last fully verified baseline before the current PR #7 extension is [run 41030648870](https://github.com/VireonNoctis/SkillTether/actions/runs/41030648870), head `bf2698d72d70e311b95d5fb948b64ed9ddc73464` (2026-10-30). It does not cover the added PR #7 fixtures and changes; the current PR head needs its own passing matrix and reference-conformance result. It passed 244 tests on Ubuntu/macOS and 239 with five platform-specific skips on Windows, across Python 3.13/3.14; the separate pinned `skills-ref@v0.0.1` reference-conformance job passed. Aggregate coverage was 86% on Linux and Windows; only Linux enforces the 80% floor. Documentation updates after this baseline run need their own CI verification.


## Required fixtures

| Test class | Example | Expected result |
|---|---|---|
| Multilingual invariant evaluation | Human-labelled English/French/Spanish/German/Portuguese/Italian/Arabic/Hindi/Russian candidate examples with operational positives and descriptive-number/date/code negatives | Exact fixture match; assert 45 curated TP, zero FP/FN, per-language and per-family metrics without presenting the sample as a general benchmark |
| Language profile selection | BCP 47 tag with a supported primary language and region/script subtags | Select primary-language profile; unknown language returns no candidate suggestions rather than guessing |
| Frontmatter invariant isolation | Metadata contains mandatory/negation/numeric cue words that resemble instructions, with and without a BOM | Draft suggestions ignore all header lines; malformed or unclosed frontmatter blocks manifest generation |
| Unsupported source locale | `init-manifest` receives a well-formed language without a built-in cue profile | Write an empty, unreviewed manifest and explain that no profile exists; do not guess |
| Regional multilingual evaluation | Document-like skill instructions under en-GB, fr-CA, es-MX, de-AT, pt-BR, and it-CH, including descriptive facts and code examples | Assert 24 curated positive candidates, zero fixture false positives/negatives, per-region metrics, and explicit non-claims about general dialect accuracy |
| Human-verified target context anchor | Translated invariant uses different vocabulary or appears on a different line after localization | Exact `target_lines`/`target_text` excerpt is used instead of a positional guess; critical sign-off remains required |
| Stale target context anchor | Target excerpt no longer matches its declared line range or range exceeds the target resource | Deterministic critical finding; approval remains blocked even after a reviewer disposition is recorded |
| Cross-language context fallback | Source English instruction and translated French line with no shared words but preserved line count | Emit an explicitly high-uncertainty positional alignment finding; retain critical human sign-off |
| Negation-loss negative case | Same positional mapping but target translation omits locale negation markers | Emit heuristic negation uncertainty; positional mapping does not suppress drift warnings |
| GFM/Pandoc Markdown | Table, task list, alert, strikethrough, footnote, and definition list | Shared parser recognizes structure; translation masks delimiters and preserves parser-visible signature |
| MDX unsupported syntax | Import/export, JSX tag, or embedded JavaScript expression outside code fence | High-severity unsupported-syntax finding; code-fenced examples are negative cases; no evaluation/execution |
| Windows path portability | Reserved device name, forbidden character, trailing dot/space | Deterministic portability finding |
| Unicode/case path collision | Two file paths share NFC + case-folded key | Critical normalized-path collision finding on case-sensitive hosts; aliasing hosts skip fixture |
| Offline reviewer workbench | Load unsigned JSON, append a review event and export; attempt to edit signed report | Unsigned report edits are local and append-only; signed report remains read-only; content is rendered as text and no network/storage API is used |

| Test class | Example | Expected result |
|---|---|---|
| Package structure | Valid package with references and assets | All declared resources resolve |
| Markdown links in tables | GFM-style table cell contains a local link | Link is parsed and broken target is reported |
| Malformed local-link URL | Markdown URL contains invalid bracketed host syntax | Explicit `LOCAL_LINK_URL_INVALID` finding; validator does not crash |
| Invalid decoded link path | Local Markdown link contains a percent-encoded NUL that decodes to an unrepresentable filesystem path | Emit `LOCAL_LINK_PATH_INVALID`; package inspection continues without raising |
| Absolute local filesystem link | Markdown uses a `file://` URI, Windows drive-absolute/drive-relative path, rooted path, or UNC path | Emit review-required `LOCAL_LINK_EXTERNAL_PATH`; ordinary HTTPS and mailto schemes remain ignored as external links |
| URL fragment encoding | Local fragment contains percent-encoded characters | Decode fragment before comparing detected anchors/headings |
| Heading-anchor collision | Duplicate `Setup` headings mixed with literal `Setup-1` headings | Allocate collision-free suffixes so every detected heading has a unique anchor |
| Fragment target safety | Local anchor target is already in bounded package inventory | Reuse snapshot; fallback read is bounded and does not follow final symlink |
| BCP 47 extlang cardinality | Language tag contains one to three structural extlang subtags; a fourth appears before following components | One to three are accepted by grammar; excess extlang sequence is rejected |
| Coverage floor | Aggregate branch-aware coverage falls below 80% | Linux GitHub Actions job fails the coverage-report step |
| CI trigger/concurrency | Feature branch commit is pushed to an open PR | Run the PR matrix once (not again for a feature-branch push); cancel an obsolete run when the same PR head advances; retain main-branch push validation |
| Regex policy scanner boundaries | Non-string/oversized/malformed regex, escaped quantifiers, character classes, bounded and unbounded repeats, nested groups, repeated alternation | Reject invalid/risky shapes with bounded errors while retaining escaped/class/bounded safe forms |
| Signing-key creation failure | CSPRNG or descriptor-to-stream wrapping fails during key creation | Fail without leaving a partial key file; close any descriptor not transferred to a stream |
| Signing-key no-overwrite precedence | Destination already exists while the CSPRNG is unavailable | Return the existing-path `FileExistsError` without changing the destination or requesting random bytes |
| Official reference validator | Valid base fixture, valid optional-field fixture, and intentionally invalid fixture | Pinned `skills-ref` CLI accepts both valid fixtures and returns its documented invalid-skill exit code for the invalid fixture; tool stays out of runtime dependencies |
| Python and OS matrix | Python 3.13/3.14 × Ubuntu/macOS/Windows | Full pytest suite, coverage report, schema/policy checks, and bundled fixtures run on all six combinations; aggregate 80% floor is enforced only on Linux |
| Invariant manifest output path | Destination is inside source, already exists, is a symlink, or appears during publication | Refuse write; preserve source and destination target |
| Approval output symlink | Requested approved-output path is a final-component symlink, including a broken symlink | Refuse approval before report access or publication |
| Approval report input symlink | Report argument is a symlink to an otherwise valid JSON report | Reject with the bounded-reader regular-file error; do not resolve/follow the final-component symlink |
| Invariant suggestion examples | Fenced, indented, or recognized HTML code examples contain imperative words/numbers | Do not emit those code-example lines as invariant candidates; candidates remain unreviewed |
| Numeric fact vs. numeric constraint | A factual sentence contains a number but no limit/action/modality/negation/conditional cue | Do not suggest it solely because a digit is present; retain explicit numeric limits and action-oriented numeric rules |
| Binary asset/key bytes on Windows | File contains CRLF and `0x1A` bytes | Binary-mode descriptors preserve exact bytes for fingerprints, package limits, and signing-key verification |
| Package root symlink | A package directory is reached through a symlink alias | Reject the root alias before reading package content |
| Package resource integrity | Same-path binary asset differs by byte hash | Review-required resource-change finding |
| Package permission integrity | Script executable bit changes while bytes remain equal | Package fingerprint changes and review-required file-mode finding |
| Resource exhaustion | Aggregate package bytes or directory count exceeds limit | Inspection fails closed without unbounded reads |
| Package entry identity race | A package entry is replaced between metadata inspection and descriptor open | Emit `FILE_IDENTITY_CHANGED`; comparison reports structural failure and approval cannot publish the unstable package |
| Directory enumeration failure | A nested package directory cannot be enumerated | Inspection fails closed; an unreadable subtree cannot silently disappear from the fingerprint or candidate copy |
| Non-directory package root | A regular file is passed as the package root | Reject with a clear error instead of treating it as an empty package |
| In-package symlink directory | A package subdirectory points to an outside directory | Report `SYMLINK_NOT_ALLOWED` and never inventory files beneath the link |
| Package file-count limit | Inventory contains more than the configured number of regular files | Fail closed at the bound rather than returning a partial inventory |
| Special filesystem entry | Named pipe, socket, device, or symlink is present | Critical structural finding; special files are never read |
| Output path integrity | Report path inside package or reached through a symlink alias; candidate/approval output is a broken symlink or parent-symlink alias to source | Command refuses before writing; package remains unchanged |
| Frontmatter | Missing required field, invalid YAML, wrong field type | Explicit validation failure |
| UTF-8 BOM frontmatter | `SKILL.md` starts with a UTF-8 BOM immediately before `---` | Accept frontmatter while preserving original bytes; translation and MDX scanning keep metadata opaque; pinned reference validator fixture passes |
| CRLF frontmatter | `SKILL.md` uses CRLF for every frontmatter/body line ending | Accept frontmatter, preserve source bytes and CRLF when translating eligible body prose; pinned reference fixture passes |
| Frontmatter edge cases | Explicit `compatibility: null` or a non-string top-level YAML key mixed with normal fields | Null compatibility is rejected; non-string keys produce a high-severity finding without crashing; omitted compatibility remains valid |
| Unicode skill-name grammar | Lowercase Unicode alphanumeric identifiers, trimmed surrounding whitespace, canonical and compatibility-form NFKC spellings, uppercase Unicode, and invalid hyphen sequences | Accept valid Unicode identifiers and normalized directory equivalents without rewriting; reject uppercase and invalid separator forms |
| Pinned reference differential | Valid 64-character Unicode/ASCII names and 1,024/500-character metadata boundaries; invalid 65-character names and 501-character compatibility; unknown extension field | Accept valid boundaries and reject invalid boundaries in both tools; record unknown-field handling as an intentional policy divergence (SkillTether warning/accept, pinned `skills-ref` reject) |
| Unknown-field differential | Skill contains an unknown top-level extension | SkillTether emits a low-severity warning and exits successfully; pinned `skills-ref@v0.0.1` rejects the extension; CI asserts this intentional difference |
| Metadata scalar differential | Metadata map contains an unquoted numeric key and value (`42: 7`) | SkillTether reports `METADATA_INVALID` because the specification requires string keys/values; pinned `skills-ref@v0.0.1` accepts scalar nodes and stringifies their text; CI asserts this deliberate strictness difference |
| Draft invariant false positive | Rule-like words inside tilde/backtick code fences or a line over 1,200 characters | Example content/long line is not emitted as a candidate; manifest remains unreviewed |
| Text resource encoding | Invalid UTF-8 in Markdown/script resource versus invalid bytes in `.bin` asset | Expected text/script suffix reports an encoding finding; binary asset is not called malformed text |
| Manifest output race | Destination exists or appears during generation | Create-only publication refuses the destination and leaves it unchanged |
| Agent Skills optional fields | Optional license/compatibility/metadata/allowed-tools are valid | No false requirement to include fields; correct types are accepted |
| BCP 47 language tags | Languages, scripts, regions, variants, extensions, private-use and grandfathered tags | Structurally well-formed tags accepted without rewriting; malformed ordering, empty extension values, duplicate variants/singletons rejected |
| Locale registry boundary | Unknown but syntactically valid subtags | Accepted without claiming IANA registry validity or canonicalization |
| Manifest/report locale fields | Locale supplied through YAML manifest or serialized report rather than CLI arguments | Pydantic models apply the same BCP 47 structural checks; target locale remains optional in the manifest |
| Extension metadata | Unknown client-specific field appears | Low-severity notice, not an automatic blocking error |
| Exact identifiers | Command, path, tool name changed | Protected-token finding |
| Markdown syntax preservation | Emphasis, inline links, reference links, task-list checkboxes, escaped punctuation, and hard line breaks | Syntax is restored exactly; label text remains translatable; syntax placeholder deletion/duplication/reordering aborts translation |
| Markdown table localization | Header/data rows with pipe delimiters plus alignment separators | Cell prose is translated, pipes stay intact, and delimiter-only rows remain byte-for-byte unchanged |
| HTML opaque-block preservation | Multiline comments and `script`, `style`, `pre`, `code`, or `textarea` blocks | Contents remain untranslated; unclosed comment/block fails closed |
| Provider line injection | A one-line translation result contains CR/LF | Translation is rejected and candidate output is not published |
| Parser-visible structure injection | Provider adds a link, emphasis, list, heading, or other Markdown structure while retaining source placeholders | Structural signature differs; translation fails before candidate publication |
| Custom adapter response budget | Custom local adapter emits an oversized single response or exceeds aggregate output bytes | Translation fails before candidate publication, even when the adapter does not use HTTP |
| Remote translation consent | HTTP adapter endpoint is supplied without `--allow-remote` | Return a CLI error before network access or candidate/report/history publication |
| Provider control characters | Adapter emits NUL, unsupported C0/DEL control characters, or line separators | Translation fails before output publication |
| Protected-token order | Same command flags/identifiers remain present but their order changes | High-severity, high-uncertainty review finding; unchanged order is a negative case |
| Negation | “Do” changed to “do not”, or negation removed | Critical review warning |
| Modal strength | “Must” weakened to “may” | Invariant review warning |
| Threshold | Number, time, or limit changed | Difference and rationale shown |
| Conditional logic | “Only if” or prerequisite removed | Review finding |
| Harmless rephrase | Non-critical prose rewritten with same invariant | No structural false alarm where rules can determine equivalence |
| Omitted sections | Paragraph, list item, or reference file removed | Missing-content finding |
| Comparison complexity | Repeated-line source/target exceeds diff-pair budget | Explicit high-uncertainty finding; no silent semantic pass |
| Added instructions | Target contains new imperative not in source | Unexpected addition warning |
| Provider privacy | Provider disabled or mock provider configured | No network call without explicit setup |
| Translation workload budget | Whole package exceeds request-count or aggregate outbound-byte cap | Rejected during local preflight before any provider call |
| HTTP aggregate response budget | Provider responses cumulatively exceed the configured response cap | Adapter reads only the remaining budget plus one byte and fails closed |
| Review evidence | Critical finding approved, then deferred | Approval is blocked until a newer consistent approval event exists |
| Invariant source evidence | Manifest quote/path/line range is stale, missing, or beyond current source | Deterministic critical finding; approval remains blocked until the manifest is corrected and comparison rerun |
| Signed report integrity | Signed report field is edited before export | HMAC verification rejects the report and no output package is published |
| Standalone report verification | Signed JSON report is unchanged / signature bytes are altered | `verify-report` returns 0 for valid signature and non-zero for tampered report without modifying it |
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
| Regex backtracking | Nested unbounded repeats or repeated alternation supplied as a policy regex | Conservative validator rejects known-risk shapes before matching |
| Regex compatibility | Bounded quantifiers and ordinary literals in a policy regex | Safe bounded pattern remains accepted |
| Config input safety | Oversized policy/manifest/report, symlink, FIFO, or special file | Bounded read rejects it without blocking or following the link |
| Protected-token overlap | `TOOL` and `TOOL_NAME` both protected | Longest matching span is masked once |
| Placeholder collision | Source prose contains a reserved-looking placeholder | Placeholder namespace is chosen without colliding with the prose |
| Terminal output | Finding contains ANSI/control characters and newlines | CLI output collapses control characters |
| Schema conformance | Serialized report and negative enum payload are checked against Draft 2020-12 schema | Valid report passes, unsupported severity fails |

| Fresh approval evidence | Unsigned report has a machine-generated finding removed or altered after comparison | Approval recomputes comparison and rejects the report before publishing any package |
| Reviewed report compatibility | A valid review decision changes disposition/reviewer/note/history without changing machine evidence | Fresh-evidence check allows the reviewed decision and approval continues through structural and fingerprint gates |
| Structural status classification | Non-string frontmatter key, invalid optional license type, malformed decoded local-link path, or invalid UTF-8 Markdown resource | `compare` reports structural failure; human disposition cannot waive it and `approve` refuses export |

| Markdown inline AST eligibility | Prose appears in nested blockquote/list items alongside frontmatter and fenced code | Parser source maps identify prose lines for translation; nested container prefixes remain stable; frontmatter and code are not sent to adapters |
| MDX direct translation | Markdown resource contains an MDX module import, JSX component, or embedded JavaScript expression outside a code example | Direct translation fails closed before adapter use; MDX source is not interpreted or executed |
| Non-Markdown text containing import-like prose | A .txt or .rst resource contains a line beginning with an ordinary programming-language import form | MDX detection is disabled for non-Markdown resources; plain text is not rejected as MDX |
| Local script parser | Bash/sh, JavaScript, or PowerShell script with a locally installed matching parser | Fixed syntax-only invocation receives source on stdin, uses shell=False, minimal environment, discarded stdout/stderr, and does not execute package source |
| Missing local script parser | Script exists but no supported local parser executable is installed | Emit SCRIPT_SYNTAX_CHECK_UNAVAILABLE; no download, network request, or script execution |
| Script parser error/timeout | Local syntax parser reports invalid syntax or exceeds its three-second timeout | Emit explicit invalid/incomplete finding with parser identity and uncertainty; do not persist parser diagnostics |
| Script parser work budget | Package contains more than 16 parse-supported script resources | Launch at most 16 parser processes; emit one review-required budget finding for unchecked scripts |
| Extended script suffixes | .cjs, .mjs, .psm1, and .psd1 files occur in a package | Include files in bounded text inventory and run the corresponding parser-only check when available |
| Unicode decimal numeric invariant | Expected numeric limit 3 appears as Arabic-Indic, Extended Arabic-Indic, Devanagari, or fullwidth decimal digit | Normalize Unicode decimal digits and match the exact numeric literal; retain critical human sign-off |
| Numeric boundary negative cases | Target has 13, 3.5, 3,5, 3rd, or -3 where the manifest expects 3 | Do not accept a partial numeric match; emit the required-token finding with deterministic evidence |
| Cross-script target anchor | Human-reviewed target excerpt contains Arabic, Hindi, Japanese, Chinese, or Russian text and a localized decimal digit | Exact anchor identifies the corresponding target context without word-overlap or positional guessing; critical sign-off remains required |

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
