"""Tests for the CI-OS channel adapter layer.

All network I/O is mocked. No live network calls.
"""

from __future__ import annotations

import email
from datetime import datetime, timezone
from email.message import Message

import httpx
import pytest

from cios.platform.channels.adapter import NotSupported
from cios.platform.channels.adapters.email_smtp import EmailSmtpAdapter
from cios.platform.channels.adapters.telegram import TelegramAdapter
from cios.platform.channels.registry import UnknownChannelError, get_adapter, register_adapter
from cios.platform.channels.types import Channel, ResponseEnvelope


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------


@pytest.fixture
def telegram_adapter(monkeypatch):
    monkeypatch.setenv("ARGUS_TELEGRAM_BOT_TOKEN", "test-bot-token")
    monkeypatch.setenv("ARGUS_TELEGRAM_CHAT_ID", "6789423537")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "6789423537,111222333")
    return TelegramAdapter()


class _FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)


@pytest.mark.asyncio
async def test_telegram_send_builds_send_message_payload_with_html(telegram_adapter, monkeypatch):
    captured = {}

    async def fake_post(self, url, json=None, data=None, files=None, **kwargs):
        captured["url"] = url
        captured["json"] = json
        return _FakeResponse({"ok": True, "result": {"message_id": 42}})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    envelope = ResponseEnvelope(
        recipient_user_id="6789423537",
        channel=Channel.TELEGRAM,
        thread_id="6789423537",
        text="plain fallback",
        html_text="<b>bold brief</b>",
    )

    result = await telegram_adapter.send(envelope)

    assert result.success is True
    assert "sendMessage" in captured["url"]
    assert captured["json"]["parse_mode"] == "HTML"
    assert captured["json"]["text"] == "<b>bold brief</b>"
    assert captured["json"]["chat_id"] == "6789423537"


@pytest.mark.asyncio
async def test_telegram_send_falls_back_to_plain_text_without_html(telegram_adapter, monkeypatch):
    captured = {}

    async def fake_post(self, url, json=None, data=None, files=None, **kwargs):
        captured["json"] = json
        return _FakeResponse({"ok": True, "result": {"message_id": 43}})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    envelope = ResponseEnvelope(
        recipient_user_id="6789423537",
        channel=Channel.TELEGRAM,
        thread_id="6789423537",
        text="just plain text",
    )

    result = await telegram_adapter.send(envelope)

    assert result.success is True
    assert "parse_mode" not in captured["json"] or captured["json"].get("parse_mode") is None
    assert captured["json"]["text"] == "just plain text"


@pytest.mark.asyncio
async def test_telegram_send_splits_long_html_text_across_messages(telegram_adapter, monkeypatch):
    calls = []

    async def fake_post(self, url, json=None, data=None, files=None, **kwargs):
        calls.append((url, json))
        return _FakeResponse({"ok": True, "result": {"message_id": len(calls)}})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    # Build > 4096 char html text out of paragraphs so the splitter has
    # natural break points.
    paragraph = "<p>" + ("x" * 500) + "</p>"
    long_html = "\n\n".join([paragraph] * 12)  # ~ 6000+ chars
    assert len(long_html) > 4096

    envelope = ResponseEnvelope(
        recipient_user_id="6789423537",
        channel=Channel.TELEGRAM,
        thread_id="6789423537",
        text="fallback",
        html_text=long_html,
    )

    result = await telegram_adapter.send(envelope)

    assert result.success is True
    # Must have made more than one sendMessage call, each within the limit.
    send_message_calls = [c for c in calls if "sendMessage" in c[0]]
    assert len(send_message_calls) >= 2
    for _, payload in send_message_calls:
        assert len(payload["text"]) <= 4096


def test_telegram_allowlist_denies_unknown_user(telegram_adapter):
    raw_event = {
        "message": {
            "message_id": 1,
            "date": 1700000000,
            "text": "hello",
            "chat": {"id": 999999999},
            "from": {"id": 999999999, "first_name": "Stranger"},
        }
    }

    identity = telegram_adapter.map_identity(raw_event)

    assert identity.is_allowed is False
    assert identity.resolved_user_id is None


def test_telegram_allowlist_allows_known_user(telegram_adapter):
    raw_event = {
        "message": {
            "message_id": 2,
            "date": 1700000000,
            "text": "hello",
            "chat": {"id": 6789423537},
            "from": {"id": 6789423537, "first_name": "Arijit"},
        }
    }

    identity = telegram_adapter.map_identity(raw_event)

    assert identity.is_allowed is True


@pytest.mark.asyncio
async def test_telegram_receive_denies_unknown_user_never_leaks_text(telegram_adapter):
    raw_event = {
        "message": {
            "message_id": 3,
            "date": 1700000000,
            "text": "give me the report",
            "chat": {"id": 999999999},
            "from": {"id": 999999999, "first_name": "Stranger"},
        }
    }

    normalized = await telegram_adapter.receive(raw_event)

    assert normalized.signature_verified is False
    assert normalized.metadata.get("identity_unlinked") is True


def test_telegram_supports_declares_capabilities(telegram_adapter):
    assert telegram_adapter.supports("html") is True
    assert telegram_adapter.supports("attachments") is True
    assert telegram_adapter.supports("native_cards") is False


# ---------------------------------------------------------------------------
# Email / SMTP
# ---------------------------------------------------------------------------


@pytest.fixture
def email_adapter(monkeypatch):
    monkeypatch.setenv("CIOS_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("CIOS_SMTP_PORT", "587")
    monkeypatch.setenv("CIOS_SMTP_USER", "argus@example.com")
    monkeypatch.setenv("CIOS_SMTP_PASSWORD", "test-password")
    monkeypatch.setenv("CIOS_SMTP_FROM", "argus@example.com")
    return EmailSmtpAdapter()


@pytest.mark.asyncio
async def test_email_send_builds_valid_multipart_mime(email_adapter, monkeypatch):
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=10):
            sent["host"] = host
            sent["port"] = port

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self):
            sent["starttls"] = True

        def login(self, user, password):
            sent["login"] = (user, password)

        def send_message(self, msg):
            sent["message"] = msg

    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)

    envelope = ResponseEnvelope(
        recipient_user_id="exec@example.com",
        channel=Channel.EMAIL,
        text="Plain fallback body",
        html_text="<h1>Daily Brief</h1><p>Signals here.</p>",
    )

    result = await email_adapter.send(envelope)

    assert result.success is True
    assert sent["login"] == ("argus@example.com", "test-password")

    msg: Message = sent["message"]
    assert msg.is_multipart()

    # Parse back and assert both plain and html parts exist.
    raw_bytes = msg.as_bytes()
    parsed = email.message_from_bytes(raw_bytes)
    parts_by_type = {part.get_content_type(): part for part in parsed.walk()}

    assert "text/plain" in parts_by_type
    assert "text/html" in parts_by_type
    assert "Plain fallback body" in parts_by_type["text/plain"].get_payload(decode=True).decode()
    assert "Daily Brief" in parts_by_type["text/html"].get_payload(decode=True).decode()


@pytest.mark.asyncio
async def test_email_receive_not_supported(email_adapter):
    with pytest.raises(NotSupported):
        await email_adapter.receive({"anything": "goes"})


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registry_get_adapter_unknown_channel_raises_clear_error():
    with pytest.raises(UnknownChannelError) as exc_info:
        get_adapter("carrier_pigeon")

    assert "carrier_pigeon" in str(exc_info.value)


def test_registry_get_adapter_returns_registered_instance():
    class DummyAdapter:
        channel_name = "dummy"

    instance = DummyAdapter()
    register_adapter("dummy", instance)

    assert get_adapter("dummy") is instance
