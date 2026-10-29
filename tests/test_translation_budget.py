from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from skilltether.translation import (
    HttpJsonAdapter,
    MAX_TRANSLATION_TOTAL_REQUEST_BYTES,
    IdentityAdapter,
    translate_package,
)


def make_package(root: Path, instructions: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "SKILL.md").write_text(
        f"---\nname: {root.name}\ndescription: A translation budget test skill.\n---\n\n"
        f"# Instructions\n\n{instructions}\n",
        encoding="utf-8",
    )
    return root


def test_package_budget_preflight_stops_before_first_adapter_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import skilltether.translation as translation

    source = make_package(
        tmp_path / "source" / "sample-skill",
        "Translate this first instruction.\nTranslate this second instruction.",
    )
    output = tmp_path / "candidate" / "sample-skill"
    calls: list[str] = []

    class RemoteSpy:
        name = "remote-spy"
        remote = True

        def translate(self, text: str, source_locale: str, target_locale: str) -> str:
            calls.append(text)
            return text

    monkeypatch.setattr(translation, "MAX_TRANSLATION_REQUESTS", 1)

    with pytest.raises(RuntimeError, match="no provider request was sent"):
        translate_package(source, output, RemoteSpy(), "en", "fr")

    assert calls == []
    assert not output.exists()


def test_package_aggregate_byte_budget_preflights_without_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import skilltether.translation as translation

    source = make_package(
        tmp_path / "source" / "sample-skill",
        "A sufficiently long instruction should exceed a deliberately tiny request budget.",
    )
    output = tmp_path / "candidate" / "sample-skill"
    calls: list[str] = []

    class RemoteSpy:
        name = "remote-spy"
        remote = True

        def translate(self, text: str, source_locale: str, target_locale: str) -> str:
            calls.append(text)
            return text

    monkeypatch.setattr(translation, "MAX_TRANSLATION_TOTAL_REQUEST_BYTES", 64)

    with pytest.raises(RuntimeError, match="no provider request was sent"):
        translate_package(source, output, RemoteSpy(), "en", "fr")

    assert calls == []
    assert not output.exists()


def test_http_adapter_enforces_aggregate_request_count_before_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import urllib.request

    calls = 0

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, limit: int) -> bytes:
            return b'{"text":"ok"}'

    class Opener:
        def open(self, _request, timeout: float):
            nonlocal calls
            calls += 1
            return Response()

    monkeypatch.setattr(urllib.request, "build_opener", lambda *_args: Opener())
    monkeypatch.setattr("skilltether.translation.MAX_TRANSLATION_REQUESTS", 1)
    adapter = HttpJsonAdapter("https://provider.example.test/translate")

    assert adapter.translate("first", "en", "fr") == "ok"
    with pytest.raises(RuntimeError, match="request count exceeds"):
        adapter.translate("second", "en", "fr")
    assert calls == 1


def test_http_adapter_enforces_aggregate_request_bytes_before_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import urllib.request

    calls = 0
    first_body = json.dumps(
        {"text": "first", "source_locale": "en", "target_locale": "fr"},
        ensure_ascii=False,
    ).encode("utf-8")

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit: int) -> bytes:
            return b'{"text":"ok"}'

    class Opener:
        def open(self, _request, timeout: float):
            nonlocal calls
            calls += 1
            return Response()

    monkeypatch.setattr(urllib.request, "build_opener", lambda *_args: Opener())
    monkeypatch.setattr(
        "skilltether.translation.MAX_TRANSLATION_TOTAL_REQUEST_BYTES",
        len(first_body),
    )
    adapter = HttpJsonAdapter("https://provider.example.test/translate")

    assert adapter.translate("first", "en", "fr") == "ok"
    with pytest.raises(RuntimeError, match="aggregate request bytes exceed"):
        adapter.translate("first", "en", "fr")
    assert calls == 1


def test_http_adapter_bounds_responses_by_remaining_aggregate_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import urllib.request

    read_limits: list[int] = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, limit: int) -> bytes:
            read_limits.append(limit)
            return b'{"text":"translation longer than budget"}'[:limit]

    class Opener:
        def open(self, _request, timeout: float):
            return Response()

    monkeypatch.setattr(urllib.request, "build_opener", lambda *_args: Opener())
    monkeypatch.setattr("skilltether.translation.MAX_TRANSLATION_TOTAL_RESPONSE_BYTES", 8)
    adapter = HttpJsonAdapter("https://provider.example.test/translate")

    with pytest.raises(RuntimeError, match="aggregate response-byte safety limit"):
        adapter.translate("one short line", "en", "fr")

    assert read_limits == [9]


def test_custom_adapter_per_line_response_limit_prevents_candidate_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import skilltether.translation as translation

    source = make_package(tmp_path / "source" / "sample-skill", "Short line.")
    output = tmp_path / "candidate" / "sample-skill"

    class OversizedAdapter:
        name = "oversized-custom-adapter"
        remote = False

        def translate(self, text: str, source_locale: str, target_locale: str) -> str:
            return "x" * 17

    monkeypatch.setattr(translation, "MAX_TRANSLATION_RESPONSE_BYTES", 16)
    with pytest.raises(RuntimeError, match="per-line safety limit"):
        translate_package(source, output, OversizedAdapter(), "en", "fr")
    assert not output.exists()


def test_custom_adapter_aggregate_response_budget_is_enforced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import skilltether.translation as translation

    source = make_package(
        tmp_path / "source" / "sample-skill",
        "Short one.\nShort two.",
    )
    output = tmp_path / "candidate" / "sample-skill"

    class RepeatedOutputAdapter:
        name = "aggregate-budget-adapter"
        remote = False

        def translate(self, text: str, source_locale: str, target_locale: str) -> str:
            return "bonjour"

    monkeypatch.setattr(translation, "MAX_TRANSLATION_RESPONSE_BYTES", 100)
    monkeypatch.setattr(translation, "MAX_TRANSLATION_TOTAL_RESPONSE_BYTES", 10)
    with pytest.raises(RuntimeError, match="aggregate response bytes exceed"):
        translate_package(source, output, RepeatedOutputAdapter(), "en", "fr")
    assert not output.exists()


def test_identity_translation_still_passes_preflight_and_creates_candidate(
    tmp_path: Path,
) -> None:
    source = make_package(
        tmp_path / "source" / "sample-skill",
        "A small instruction for local processing.",
    )
    output = tmp_path / "candidate" / "sample-skill"

    _source_inventory, target_inventory, changed = translate_package(
        source, output, IdentityAdapter(), "en", "fr",
    )

    assert output.is_dir()
    assert "SKILL.md" in target_inventory
    assert changed == 0
