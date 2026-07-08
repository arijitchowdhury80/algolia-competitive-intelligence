"""Daily brief composer: turns a list of promoted Signal objects into the
doctrine-shaped markdown brief for the tenant's CMO/marketing leadership.

Doctrine (docs/planning/CI-OS-product-doctrine-2026-07-08.md):
  - Header: "Your competitive picture -- <date>"
  - WHAT HAPPENED (24h)
  - WHERE TO PAY ATTENTION TODAY (top signal gets the three-position framing:
    where the competitor is / where the tenant is / where they could go)
  - ACTIONS BY TEAM (grouped by team_to_involve)

Succinct, not a data dump. No em dashes. Zero Algolia (or any other fixed
domain) vocabulary -- tenant name and every signal come from the caller.

This module owns composition only. It does not decide delivery cadence or
touch ReportReadyEvent/commander -- whatever builds a ReportReadyEvent calls
this first to get markdown_body, then sets it on the event.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from .types import Signal


def _format_signal_line(signal: Signal) -> str:
    return f"- **{signal.headline}** ({signal.signal_type}): {signal.what_changed}"


def _format_top_signal(signal: Signal) -> list[str]:
    """The top signal gets the doctrine's three-position framing. We do not
    invent the framing text here (that is the synthesizer/LLM's job, guided
    by SYNTHESIS_SYSTEM rule 7); we surface what the signal already carries
    (why_it_matters / implication) under a heading that names the frame, so
    the reader sees it without the composer fabricating anything."""
    lines = [f"**{signal.headline}**", ""]
    lines.append(f"What changed: {signal.what_changed}")
    if signal.why_it_matters:
        lines.append(f"Why it matters (competitor position and what it implies for you): {signal.why_it_matters}")
    if signal.implication:
        lines.append(f"Where this could go next: {signal.implication}")
    lines.append(f"Recommended action: {signal.recommended_action} (route to: {signal.team_to_involve})")
    return lines


def compose_daily_brief(
    signals: list[Signal],
    tenant_name: str,
    brief_date: date,
    dashboard_url: Optional[str] = None,
) -> str:
    """Compose the markdown daily brief from a list of already-promoted,
    already-vetted Signal objects (evidence-or-silence, decision-layer-not-
    feed already enforced upstream by the Synthesizer). Returns a succinct
    markdown string, not a data dump."""
    lines: list[str] = [f"## Your competitive picture -- {brief_date.isoformat()}", ""]

    if not signals:
        lines.append(f"Nothing material for {tenant_name} in the last 24 hours.")
        return "\n".join(lines)

    ranked = sorted(signals, key=lambda s: s.materiality_score, reverse=True)
    top = ranked[0]

    lines.append("## WHAT HAPPENED (24h)")
    for s in ranked:
        lines.append(_format_signal_line(s))
    lines.append("")

    lines.append("## WHERE TO PAY ATTENTION TODAY")
    lines.extend(_format_top_signal(top))
    lines.append("")

    lines.append("## ACTIONS BY TEAM")
    by_team: dict[str, list[Signal]] = {}
    for s in ranked:
        by_team.setdefault(s.team_to_involve, []).append(s)
    for team in sorted(by_team):
        lines.append(f"**{team}**")
        for s in by_team[team]:
            lines.append(f"- {s.recommended_action} (re: {s.headline})")
        lines.append("")

    if dashboard_url:
        lines.append(f"[View on the dashboard]({dashboard_url})")

    return "\n".join(lines).rstrip() + "\n"
