"""Versioned, strict data contracts used by the CLI and reports."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Severity = Literal["info", "low", "medium", "high", "critical"]
Disposition = Literal["pending", "approved", "rejected", "deferred"]
InvariantCategory = Literal[
    "safety_constraint", "mandatory_condition", "negation", "numeric_limit",
    "precondition", "decision_rule", "other",
]
_BCP47_SHAPE = re.compile(r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class FileFingerprint(StrictModel):
    path: str
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    encoding: str | None = None
    kind: str


class ProtectedToken(StrictModel):
    path: str
    category: str
    value: str
    line: int = Field(ge=1)


class Invariant(StrictModel):
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
    statement: str = Field(min_length=1)
    category: InvariantCategory = "other"
    severity: Literal["low", "medium", "high", "critical"] = "high"
    source_path: str = "SKILL.md"
    source_lines: tuple[int, int] | None = None
    source_text: str | None = None
    required_tokens: list[str] = Field(default_factory=list)
    forbidden_tokens: list[str] = Field(default_factory=list)
    expected_numbers: list[str] = Field(default_factory=list)
    negation_required: bool = False
    negation_markers: list[str] = Field(default_factory=list)
    mandatory_required: bool = False
    mandatory_markers: list[str] = Field(default_factory=list)
    reviewed: bool = False
    reviewer: str | None = None

    @model_validator(mode="after")
    def reviewed_invariant_has_reviewer(self) -> "Invariant":
        if self.reviewed and not (self.reviewer and self.reviewer.strip()):
            raise ValueError("reviewed=true requires a non-empty reviewer")
        if self.source_lines and (self.source_lines[0] < 1 or self.source_lines[1] < self.source_lines[0]):
            raise ValueError("source_lines must be a valid inclusive line range")
        return self


class InvariantManifest(StrictModel):
    manifest_version: Literal["1.0"] = "1.0"
    source_locale: str
    target_locale: str | None = None
    invariants: list[Invariant] = Field(default_factory=list)
    manifest_reviewer: str | None = None
    manifest_reviewed: bool = False

    @field_validator("source_locale", "target_locale")
    @classmethod
    def valid_bcp47_shape(cls, value: str | None) -> str | None:
        if value is not None and not _BCP47_SHAPE.fullmatch(value):
            raise ValueError(f"{value!r} is not a valid-looking BCP 47 language tag")
        return value

    @model_validator(mode="after")
    def reviewed_manifest_has_reviewer(self) -> "InvariantManifest":
        if self.manifest_reviewed and not (self.manifest_reviewer and self.manifest_reviewer.strip()):
            raise ValueError("manifest_reviewed=true requires manifest_reviewer")
        duplicate_ids = [item.id for item in self.invariants]
        if len(duplicate_ids) != len(set(duplicate_ids)):
            raise ValueError("invariant IDs must be unique")
        return self


class Finding(StrictModel):
    id: str
    code: str
    severity: Severity
    category: str
    message: str
    rationale: str
    path: str | None = None
    source_line: int | None = None
    target_line: int | None = None
    original_context: str | None = None
    target_context: str | None = None
    proposed_change: str | None = None
    requires_review: bool = False
    disposition: Disposition = "pending"
    reviewer: str | None = None
    review_note: str | None = None


class ComparisonReport(StrictModel):
    report_version: Literal["1.0"] = "1.0"
    tool_version: str
    generated_at: str
    source_locale: str | None = None
    target_locale: str | None = None
    translation_provider: str | None = None
    invariant_manifest_fingerprint: str | None = None
    protected_policy_fingerprint: str
    source_fingerprint: str
    target_fingerprint: str
    source_files: dict[str, str]
    target_files: dict[str, str]
    structural_status: Literal["pass", "fail", "unsupported", "error"]
    semantic_status: Literal["no_issue_detected", "review_recommended", "unknown"]
    limitations: list[str] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)

    @classmethod
    def create(cls, **kwargs) -> "ComparisonReport":
        kwargs.setdefault("generated_at", datetime.now(timezone.utc).isoformat())
        return cls(**kwargs)


def new_finding(
    code: str, severity: Severity, category: str, message: str, rationale: str,
    *, path: str | None = None, source_line: int | None = None,
    target_line: int | None = None, original_context: str | None = None,
    target_context: str | None = None, proposed_change: str | None = None,
    requires_review: bool = False,
) -> Finding:
    """Create a deterministic finding ID so repeated runs can be compared."""
    identity = "\\0".join(
        [code, path or "", str(source_line or ""), str(target_line or ""),
         message, original_context or "", target_context or ""]
    )
    suffix = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
    return Finding(
        id=f"{code.lower()}-{suffix}", code=code, severity=severity,
        category=category, message=message, rationale=rationale,
        path=path, source_line=source_line, target_line=target_line,
        original_context=original_context, target_context=target_context,
        proposed_change=proposed_change, requires_review=requires_review,
    )
