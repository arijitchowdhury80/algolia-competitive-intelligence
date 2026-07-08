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

# Optional: prescriptions render as a "YOUR PLAYS" section when supplied.
# Imported lazily-by-name only (cios.prescribe -> cios.brain.types, not the
# reverse) so this stays a one-way dependency; cios.prescribe never imports
# this module.
try:  # pragma: no cover - import guard, both sides always available in prod
    from cios.prescribe.types import Prescription
except ImportError:  # pragma: no cover
    Prescription = None  # type: ignore[assignment,misc]

_URGENCY_ORDER = {"act_now": 0, "this_week": 1, "this_month": 2}
_URGENCY_LABEL = {"act_now": "act now", "this_week": "this week", "this_month": "this month"}


def _format_prescription_block(p) -> list[str]:
    urgency = getattr(p.urgency_window, "value", p.urgency_window)
    team = getattr(p.team, "value", p.team)
    lines = [f"**{p.title}** ({team}, {_URGENCY_LABEL.get(urgency, urgency)})"]
    for step in p.play:
        lines.append(f"- {step}")
    lines.append(f"Expected effect: {p.expected_effect}")
    lines.append("")
    return lines


def _format_your_plays(prescriptions) -> list[str]:
    """Renders the "YOUR PLAYS" section: title, play steps, team, urgency
    window, sorted so act-now urgency prescriptions render first. Returns an
    empty list (no section) when there is nothing to show -- never a
    fabricated or empty-but-present heading."""
    if not prescriptions:
        return []
    ranked = sorted(
        prescriptions,
        key=lambda p: _URGENCY_ORDER.get(getattr(p.urgency_window, "value", p.urgency_window), 99),
    )
    lines = ["## YOUR PLAYS", ""]
    for p in ranked:
        lines.extend(_format_prescription_block(p))
    return lines


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
    prescriptions: Optional[list] = None,
) -> str:
    """Compose the markdown daily brief from a list of already-promoted,
    already-vetted Signal objects (evidence-or-silence, decision-layer-not-
    feed already enforced upstream by the Synthesizer). Returns a succinct
    markdown string, not a data dump.

    `prescriptions` is optional (cios.prescribe.types.Prescription list): when
    supplied and non-empty, a "YOUR PLAYS" section renders after ACTIONS BY
    TEAM, sorted act-now urgency first (see _format_your_plays)."""
    lines: list[str] = [f"## Your competitive picture -- {brief_date.isoformat()}", ""]

    if not signals:
        lines.append(f"Nothing material for {tenant_name} in the last 24 hours.")
        plays_lines = _format_your_plays(prescriptions)
        if not plays_lines:
            return "\n".join(lines)
        lines.append("")
        lines.extend(plays_lines)
        return "\n".join(lines).rstrip() + "\n"

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

    plays_lines = _format_your_plays(prescriptions)
    if plays_lines:
        lines.extend(plays_lines)

    if dashboard_url:
        lines.append(f"[View on the dashboard]({dashboard_url})")

    return "\n".join(lines).rstrip() + "\n"
