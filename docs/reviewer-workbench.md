# Offline reviewer workbench

The optional browser workbench is a dependency-free, local-only report viewer and decision editor. It lives at reviewer/index.html and can be opened directly from a local checkout; it does not require a server, hosted service, account, or browser storage.

## Workflow

1. Generate a JSON report with the SkillTether CLI.
2. Open reviewer/index.html in a browser and choose the report JSON file.
3. Filter findings by text, severity, or disposition. Select a finding to inspect its source/target excerpts, rule method, uncertainty, severity rationale, and prior review history.
4. For an unsigned report, enter a reviewer identifier, choose approved/rejected/deferred, and supply a concise rationale. Each save appends a timestamped review event in memory and updates the current disposition.
5. Export the changed JSON report. The original file is not overwritten.
6. Use the SkillTether CLI for final validation and approval/export, supplying the same source, target, manifest, and policy inputs used for comparison.

## Signed reports

Reports carrying an HMAC signature are displayed read-only. The workbench does not accept or retain HMAC keys and does not verify signatures. Use the CLI to verify, review, and re-sign these reports:

~~~sh
skilltether verify-report ./review/report.json --signing-key ~/.skilltether/report-signing.key
skilltether review ./review/report.json FINDING_ID \
  --disposition approved --reviewer reviewer-id --note "Reviewed both contexts" \
  --signing-key ~/.skilltether/report-signing.key
~~~

## Privacy and trust boundaries

- The report is read from a user-selected file and processed in the current tab. The workbench does not make network requests and does not use localStorage or sessionStorage.
- Source and target contexts, notes, and metadata are treated as untrusted. The interface inserts them as plain text rather than interpreting them as HTML.
- Files larger than 20 MiB are rejected by the browser workbench.
- Reviewer identifiers and notes have the same 200/4,000 character limits as the report model and a small credential-pattern guard. That guard is not a complete secret scanner.
- Browser decisions are local edits, not authenticated identity claims. Anyone able to modify the file can forge review history. Use trusted version control, organizational review controls, and optional HMAC signing where stronger integrity is needed.
- The browser workbench performs basic report-shape checks, not the complete Pydantic/JSON Schema or package-fingerprint validation. Always validate and approve through the CLI.

The UI is intentionally a small adjunct to the CLI, not a replacement for structural validation, signature verification, or the approval gate.
