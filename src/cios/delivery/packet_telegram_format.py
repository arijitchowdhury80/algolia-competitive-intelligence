"""Telegram HTML renderers for canonical Argus intelligence packets."""

from __future__ import annotations

from cios.intelligence.argus_packet import ArgusIntelligencePacket

from .telegram_format import render_brief_html


def render_daily_packet_brief_html(packet: ArgusIntelligencePacket, *, dashboard_url: str | None = None) -> str:
    """Render the daily mobile command brief from the canonical packet."""

    body = _failure_body(packet) if packet.status in {"failed", "blocked"} else _daily_body(packet)
    return render_brief_html(packet.executive_read.headline, body, dashboard_url=dashboard_url)


def render_weekly_packet_brief_html(packet: ArgusIntelligencePacket, *, dashboard_url: str | None = None) -> str:
    """Render a weekly pattern brief from the canonical packet."""

    body = _failure_body(packet) if packet.status in {"failed", "blocked"} else _weekly_body(packet)
    return render_brief_html(f"Argus weekly pattern brief - {packet.tenant.display_name}", body, dashboard_url=dashboard_url)


def _daily_body(packet: ArgusIntelligencePacket) -> str:
    lines = [
        f"Status: {packet.status}",
        f"Run: {packet.run.run_id}",
        f"Window: {packet.time_window.label}",
        "",
        packet.executive_read.plain_read,
        "",
        f"Why it matters: {packet.executive_read.why_it_matters_to_algolia}",
    ]
    if packet.market_movements:
        movement = packet.market_movements[0]
        lines.extend(
            [
                "",
                f"Movement: {movement.label}",
                movement.summary,
            ]
        )
    if packet.recommendations:
        recommendation = packet.recommendations[0]
        lines.extend(
            [
                "",
                f"Owner: {recommendation.owner}",
                f"Action: {recommendation.action}",
                f"Why now: {recommendation.why_now}",
            ]
        )
    elif packet.blocked_actions:
        blocked = packet.blocked_actions[0]
        lines.extend(["", f"Blocked action: {blocked.proposed_action}", f"Needed: {', '.join(blocked.needed_evidence)}"])
    lines.extend(_plane_lines(packet))
    return "\n".join(line for line in lines if line is not None)


def _weekly_body(packet: ArgusIntelligencePacket) -> str:
    lines = [
        f"Weekly window: {packet.time_window.start_at.date()} to {packet.time_window.end_at.date()}",
        f"Run: {packet.run.run_id}",
        "",
        packet.executive_read.plain_read,
    ]
    if packet.market_movements:
        lines.extend(["", "Weekly pattern:"])
        for movement in packet.market_movements[:3]:
            lines.append(f"- {movement.summary}")
    if packet.recommendations:
        recommendation = packet.recommendations[0]
        lines.extend(["", f"Owner: {recommendation.owner}", f"Action: {recommendation.action}"])
    lines.extend(_plane_lines(packet))
    return "\n".join(lines)


def _failure_body(packet: ArgusIntelligencePacket) -> str:
    lines = [
        f"Status: {packet.status}",
        f"Run: {packet.run.run_id}",
        "",
        packet.executive_read.plain_read,
    ]
    if packet.quality.known_failures:
        lines.extend(["", "Failure detail:"])
        lines.extend(f"- {failure}" for failure in packet.quality.known_failures)
    return "\n".join(lines)


def _plane_lines(packet: ArgusIntelligencePacket) -> list[str]:
    if not packet.evidence_planes:
        return []
    lines = ["", "Evidence planes:"]
    for plane in packet.evidence_planes:
        lines.append(f"- {plane.plane.replace('_', ' ').title()}: {plane.summary}")
    return lines


__all__ = ["render_daily_packet_brief_html", "render_weekly_packet_brief_html"]
