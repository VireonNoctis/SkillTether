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

A skill directory must contain a readable UTF-8 SKILL.md beginning with a closed YAML frontmatter block. The base Agent Skills contract requires non-empty name and description. The name must be lowercase kebab-case, at most 64 characters, and match the package directory name. The implementation also checks optional compatibility and metadata types, local links, fragments, symlinks, and bounded input sizes.

External HTTP(S) links are preserved but are not fetched. Scripts and other assets are never executed.

## Create a manifest for human review

~~~sh
skilltether init-manifest ./sample-skill --out ./sample-skill/.skilltether-invariants.yaml --source-locale en --target-locale fr
~~~

The generator looks for lines that may express negation, a requirement, a prerequisite, a number, or a limit. It intentionally creates an unreviewed manifest. A reviewer must:
1. Confirm each suggestion is a real requirement, and add invariants the heuristic missed.
2. Correct its category/severity, source lines, and supporting text.
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

The built-in identity adapter sends nothing and leaves prose unchanged. The generic HTTP adapter sends POST JSON with source text and locale tags and accepts a JSON object containing a string field named text. Remote use requires both an endpoint and explicit --allow-remote consent; production endpoints must use HTTPS. The payload does not include file paths, invariant manifests, scripts, or binary assets, but eligible prose may contain sensitive information. Use only an approved endpoint.

## Translate and compare

~~~sh
skilltether translate ./sample-skill /tmp/candidate/sample-skill \
  --source-locale en --target-locale fr --adapter identity \
  --invariants ./sample-skill/.skilltether-invariants.yaml
~~~

The identity adapter is for testing the pipeline, not for producing a real translation. For a configured HTTP bridge, set --adapter http-json --endpoint URL --allow-remote.

A candidate directory must not exist and must have the same leaf directory name as the source package. Source and output may not overlap. Candidate construction uses a temporary sibling and publishes only when all translation calls finish and structural validation passes.

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

## Reports and local history

JSON reports are intended for tooling; Markdown reports fence untrusted context and review notes before presenting them. New findings include a rule ID, detection method, explicit uncertainty state, and severity rationale. Review history is preserved within one report; rerunning comparison creates a new report and requires new review decisions. A generated timestamp and provider output may differ between runs.

SQLite history defaults to ~/.skilltether/history.sqlite3. It contains run timestamps, provider name, locales, status, and package fingerprints—not translated prose, source content, API credentials, or authorization headers. Pass --history-db to select another local database.

Reports carry source/target fingerprints, a canonical manifest fingerprint (when supplied), a protected-policy fingerprint, locale information, tool version, and the adapter name for translation runs. Finding IDs are deterministic for the same evidence and fields; the generated timestamp changes from run to run.
