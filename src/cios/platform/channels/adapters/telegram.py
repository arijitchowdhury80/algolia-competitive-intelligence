"""Telegram channel adapter.

Uses the Telegram Bot HTTP API directly via httpx (no third-party Telegram
SDK). This is V1's production channel -- see
docs/planning/CI-OS-gate0-implementation-plan.md §1: Hermes cron delivers via
`deliver: telegram` today with a plain-text renderer. This adapter's
html_text -> parse_mode=HTML path is the rich-brief replacement for that.

Env vars (docs/planning/CI-OS-env-and-secrets-spec.md):
  ARGUS_TELEGRAM_BOT_TOKEN   - bot token
  ARGUS_TELEGRAM_CHAT_ID     - default delivery target
  TELEGRAM_ALLOWED_USER_IDS  - comma-separated allowlist of Telegram user ids

Security: allowlist is enforced in map_identity() and receive(). Unknown
senders are denied by default and never get their message content routed
anywhere -- receive() marks them identity_unlinked and does not proceed to
serve any data. No channel command may bypass this (see architecture doc,
Access Control Model: "No channel command bypasses ACL").
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import httpx

from cios.platform.channels.adapter import ChannelAdapter
from cios.platform.channels.types import (
    Attachment,
    Channel,
    ChannelIdentity,
    DeliveryResult,
    NormalizedInboundMessage,
    ResponseEnvelope,
    VerificationResult,
)

TELEGRAM_API_BASE = "https://api.telegram.org"
TELEGRAM_TEXT_LIMIT = 4096

_CAPABILITIES = {
    "html": True,
    "attachments": True,
    "native_cards": False,
}


def _split_html_text(html_text: str, limit: int = TELEGRAM_TEXT_LIMIT) -> list[str]:
    """Split long HTML text into chunks under Telegram's message limit.

    Splits on paragraph boundaries ("\n\n") where possible so we don't break
    mid-tag; falls back to a hard split if a single paragraph exceeds the
    limit on its own.
    """
    if len(html_text) <= limit:
        return [html_text]

    paragraphs = html_text.split("\n\n")
    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= limit:
            current = candidate
            continue

        if current:
            chunks.append(current)
            current = ""

        if len(paragraph) <= limit:
            current = paragraph
        else:
            # Single paragraph too long on its own: hard split.
            for i in range(0, len(paragraph), limit):
                chunks.append(paragraph[i : i + limit])

    if current:
        chunks.append(current)

    return chunks


class TelegramAdapter(ChannelAdapter):
    channel_name = "telegram"

    def __init__(self) -> None:
        self.bot_token = os.environ.get("ARGUS_TELEGRAM_BOT_TOKEN", "")
        self.default_chat_id = os.environ.get("ARGUS_TELEGRAM_CHAT_ID", "")
        allowed_raw = os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "")
        self.allowed_user_ids = {
            uid.strip() for uid in allowed_raw.split(",") if uid.strip()
        }

    def _api_url(self, method: str) -> str:
        return f"{TELEGRAM_API_BASE}/bot{self.bot_token}/{method}"

    def _is_allowed(self, telegram_user_id: str) -> bool:
        return telegram_user_id in self.allowed_user_ids

    def map_identity(self, raw_event: Any) -> ChannelIdentity:
        message = raw_event.get("message", {})
        sender = message.get("from", {})
        user_id = str(sender.get("id", ""))
        allowed = self._is_allowed(user_id)
        return ChannelIdentity(
            channel=Channel.TELEGRAM,
            channel_user_id=user_id,
            display_name=sender.get("first_name"),
            is_allowed=allowed,
            resolved_user_id=user_id if allowed else None,
        )

    def verify_signature(self, raw_event: Any) -> VerificationResult:
        # Telegram Bot API webhooks are verified via a secret token header at
        # the transport layer (set on setWebhook), not a payload signature.
        # That check happens in the gateway before raw_event reaches here;
        # this adapter treats a well-formed message payload as verified.
        if isinstance(raw_event, dict) and "message" in raw_event:
            return VerificationResult(verified=True)
        return VerificationResult(verified=False, reason="malformed_event")

    async def receive(self, raw_event: Any) -> NormalizedInboundMessage:
        message = raw_event.get("message", {})
        identity = self.map_identity(raw_event)
        verification = self.verify_signature(raw_event)

        chat = message.get("chat", {})
        received_at = datetime.fromtimestamp(
            message.get("date", 0), tz=timezone.utc
        )

        metadata: dict[str, Any] = {}
        text = message.get("text")

        if not identity.is_allowed:
            # Deny by default: never surface message text for unlinked
            # identities, and flag it so upstream never routes to Argus.
            metadata["identity_unlinked"] = True
            text = None

        return NormalizedInboundMessage(
            channel=Channel.TELEGRAM,
            channel_user_id=identity.channel_user_id,
            channel_thread_id=str(chat.get("id")) if chat.get("id") is not None else None,
            message_id=str(message.get("message_id", "")),
            text=text,
            attachments=[],
            received_at=received_at,
            signature_verified=verification.verified and identity.is_allowed,
            metadata=metadata,
        )

    async def send(self, response: ResponseEnvelope) -> DeliveryResult:
        chat_id = response.thread_id or self.default_chat_id

        try:
            async with httpx.AsyncClient() as client:
                if response.html_text:
                    chunks = _split_html_text(response.html_text)
                    last_result: dict[str, Any] = {}
                    for chunk in chunks:
                        payload = {
                            "chat_id": chat_id,
                            "text": chunk,
                            "parse_mode": "HTML",
                        }
                        http_response = await client.post(
                            self._api_url("sendMessage"), json=payload
                        )
                        http_response.raise_for_status()
                        last_result = http_response.json()
                else:
                    payload = {"chat_id": chat_id, "text": response.text}
                    http_response = await client.post(
                        self._api_url("sendMessage"), json=payload
                    )
                    http_response.raise_for_status()
                    last_result = http_response.json()

                for attachment in response.attachments:
                    await self._send_attachment(client, chat_id, attachment)

            message_id = str(last_result.get("result", {}).get("message_id", ""))
            return DeliveryResult(
                success=bool(last_result.get("ok", True)),
                channel=Channel.TELEGRAM,
                provider_message_id=message_id,
                raw_response=last_result,
            )
        except httpx.HTTPError as exc:
            return DeliveryResult(
                success=False,
                channel=Channel.TELEGRAM,
                error=str(exc),
            )

    async def _send_attachment(
        self, client: httpx.AsyncClient, chat_id: str, attachment: Attachment
    ) -> None:
        data = {"chat_id": chat_id}
        if attachment.caption:
            data["caption"] = attachment.caption

        if attachment.url:
            data["document"] = attachment.url
            http_response = await client.post(self._api_url("sendDocument"), data=data)
            http_response.raise_for_status()
        elif attachment.data:
            files = {"document": (attachment.filename, attachment.data)}
            http_response = await client.post(
                self._api_url("sendDocument"), data=data, files=files
            )
            http_response.raise_for_status()

    def supports(self, capability: str) -> bool:
        return _CAPABILITIES.get(capability, False)
