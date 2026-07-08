"""ChannelAdapter interface.

Per docs/planning/CI-OS-channels-identity-acl-and-model-provider-architecture.md:

    ChannelAdapter
      receive(raw_event) -> NormalizedInboundMessage
      send(response_envelope) -> DeliveryResult
      verify_signature(raw_event) -> VerificationResult
      map_identity(raw_event) -> ChannelIdentity
      supports(capability) -> boolean

Identity and ACL resolution (steps 3-6 of the identity resolution flow) live
one layer above adapters, in the platform's identity module. Adapters only
resolve as far as "does this raw channel event belong to a known channel
identity" -- they must never grant data access themselves.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from cios.platform.channels.types import (
    ChannelIdentity,
    DeliveryResult,
    NormalizedInboundMessage,
    ResponseEnvelope,
    VerificationResult,
)


class NotSupported(NotImplementedError):
    """Raised when an adapter does not implement a given operation.

    Example: an outbound-only channel adapter's receive() must raise this
    rather than silently returning a fake/empty message.
    """


class ChannelAdapter(ABC):
    """Base class every channel adapter (Telegram, WhatsApp, email, ...) implements."""

    channel_name: str

    @abstractmethod
    async def receive(self, raw_event: Any) -> NormalizedInboundMessage:
        """Normalize a raw inbound channel event."""

    @abstractmethod
    async def send(self, response: ResponseEnvelope) -> DeliveryResult:
        """Deliver a response envelope through this channel."""

    @abstractmethod
    def verify_signature(self, raw_event: Any) -> VerificationResult:
        """Verify the authenticity of a raw inbound event (webhook signature, etc)."""

    @abstractmethod
    def map_identity(self, raw_event: Any) -> ChannelIdentity:
        """Resolve a raw event to a channel-level identity. Deny by default."""

    @abstractmethod
    def supports(self, capability: str) -> bool:
        """Report whether this adapter supports a given capability string."""
