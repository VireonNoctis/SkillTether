# Agent Skills specification boundary

The normative format reference is the [official Agent Skills specification](https://agentskills.io/specification). Re-check that document when changing structural validation rules; this file records the distinction between base-format requirements and additional SkillTether safeguards.

## Base-format checks implemented here

SkillTether validates that a package has a readable UTF-8 `SKILL.md` with YAML frontmatter and non-empty `name` and `description` fields. It checks the skill name's lowercase, hyphen-separated syntax, 64-character maximum, and match with the package directory name; it caps descriptions at 1,024 characters.

When optional fields are present, SkillTether checks that:
- `license` is a string.
- `compatibility` is a non-empty string of at most 500 characters.
- `metadata` is a mapping with string keys and string values.
- `allowed-tools` is a space-delimited string. The field is experimental, and client support may vary.

Optional fields are not required just because SkillTether knows how to validate them. Unknown fields receive a low-severity warning rather than an automatic blocking failure because client-specific extensions may be intentional.

## Additional SkillTether safeguards

The following checks are implementation policy or localization-integrity controls, not additional claims about the base specification:

- An empty instruction body is treated as a high-severity operational problem because metadata alone does not describe a workflow.
- Local Markdown links, fragments, and conventional resource references are checked for integrity.
- Files and directories are bounded; symlinks and special files are rejected; scripts are never executed during inspection.
- Non-text asset hashes and file permission bits participate in integrity comparison.
- Protected tokens, reviewed invariants, language-specific negation/modality markers, and human approval are localization workflow controls.
- Long `SKILL.md` files receive a low-severity notice reflecting the specification's progressive-disclosure recommendation, not a structural rejection.

A structural pass is not a semantic-equivalence guarantee. A package can be structurally conformant while its localized instructions have changed important meaning.

## Regression expectations

Fixtures cover valid optional fields, malformed optional-field types, unknown extension fields, malformed/duplicate YAML, missing required fields, resource integrity, and security-boundary behavior. Changes to this document's base-format assumptions should be accompanied by tests and a reference update.
