"""Versioned, strict data contracts used by the CLI and reports."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .redaction import redact_sensitive_text

Severity = Literal["info", "low", "medium", "high", "critical"]
Disposition = Literal["pending", "approved", "rejected", "deferred"]
AnalysisMethod = Literal["deterministic", "heuristic", "human_review", "unknown"]
Uncertainty = Literal["none", "low", "medium", "high", "unknown"]
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
    # Optional so existing in-memory callers that create fingerprints still parse.
    mode: int | None = Field(default=None, ge=0, le=0o7777)

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

class ReviewEvent(StrictModel):
    """One attributable review action; history is auditable but not cryptographically signed."""

    recorded_at: str
    previous_disposition: Disposition
    disposition: Disposition
    reviewer: str = Field(min_length=1, max_length=200)
    note: str = Field(min_length=1, max_length=4000)

    @field_validator("recorded_at")
    @classmethod
    def timestamp_is_timezone_aware(cls, value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("recorded_at must be an ISO-8601 timestamp") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("recorded_at must include a timezone")
        return value

    @field_validator("reviewer", "note")
    @classmethod
    def required_review_text_is_not_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("reviewer and review note must not be blank")
        return normalized

class Finding(StrictModel):
    id: str
    code: str
    severity: Severity
    category: str
    message: str
    rationale: str
    path: str | None = None
    source_line: int | None = Field(default=None, ge=1)
    target_line: int | None = Field(default=None, ge=1)
    original_context: str | None = None
    target_context: str | None = None
    proposed_change: str | None = None
    requires_review: bool = False
    disposition: Disposition = "pending"
    reviewer: str | None = None
    review_note: str | None = None
    # Optional additive fields keep earlier 1.0 JSON reports readable.
    rule_id: str | None = None
    analysis_method: AnalysisMethod = "unknown"
    uncertainty: Uncertainty = "unknown"
    severity_rationale: str = ""
    review_history: list[ReviewEvent] = Field(default_factory=list)

class ComparisonReport(StrictModel):
    report_version: Literal["1.0"] = "1.0"
    tool_version: str
    generated_at: str
    source_locale: str | None = None
    target_locale: str | None = None
    translation_provider: str | None = None
    invariant_manifest_fingerprint: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    protected_policy_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    target_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_files: dict[str, str]
    target_files: dict[str, str]
    structural_status: Literal["pass", "fail", "unsupported", "error"]
    semantic_status: Literal["no_issue_detected", "review_recommended", "unknown"]
    limitations: list[str] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    integrity_algorithm: Literal["hmac-sha256"] | None = None
    integrity_signature: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def integrity_fields_are_paired(self) -> "ComparisonReport":
        if (self.integrity_algorithm is None) != (self.integrity_signature is None):
            raise ValueError("integrity_algorithm and integrity_signature must be supplied together")
        return self

    @field_validator("generated_at")
    @classmethod
    def generated_timestamp_is_timezone_aware(cls, value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("generated_at must be an ISO-8601 timestamp") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("generated_at must include a timezone")
        return value

    @field_validator("source_locale", "target_locale")
    @classmethod
    def report_locale_has_bcp47_shape(cls, value: str | None) -> str | None:
        if value is not None and not _BCP47_SHAPE.fullmatch(value):
            raise ValueError(f"{value!r} is not a valid-looking BCP 47 language tag")
        return value

    @field_validator("source_files", "target_files")
    @classmethod
    def report_file_hashes_are_sha256(cls, value: dict[str, str]) -> dict[str, str]:
        for path, digest in value.items():
            if not path or not re.fullmatch(r"[a-f0-9]{64}", digest):
                raise ValueError("file map entries require a non-empty path and a lowercase SHA-256 digest")
        return value

    @classmethod
    def create(cls, **kwargs) -> "ComparisonReport":
        kwargs.setdefault("generated_at", datetime.now(timezone.utc).isoformat())
        return cls(**kwargs)

_HEURISTIC_CODES = {
    "CONTENT_OMITTED", "CONTENT_ADDED", "LINE_CHANGED",
    "INVARIANT_TARGET_CONTEXT_UNCERTAIN", "INVARIANT_NEGATION_UNCERTAIN",
    "INVARIANT_MODALITY_UNCERTAIN", "INVARIANT_FORBIDDEN_TOKEN_CONTEXT_UNCERTAIN",
}
_HUMAN_REVIEW_CODES = {
    "CRITICAL_INVARIANT_REVIEW_REQUIRED", "INVARIANT_MANIFEST_MISSING",
    "INVARIANT_MANIFEST_UNREVIEWED", "INVARIANT_NOT_HUMAN_REVIEWED",
}
_SEVERITY_RATIONALE = {
    "critical": "Could alter a safety constraint, machine-facing behavior, or an approval prerequisite; fail closed pending explicit review.",
    "high": "May break package integrity or change required operational content; focused review is warranted.",
    "medium": "May introduce unintended operational detail or compatibility risk; confirm the change is intentional.",
    "low": "Indicates a possible format or client-compatibility issue without evidence of direct breakage.",
    "info": "Records a difference as evidence; the rule does not by itself establish semantic harm.",
}

def new_finding(
    code: str, severity: Severity, category: str, message: str, rationale: str,
    *, path: str | None = None, source_line: int | None = None,
    target_line: int | None = None, original_context: str | None = None,
    target_context: str | None = None, proposed_change: str | None = None,
    requires_review: bool = False, rule_id: str | None = None,
    analysis_method: AnalysisMethod | None = None, uncertainty: Uncertainty | None = None,
    severity_rationale: str | None = None,
) -> Finding:
    """Create a stable finding with explicit rule provenance and redacted evidence."""
    # Redact before deriving the stable ID as well as before exposing evidence in a
    # report. The patterns are high-confidence guardrails, not a complete secret scan.
    path = redact_sensitive_text(path) if path is not None else None
    message = redact_sensitive_text(message)
    rationale = redact_sensitive_text(rationale)
    original_context = redact_sensitive_text(original_context) if original_context is not None else None
    target_context = redact_sensitive_text(target_context) if target_context is not None else None
    proposed_change = redact_sensitive_text(proposed_change) if proposed_change is not None else None
    severity_rationale = redact_sensitive_text(severity_rationale) if severity_rationale is not None else None
    rule_id = redact_sensitive_text(rule_id) if rule_id is not None else None
    identity = "\\0".join(
        [code, path or "", str(source_line or ""), str(target_line or ""),
         message, original_context or "", target_context or ""]
    )
    suffix = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
    if analysis_method is None:
        analysis_method = (
            "human_review" if code in _HUMAN_REVIEW_CODES
            else "heuristic" if code in _HEURISTIC_CODES
            else "deterministic"
        )
    if uncertainty is None:
        uncertainty = {
            "deterministic": "none",
            "heuristic": "high",
            "human_review": "unknown",
            "unknown": "unknown",
        }[analysis_method]
    return Finding(
        id=f"{code.lower()}-{suffix}", code=code, severity=severity,
        category=category, message=message, rationale=rationale,
        path=path, source_line=source_line, target_line=target_line,
        original_context=original_context, target_context=target_context,
        proposed_change=proposed_change, requires_review=requires_review,
        rule_id=rule_id or code, analysis_method=analysis_method,
        uncertainty=uncertainty,
        severity_rationale=severity_rationale or _SEVERITY_RATIONALE[severity],
    )
