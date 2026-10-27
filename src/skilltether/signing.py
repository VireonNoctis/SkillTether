"""Optional local HMAC seals for comparison reports.

This detects accidental or unauthorized report edits when the signing key remains
private. It does not provide non-repudiation: anyone with the key can re-sign a report.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path
from typing import Any

from .safeio import read_bounded_regular_file

MIN_KEY_BYTES = 32
MAX_KEY_FILE_BYTES = 4096


def create_signing_key(path: str | Path) -> Path:
    """Create a new 256-bit report-signing key without overwriting any existing path."""
    output = Path(path).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(output, flags, 0o600)
    except FileExistsError:
        raise FileExistsError(f"Signing-key path already exists: {output}") from None
    key = secrets.token_bytes(MIN_KEY_BYTES)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(key)
            stream.flush()
            os.fsync(stream.fileno())
        if os.name == "posix":
            output.chmod(0o600)
    except Exception:
        try:
            output.unlink()
        except OSError:
            pass
        raise
    return output


def load_signing_key(path: str | Path) -> bytes:
    """Read a regular, private local key; never print or log key material."""
    key_path = Path(path).expanduser()
    raw = read_bounded_regular_file(
        key_path, max_bytes=MAX_KEY_FILE_BYTES, purpose="Report signing key",
        require_private_mode=True,
    )
    if len(raw) < MIN_KEY_BYTES:
        raise ValueError(f"Report signing key must contain at least {MIN_KEY_BYTES} bytes")
    return raw


def _canonical_unsigned_payload(payload: dict[str, Any]) -> bytes:
    unsigned = dict(payload)
    unsigned.pop("integrity_signature", None)
    unsigned.pop("integrity_algorithm", None)
    return json.dumps(
        unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def sign_payload(payload: dict[str, Any], key_path: str | Path) -> str:
    key = load_signing_key(key_path)
    return hmac.new(key, _canonical_unsigned_payload(payload), hashlib.sha256).hexdigest()


def verify_payload(payload: dict[str, Any], key_path: str | Path) -> bool:
    signature = payload.get("integrity_signature")
    algorithm = payload.get("integrity_algorithm")
    if algorithm != "hmac-sha256" or not isinstance(signature, str):
        return False
    expected = sign_payload(payload, key_path)
    return hmac.compare_digest(signature, expected)
