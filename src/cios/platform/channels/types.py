"""Shared data types for the CI-OS channel adapter layer.

See docs/planning/CI-OS-channels-identity-acl-and-model-provider-architecture.md
for the source spec (ChannelAdapter interface, NormalizedInboundMessage,
ResponseEnvelope shapes).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class Channel(str, Enum):
    """Known channel identifiers. New channels append here."""

    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"
    APPLE_MESSAGES_BUSINESS = "apple_messages_business"
    WEB_APP = "web_app"
    EMAIL = "email"


class Attachment(BaseModel):
    """A single file/media attachment, inbound or outbound."""

    filename: str
    content_type: Optional[str] = None
    url: Optional[str] = None
    data: Optional[bytes] = None
    caption: Optional[str] = None


class NormalizedInboundMessage(BaseModel):
    """Channel-agnostic representation of an inbound message.

    Every adapter's `receive()` must normalize raw channel payloads into this
    shape before anything downstream (identity resolution, ACL, Argus) sees it.
    """

    channel: Channel
    channel_user_id: str
    channel_thread_id: Optional[str] = None
    message_id: str
    text: Optional[str] = None
    attachments: list[Attachment] = Field(default_factory=list)
    received_at: datetime
    signature_verified: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliveryPolicy(BaseModel):
    """How a ResponseEnvelope should be delivered."""

    retry: bool = True
    max_retries: int = 3
    priority: str = "normal"


class ResponseEnvelope(BaseModel):
    """Channel-agnostic representation of an outbound response.

    Adapters translate this into the wire format for their specific channel
    (e.g. Telegram sendMessage payload, SMTP MIME message).
    """

    recipient_user_id: str
    channel: Channel
    thread_id: Optional[str] = None
    text: str
    html_text: Optional[str] = None
    cards: list[dict[str, Any]] = Field(default_factory=list)
    attachments: list[Attachment] = Field(default_factory=list)
    evidence_links: list[str] = Field(default_factory=list)
    classification: Optional[str] = None
    delivery_policy: DeliveryPolicy = Field(default_factory=DeliveryPolicy)


class DeliveryResult(BaseModel):
    """Outcome of a ChannelAdapter.send() call."""

    success: bool
    channel: Channel
    provider_message_id: Optional[str] = None
    error: Optional[str] = None
    raw_response: Optional[dict[str, Any]] = None


class ChannelIdentity(BaseModel):
    """Result of resolving a raw channel event to a channel-level identity.

    This is NOT the canonical CI-OS user -- that resolution happens one layer
    up (identity resolution step 3 in the architecture doc). This model only
    carries what the adapter itself can determine from the raw event.
    """

    channel: Channel
    channel_user_id: str
    display_name: Optional[str] = None
    is_allowed: bool = False
    resolved_user_id: Optional[str] = None


class VerificationResult(BaseModel):
    """Outcome of verifying a raw inbound event's authenticity."""

    verified: bool
    reason: Optional[str] = None
