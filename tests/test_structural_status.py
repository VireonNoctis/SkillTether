from __future__ import annotations

from pathlib import Path

import pytest

from skilltether.compare import compare_packages


def make_package(
    root: Path,
    *,
    frontmatter_extra: str = "",
    body: str = "Follow the documented workflow.\\n",
    extra_resources: dict[str, bytes] | None = None,
) -> Path:
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text(
        "---\\n"
        f"name: {root.name}\\n"
        "description: A structural validation fixture.\\n"
        f"{frontmatter_extra}"
        "---\\n\\n"
        f"{body}",
        encoding="utf-8",
    )
    for relative, data in (extra_resources or {}).items():
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    return root


@pytest.mark.parametrize(
    ("frontmatter_extra", "body", "extra_resources", "expected_code"),
    [
        ("7: invalid-extension-key\\n", "Instructions.\\n", None, "FRONTMATTER_KEY_INVALID"),
        ("license: [MIT]\\n", "Instructions.\\n", None, "LICENSE_INVALID"),
        ("", "Instructions.\\n", {"references/bad.md": b"invalid UTF-8: \\xff"}, "TEXT_RESOURCE_NOT_UTF8"),
        ("", "See [invalid](%00).\\n", None, "LOCAL_LINK_PATH_INVALID"),
    ],
)
def test_structural_validation_errors_cannot_become_review_only_findings(
    tmp_path: Path,
    frontmatter_extra: str,
    body: str,
    extra_resources: dict[str, bytes] | None,
    expected_code: str,
) -> None:
    source = make_package(
        tmp_path / "source" / "sample-skill",
        frontmatter_extra=frontmatter_extra,
        body=body,
        extra_resources=extra_resources,
    )
    target = make_package(
        tmp_path / "target" / "sample-skill",
        frontmatter_extra=frontmatter_extra,
        body=body,
        extra_resources=extra_resources,
    )

    report = compare_packages(source, target)

    assert any(finding.code == expected_code for finding in report.findings)
    assert report.structural_status == "fail"
