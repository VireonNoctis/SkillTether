from __future__ import annotations

import os
from pathlib import Path

import pytest

from skilltether.safeio import read_bounded_regular_file


def test_reads_regular_file_exactly_at_limit(tmp_path: Path) -> None:
    path = tmp_path / "input.txt"
    path.write_bytes(b"abcdef")

    assert read_bounded_regular_file(path, max_bytes=6) == b"abcdef"


def test_binary_read_preserves_crlf_and_windows_text_sentinel_bytes(tmp_path: Path) -> None:
    path = tmp_path / "binary.dat"
    payload = b"prefix\r\n\x1a\nsuffix\x00\xff"
    path.write_bytes(payload)

    assert read_bounded_regular_file(path, max_bytes=1024) == payload


def test_rejects_file_over_byte_limit(tmp_path: Path) -> None:
    path = tmp_path / "input.txt"
    path.write_bytes(b"abcdefg")

    with pytest.raises(ValueError, match="6-byte safety limit"):
        read_bounded_regular_file(path, max_bytes=6)


def test_rejects_symlink_without_following_or_modifying_target(tmp_path: Path) -> None:
    target = tmp_path / "target.txt"
    target.write_text("sentinel", encoding="utf-8")
    link = tmp_path / "input.txt"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation is not permitted")

    with pytest.raises(ValueError, match="regular file"):
        read_bounded_regular_file(link, max_bytes=1024)

    assert target.read_text(encoding="utf-8") == "sentinel"


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="named pipes are not available on this platform")
def test_rejects_fifo_without_blocking_read(tmp_path: Path) -> None:
    path = tmp_path / "input.txt"
    os.mkfifo(path)

    with pytest.raises(ValueError, match="regular file"):
        read_bounded_regular_file(path, max_bytes=1024)


def test_missing_input_raises_without_creating_any_file(tmp_path: Path) -> None:
    path = tmp_path / "missing.txt"

    with pytest.raises(FileNotFoundError):
        read_bounded_regular_file(path, max_bytes=1024)

    assert not path.exists()


@pytest.mark.parametrize("limit", [-1, -1024])
def test_negative_limits_are_rejected(limit: int, tmp_path: Path) -> None:
    path = tmp_path / "input.txt"
    path.write_text("text", encoding="utf-8")

    with pytest.raises(ValueError, match="non-negative"):
        read_bounded_regular_file(path, max_bytes=limit)



def test_policy_loader_uses_bounded_regular_file_reads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import skilltether.analysis as analysis

    monkeypatch.setattr(analysis, "MAX_POLICY_FILE_BYTES", 8)
    oversized = tmp_path / "policy.yaml"
    oversized.write_text("patterns: []\n", encoding="utf-8")
    with pytest.raises(ValueError, match="safety limit"):
        analysis.load_policy(oversized)

    monkeypatch.setattr(analysis, "MAX_POLICY_FILE_BYTES", 1024)
    valid = tmp_path / "valid.yaml"
    valid.write_text("patterns: []\nexplicit_tokens: []\n", encoding="utf-8")
    alias = tmp_path / "alias.yaml"
    try:
        alias.symlink_to(valid)
    except OSError:
        pytest.skip("symlink creation is not permitted")
    with pytest.raises(ValueError, match="regular file"):
        analysis.load_policy(alias)


def test_manifest_loader_bounds_input_and_rejects_symlink(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import skilltether.compare as compare

    monkeypatch.setattr(compare, "MAX_MANIFEST_FILE_BYTES", 16)
    oversized = tmp_path / "manifest.yaml"
    oversized.write_text("source_locale: en\ninvariants: []\n", encoding="utf-8")
    with pytest.raises(ValueError, match="safety limit"):
        compare.load_invariant_manifest(oversized)

    monkeypatch.setattr(compare, "MAX_MANIFEST_FILE_BYTES", 1024)
    valid = tmp_path / "valid.yaml"
    valid.write_text("source_locale: en\ninvariants: []\n", encoding="utf-8")
    alias = tmp_path / "alias.yaml"
    try:
        alias.symlink_to(valid)
    except OSError:
        pytest.skip("symlink creation is not permitted")
    with pytest.raises(ValueError, match="regular file"):
        compare.load_invariant_manifest(alias)

def test_rejects_regular_file_replaced_between_lstat_and_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "input.txt"
    path.write_bytes(b"original content")
    replacement = tmp_path / "replacement.txt"
    replacement.write_bytes(b"replacement content")

    original_open = os.open
    swapped = False

    def replace_before_open(file, flags, *args, **kwargs):
        nonlocal swapped
        if Path(file) == path and not swapped:
            swapped = True
            os.replace(replacement, path)
        return original_open(file, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", replace_before_open)

    with pytest.raises(ValueError, match="changed identity between lstat and open"):
        read_bounded_regular_file(path, max_bytes=1024)

    assert swapped

