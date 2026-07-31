"""Telegram HTML renderers for canonical Argus intelligence packets."""

from __future__ import annotations

from cios.intelligence.argus_packet import ArgusIntelligencePacket

from .telegram_format import render_brief_html


def render_daily_packet_brief_html(packet: ArgusIntelligencePacket, *, dashboard_url: str | None = None) -> str:
    """Render the daily mobile command brief from the canonical packet."""

    body = render_daily_packet_brief_markdown(packet)
    return render_brief_html(daily_packet_brief_title(packet), body, dashboard_url=dashboard_url)


def render_weekly_packet_brief_html(packet: ArgusIntelligencePacket, *, dashboard_url: str | None = None) -> str:
    """Render a weekly pattern brief from the canonical packet."""

    body = render_weekly_packet_brief_markdown(packet)
    return render_brief_html(weekly_packet_brief_title(packet), body, dashboard_url=dashboard_url)


def render_daily_packet_brief_markdown(packet: ArgusIntelligencePacket) -> str:
    """Render the daily mobile command brief body from the canonical packet."""

    return _failure_body(packet) if packet.status in {"failed", "blocked"} else _daily_body(packet)


def render_weekly_packet_brief_markdown(packet: ArgusIntelligencePacket) -> str:
    """Render the weekly pattern brief body from the canonical packet."""

    return _failure_body(packet) if packet.status in {"failed", "blocked"} else _weekly_body(packet)


def _daily_body(packet: ArgusIntelligencePacket) -> str:
    if packet.status in {"watch", "degraded", "stale"} and not packet.recommendations:
        return _watch_body(packet)

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
    if packet.cadence != "weekly" or packet.time_window.grain != "weekly":
        return _weekly_unavailable_body(packet)

    lines = [
        f"Weekly window: {packet.time_window.start_at.date()} to {packet.time_window.end_at.date()}",
        f"Run: {packet.run.run_id}",
        "",
        packet.executive_read.plain_read,
    ]
    movements = _unique_movements(packet)
    if movements:
        lines.extend(["", "Weekly pattern:"])
        for movement in movements[:3]:
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


def _watch_body(packet: ArgusIntelligencePacket) -> str:
    movement = _unique_movements(packet)[0] if _unique_movements(packet) else None
    blocked = packet.blocked_actions[0] if packet.blocked_actions else None
    next_action = packet.next_monitoring_actions[0] if packet.next_monitoring_actions else None
    next_check = _next_check_text(packet, blocked, next_action)

    lines = [
        "Argus read: Watch, no owner action",
        f"Run: {packet.run.run_id}",
        f"Window: {packet.time_window.label}",
    ]
    if movement is not None:
        lines.extend(["", f"Market movement: {movement.label}", movement.summary])
    else:
        lines.extend(["", packet.executive_read.plain_read])

    lines.extend(
        [
            "",
            (
                "Why it matters: Product and market-conversation proof exist, but no tenant-side demand "
                "evidence was captured, so Argus is watching instead of promoting an owner action."
            ),
        ]
    )
    if next_check:
        lines.extend(["", f"Next check: {next_check}"])
    lines.extend(_plane_status_line(packet))
    return "\n".join(lines)


def _weekly_unavailable_body(packet: ArgusIntelligencePacket) -> str:
    blocked = packet.blocked_actions[0] if packet.blocked_actions else None
    next_action = packet.next_monitoring_actions[0] if packet.next_monitoring_actions else None
    next_check = _next_check_text(packet, blocked, next_action)
    lines = [
        "Weekly synthesis unavailable",
        f"This is a {packet.cadence} packet, not a weekly synthesis packet.",
        f"Run: {packet.run.run_id}",
    ]
    if next_check:
        lines.extend(["", f"Next check: {next_check}"])
    else:
        lines.extend(["", "Next check: Build the weekly packet from multi-day movement memory before sending a weekly read."])
    return "\n".join(lines)


def daily_packet_brief_title(packet: ArgusIntelligencePacket) -> str:
    if packet.status in {"watch", "degraded", "stale"} and not packet.recommendations:
        return f"Argus read: watch, no owner action - {packet.tenant.display_name}"
    return packet.executive_read.headline


def weekly_packet_brief_title(packet: ArgusIntelligencePacket) -> str:
    if packet.cadence != "weekly" or packet.time_window.grain != "weekly":
        return f"Argus weekly synthesis unavailable - {packet.tenant.display_name}"
    return f"Argus weekly pattern brief - {packet.tenant.display_name}"


def _unique_movements(packet: ArgusIntelligencePacket):
    seen: set[tuple[str, str]] = set()
    out = []
    for movement in packet.market_movements:
        key = (movement.label.strip().lower(), movement.summary.strip().lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(movement)
    return out


def _next_check_text(packet: ArgusIntelligencePacket, blocked, next_action) -> str:
    movement = _unique_movements(packet)[0] if _unique_movements(packet) else None
    if movement is not None and _demand_evidence_blocks_action(packet, blocked):
        return f"Collect GA / Looker demand evidence for {movement.label} before promoting it into a recommendation."

    candidates = []
    if next_action is not None:
        candidates.append(getattr(next_action, "summary", ""))
        candidates.extend(getattr(next_action, "evidence_needed", []) or [])
    if blocked is not None:
        candidates.extend(getattr(blocked, "needed_evidence", []) or [])

    for candidate in candidates:
        text = str(candidate).strip()
        if not text:
            continue
        if _looks_like_blocker_explanation(text):
            continue
        return text

    subject = movement.label if movement is not None else "the selected movement"
    return f"Collect fresh Audience Demand evidence for {subject}."


def _demand_evidence_blocks_action(packet: ArgusIntelligencePacket, blocked) -> bool:
    blocker_text = str(getattr(blocked, "blocked_reason", "") if blocked else "").lower()
    if "tenant-side demand" in blocker_text or "audience demand" in blocker_text:
        return True
    return any(
        plane.plane == "audience_demand" and plane.status in {"missing", "partial", "stale", "failed"}
        for plane in packet.evidence_planes
    )


def _looks_like_blocker_explanation(text: str) -> bool:
    lowered = text.lower()
    return (
        "no tenant-side demand evidence" in lowered
        or "cannot promote" in lowered
        or "could not become" in lowered
        or "withheld" in lowered
    )


def _plane_status_line(packet: ArgusIntelligencePacket) -> list[str]:
    if not packet.evidence_planes:
        return []
    parts: list[str] = []
    for plane in packet.evidence_planes[:3]:
        label = plane.plane.replace("_", " ").title()
        count = plane.evidence_count or plane.signal_count
        count_suffix = f" ({count})" if count else ""
        parts.append(f"{label} {plane.status}{count_suffix}")
    return ["", f"Proof: {'; '.join(parts)}"] if parts else []


def _plane_lines(packet: ArgusIntelligencePacket) -> list[str]:
    if not packet.evidence_planes:
        return []
    lines = ["", "Evidence planes:"]
    for plane in packet.evidence_planes:
        lines.append(f"- {plane.plane.replace('_', ' ').title()}: {plane.summary}")
    return lines


__all__ = [
    "daily_packet_brief_title",
    "render_daily_packet_brief_html",
    "render_weekly_packet_brief_html",
    "render_daily_packet_brief_markdown",
    "render_weekly_packet_brief_markdown",
    "weekly_packet_brief_title",
]
