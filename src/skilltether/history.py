"""Optional local SQLite metadata history; never stores skill text or credentials."""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def default_history_path() -> Path:
    return Path.home() / ".skilltether" / "history.sqlite3"


def record_event(
    *, source_fingerprint: str, target_fingerprint: str, source_locale: str,
    target_locale: str, provider: str, status: str,
    database: str | Path | None = None,
) -> Path:
    """Persist hashes and run metadata locally, omitting document text and credentials."""
    path = Path(database).expanduser() if database else default_history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
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
    try:
        if os.name == "posix":
            path.chmod(0o600)
    except OSError:
        pass
    return path
