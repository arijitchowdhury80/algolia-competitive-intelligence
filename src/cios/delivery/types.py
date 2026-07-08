"""Shared data types for the argus-delivery-commander / argus-action-router skills.

Mirrors src/cios/db/schema.sql: bot_deliveries, delivery_attempts, action_items,
reports. See docs/planning/Argus-project-manifesto.md Phase 8 and
docs/planning/CI-OS-Fable-build-goal-spec.md Gate 6.

Known V0 defect this module fixes by design (Gate 6 mandate): bot_deliveries
must record the TRUE send state returned by the channel adapter -- 'sent'
only when the adapter confirms success, 'failed' with the adapter's error
otherwise. V0 recorded rows regardless of actual send outcome.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from cios.platform.channels.types import Channel

# Default channel fallback order per the manifesto's locked delivery priority
# (CI-OS-Fable-build-goal-spec.md §3, §9.3): Telegram-rich first, then email
# (renders the HTML template natively), then a dashboard ping as the final
# always-available fallback.
DEFAULT_CHANNEL_ORDER: list[Channel] = [Channel.TELEGRAM, Channel.EMAIL, Channel.WEB_APP]

# Bounded retry policy: at most this many attempts per channel before the
# router falls through to the next channel in preference order.
DEFAULT_MAX_ATTEMPTS_PER_CHANNEL = 3


class BotDeliveryStatus(str, Enum):
    QUEUED = "queued"
    SENDING = "sending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    # A reviewable brief that failed quality review never reaches an adapter
    # (manifesto Phase 6: a failed verdict must never ship). BLOCKED records
    # that the gate stopped delivery, distinct from FAILED (adapter tried and
    # failed) so operators can tell "we chose not to send" from "we tried and
    # couldn't."
    BLOCKED = "blocked"


class DeliveryAttemptStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


class Cadence(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    AD_HOC = "ad_hoc"
    ALERT = "alert"


class ActionItem(BaseModel):
    """Routed action item (schema: action_items).

    `evidence_ids` must be non-empty -- the schema enforces
    action_item_needs_evidence (evidence-or-silence doctrine); the router
    never routes an action without at least one evidence id.
    """

    id: Optional[int] = None
    tenant_id: int
    owner: Optional[str] = None
    recommendation: str
    evidence_ids: list[Any] = Field(default_factory=list)
    source_delta_ids: list[Any] = Field(default_factory=list)
    priority: Optional[str] = None
    confidence: Optional[float] = None
    due_window: Optional[str] = None
    status: str = "open"
    report_id: Optional[int] = None


class ReportReadyEvent(BaseModel):
    """A certified report/brief ready for delivery (schema: reports).

    `is_material_alert` + `confidence` drive the off-schedule interrupt
    policy in the action router (manifesto: "Argus may interrupt outside
    9 AM only for high-confidence material alerts").
    """

    report_id: int
    tenant_id: int
    cadence: Cadence
    title: Optional[str] = None
    summary: Optional[str] = None
    markdown_path: Optional[str] = None
    html_path: Optional[str] = None
    markdown_body: Optional[str] = None
    dashboard_url: Optional[str] = None
    is_material_alert: bool = False
    confidence: Optional[float] = None


# Confidence threshold above which a material report may interrupt the
# normal 9 AM schedule (manifesto alert policy).
MATERIAL_ALERT_CONFIDENCE_THRESHOLD = 0.8


class RecipientTarget(BaseModel):
    """A resolved (channel, address) pair to deliver to."""

    channel: Channel
    recipient_user_id: str
    thread_id: Optional[str] = None


class RoutingPlan(BaseModel):
    """Output of ActionRouter.route*(): ordered fallback targets + owner."""

    tenant_id: int
    owner: Optional[str] = None
    targets: list[RecipientTarget] = Field(default_factory=list)
    classification: Optional[str] = None


class DeliveryRequest(BaseModel):
    """Input to DeliveryCommander.deliver(): a report/brief to fan out."""

    tenant_id: int
    report: ReportReadyEvent
    plan: RoutingPlan
    max_attempts_per_channel: int = DEFAULT_MAX_ATTEMPTS_PER_CHANNEL


class DeliveryAttemptRecord(BaseModel):
    """Mirrors schema.sql delivery_attempts. One row per channel API call."""

    id: Optional[int] = None
    tenant_id: int
    user_id: Optional[int] = None
    channel: Channel
    status: DeliveryAttemptStatus
    delivery_ref: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BotDeliveryRecord(BaseModel):
    """Mirrors schema.sql bot_deliveries. One row per delivery-commander run
    per channel, carrying the TRUE final state (never assumed)."""

    id: Optional[int] = None
    tenant_id: int
    cadence: Cadence
    bot_profile: Optional[str] = "argus"
    channel: Channel
    recipient_redacted: Optional[str] = None
    status: BotDeliveryStatus = BotDeliveryStatus.QUEUED
    markdown_path: Optional[str] = None
    html_path: Optional[str] = None
    dashboard_url: Optional[str] = None
    report_id: Optional[int] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DeliveryOutcome(BaseModel):
    """Result of DeliveryCommander.deliver(): what actually happened."""

    tenant_id: int
    report_id: int
    delivered: bool
    delivered_channel: Optional[Channel] = None
    bot_deliveries: list[BotDeliveryRecord] = Field(default_factory=list)
    attempts: list[DeliveryAttemptRecord] = Field(default_factory=list)


def redact_recipient(recipient_user_id: str) -> str:
    """Redact a recipient identifier for storage in bot_deliveries.recipient_redacted.

    Keeps the last 4 characters visible for operator debuggability; masks
    the rest. Never store a raw phone/email/chat id in the ledger.
    """
    if len(recipient_user_id) <= 4:
        return "*" * len(recipient_user_id)
    return "*" * (len(recipient_user_id) - 4) + recipient_user_id[-4:]
