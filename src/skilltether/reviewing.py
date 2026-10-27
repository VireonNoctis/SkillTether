"""Auditable reviewer decisions for report findings.

The history detects missing or internally inconsistent review evidence. It is not a
cryptographic signature and must not be treated as proof of reviewer identity.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from .models import Disposition, Finding, ReviewEvent

# High-confidence credential forms only. Notes are stored in reports, so reject
# obvious credentials instead of echoing or persisting them in an audit trail.
_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|client[_-]?secret)\b\s*[:=]\s*\S{8,}"),
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,})\b"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)

def record_review(
    finding: Finding,
    *,
    disposition: Disposition,
    reviewer: str,
    note: str,
    recorded_at: datetime | None = None,
) -> ReviewEvent:
    """Append a human decision and update the current disposition in-place."""
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise ValueError("Reviewer identifier must not be blank")
    if not isinstance(note, str) or not note.strip():
        raise ValueError("Review note must not be blank; record the reason for the decision")
    reviewer = reviewer.strip()
    note = note.strip()
    if len(reviewer) > 200:
        raise ValueError("Reviewer identifier must be 200 characters or fewer")
    if len(note) > 4000:
        raise ValueError("Review note must be 4000 characters or fewer")
    if any(pattern.search(note) for pattern in _SECRET_PATTERNS):
        raise ValueError("Review note resembles credential material; remove secrets and retry")

    timestamp = recorded_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("Review timestamp must be timezone-aware")
    event = ReviewEvent(
        recorded_at=timestamp.isoformat(),
        previous_disposition=finding.disposition,
        disposition=disposition,
        reviewer=reviewer,
        note=note,
    )
    finding.review_history.append(event)
    finding.disposition = disposition
    finding.reviewer = reviewer
    finding.review_note = note
    return event

def has_audited_approval(finding: Finding) -> bool:
    """Return true only when the current approval matches the final recorded event."""
    if (
        finding.disposition != "approved"
        or not finding.reviewer
        or not finding.reviewer.strip()
        or not finding.review_note
        or not finding.review_note.strip()
        or not finding.review_history
    ):
        return False

    expected: Disposition = "pending"
    for event in finding.review_history:
        if event.previous_disposition != expected:
            return False
        expected = event.disposition

    last = finding.review_history[-1]
    return (
        expected == "approved"
        and last.disposition == "approved"
        and last.reviewer == finding.reviewer
        and last.note == finding.review_note
    )
