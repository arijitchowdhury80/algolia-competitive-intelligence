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
from datetime import date
from pathlib import Path

import pytest

from cios.dashboard.cockpit_renderer import _truncate, render_cockpit_html
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


def _row_id(card, fallback_index: int) -> str:
    """Row id for the competitor GROUP a card's own delta belongs to (the
    barometer is one row per competitor since the grouping fix -- the row id
    is keyed off the group's top-scoring signal's delta_id)."""
    return f"competitor-{card.competitor_id}-{card.delta_id if card.delta_id is not None else fallback_index}"


def _make_card(**overrides):
    from cios.dashboard.types import CompetitorSignalCard

    base = dict(
        competitor_id=1,
        competitor_name="AWS",
        attention_score=50.0,
        attention_level=AttentionLevel.MONITOR,
        action_cue="Monitor: no action yet, keep this on the radar.",
        top_signal_headline="AWS shipped a minor update.",
        what_changed="AWS shipped a minor update.",
        why_it_matters="Low materiality.",
        evidence_ids=["https://example.com/aws"],
        delta_id=1,
    )
    base.update(overrides)
    return CompetitorSignalCard(**base)


def test_barometer_is_one_row_per_competitor_fixture(state: DashboardState) -> None:
    # Fixture ships 3 distinct Coveo signals (competitor_id=3, delta_id
    # 230/231/232) that never merged in the builder's near-duplicate
    # dedup because the underlying text differs -- the barometer must still
    # collapse them into a single Coveo row, not render 3 rows for Coveo.
    assert len({c.competitor_id for c in state.competitor_cards}) == 1
    assert len(state.competitor_cards) == 3
    html_out = render_cockpit_html(state)
    assert html_out.count('class="competitor-name">Coveo<') == 1
    assert html_out.count('id="competitor-3-') == 1


def test_barometer_row_uses_max_score_and_top_cue(state: DashboardState) -> None:
    html_out = render_cockpit_html(state)
    top = state.competitor_cards[0]  # highest attention_score (75.0, act_now)
    row_start = html_out.index(f'id="{_row_id(top, 0)}"')
    row_end = html_out.index("</details>", row_start)
    row_html = html_out[row_start:row_end]
    assert f'style="width:{top.attention_score:g}%"' in row_html
    assert "action-act" in html_out[max(0, row_start - 80) : row_start]
    # Subtitle is the top (highest-scoring) signal's action cue, not a
    # concatenation or the lowest-scoring signal's.
    assert _truncate(top.action_cue, 42) in row_html or top.action_cue[:20] in row_html


def test_barometer_proof_shows_top_two_signals_not_all_three(state: DashboardState) -> None:
    html_out = render_cockpit_html(state)
    top, second, third = state.competitor_cards
    row_start = html_out.index(f'id="{_row_id(top, 0)}"')
    row_end = html_out.index("</details>", row_start)
    row_html = html_out[row_start:row_end]
    assert html.escape(top.why_it_matters or "") in row_html
    assert html.escape(second.why_it_matters or "") in row_html
    assert html.escape(third.why_it_matters or "") not in row_html


def test_barometer_ranks_multiple_competitors_by_max_score() -> None:
    # Cards arrive already materiality-ranked (the state builder's job, not
    # the renderer's -- see module docstring), so this fixture is supplied
    # in the same globally-sorted-desc order build() would produce.
    cards = [
        _make_card(competitor_id=2, competitor_name="Elastic", attention_score=90.0,
                   attention_level=AttentionLevel.ACT_NOW, delta_id=20),
        _make_card(competitor_id=1, competitor_name="AWS", attention_score=40.0,
                   attention_level=AttentionLevel.MONITOR, delta_id=10),
        _make_card(competitor_id=2, competitor_name="Elastic", attention_score=20.0,
                   attention_level=AttentionLevel.NORMAL, delta_id=21),
    ]
    state = DashboardState(tenant_id=1, cadence="daily", competitor_cards=cards)
    html_out = render_cockpit_html(state)
    elastic_pos = html_out.index('class="competitor-name">Elastic<')
    aws_pos = html_out.index('class="competitor-name">AWS<')
    assert elastic_pos < aws_pos, "Elastic (max score 90) must rank above AWS (score 40)"
    # Only one Elastic row, even though it has two signals.
    assert html_out.count('class="competitor-name">Elastic<') == 1


def test_attention_level_maps_to_design_color_classes(state: DashboardState) -> None:
    html_out = render_cockpit_html(state)
    # Fixture's single Coveo row must carry its top (highest-scoring)
    # signal's attention level -- act_now, not the lowest-scoring signal's.
    top = state.competitor_cards[0]
    row_marker = f'id="{_row_id(top, 0)}"'
    row_start = html_out.index(row_marker)
    row_html = html_out[max(0, row_start - 80) : row_start]
    assert "action-act" in row_html


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
    # All 3 fixture cards are one Coveo group (barometer grouping fix) --
    # clear evidence on every member the row's proof actually shows (top 2)
    # so the fallback line is genuinely exercised, not masked by a sibling
    # signal's real evidence.
    for card in payload["competitor_cards"]:
        card["evidence_ids"] = []
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
    source_text = " ".join((top.top_signal_headline or top.what_changed or "").split())
    h1_start = html_out_1.index("<h1>")
    h1_end = html_out_1.index("</h1>")
    h1_text = html.unescape(html_out_1[h1_start + len("<h1>") : h1_end])
    # No mid-word ellipsis: the headline is a real prefix (or leading
    # clause) of the source text, never truncated with a trailing "…".
    assert "…" not in h1_text
    assert source_text.startswith(h1_text) or h1_text == source_text.split(".", 1)[0].strip()
    assert len(h1_text.split()) <= 9


def test_hero_headline_uses_top_signal_headline_not_what_changed() -> None:
    from cios.dashboard.types import CompetitorSignalCard

    card = _make_card(
        top_signal_headline="Elastic ships a nine word headline for the hero exactly.",
        what_changed="A completely different, much longer what_changed narrative that should not appear in the hero.",
    )
    state = DashboardState(tenant_id=1, cadence="daily", competitor_cards=[card])
    html_out = render_cockpit_html(state)
    h1_start = html_out.index("<h1>")
    h1_end = html_out.index("</h1>")
    h1_text = html.unescape(html_out[h1_start + len("<h1>") : h1_end])
    assert "what_changed narrative" not in h1_text
    assert h1_text.startswith("Elastic ships a nine word headline")


def test_hero_headline_caps_at_nine_words_no_mid_word_cut() -> None:
    card = _make_card(
        top_signal_headline=(
            "This headline definitely has way more than nine words in it "
            "and should be cut cleanly at a word boundary without any ellipsis"
        ),
        what_changed=None,
    )
    state = DashboardState(tenant_id=1, cadence="daily", competitor_cards=[card])
    html_out = render_cockpit_html(state)
    h1_start = html_out.index("<h1>")
    h1_end = html_out.index("</h1>")
    h1_text = html.unescape(html_out[h1_start + len("<h1>") : h1_end])
    assert len(h1_text.split()) == 9
    assert h1_text == "This headline definitely has way more than nine words"
    assert "…" not in h1_text


def test_brand_and_hero_images_are_inlined_not_broken(state: DashboardState) -> None:
    html_out = render_cockpit_html(state)
    # No reference to the mockup's own asset directory -- the rendered HTML
    # must be self-contained and not depend on docs/mockups/assets/ existing
    # alongside wherever it gets published.
    assert "assets/argus-logo-mark.png" not in html_out
    assert "assets/argus-search-intelligence-weekly.png" not in html_out
    assert 'class="sigil" src="data:image/png;base64,' in html_out
    assert 'src="data:image/jpeg;base64,' in html_out


def test_brief_link_falls_back_to_sibling_brief_html_when_published_today() -> None:
    state = _load_state()
    payload = state.model_dump(mode="json")
    payload["report_history"] = [{
        "report_id": 999,
        "report_date": date.today().isoformat(),
        "cadence": "daily",
        "title": "Argus daily brief",
        "summary": "summary",
        "status": "rendered",
        "html_path": None,  # runner does not populate reports.html_path today
    }]
    today_state = DashboardState.model_validate(payload)
    html_out = render_cockpit_html(today_state)
    assert '<a class="deep-link" href="./brief.html">Open full brief</a>' in html_out
    assert 'aria-disabled="true"' not in html_out


def test_brief_link_stays_no_brief_when_latest_report_is_not_today() -> None:
    state = _load_state()
    payload = state.model_dump(mode="json")
    payload["report_history"] = [{
        "report_id": 998,
        "report_date": "2020-01-01",
        "cadence": "daily",
        "title": "Argus daily brief",
        "summary": "summary",
        "status": "rendered",
        "html_path": None,
    }]
    stale_state = DashboardState.model_validate(payload)
    html_out = render_cockpit_html(stale_state)
    assert 'aria-disabled="true"' in html_out
    assert 'href="./brief.html"' not in html_out


# -- Bug 3: sources/bibliography accordion dedup -----------------------------


def test_bibliography_dedupes_duplicate_urls_preserving_first_occurrence() -> None:
    # Two signals for the SAME competitor group, one URL cited by both (e.g.
    # a competitor's page cited both as this cycle's top signal's evidence
    # and again as the second-ranked signal's evidence). The accordion must
    # cite it once, not once per signal that references it.
    dupe_url = "https://constructor.com/solutions/ai-shopping-agent"
    other_url = "https://constructor.com/blog/launch"
    cards = [
        _make_card(
            competitor_id=5, competitor_name="Constructor", attention_score=80.0,
            attention_level=AttentionLevel.ACT_NOW, delta_id=1,
            what_changed="Constructor launches an AI shopping agent.",
            why_it_matters="Direct overlap with our roadmap.",
            evidence_ids=[dupe_url, other_url],
        ),
        _make_card(
            competitor_id=5, competitor_name="Constructor", attention_score=60.0,
            attention_level=AttentionLevel.WATCH, delta_id=2,
            what_changed="Constructor reiterates the AI shopping agent in a case study.",
            why_it_matters="Same story resurfacing.",
            evidence_ids=[dupe_url],
        ),
    ]
    state = DashboardState(tenant_id=1, cadence="daily", competitor_cards=cards)
    html_out = render_cockpit_html(state)

    top = state.competitor_cards[0]
    row_start = html_out.index(f'id="{_row_id(top, 0)}"')
    row_end = html_out.index("</details>", row_start)
    row_html = html_out[row_start:row_end]

    # Each <li> cites the URL twice (href + anchor text), so one bibliography
    # entry means the URL string appears exactly twice in the row, not four
    # times (which would mean two separate <li> entries for it).
    assert row_html.count(dupe_url) == 2
    assert row_html.count(other_url) == 2
    assert row_html.count("<li>") == 2  # one entry per distinct URL, not per citing signal
