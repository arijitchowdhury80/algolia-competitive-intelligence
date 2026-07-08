"""Marketing dashboard generator: renders a Prescription as a campaign
tracking view -- the prescription's plays as tracked initiatives, the
signals (evidence) behind them, and the urgency window -- as a self-
contained HTML page.

Purely deterministic (no model call): a Prescription is already the fully
decided, evidence-backed unit; this generator's only job is to lay it out.
Reuses the CSS custom-property / .panel / .quality-row / .mini-card
vocabulary from cios.dashboard.html_renderer so campaign views read as the
same visual system as the competitive dashboard, with brand tokens
substituted for Arijit's fixed palette. stdlib only, html.escape everything,
no external JS/CSS.
"""

from __future__ import annotations

import html
from typing import Optional

from .types import BrandTokens, CollateralAsset, CollateralKind, CollateralRequest, ReviewStatus

_URGENCY_LABEL = {
    "act_now": "Act now",
    "this_week": "This week",
    "this_month": "This month",
}


def _e(value: Optional[object]) -> str:
    if value is None:
        return ""
    return html.escape(str(value))


def _style(brand: BrandTokens) -> str:
    return f"""
    :root {{
      --brand-primary: {_e(brand.primary_color)};
      --brand-secondary: {_e(brand.secondary_color)};
      --brand-accent: {_e(brand.accent_color)};
      --line: #d9e1ef; --canvas: #f6f8fc; --paper: #ffffff; --soft: #fbfcff;
      font-family: {_e(brand.font_family)};
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: var(--canvas); color: var(--brand-secondary); font-family: inherit; }}
    .shell {{ max-width: 1100px; margin: 0 auto; padding: 28px 24px; }}
    .topbar {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 22px; padding-bottom: 16px; border-bottom: 1px solid var(--line); }}
    .brand {{ font-weight: 900; font-size: 18px; color: var(--brand-primary); }}
    h1 {{ margin: 0 0 6px; font-size: clamp(24px, 3vw, 36px); color: var(--brand-secondary); }}
    .panel {{ border: 1px solid var(--line); border-radius: 8px; background: var(--paper); padding: 20px; margin-bottom: 18px; box-shadow: 0 12px 30px rgba(6,19,63,.06); }}
    .pill {{ display: inline-flex; align-items: center; border-radius: 999px; padding: 4px 12px; font-size: 12px; font-weight: 850; background: var(--brand-accent); color: white; }}
    .initiative-list {{ display: grid; gap: 10px; }}
    .initiative-row {{ display: grid; grid-template-columns: 28px minmax(0, 1fr); gap: 10px; border: 1px solid var(--line); border-radius: 8px; background: var(--soft); padding: 12px; }}
    .step-index {{ width: 28px; height: 28px; display: grid; place-items: center; border-radius: 50%; background: var(--brand-primary); color: white; font-weight: 900; font-size: 13px; }}
    .signal-list {{ display: grid; gap: 6px; margin-top: 8px; }}
    .signal-list a {{ color: var(--brand-primary); font-size: 12px; overflow-wrap: anywhere; }}
    .empty {{ color: #68748c; font-size: 13px; }}
    """


def _initiatives_html(plays: list[str]) -> str:
    if not plays:
        return '<div class="empty">No tracked initiatives on this play.</div>'
    rows = []
    for idx, step in enumerate(plays, start=1):
        rows.append(
            f"""<div class="initiative-row"><div class="step-index">{idx}</div><div>{_e(step)}</div></div>"""
        )
    return f'<div class="initiative-list">{"".join(rows)}</div>'


def _signals_html(evidence_urls: list[str]) -> str:
    if not evidence_urls:
        return '<div class="empty">No supporting signal recorded.</div>'
    links = "".join(f'<a href="{_e(u)}">{_e(u)}</a>' for u in evidence_urls)
    return f'<div class="signal-list">{links}</div>'


class MarketingDashboardGenerator:
    """Deterministic campaign-view renderer over a Prescription. No model
    dependency -- the prescription is already decided; this only lays it out."""

    def generate(self, request: CollateralRequest) -> CollateralAsset:
        if request.kind is not CollateralKind.MARKETING_DASHBOARD:
            raise ValueError(
                f"MarketingDashboardGenerator only handles {CollateralKind.MARKETING_DASHBOARD}, "
                f"got {request.kind}"
            )
        prescription = request.prescription
        brand = request.brand
        urgency = _URGENCY_LABEL.get(prescription.urgency_window.value, prescription.urgency_window.value)
        evidence_urls = sorted(set(prescription.grounding.evidence_urls))

        html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_e(brand.company_name)} campaign: {_e(prescription.title)}</title>
  <style>{_style(brand)}</style>
</head>
<body>
  <main class="shell">
    <header class="topbar">
      <div class="brand">{_e(brand.company_name)}</div>
      <span class="pill">{_e(urgency)}</span>
    </header>
    <section class="panel">
      <h1>{_e(prescription.title)}</h1>
      <p>{_e(prescription.expected_effect)}</p>
    </section>
    <section class="panel">
      <h2>Tracked initiatives</h2>
      {_initiatives_html(prescription.play)}
    </section>
    <section class="panel">
      <h2>Signals behind this campaign</h2>
      {_signals_html(evidence_urls)}
    </section>
  </main>
</body>
</html>
"""

        return CollateralAsset(
            tenant_id=request.tenant_id,
            kind=CollateralKind.MARKETING_DASHBOARD,
            html=html_doc,
            sources=evidence_urls,
            prescription_title=prescription.title,
            review_status=ReviewStatus.DRAFT,
        )
