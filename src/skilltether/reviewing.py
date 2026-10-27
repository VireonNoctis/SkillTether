"""Auditable reviewer decisions for report findings.

The history detects missing or internally inconsistent review evidence. It is not a
cryptographic signature and must not be treated as proof of reviewer identity.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .models import Disposition, Finding, ReviewEvent
from .redaction import redact_sensitive_text

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
    if redact_sensitive_text(note) != note:
        raise ValueError("Review note resembles credential material; remove secrets and retry")

    timestamp = recorded_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("Review timestamp must be timezone-aware")
    if finding.review_history:
        previous_time = datetime.fromisoformat(
            finding.review_history[-1].recorded_at.replace("Z", "+00:00")
        )
        if timestamp.astimezone(timezone.utc) < previous_time.astimezone(timezone.utc):
            raise ValueError("Review timestamp must not precede the previous review event")

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

    # The first recorded event may start from a legacy report disposition. Once
    # the audit trail exists, every subsequent event must follow the prior event.
    expected: Disposition = finding.review_history[0].disposition
    previous_time: datetime | None = None
    for index, event in enumerate(finding.review_history):
        if index > 0 and event.previous_disposition != expected:
            return False
        event_time = datetime.fromisoformat(event.recorded_at.replace("Z", "+00:00"))
        if previous_time is not None and event_time.astimezone(timezone.utc) < previous_time.astimezone(timezone.utc):
            return False
        previous_time = event_time
        expected = event.disposition

    last = finding.review_history[-1]
    return (
        expected == "approved"
        and last.disposition == "approved"
        and last.reviewer == finding.reviewer
        and last.note == finding.review_note
    )
