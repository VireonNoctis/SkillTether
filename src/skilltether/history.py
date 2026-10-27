"""Optional local SQLite metadata history; never stores skill text or credentials."""
from __future__ import annotations

import os
import re
import sqlite3
import stat
from datetime import datetime, timezone
from pathlib import Path

_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_BCP47_SHAPE = re.compile(r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$")
_SAFE_METADATA = re.compile(r"^[^\\x00-\\x1f\\x7f-\\x9f]{1,128}$")


def default_history_path() -> Path:
    return Path.home() / ".skilltether" / "history.sqlite3"


def _validate_metadata(
    *, source_fingerprint: str, target_fingerprint: str,
    source_locale: str, target_locale: str, provider: str, status: str,
) -> None:
    if not _SHA256.fullmatch(source_fingerprint) or not _SHA256.fullmatch(target_fingerprint):
        raise ValueError("History fingerprints must be lowercase SHA-256 digests")
    if not _BCP47_SHAPE.fullmatch(source_locale) or not _BCP47_SHAPE.fullmatch(target_locale):
        raise ValueError("History locales must be valid-looking BCP 47 language tags")
    for label, value in (("provider", provider), ("status", status)):
        if not isinstance(value, str) or not _SAFE_METADATA.fullmatch(value):
            raise ValueError(f"History {label} must be 1–128 printable characters without control characters")


def _prepare_private_database(path: Path) -> None:
    """Refuse symlinks and special files, and create/restrict the DB with private mode."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = path.lstat()
    except FileNotFoundError:
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(path, flags, 0o600)
        except FileExistsError:
            # Another process may have created it; classify the actual entry below.
            pass
        else:
            os.close(descriptor)
            existing = path.lstat()
    else:
        pass

    try:
        existing = path.lstat()
    except OSError as exc:
        raise ValueError(f"Unable to inspect local history database: {exc.__class__.__name__}") from exc
    if not stat.S_ISREG(existing.st_mode):
        raise ValueError("History database path must be a regular file, not a symlink or special filesystem entry")
    if os.name == "posix":
        # Fail closed instead of silently leaving locally persisted metadata world-readable.
        path.chmod(0o600)


def record_event(
    *, source_fingerprint: str, target_fingerprint: str, source_locale: str,
    target_locale: str, provider: str, status: str,
    database: str | Path | None = None,
) -> Path:
    """Persist bounded hashes and run metadata locally, omitting document text and credentials."""
    _validate_metadata(
        source_fingerprint=source_fingerprint,
        target_fingerprint=target_fingerprint,
        source_locale=source_locale,
        target_locale=target_locale,
        provider=provider,
        status=status,
    )
    path = Path(database).expanduser() if database else default_history_path()
    _prepare_private_database(path)
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA trusted_schema = OFF")
        connection.execute("""
            CREATE TABLE IF NOT EXISTS translation_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                source_fingerprint TEXT NOT NULL,
                target_fingerprint TEXT NOT NULL,
                source_locale TEXT NOT NULL,
                target_locale TEXT NOT NULL,
                provider TEXT NOT NULL,
                status TEXT NOT NULL
            )
        """)
        connection.execute(
            """INSERT INTO translation_runs
               (created_at, source_fingerprint, target_fingerprint, source_locale,
                target_locale, provider, status)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (datetime.now(timezone.utc).isoformat(), source_fingerprint,
             target_fingerprint, source_locale, target_locale, provider, status),
        )
        connection.commit()
    if os.name == "posix":
        path.chmod(0o600)
    return path
