"""Build delivery requests from canonical Argus intelligence packets."""

from __future__ import annotations

from cios.delivery.packet_telegram_format import (
    daily_packet_brief_title,
    render_daily_packet_brief_markdown,
    render_weekly_packet_brief_markdown,
    weekly_packet_brief_title,
)
from cios.delivery.types import Cadence, DeliveryRequest, RecipientTarget, ReportReadyEvent, RoutingPlan
from cios.intelligence.argus_packet import ArgusIntelligencePacket
from cios.platform.channels.types import Channel


def build_packet_delivery_request(
    packet: ArgusIntelligencePacket,
    *,
    cadence: Cadence,
    telegram_chat_id: str,
    dashboard_url: str | None = None,
    report_id: int = 0,
) -> DeliveryRequest:
    """Build a Telegram delivery request that preserves packet/run identity."""

    if cadence == Cadence.DAILY:
        title = daily_packet_brief_title(packet)
        markdown_body = render_daily_packet_brief_markdown(packet)
    elif cadence == Cadence.WEEKLY:
        title = weekly_packet_brief_title(packet)
        markdown_body = render_weekly_packet_brief_markdown(packet)
    else:
        raise ValueError("packet delivery supports daily and weekly cadences only")

    report = ReportReadyEvent(
        report_id=report_id,
        tenant_id=packet.tenant.tenant_id,
        cadence=cadence,
        title=title,
        summary=packet.executive_read.plain_read,
        markdown_body=markdown_body,
        dashboard_url=dashboard_url,
        packet_id=packet.packet_id,
        run_id=packet.run.run_id,
        is_material_alert=packet.status == "actionable",
        confidence=packet.recommendations[0].confidence if packet.recommendations else None,
    )
    plan = RoutingPlan(
        tenant_id=packet.tenant.tenant_id,
        owner="Argus",
        targets=[RecipientTarget(channel=Channel.TELEGRAM, recipient_user_id=telegram_chat_id)],
        classification=cadence.value,
    )
    return DeliveryRequest(tenant_id=packet.tenant.tenant_id, report=report, plan=plan)


__all__ = ["build_packet_delivery_request"]
