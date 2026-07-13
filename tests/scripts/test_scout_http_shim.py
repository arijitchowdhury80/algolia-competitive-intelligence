"""Tests for the hosted Scout CLI-compatible shim."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "scout_http_shim.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("scout_http_shim", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_extract_payload_maps_scout_cli_shape_to_hosted_api():
    shim = _load_module()

    args = shim.parse_args(
        [
            "extract",
            "https://constructor.com/changelog",
            "--schema",
            '{"type":"object"}',
            "--instruction",
            "Extract product changes.",
            "--provider",
            "gemini/gemini-2.5-flash",
            "--js",
            "--timeout-seconds",
            "7",
        ]
    )

    payload = shim.build_extract_payload(args)

    assert payload == {
        "url": "https://constructor.com/changelog",
        "schema": {"type": "object"},
        "instruction": "Extract product changes.",
        "llm_provider": "gemini/gemini-2.5-flash",
        "use_js": True,
        "timeout_ms": 7000,
    }


def test_main_posts_to_hosted_scout_and_prints_json(monkeypatch, capsys):
    shim = _load_module()
    calls = []
    monkeypatch.delenv("SCOUT_API_KEY", raising=False)
    monkeypatch.delenv("SCOUT_HTTP_API_KEY", raising=False)

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "success": True,
                "url": "https://constructor.com/changelog",
                "metadata": {"crawled_at": "2026-07-10T00:00:00+00:00"},
                "data": {"changes": []},
                "duration_ms": 10,
            }

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def post(self, url, json, headers=None):
            calls.append({"url": url, "json": json, "headers": headers or {}, "timeout": self.timeout})
            return FakeResponse()

    monkeypatch.setattr(shim.httpx, "Client", FakeClient)

    rc = shim.main(
        [
            "extract",
            "https://constructor.com/changelog",
            "--schema",
            '{"type":"object"}',
            "--instruction",
            "Extract.",
            "--provider",
            "gemini/gemini-2.5-flash",
            "--base-url",
            "http://127.0.0.1:8421",
        ]
    )

    assert rc == 0
    assert calls == [
        {
            "url": "http://127.0.0.1:8421/extract",
            "json": {
                "url": "https://constructor.com/changelog",
                "schema": {"type": "object"},
                "instruction": "Extract.",
                "llm_provider": "gemini/gemini-2.5-flash",
                "use_js": False,
                "timeout_ms": 120000,
            },
            "headers": {},
            "timeout": 125.0,
        }
    ]
    assert json.loads(capsys.readouterr().out)["success"] is True


def test_main_sends_scout_api_key_header_from_environment(monkeypatch, capsys):
    shim = _load_module()
    calls = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"success": True, "url": "https://elastic.co/guide", "data": {}}

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def post(self, url, json, headers=None):
            calls.append(headers or {})
            return FakeResponse()

    monkeypatch.setenv("SCOUT_API_KEY", "test-secret")
    monkeypatch.delenv("SCOUT_HTTP_API_KEY", raising=False)
    monkeypatch.setattr(shim.httpx, "Client", FakeClient)

    rc = shim.main(
        [
            "extract",
            "https://elastic.co/guide",
            "--schema",
            '{"type":"object"}',
            "--base-url",
            "http://127.0.0.1:8421",
        ]
    )

    assert rc == 0
    assert calls == [{"X-API-Key": "test-secret"}]
    assert json.loads(capsys.readouterr().out)["success"] is True


def test_main_scrape_posts_to_hosted_scout_and_prints_json(monkeypatch, capsys):
    shim = _load_module()
    calls = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "success": True,
                "url": "https://constructor.com/changelog",
                "clean_markdown": "# Changelog\n\nAI Shopping Agent released.",
                "metadata": {"crawled_at": "2026-07-10T00:00:00+00:00"},
                "duration_ms": 10,
            }

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def post(self, url, json, headers=None):
            calls.append({"url": url, "json": json, "headers": headers or {}, "timeout": self.timeout})
            return FakeResponse()

    monkeypatch.setenv("SCOUT_HTTP_API_KEY", "bridge-secret")
    monkeypatch.setattr(shim.httpx, "Client", FakeClient)

    rc = shim.main(
        [
            "scrape",
            "https://constructor.com/changelog",
            "--base-url",
            "http://127.0.0.1:8421",
            "--js",
            "--timeout-seconds",
            "9",
        ]
    )

    assert rc == 0
    assert calls == [
        {
            "url": "http://127.0.0.1:8421/scrape",
            "json": {
                "url": "https://constructor.com/changelog",
                "formats": ["markdown"],
                "use_js": True,
                "timeout_ms": 9000,
            },
            "headers": {"X-API-Key": "bridge-secret"},
            "timeout": 14.0,
        }
    ]
    assert json.loads(capsys.readouterr().out)["clean_markdown"].startswith("# Changelog")
