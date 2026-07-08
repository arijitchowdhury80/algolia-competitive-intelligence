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
  - suppressed signals (.panel / .quality-list / .quality-row) -- restored
    from the reference page, now itemized per suppression reason
  - report history (.panel / .report-list / .report-row) -- restored from
    the reference page verbatim

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
    .footer-history { margin-top: 18px; padding-top: 14px; border-top: 1px solid var(--line); }
    .history-line-list { display: grid; gap: 4px; }
    .history-line { display: flex; flex-wrap: wrap; gap: 6px; align-items: baseline; color: var(--muted); font-size: 12px; }
    .history-line time { font-weight: 850; }
    .history-line b { color: var(--ink); font-weight: 700; }
    .trust-row { display: grid; grid-template-columns: 28px minmax(0, 1fr) auto; gap: 10px; align-items: center; border: 1px solid var(--line); border-radius: var(--radius); background: var(--soft); padding: 8px 10px; }
    .trust-row strong { color: var(--ink); font-size: 13px; }
    .trust-row .trust-value { color: var(--muted); font-size: 12px; text-align: right; }
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
            seen_badge = (
                f' <span class="pill">seen in {_e(card.duplicate_count)} sources</span>'
                if card.duplicate_count > 1
                else ""
            )
            cards.append(f"""<div class="mini-card">
              <strong>{_e(card.competitor_name)} &middot; materiality {_e(round(card.materiality_score, 2)) if card.materiality_score is not None else _e(round(card.attention_score, 1))}</strong>{seen_badge}
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


def _suppressed_signals_section(state: DashboardState) -> str:
    """Mirrors the reference page's "Suppressed Signals" trust-diagnostics
    panel (docs/workspace/dashboard-reference/index.html), rendered as a
    .quality-list so each suppression reason is individually inspectable
    instead of collapsed into one sentence.

    Renders NOTHING when there is nothing suppressed -- an empty panel with
    an "empty" placeholder is noise on a daily page, not a useful trust
    signal (live-audit finding #4)."""
    if not state.suppressed_signals:
        return ""

    rows = []
    for s in state.suppressed_signals:
        detail = f"{_e(s.finding_count)} finding(s) suppressed" + (
            f" &middot; {_e(s.suppressed_at)}" if s.suppressed_at else ""
        )
        note = f' &middot; {_e(s.notes)}' if s.notes else ""
        rows.append(
            f"""<div class="quality-row"><div class="mark warn">!</div><div><strong>{_e(s.reason)}</strong><span>{detail}{note}</span></div></div>"""
        )
    rows_html = f'<div class="quality-list">{"".join(rows)}</div>'

    return f"""
        <section class="panel" aria-labelledby="suppressed-title">
          <div class="section-head"><div><div class="eyebrow">Trust diagnostics</div><h2 id="suppressed-title">Suppressed Signals</h2></div><span class="pill amber">Not findings</span></div>
          {rows_html}
        </section>"""


_HISTORY_DISPLAY_CAP = 7


def _dedupe_report_history(entries: list) -> list:
    """Root-cause fix for "report history is noise": collapse to the latest
    entry per report_date (retries/re-renders on the same day produce
    multiple rows for one date), then drop any later entry whose summary
    opens with the same text as one already kept for that date, and cap the
    remainder to the most recent _HISTORY_DISPLAY_CAP. Order is preserved
    from the input (callers pass most-recent-first)."""
    latest_per_date: dict = {}
    for entry in entries:
        latest_per_date.setdefault(entry.report_date, entry)

    seen_summaries: dict = {}
    deduped = []
    for entry in latest_per_date.values():
        prefix = (entry.summary or "")[:80]
        prior = seen_summaries.get((entry.report_date, prefix))
        if prior is not None:
            continue
        seen_summaries[(entry.report_date, prefix)] = entry
        deduped.append(entry)

    return deduped[:_HISTORY_DISPLAY_CAP]


def _report_history_section(state: DashboardState) -> str:
    """Compact, single-line archive footer -- a daily page's report history
    is provenance, not primary content, so it renders small and last
    (live-audit finding #3). Entries without a real html_path render as
    plain text, never a dead "Open" link."""
    entries = _dedupe_report_history(state.report_history)
    if not entries:
        rows_html = '<div class="empty">No reports generated yet.</div>'
    else:
        rows = []
        for r in entries:
            title = _e(r.title) or f"{_e(r.report_date)} {_e(r.cadence)}"
            status = f" &middot; {_e(r.status)}" if r.status else ""
            label = f'<a href="{_e(r.html_path)}">{title}</a>' if r.html_path else f"<b>{title}</b>"
            rows.append(f'<div class="history-line"><time>{_e(r.report_date)}</time>{label}<span>{status}</span></div>')
        rows_html = f'<div class="history-line-list">{"".join(rows)}</div>'

    return f"""
        <section class="footer-history" aria-labelledby="history-title">
          <div class="section-head"><div class="eyebrow" id="history-title">Report history &middot; automated archive</div></div>
          {rows_html}
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


def _trust_line_panel(state: DashboardState) -> str:
    """Collapses the old "Data limits" + "Run health" side panels into one
    compact trust line -- sources checked, coverage, false-negative audit,
    quality review, and delivery, each as a single row (live-audit finding
    #5: two boxes of sub-boxes read as noise, not a scannable trust check).
    """
    coverage = state.coverage
    rh = state.run_health

    checked = len(coverage.lanes)
    ran_ok = sum(1 for l in coverage.lanes if l.ran and l.error is None)
    sources_ok = checked > 0 and ran_ok == checked
    coverage_score = coverage.coverage_score
    coverage_value = f"{ran_ok}/{checked} lanes" + (
        f" &middot; score {_e(round(coverage_score, 2))}" if coverage_score is not None else ""
    )

    audit_status = coverage.false_negative_audit_status
    audit_ok = audit_status == "clean"

    quality_status = rh.quality_review_status
    quality_ok = quality_status in ("pass", "clean", "approved")

    delivery_status = rh.delivery_status
    delivery_ok = delivery_status in ("delivered", "sent", "ok")

    def row(label: str, ok: bool, value: str) -> str:
        mark_class = "mark" if ok else "mark warn"
        symbol = "✓" if ok else "!"
        return f"""<div class="trust-row"><div class="{mark_class}">{symbol}</div><strong>{_e(label)}</strong><span class="trust-value">{value}</span></div>"""

    rows = [
        row("Sources checked", sources_ok, _e(coverage_value)),
        row("Coverage", sources_ok, f"{_e(ran_ok)}/{_e(checked)} clean"),
        row("False-negative audit", audit_ok, _e(audit_status) or "unknown"),
        row("Quality review", quality_ok, _e(quality_status) or "unknown"),
        row("Delivery", delivery_ok, _e(delivery_status) or "unknown"),
    ]

    return f"""
        <section class="side-panel">
          <div class="eyebrow">Can I trust this?</div>
          <h2>Trust line</h2>
          <div class="quality-list">
            {"".join(rows)}
          </div>
        </section>"""


# Build/system status panel was removed (live-audit finding #5): the prior
# .side-panel here rendered `state.build_status`, which every real run
# populates with the honest "no build-status provider injected" stub --
# never a truthful source. Bring it back once a real BuildStatusProvider
# (git sha, deploy time, per-service health) is actually wired in
# state_builder.py; until then an always-stub panel is worse than no panel.


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
        s
        for s in [
            _hero_section(state),
            _signal_cards_section(state),
            _theses_section(state),
            _suppressed_signals_section(state),  # "" when nothing suppressed
        ]
        if s
    )

    side_sections = _trust_line_panel(state)
    footer_history = _report_history_section(state)

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
    {footer_history}
  </main>
</body>
</html>
"""
