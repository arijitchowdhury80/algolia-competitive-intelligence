"""Renders DashboardState into Arijit's existing ci.chowmes.com page design.

This module does NOT invent a new visual design. The markup, CSS classes, and
inline styles below are copied verbatim from the design contract at
docs/workspace/dashboard-reference/index.html (Arijit's own hand-built page,
mirrored from the live /tmp/dash-ui/public/index.html capture). This file
templates that page's sections with data pulled from a DashboardState -- it
does not add new visual language beyond the two additions the goal-spec calls
for explicitly: a build/system-status panel and a living-theses panel, both
built out of the SAME .panel / .quality-row / .mini-card / .pill visual
vocabulary already present in the reference page.

Sections carried over unchanged in structure:
  - topbar (eyebrow + h1 + meta)
  - hero (.hero) -- primary finding
  - competitor signal panel (.panel with .mini-grid / .mini-card) -- reuses
    the "Customer Proof Radar" pattern for competitor_cards
  - trust diagnostics side panel (.side-panel with .quality-list /
    .quality-row) -- reuses the "Can I trust this?" pattern for coverage
  - delivery status side panel -- reuses the "Telegram delivery" pattern

Sections added, in the same visual language:
  - living theses (.panel / .mini-grid / .mini-card)
  - build/system status (.side-panel / .quality-list / .quality-row)

All dynamic text is passed through html.escape() before being placed in
markup. No external JS or CSS is loaded; the page is self-contained.
"""

from __future__ import annotations

import html
from typing import Optional

from .types import AttentionLevel, DashboardState

_STYLE = """
    :root {
      --blue: #003dff; --ink: #06133f; --body: #2f374e; --muted: #68748c; --line: #d9e1ef;
      --canvas: #f6f8fc; --paper: #ffffff; --soft: #fbfcff; --blue-soft: #eef3ff;
      --green: #087f5b; --green-soft: #e9fbf3; --amber: #9a6700; --amber-soft: #fff5d6;
      --shadow: 0 12px 30px rgba(6, 19, 63, .08); --radius: 8px;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    * { box-sizing: border-box; }
    html, body { max-width: 100%; overflow-x: hidden; }
    body { margin: 0; background: var(--canvas); color: var(--body); }
    a { color: var(--blue); font-weight: 760; text-decoration: none; overflow-wrap: anywhere; }
    a:hover { text-decoration: underline; }
    h1, h2, h3, p { margin-top: 0; }
    h1 { margin-bottom: 8px; color: var(--ink); font-size: clamp(34px, 5vw, 58px); line-height: 1; letter-spacing: 0; }
    h2 { margin-bottom: 12px; color: var(--ink); font-size: 22px; line-height: 1.2; letter-spacing: 0; }
    h3 { margin-bottom: 8px; color: var(--ink); font-size: 17px; line-height: 1.25; letter-spacing: 0; }
    p { margin-bottom: 12px; line-height: 1.5; }
    .shell { width: min(1280px, 100%); margin: 0 auto; padding: 28px; }
    .topbar { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 20px; align-items: end; margin-bottom: 22px; padding-bottom: 18px; border-bottom: 1px solid var(--line); }
    .eyebrow { color: var(--blue); font-size: 12px; font-weight: 900; letter-spacing: .09em; text-transform: uppercase; }
    .meta { color: var(--muted); font-size: 13px; line-height: 1.5; text-align: right; }
    .layout { display: grid; grid-template-columns: minmax(0, 1fr) 340px; gap: 18px; align-items: start; }
    .main { display: grid; gap: 18px; min-width: 0; }
    .side { position: sticky; top: 18px; display: grid; gap: 14px; min-width: 0; }
    .hero, .panel, .side-panel, .report-row { border: 1px solid var(--line); border-radius: var(--radius); background: var(--paper); box-shadow: var(--shadow); }
    .hero { padding: 24px; border-top: 5px solid var(--blue); }
    .answer { margin-bottom: 14px; color: var(--ink); font-size: clamp(24px, 3vw, 38px); line-height: 1.08; font-weight: 900; letter-spacing: 0; overflow-wrap: anywhere; }
    .panel, .side-panel { padding: 20px; }
    .section-head { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; margin-bottom: 14px; }
    .mini-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
    .mini-card, .empty { border: 1px solid var(--line); border-radius: var(--radius); background: var(--soft); padding: 12px; }
    .mini-card strong { display: inline-flex; width: fit-content; margin-bottom: 8px; border-radius: var(--radius); background: var(--blue-soft); color: var(--blue); padding: 5px 8px; font-size: 11px; line-height: 1; }
    .mini-card p { margin: 0 0 8px; color: var(--ink); font-size: 14px; line-height: 1.45; font-weight: 680; }
    .empty { color: var(--muted); font-size: 13px; }
    .pill { min-height: 26px; display: inline-flex; align-items: center; border-radius: 999px; padding: 0 9px; font-size: 12px; font-weight: 850; white-space: nowrap; background: var(--blue-soft); color: var(--blue); }
    .pill.green { background: var(--green-soft); color: var(--green); }
    .pill.amber { background: var(--amber-soft); color: var(--amber); }
    .note { margin: 8px 0 0; color: var(--muted); font-size: 12px; line-height: 1.45; font-weight: 500; }
    .quality-list, .report-list { display: grid; gap: 9px; }
    .quality-row { display: grid; grid-template-columns: 28px minmax(0, 1fr); gap: 10px; border: 1px solid var(--line); border-radius: var(--radius); background: var(--soft); padding: 10px; }
    .mark { width: 28px; height: 28px; display: grid; place-items: center; border-radius: 50%; background: var(--green-soft); color: var(--green); font-weight: 900; }
    .mark.warn { background: var(--amber-soft); color: var(--amber); }
    .quality-row strong { display: block; color: var(--ink); font-size: 14px; }
    .quality-row span { display: block; margin-top: 3px; color: var(--muted); font-size: 12px; line-height: 1.35; }
    .report-row { display: grid; grid-template-columns: 92px minmax(0, 1fr) auto; gap: 12px; align-items: start; padding: 12px; box-shadow: none; }
    .report-row time { color: var(--muted); font-size: 12px; font-weight: 850; }
    .report-row b { display: block; color: var(--ink); margin-bottom: 3px; }
    .report-row span { display: block; color: var(--muted); font-size: 12px; line-height: 1.35; }
    details { margin-top: 12px; border-top: 1px solid var(--line); padding-top: 10px; }
    summary { width: fit-content; color: var(--blue); cursor: pointer; font-weight: 850; }
    @media (max-width: 980px) { .layout { grid-template-columns: 1fr; } .side { position: static; } }
    @media (max-width: 680px) { .shell { padding: 16px; } .topbar, .report-row { grid-template-columns: 1fr; } .meta { text-align: left; } .mini-grid { grid-template-columns: 1fr; } }
"""

_ATTENTION_PILL_CLASS = {
    AttentionLevel.NORMAL: "pill green",
    AttentionLevel.MONITOR: "pill",
    AttentionLevel.WATCH: "pill amber",
    AttentionLevel.ACT_NOW: "pill amber",
}


def _e(value: Optional[object]) -> str:
    """Escape any dynamic value for safe HTML placement. None becomes ''."""
    if value is None:
        return ""
    return html.escape(str(value))


def _hero_section(state: DashboardState) -> str:
    coverage = state.coverage
    quiet_eligible = coverage.is_quiet_eligible

    if state.is_quiet:
        headline = "Quiet today" if state.cadence == "daily" else "Quiet this period"
        checked = len(coverage.lanes)
        ran_ok = sum(1 for l in coverage.lanes if l.ran and l.error is None)
        body = (
            f"No material public competitive signal was stored in the ledger this cycle. "
            f"Collection checked {checked} of {checked} enabled lanes; {ran_ok} succeeded, "
            f"{checked - ran_ok} failed. Treat this as a quiet cycle: collection completed "
            f"and the false-negative audit came back clean."
        )
        why = "No action changes. The system checked public sources and found no material semantic delta."
        response = "No immediate competitive action is recommended. Maintain the watchlist and wait for a material semantic delta before changing sales, PMM, or product guidance."
    elif not quiet_eligible:
        headline = "Coverage incomplete"
        failed = ", ".join(coverage.failed_lanes) or "unknown lane(s)"
        body = (
            f"Coverage is not strong enough to call this cycle quiet. Lane(s) that did not run "
            f"cleanly: {_e(failed)}. False-negative audit status: {_e(coverage.false_negative_audit_status) or 'unknown'}."
        )
        why = "An incomplete-coverage cycle cannot be reported as green-quiet, even with zero surfaced signals."
        response = "Re-run or investigate the failed lane(s) before treating this cycle as verified-quiet."
    else:
        top = state.competitor_cards[0] if state.competitor_cards else None
        headline = _e(top.competitor_name) if top else "Signal detected"
        body = _e(state.argus_read.useful_truth) or _e(top.top_signal_headline if top else None) or "A material competitive signal was recorded this cycle."
        why = _e(state.argus_read.why_it_matters) or _e(top.why_it_matters if top else None) or ""
        response = _e(state.argus_read.recommended_move) or _e(top.recommended_action if top else None) or ""
        return f"""
        <section class="hero" id="primary-daily" aria-labelledby="daily-title">
          <div class="eyebrow">Primary finding</div>
          <h2 class="answer" id="daily-title">{headline}</h2>
          <h3>What happened</h3>
          <p>{body}</p>
          <h3>Why it matters</h3>
          <p>{why or "No further context recorded."}</p>
          <h3>Recommended response</h3>
          <p>{response or "No recommended response recorded."}</p>
        </section>"""

    return f"""
        <section class="hero" id="primary-daily" aria-labelledby="daily-title">
          <div class="eyebrow">Primary finding</div>
          <h2 class="answer" id="daily-title">{_e(headline)}</h2>
          <h3>What happened</h3>
          <p>{body}</p>
          <h3>Why it matters</h3>
          <p>{_e(why)}</p>
          <h3>Recommended response</h3>
          <p>{_e(response)}</p>
        </section>"""


def _signal_cards_section(state: DashboardState) -> str:
    if not state.competitor_cards:
        cards_html = '<div class="empty">No material semantic delta is available right now.</div>'
    else:
        cards = []
        for card in state.competitor_cards:
            pill_class = _ATTENTION_PILL_CLASS.get(card.attention_level, "pill")
            evidence_links = "".join(
                f'<div><a href="{_e(eid)}">Evidence</a></div>' for eid in card.evidence_ids
            )
            owner_action = _e(card.action_cue)
            cards.append(f"""<div class="mini-card">
              <strong>{_e(card.competitor_name)} &middot; materiality {_e(round(card.materiality_score, 2)) if card.materiality_score is not None else _e(round(card.attention_score, 1))}</strong>
              <p>{_e(card.top_signal_headline) or _e(card.what_changed) or "No headline recorded."}</p>
              <div class="note">Action: {owner_action or "No action cue recorded."}</div>
              {evidence_links}
            </div>""")
        cards_html = f'<div class="mini-grid">{"".join(cards)}</div>'

    top_pill_class = _ATTENTION_PILL_CLASS.get(state.top_attention_level, "pill")
    return f"""
        <section class="panel" aria-labelledby="signals-title">
          <div class="section-head"><div><div class="eyebrow">Competitor attention barometer</div><h2 id="signals-title">Signal Cards</h2></div><span class="{top_pill_class}">{_e(state.top_attention_level.value)}</span></div>
          {cards_html}
        </section>"""


def _theses_section(state: DashboardState) -> str:
    if not state.theses:
        theses_html = '<div class="empty">No living thesis is currently tracked.</div>'
    else:
        items = []
        for thesis in state.theses:
            items.append(f"""<div class="mini-card">
              <strong>{_e(thesis.competitor_name) or "Competitor " + _e(thesis.competitor_id)} &middot; {_e(thesis.status)}</strong>
              <p>{_e(thesis.thesis)}</p>
              <div class="note">Supporting deltas: {_e(thesis.supporting_delta_count)} &middot; Contradicting: {_e(thesis.contradicting_delta_count)}{" &middot; confidence " + _e(thesis.confidence) if thesis.confidence is not None else ""}</div>
            </div>""")
        theses_html = f'<div class="mini-grid">{"".join(items)}</div>'

    return f"""
        <section class="panel" aria-labelledby="theses-title">
          <div class="section-head"><div><div class="eyebrow">Standing hypotheses</div><h2 id="theses-title">Living Theses</h2></div><span class="pill">Non-destructive</span></div>
          {theses_html}
        </section>"""


def _coverage_side_panel(state: DashboardState) -> str:
    coverage = state.coverage
    rows = []
    for lane in coverage.lanes:
        mark_class = "mark" if lane.ran and lane.error is None else "mark warn"
        symbol = "✓" if lane.ran and lane.error is None else "!"
        detail = _e(lane.error) if lane.error else "ran cleanly"
        rows.append(f"""<div class="quality-row"><div class="{mark_class}">{symbol}</div><div><strong>{_e(lane.lane)}</strong><span>{detail}</span></div></div>""")

    audit_status = coverage.false_negative_audit_status
    audit_ok = audit_status == "clean"
    audit_class = "mark" if audit_ok else "mark warn"
    audit_symbol = "✓" if audit_ok else "!"
    rows.append(f"""<div class="quality-row"><div class="{audit_class}">{audit_symbol}</div><div><strong>False-negative audit</strong><span>{_e(audit_status) or "unknown"}</span></div></div>""")

    if coverage.missing_source_families:
        rows.append(
            f"""<div class="quality-row"><div class="mark warn">!</div><div><strong>Missing source families</strong><span>{_e(", ".join(coverage.missing_source_families))}</span></div></div>"""
        )

    score = coverage.coverage_score
    score_note = f"Coverage score: {_e(round(score, 4))}" if score is not None else "Coverage score not computed."

    return f"""
        <section class="side-panel">
          <div class="eyebrow">Coverage-before-quiet</div>
          <h2>Data limits</h2>
          <div class="quality-list">
            {"".join(rows)}
          </div>
          <p class="note">{score_note}</p>
        </section>"""


def _run_health_side_panel(state: DashboardState) -> str:
    rh = state.run_health
    rows = [
        f"""<div class="quality-row"><div class="mark">&#9679;</div><div><strong>Run</strong><span>{_e(rh.run_id) or "unknown"} &middot; generated {_e(rh.generated_at) or "unknown"}</span></div></div>""",
        f"""<div class="quality-row"><div class="mark">&#9679;</div><div><strong>Model tier</strong><span>{_e(rh.model_tier) or "unknown"}</span></div></div>""",
        f"""<div class="quality-row"><div class="mark">&#9679;</div><div><strong>Delivery</strong><span>{_e(rh.delivery_status) or "unknown"}</span></div></div>""",
        f"""<div class="quality-row"><div class="mark">&#9679;</div><div><strong>Quality review</strong><span>{_e(rh.quality_review_status) or "unknown"}</span></div></div>""",
    ]
    return f"""
        <section class="side-panel">
          <div class="eyebrow">Trust bar</div>
          <h2>Run health</h2>
          <div class="quality-list">
            {"".join(rows)}
          </div>
        </section>"""


def _build_status_side_panel(state: DashboardState) -> str:
    bs = state.build_status
    if not bs.services:
        services_html = '<div class="empty">No service health reported for this build.</div>'
    else:
        rows = []
        for svc in bs.services:
            ok = svc.status == "ok"
            mark_class = "mark" if ok else "mark warn"
            symbol = "✓" if ok else "!"
            rows.append(f"""<div class="quality-row"><div class="{mark_class}">{symbol}</div><div><strong>{_e(svc.name)}</strong><span>{_e(svc.status)}{" · " + _e(svc.detail) if svc.detail else ""}</span></div></div>""")
        services_html = f'<div class="quality-list">{"".join(rows)}</div>'

    error_note = f'<p class="note">Last error: {_e(bs.last_error)}</p>' if bs.last_error else ""
    return f"""
        <section class="side-panel">
          <div class="eyebrow">System status</div>
          <h2>Build health</h2>
          <p class="note">Build {_e(bs.build_id) or "unknown"} &middot; {_e(bs.environment) or "unknown"} &middot; sha {_e(bs.git_sha) or "unknown"}</p>
          {services_html}
          {error_note}
        </section>"""


def render_dashboard_html(state: DashboardState) -> str:
    """Renders `state` into Arijit's existing dashboard page design.

    Reuses the exact CSS and section scaffolding from
    docs/workspace/dashboard-reference/index.html. All dynamic text is
    html.escape()'d before insertion. The output is a single self-contained
    HTML document with no external JS or CSS.
    """
    generated_at = _e(state.generated_at)
    cadence_label = _e(state.cadence)
    tenant_label = _e(state.tenant_id)

    body_sections = "\n".join(
        [
            _hero_section(state),
            _signal_cards_section(state),
            _theses_section(state),
        ]
    )

    side_sections = "\n".join(
        [
            _coverage_side_panel(state),
            _run_health_side_panel(state),
            _build_status_side_panel(state),
        ]
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <base target="_blank">
  <title>Algolia Competitive Intelligence</title>
  <style>{_STYLE}</style>
</head>
<body>
  <main class="shell">
    <header class="topbar">
      <div><div class="eyebrow">Algolia competitive intelligence</div><h1>Competitive Brief</h1></div>
      <div class="meta">
        <div>Tenant {tenant_label} &middot; {cadence_label} cadence</div>
        <div>Generated from CI-OS dashboard state, not mock data</div>
        <div>Last generated at {generated_at}</div>
      </div>
    </header>
    <div class="layout">
      <div class="main">
        {body_sections}
      </div>
      <aside class="side" aria-label="Data reliability">
        {side_sections}
      </aside>
    </div>
  </main>
</body>
</html>
"""
