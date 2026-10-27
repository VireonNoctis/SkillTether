# SkillTether CLI workflow

## Installation and development

Install with Python 3.13+:

~~~sh
python -m pip install -e ".[dev]"
pytest
~~~

Run commands from the repository root or pass a repository-relative policy file explicitly.

## Validate a package

~~~sh
skilltether validate ./sample-skill
skilltether validate ./sample-skill --json
~~~

A skill directory must contain a readable UTF-8 SKILL.md beginning with a closed YAML frontmatter block. The base Agent Skills contract requires non-empty name and description. The name must be lowercase kebab-case, at most 64 characters, and match the package directory name. The package root itself may not be a symlink alias, and symlinked entries inside the package are rejected; symlinks in parent path components are resolved normally. The implementation also checks optional compatibility and metadata types, local links, fragments, and bounded input sizes.

External HTTP(S) links are preserved but are not fetched. Scripts and other assets are never executed.

## Create a manifest for human review

~~~sh
skilltether init-manifest ./sample-skill --out ./sample-skill/.skilltether-invariants.yaml --source-locale en --target-locale fr
~~~

The generator looks for lines that may express negation, a requirement, a prerequisite, a number, or a limit. It intentionally creates an unreviewed manifest. A reviewer must:
1. Confirm each suggestion is a real requirement, and add invariants the heuristic missed.
2. Correct its category/severity, source lines, and supporting text. When source_lines or source_text are supplied, they must still match the current source package; comparison rejects stale source evidence, and approval remains blocked until the manifest is corrected and comparison is rerun.
3. Set reviewed=true and reviewer to an accountable reviewer identifier on each approved invariant.
4. Set manifest_reviewed=true and manifest_reviewer on the manifest.
5. Configure target-locale negation_markers and mandatory_markers where marker checks are appropriate.

Do not mark a manifest reviewed merely to bypass a gate.

## Translation adapter contract

The core depends on the TranslationAdapter protocol, not on a particular vendor. A custom adapter implements:

~~~python
class TranslationAdapter(Protocol):
    name: str
    remote: bool

    def translate(self, text: str, source_locale: str, target_locale: str) -> str:
        ...
~~~

The built-in identity adapter sends nothing and leaves prose unchanged. The generic HTTP adapter sends POST JSON with source text and locale tags and accepts a JSON object containing a string field named text. Remote use requires both an endpoint and explicit --allow-remote consent; production endpoints must use HTTPS. The payload does not include file paths, invariant manifests, scripts, or binary assets, but eligible prose may contain sensitive information. Use only an approved endpoint. Outbound JSON requests and responses are each capped at 2 MiB per translated line. Before the first provider request, SkillTether preflights the whole package locally and refuses workloads exceeding 10,000 translation requests or 10 MiB of aggregate request bodies; this prevents partial transmission before a workload cap is discovered. The HTTP adapter independently enforces the same request-count and outbound-byte budgets and caps aggregate response bytes at 10 MiB, in addition to the per-response limit. The timeout must be positive and no more than five minutes, and URLs with userinfo, query parameters, or fragments are rejected. These bounds do not replace review of the provider's data-handling practices.

## Translate and compare

~~~sh
skilltether translate ./sample-skill /tmp/candidate/sample-skill \
  --source-locale en --target-locale fr --adapter identity \
  --invariants ./sample-skill/.skilltether-invariants.yaml
~~~

The identity adapter is for testing the pipeline, not for producing a real translation. For a configured HTTP bridge, set --adapter http-json --endpoint URL --allow-remote.

A candidate directory must not exist and must have the same leaf directory name as the source package. Source and output may not overlap. Candidate construction uses a temporary sibling, preserves rather than follows symlinks during staging, and revalidates the staged bytes and permission metadata before writing translated text. It publishes only when all translation calls finish and structural validation passes. Approval export also preserves late-arriving symlinks during staging and rejects a fingerprint mismatch before publishing.

For CI workflows, add `--fail-on-review` to `compare` or `translate` to return exit status 1 when the report recommends human review or leaves semantic status unknown. Without this opt-in flag, commands retain their existing structural-failure exit semantics while still recording review findings.

To rerun comparison after manifest edits or reviewer changes:

~~~sh
skilltether compare ./sample-skill /tmp/candidate/sample-skill \
  --invariants ./sample-skill/.skilltether-invariants.yaml \
  --target-locale fr --policy config/protected-tokens.yaml \
  --out ./review/report.json --markdown ./review/report.md
~~~

## Review and approve

Open the report and review all critical/uncertain entries in their full context. Each finding includes evidence, rationale, suggested change, and a disposition. Use:

~~~sh
skilltether review ./review/report.json FINDING_ID --disposition approved --reviewer reviewer-id --note "Reasoned review"
~~~

Run the command separately for each finding and provide a meaningful, non-empty `--note`. The note should explain the decision without copying skill content or credentials. Obvious credential-like note values are rejected. Each invocation appends a timestamped decision, retaining prior approvals, rejections, and deferrals. To change a disposition, run it again with approved, rejected, or deferred. If the source/candidate changes after the report is created, the fingerprint check fails and comparison must be rerun.

~~~sh
skilltether approve ./sample-skill /tmp/candidate/sample-skill \
  --report ./review/report.json --output ./approved/sample-skill \
  --invariants ./sample-skill/.skilltether-invariants.yaml \
  --policy config/protected-tokens.yaml
~~~

Export requires a passing structural report, current source/candidate/manifest/policy fingerprints, a human-reviewed manifest, and approved dispositions for all review-required or critical findings. Pass the same --invariants and --policy inputs used for comparison. Output must be a new, separate directory.

## Optional signed report workflow

Create a local HMAC key once, keep it private, back it up securely, and never commit it:

~~~sh
skilltether init-signing-key --out ~/.skilltether/report-signing.key
~~~

Seal a comparison report and verify that seal before export:

~~~sh
skilltether compare ./source/sample-skill ./candidate/sample-skill \
  --invariants ./invariants.yaml --out ./review/report.json \
  --signing-key ~/.skilltether/report-signing.key

skilltether review ./review/report.json FINDING_ID \
  --disposition approved --reviewer qa-reviewer --note "Reviewed the matched source and target context" \
  --signing-key ~/.skilltether/report-signing.key

skilltether approve ./source/sample-skill ./candidate/sample-skill \
  --report ./review/report.json --output ./approved/sample-skill \
  --invariants ./invariants.yaml --signing-key ~/.skilltether/report-signing.key
~~~

You can verify a sealed report without changing it or exporting a package with `skilltether verify-report ./review/report.json --signing-key ~/.skilltether/report-signing.key`. A signed report must be verified before it can be edited through the `review` command, and the updated report is re-signed. When `approve --signing-key` is supplied, unsigned reports are rejected. Signed reports cannot be rewritten without the matching key. Key files must be regular, non-symlink files with at least 32 bytes; on POSIX systems their permissions must not grant group/other access.

HMAC provides integrity detection while the key stays private, not reviewer identity or non-repudiation. Anyone who obtains the key can alter and re-sign a report. Unsigned reports remain supported for existing workflows unless signing is required explicitly.

## Reports and local history

JSON reports are intended for tooling; Markdown reports fence untrusted context and review notes before presenting them. Reports and translation-history database outputs must live outside the source and candidate package roots; the CLI rejects overlapping paths, including symlink aliases. Report files are replaced atomically and use mode 0600 on POSIX systems. New findings include a rule ID, detection method, explicit uncertainty state, and severity rationale. Review history is preserved within one report; rerunning comparison creates a new report and requires new review decisions. A generated timestamp and provider output may differ between runs.

SQLite history defaults to ~/.skilltether/history.sqlite3. It contains run timestamps, provider name, locales, status, and package fingerprints—not translated prose, source content, API credentials, or authorization headers. Input metadata is validated, symlink/special-file database paths are rejected, and new/existing database files use mode 0600 on POSIX systems. Pass --history-db to select another local database.

Reports carry source/target fingerprints (including file permission bits), a canonical manifest fingerprint (when supplied), a protected-policy fingerprint, locale information, tool version, and the adapter name for translation runs. Configuration and report readers use bounded, regular-file-only reads; symlink inputs are rejected. Finding IDs are deterministic for the same evidence and fields; the generated timestamp changes from run to run.
