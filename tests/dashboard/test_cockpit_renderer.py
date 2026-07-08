"""Tests for src/cios/dashboard/cockpit_renderer.py.

Loads a real Gate-7 rehearsal state JSON (same fixture the existing
html_renderer tests use) and adds fake prescriptions, since no
prescriptions repo is wired into production yet. Asserts Arijit's design
tokens (Playfair Display, gold/ink palette) are present verbatim, the
barometer preserves the builder's materiality ranking, role lenses filter
prescriptions by team, empty states are honest (not fabricated), and
dynamic content is escaped.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

import pytest

from cios.dashboard.cockpit_renderer import render_cockpit_html
from cios.dashboard.types import AttentionLevel, DashboardState

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_STATE_PATH = (
    REPO_ROOT / "docs" / "planning" / "gate7-rehearsal-runs" / "dashboard-state.v2.1.daily.json"
)

_FAKE_PRESCRIPTIONS = [
    {
        "title": "Publish the OpenSearch cost-vs-relevance comparison",
        "team": "Marketing",
        "play": ["Draft the piece", "Cite the pricing evidence", "Ship before next brief"],
        "urgency_window": "act_now",
        "expected_effect": "Reframes the pricing narrative before it hardens.",
        "evidence_urls": ["https://example.com/aws-pricing"],
    },
    {
        "title": "Prep the objection-handling one-pager",
        "team": "Content",
        "play": ["List likely objections", "Pair each with a proof point"],
        "urgency_window": "this_week",
        "expected_effect": "Sales stops improvising the response.",
        "evidence_urls": ["https://example.com/aws-pricing"],
    },
    {
        "title": "Brief sales on the AWS packaging shift",
        "team": "Sales Enablement",
        "play": ["Send a Slack summary", "Add a battlecard note"],
        "urgency_window": "this_week",
        "expected_effect": "No sales rep gets blindsided in a live deal.",
        "evidence_urls": ["https://example.com/aws-pricing"],
    },
    {
        "title": "Validate whether this is pricing or packaging",
        "team": "Product",
        "play": ["Pull the OpenSearch docs diff", "Confirm with a customer-facing engineer"],
        "urgency_window": "this_month",
        "expected_effect": "Removes ambiguity before roadmap gets involved.",
        "evidence_urls": ["https://example.com/aws-pricing"],
    },
]


def _load_state(*, with_prescriptions: bool = True) -> DashboardState:
    payload = json.loads(SAMPLE_STATE_PATH.read_text(encoding="utf-8"))
    payload.pop("schema_version", None)
    payload.pop("is_quiet", None)
    payload.pop("top_attention_level", None)
    if with_prescriptions:
        payload["prescriptions"] = _FAKE_PRESCRIPTIONS
    return DashboardState.model_validate(payload)


@pytest.fixture()
def state() -> DashboardState:
    return _load_state()


def test_renders_without_error(state: DashboardState) -> None:
    html_out = render_cockpit_html(state)
    assert "<!doctype html>" in html_out.lower()
    assert "</html>" in html_out


def test_design_tokens_present_verbatim(state: DashboardState) -> None:
    html_out = render_cockpit_html(state)
    # Luxury Editorial palette + typography from the mockup, copied verbatim.
    assert "--font-display: \"Playfair Display\", Georgia, serif;" in html_out
    assert "--gold: #d4af37;" in html_out
    assert "Playfair+Display" in html_out
    assert 'class="role-rail"' in html_out
    assert 'class="attention-board"' in html_out
    assert "The eye behind the lenses" in html_out


def test_self_contained_css_and_js_inline(state: DashboardState) -> None:
    html_out = render_cockpit_html(state)
    assert "<style>" in html_out and "</style>" in html_out
    assert "<script>" in html_out and "</script>" in html_out
    # No script/stylesheet loaded from this repo's own asset pipeline.
    assert "script src" not in html_out


def _row_id(card, index: int) -> str:
    return f"competitor-{card.competitor_id}-{card.delta_id if card.delta_id is not None else index}"


def test_barometer_preserves_materiality_ranking(state: DashboardState) -> None:
    html_out = render_cockpit_html(state)
    order = [
        html_out.index(f'id="{_row_id(card, i)}"')
        for i, card in enumerate(state.competitor_cards)
    ]
    assert order == sorted(order), "barometer rows must render in the builder's ranked order"


def test_attention_level_maps_to_design_color_classes(state: DashboardState) -> None:
    html_out = render_cockpit_html(state)
    level_to_class = {
        AttentionLevel.ACT_NOW: "action-act",
        AttentionLevel.WATCH: "action-watch",
        AttentionLevel.MONITOR: "action-monitor",
        AttentionLevel.NORMAL: "action-normal",
    }
    for i, card in enumerate(state.competitor_cards):
        row_marker = f'id="{_row_id(card, i)}"'
        row_start = html_out.index(row_marker)
        row_html = html_out[max(0, row_start - 80) : row_start]
        assert level_to_class[card.attention_level] in row_html


def test_role_lens_team_filtering(state: DashboardState) -> None:
    html_out = render_cockpit_html(state)
    marketing_start = html_out.index('id="role-marketing"')
    sales_start = html_out.index('id="role-sales"')
    product_start = html_out.index('id="role-product"')
    eye_start = html_out.index("The eye behind the lenses")

    marketing_html = html_out[marketing_start:sales_start]
    sales_html = html_out[sales_start:product_start]
    product_html = html_out[product_start:eye_start]

    # Marketing lens shows Marketing + Content team plays.
    assert "Publish the OpenSearch cost-vs-relevance comparison" in marketing_html
    assert "Prep the objection-handling one-pager" in marketing_html
    assert "Brief sales on the AWS packaging shift" not in marketing_html
    assert "Validate whether this is pricing or packaging" not in marketing_html

    # Sales lens shows only Sales Enablement plays.
    assert "Brief sales on the AWS packaging shift" in sales_html
    assert "Publish the OpenSearch cost-vs-relevance comparison" not in sales_html

    # Product lens shows only Product plays.
    assert "Validate whether this is pricing or packaging" in product_html
    assert "Brief sales on the AWS packaging shift" not in product_html


def test_lens_empty_state_is_honest_not_fabricated() -> None:
    state = _load_state(with_prescriptions=False)
    html_out = render_cockpit_html(state)
    assert html_out.count("No prescribed plays for this lens this cycle.") == 3


def test_eye_behind_the_lenses_uses_real_coverage_numbers(state: DashboardState) -> None:
    html_out = render_cockpit_html(state)
    # Sample fixture: 3 lanes, coverage_score 0.6667, exec_speech failed.
    assert "<strong>3</strong><span>active source lanes feeding the lenses</span>" in html_out
    assert "<strong>67%</strong>" in html_out
    assert "exec_speech" in html_out
    assert "<strong>0</strong><span>private connectors claimed or implied</span>" in html_out


def test_no_evidence_is_honest_not_fabricated() -> None:
    state = _load_state()
    payload = state.model_dump(mode="json")
    payload["competitor_cards"][0]["evidence_ids"] = []
    empty_evidence_state = DashboardState.model_validate(payload)
    html_out = render_cockpit_html(empty_evidence_state)
    assert "No evidence link on file for this signal." in html_out


def test_no_report_history_renders_honest_no_brief_state() -> None:
    state = _load_state()
    payload = state.model_dump(mode="json")
    payload["report_history"] = []
    no_history_state = DashboardState.model_validate(payload)
    html_out = render_cockpit_html(no_history_state)
    assert "No brief on file yet for this cycle." in html_out
    assert 'aria-disabled="true"' in html_out


def test_unescaped_injection_is_escaped() -> None:
    state = _load_state()
    payload = state.model_dump(mode="json")
    payload["competitor_cards"][0]["competitor_name"] = "<img src=x onerror=alert(2)>"
    payload["competitor_cards"][0]["what_changed"] = "<script>alert(1)</script>"
    payload["prescriptions"][0]["title"] = "<script>alert(3)</script>"
    injected_state = DashboardState.model_validate(payload)

    html_out = render_cockpit_html(injected_state)
    assert "<img src=x onerror=alert(2)>" not in html_out
    assert "<script>alert(1)</script>" not in html_out
    assert "<script>alert(3)</script>" not in html_out
    assert "&lt;img src=x onerror=alert(2)&gt;" in html_out


def test_hero_headline_is_deterministic_truncation_no_llm(state: DashboardState) -> None:
    html_out_1 = render_cockpit_html(state)
    html_out_2 = render_cockpit_html(state)
    assert html_out_1 == html_out_2

    top = state.competitor_cards[0]
    source_text = " ".join((top.what_changed or "").split())
    h1_start = html_out_1.index("<h1>")
    h1_end = html_out_1.index("</h1>")
    h1_text = html.unescape(html_out_1[h1_start + len("<h1>") : h1_end])
    assert source_text.startswith(h1_text.rstrip("…"))
