"""argus-action-router: routes action items / report-ready events to the
right channel + recipient per tenant config.

Storage/config access is via injected Protocols only (no direct DB access
here; tests use in-memory fakes), matching hunter/lifecycle.py and
platform/identity/acl.py conventions.

Per the manifesto's locked delivery priority (CI-OS-Fable-build-goal-spec.md
§3, §9.3): Telegram-rich first, then email, then a dashboard ping as the
always-available fallback. A tenant's configured preference overrides the
default order when present.
"""

from __future__ import annotations

from typing import Optional, Protocol

from cios.delivery.types import (
    DEFAULT_CHANNEL_ORDER,
    MATERIAL_ALERT_CONFIDENCE_THRESHOLD,
    ActionItem,
    RecipientTarget,
    ReportReadyEvent,
    RoutingPlan,
)
from cios.platform.channels.types import Channel


class TenantChannelConfig(Protocol):
    """Per-tenant delivery configuration."""

    def get_channel_preference(self, tenant_id: int) -> list[Channel]:
        """Ordered channel fallback preference for this tenant. Empty list
        means "use the default order"."""
        ...

    def get_recipient(self, tenant_id: int, channel: Channel) -> Optional[str]:
        """The configured recipient address/chat-id for a tenant+channel.
        None means this tenant has no recipient configured for that
        channel -- the router skips it."""
        ...

    def get_thread_id(self, tenant_id: int, channel: Channel) -> Optional[str]:
        """Optional channel thread id (e.g. a Telegram chat id override)."""
        ...


class OwnerDirectory(Protocol):
    """Resolves an action item's serving function to a human owner."""

    def get_owner(self, tenant_id: int, priority: Optional[str]) -> Optional[str]: ...


class ActionRouter:
    """Routes action items and report-ready events to channel + recipient."""

    def __init__(self, channel_config: TenantChannelConfig, owners: Optional[OwnerDirectory] = None) -> None:
        self._channel_config = channel_config
        self._owners = owners

    def _resolve_targets(self, tenant_id: int) -> list[RecipientTarget]:
        preference = self._channel_config.get_channel_preference(tenant_id) or DEFAULT_CHANNEL_ORDER
        targets: list[RecipientTarget] = []
        for channel in preference:
            recipient = self._channel_config.get_recipient(tenant_id, channel)
            if not recipient:
                continue
            targets.append(
                RecipientTarget(
                    channel=channel,
                    recipient_user_id=recipient,
                    thread_id=self._channel_config.get_thread_id(tenant_id, channel),
                )
            )
        return targets

    def route_action_item(self, item: ActionItem) -> RoutingPlan:
        """Route a single action item to an owner + fallback channel chain.

        Raises ValueError if the item carries no evidence -- action items
        without evidence are noise, not a decision (manifesto doctrine),
        and must never be routed.
        """
        if not item.evidence_ids:
            raise ValueError("cannot route an action item with no evidence_ids")

        owner = item.owner
        if not owner and self._owners is not None:
            owner = self._owners.get_owner(item.tenant_id, item.priority)

        return RoutingPlan(
            tenant_id=item.tenant_id,
            owner=owner,
            targets=self._resolve_targets(item.tenant_id),
            classification=item.priority,
        )

    def route_report(self, report: ReportReadyEvent) -> RoutingPlan:
        """Route a certified report/brief to its delivery fallback chain.

        A high-confidence material alert is allowed to interrupt the normal
        schedule (manifesto alert policy) -- this method does not itself
        gate on time-of-day (a scheduling concern owned by the caller/cron);
        it only marks the plan's classification so the commander/caller can
        apply interrupt behavior.
        """
        is_interrupt = report.is_material_alert and (
            report.confidence is not None and report.confidence >= MATERIAL_ALERT_CONFIDENCE_THRESHOLD
        )
        return RoutingPlan(
            tenant_id=report.tenant_id,
            targets=self._resolve_targets(report.tenant_id),
            classification="material_alert" if is_interrupt else report.cadence.value,
        )
