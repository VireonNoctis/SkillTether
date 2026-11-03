# Agent Skills specification boundary

The normative format reference is the [official Agent Skills specification](https://agentskills.io/specification). Re-check that document when changing structural validation rules; this file records the distinction between base-format requirements and additional SkillTether safeguards.

## Base-format checks implemented here

SkillTether validates that a package has a readable UTF-8 `SKILL.md` with YAML frontmatter and non-empty `name` and `description` fields. It checks the skill name's Unicode lowercase alphanumeric syntax, 1–64 character limit, no leading/trailing or consecutive hyphens, and trimmed NFKC-equivalent match with the package directory name. Trimming and NFKC are used only for validation/comparison; source frontmatter and directory names are never rewritten. Descriptions are capped at 1,024 characters.

When optional fields are present, SkillTether checks that:
- `license` is a string.
- `compatibility`, when present, is a non-empty string of at most 500 characters.
- `metadata` is a mapping with string keys and string values. SkillTether checks the YAML scalar types and rejects numeric/boolean keys or values instead of coercing them to strings. Pinned `skills-ref@v0.0.1` checks only scalar-node shape and converts scalar text into `map[string]string`; CI records this as an intentional strictness difference.
- `allowed-tools` is a space-delimited string. The field is experimental, and client support may vary.

Optional fields are not required just because SkillTether knows how to validate them. Unknown fields receive a low-severity warning rather than an automatic blocking failure because client-specific extensions may be intentional. This is an intentional policy difference from pinned `skills-ref@v0.0.1`, which rejects an unknown top-level field: SkillTether preserves the extension and surfaces a warning so reviewers can check target-client support.

## Additional SkillTether safeguards

The following checks are implementation policy or localization-integrity controls, not additional claims about the base specification:

- An empty instruction body is treated as a high-severity operational problem because metadata alone does not describe a workflow.
- Local Markdown links, fragments, and conventional resource references are checked for integrity.
- Invalid local link paths after URL decoding are reported as findings rather than allowed to abort package inspection.
- Files and directories are bounded; symlinks and special files are rejected; scripts are never executed during inspection.
- Non-text asset hashes and file permission bits participate in integrity comparison.
- Protected tokens, reviewed invariants, language-specific negation/modality markers, and human approval are localization workflow controls.
- Non-string top-level YAML frontmatter keys receive an explicit finding and are excluded from extension-name sorting, so malformed key types do not crash validation.
- Long `SKILL.md` files receive a low-severity notice reflecting the specification's progressive-disclosure recommendation, not a structural rejection.

A structural pass is not a semantic-equivalence guarantee. A package can be structurally conformant while its localized instructions have changed important meaning.

## Reference-validator comparison

CI includes a separate, Ubuntu-only smoke check using the upstream `skills-ref` CLI pinned at `v0.0.1`. It requires the base valid fixture and a valid fixture exercising optional `license`, `compatibility`, `metadata`, and experimental `allowed-tools` to pass; an intentionally invalid package fixture must return the documented invalid-input status. This check is not a runtime dependency and does not replace SkillTether's own package-integrity checks. The upstream [`skills-ref` README](https://github.com/skills-repos/agentskills/blob/main/skills-ref/README.md) currently describes the tool as a demonstration/reference implementation rather than production software, so its result is useful for compatibility drift detection, not as the only conformance authority.

## Regression expectations

Fixtures cover valid optional fields, malformed optional-field types, unknown extension fields, malformed/duplicate YAML, missing required fields, resource integrity, and security-boundary behavior. Changes to this document's base-format assumptions should be accompanied by tests and a reference update.
