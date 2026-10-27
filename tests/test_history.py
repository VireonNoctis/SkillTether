from __future__ import annotations

import os
import sqlite3
import stat
from pathlib import Path

import pytest

from skilltether.history import record_event

SOURCE_HASH = "a" * 64
TARGET_HASH = "b" * 64


def record(database: Path, **overrides) -> Path:
    values = {
        "source_fingerprint": SOURCE_HASH,
        "target_fingerprint": TARGET_HASH,
        "source_locale": "en",
        "target_locale": "fr-CA",
        "provider": "identity",
        "status": "candidate_written",
        "database": database,
    }
    values.update(overrides)
    return record_event(**values)


def test_history_contains_only_bounded_run_metadata_and_is_private(tmp_path: Path) -> None:
    database = tmp_path / "private" / "history.sqlite3"
    record(database)

    with sqlite3.connect(database) as connection:
        columns = [row[1] for row in connection.execute("PRAGMA table_info(translation_runs)")]
        row = connection.execute(
            "SELECT source_fingerprint, target_fingerprint, source_locale, target_locale, provider, status "
            "FROM translation_runs"
        ).fetchone()

    assert columns == [
        "id", "created_at", "source_fingerprint", "target_fingerprint",
        "source_locale", "target_locale", "provider", "status",
    ]
    assert row == (SOURCE_HASH, TARGET_HASH, "en", "fr-CA", "identity", "candidate_written")
    assert not {"source_text", "target_text", "api_key", "credentials"} & set(columns)
    if os.name == "posix":
        assert stat.S_IMODE(database.stat().st_mode) == 0o600


def test_history_rejects_symlink_without_touching_target(tmp_path: Path) -> None:
    victim = tmp_path / "victim.txt"
    victim.write_text("do not modify", encoding="utf-8")
    path = tmp_path / "history.sqlite3"
    try:
        path.symlink_to(victim)
    except OSError:
        pytest.skip("symlink creation is not permitted")

    with pytest.raises(ValueError, match="regular file"):
        record(path)

    assert path.is_symlink()
    assert victim.read_text(encoding="utf-8") == "do not modify"


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="named pipes are not available on this platform")
def test_history_rejects_named_pipe_before_sqlite_open(tmp_path: Path) -> None:
    path = tmp_path / "history.sqlite3"
    os.mkfifo(path)

    with pytest.raises(ValueError, match="regular file"):
        record(path)


@pytest.mark.parametrize(
    "override,match",
    [
        ({"source_fingerprint": "not-a-hash"}, "SHA-256"),
        ({"target_fingerprint": "A" * 64}, "SHA-256"),
        ({"source_locale": "en_US"}, "BCP 47"),
        ({"target_locale": ""}, "BCP 47"),
        ({"provider": "identity\nforged"}, "control characters"),
        ({"provider": "api_key=veryPrivateCredentialValue_123456789"}, "credential material"),
        ({"status": "x" * 129}, "128 printable"),
    ],
)
def test_history_rejects_invalid_metadata(tmp_path: Path, override: dict, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        record(tmp_path / "history.sqlite3", **override)
    assert not (tmp_path / "history.sqlite3").exists()


def test_history_appends_events_without_document_payload_columns(tmp_path: Path) -> None:
    path = tmp_path / "history.sqlite3"
    record(path)
    record(path, provider="http-json", status="candidate_written")

    with sqlite3.connect(path) as connection:
        rows = connection.execute(
            "SELECT source_fingerprint, target_fingerprint, provider FROM translation_runs ORDER BY id"
        ).fetchall()

    assert rows == [
        (SOURCE_HASH, TARGET_HASH, "identity"),
        (SOURCE_HASH, TARGET_HASH, "http-json"),
    ]
