"""Bounded, non-following reads for untrusted local text/configuration files."""
from __future__ import annotations

import os
import stat
from pathlib import Path


def read_bounded_regular_file(
    path: str | Path,
    *,
    max_bytes: int,
    purpose: str = "Input file",
) -> bytes:
    """Read a regular file without following a final symlink or blocking on a FIFO.

    The descriptor is classified with fstat after opening, and the read is capped at
    max_bytes + 1 so a file that grows after lstat/fstat cannot bypass the bound.
    """
    if max_bytes < 0:
        raise ValueError("max_bytes must be non-negative")
    source = Path(path).expanduser()
    try:
        metadata = source.lstat()
    except OSError:
        raise
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"{purpose} must be a regular file; symlinks and special filesystem entries are not accepted")

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(source, flags)
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise ValueError(f"{purpose} changed to a non-regular filesystem entry while opening")
        chunks: list[bytes] = []
        total = 0
        while total <= max_bytes:
            chunk = os.read(descriptor, min(64 * 1024, max_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        raw = b"".join(chunks)
        if len(raw) > max_bytes:
            raise ValueError(f"{purpose} exceeds the {max_bytes}-byte safety limit")
        return raw
    finally:
        if descriptor is not None:
            os.close(descriptor)
