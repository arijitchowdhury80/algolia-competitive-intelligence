"""Email (SMTP) channel adapter. Outbound-only for v1.

NOTE ON ENV VARS: this adapter reads CIOS_SMTP_HOST / CIOS_SMTP_PORT /
CIOS_SMTP_USER / CIOS_SMTP_PASSWORD / CIOS_SMTP_FROM. These are NOT yet in
docs/planning/CI-OS-env-and-secrets-spec.md -- they must be appended there
(Required Secret Groups, a new "Email / SMTP" section) before this adapter
ships to any real deployment.

receive() is not supported: email is outbound-only in v1 (no inbound parsing
/ reply-threading yet). Callers must catch NotSupported.
"""

from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from cios.platform.channels.adapter import ChannelAdapter, NotSupported
from cios.platform.channels.types import (
    Channel,
    ChannelIdentity,
    DeliveryResult,
    NormalizedInboundMessage,
    ResponseEnvelope,
    VerificationResult,
)

_CAPABILITIES = {
    "html": True,
    "attachments": True,
    "native_cards": False,
}


class EmailSmtpAdapter(ChannelAdapter):
    channel_name = "email"

    def __init__(self) -> None:
        self.host = os.environ.get("CIOS_SMTP_HOST", "")
        self.port = int(os.environ.get("CIOS_SMTP_PORT", "587"))
        self.user = os.environ.get("CIOS_SMTP_USER", "")
        self.password = os.environ.get("CIOS_SMTP_PASSWORD", "")
        self.from_addr = os.environ.get("CIOS_SMTP_FROM", self.user)

    async def receive(self, raw_event: Any) -> NormalizedInboundMessage:
        raise NotSupported("EmailSmtpAdapter is outbound-only in v1")

    async def send(self, response: ResponseEnvelope) -> DeliveryResult:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = response.classification or "CI-OS Update"
            msg["From"] = self.from_addr
            msg["To"] = response.recipient_user_id

            msg.attach(MIMEText(response.text, "plain"))
            if response.html_text:
                msg.attach(MIMEText(response.html_text, "html"))

            with smtplib.SMTP(self.host, self.port, timeout=10) as smtp:
                smtp.starttls()
                smtp.login(self.user, self.password)
                smtp.send_message(msg)

            return DeliveryResult(success=True, channel=Channel.EMAIL)
        except Exception as exc:  # noqa: BLE001 - report any SMTP failure as a DeliveryResult
            return DeliveryResult(success=False, channel=Channel.EMAIL, error=str(exc))

    def verify_signature(self, raw_event: Any) -> VerificationResult:
        # No inbound support in v1; nothing to verify.
        return VerificationResult(verified=False, reason="inbound_not_supported")

    def map_identity(self, raw_event: Any) -> ChannelIdentity:
        raise NotSupported("EmailSmtpAdapter is outbound-only in v1")

    def supports(self, capability: str) -> bool:
        return _CAPABILITIES.get(capability, False)
