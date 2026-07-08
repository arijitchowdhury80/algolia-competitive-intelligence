"""Tests for cockpit_renderer.render_brief_page (src/cios/dashboard/cockpit_renderer.py).

Regression coverage for the "unstyled raw markdown, literal **" bug: the
reader_text/doctrine brief must render through real markdown handling (no
raw '**' or leading '#' markers reaching the page) and must use the SAME
Luxury Editorial design tokens as the cockpit (render_cockpit_html), not a
different visual system.
"""

from __future__ import annotations

from cios.dashboard.cockpit_renderer import render_brief_page

SAMPLE_BRIEF_MD = """# Your competitive picture

## WHAT HAPPENED
Constructor.io **shipped** a new semantic ranking feature this week.
See the announcement at https://constructor.io/blog/semantic-ranking for details.

## WHERE TO PAY ATTENTION
Their pricing page now emphasizes **AI-native search** as a category term.

## YOUR PLAYS
Brief sales on the positioning shift before the next call.
"""


def test_renders_without_error() -> None:
    html_out = render_brief_page(SAMPLE_BRIEF_MD, "2026-07-08")
    assert "<!doctype html>" in html_out.lower()
    assert "</html>" in html_out


def test_no_raw_markdown_markers_survive() -> None:
    html_out = render_brief_page(SAMPLE_BRIEF_MD, "2026-07-08")
    # The exact bug being fixed: literal ** must never reach output.
    assert "**" not in html_out
    # Isolate the rendered brief body (the reused cockpit CSS legitimately
    # contains lines starting with "#" -- id selectors, hex colors -- so the
    # leading-"#" check is scoped to the .brief-body markup, not the page).
    body_start = html_out.index('<div class="brief-body">')
    body_end = html_out.index("</div>", html_out.index("</div>", body_start) + 1)
    body_markup = html_out[body_start:body_end]
    content_lines = [line.strip() for line in body_markup.splitlines() if line.strip()]
    assert not any(line.startswith("#") for line in content_lines)


def test_headers_and_bold_render_as_real_tags() -> None:
    html_out = render_brief_page(SAMPLE_BRIEF_MD, "2026-07-08")
    assert "<h1>Your competitive picture</h1>" in html_out
    assert "<h2>WHAT HAPPENED</h2>" in html_out
    assert "<strong>shipped</strong>" in html_out
    assert "<strong>AI-native search</strong>" in html_out


def test_evidence_url_renders_as_link() -> None:
    html_out = render_brief_page(SAMPLE_BRIEF_MD, "2026-07-08")
    assert '<a href="https://constructor.io/blog/semantic-ranking"' in html_out


def test_design_tokens_match_cockpit() -> None:
    """Regression guard: the brief must share the cockpit's Luxury Editorial
    tokens (same _STYLE block), not a bespoke design."""
    html_out = render_brief_page(SAMPLE_BRIEF_MD, "2026-07-08")
    assert '--font-display: "Playfair Display", Georgia, serif;' in html_out
    assert "--gold: #d4af37;" in html_out
    assert "Playfair+Display" in html_out


def test_empty_reader_text_is_honest_not_broken() -> None:
    html_out = render_brief_page("", "2026-07-08")
    assert "No brief content is available" in html_out
    assert "**" not in html_out


def test_date_label_present() -> None:
    html_out = render_brief_page(SAMPLE_BRIEF_MD, "2026-07-08")
    assert "2026-07-08" in html_out


# ---------------------------------------------------------------------------
# render_brief_page_from_state: the state-first brief (P0 punch list
# 2026-07-08). Cards come from the DEDUPED DashboardState (never the raw
# reader_text signal list), are capped and ranked, theses render as a
# visually distinct "Living Theses" section, and the page always carries a
# back-navigation link to the cockpit.
# ---------------------------------------------------------------------------

from cios.dashboard.cockpit_renderer import render_brief_page_from_state
from cios.dashboard.types import (
    AttentionLevel,
    CompetitorSignalCard,
    DashboardState,
    LivingThesis,
    PrescriptionSummary,
)


def _card(i: int, *, name: str | None = None, dup: int = 1) -> CompetitorSignalCard:
    return CompetitorSignalCard(
        competitor_id=i,
        competitor_name=name or f"Competitor {i}",
        attention_score=90.0 - i,
        attention_level=AttentionLevel.WATCH,
        action_cue=f"Watch launch {i}",
        top_signal_headline=f"Headline {i}",
        what_changed=f"Change {i}",
        why_it_matters=f"Matters {i}",
        recommended_action=f"Act on {i}",
        materiality_score=0.9 - i * 0.05,
        duplicate_count=dup,
    )


def _state(cards: list, theses: list | None = None, plays: list | None = None) -> DashboardState:
    return DashboardState(
        tenant_id=1,
        cadence="daily",
        competitor_cards=cards,
        theses=theses or [],
        prescriptions=plays or [],
    )


def test_from_state_caps_cards_at_five_ranked() -> None:
    html_out = render_brief_page_from_state(_state([_card(i) for i in range(8)]), "2026-07-08")
    for i in range(5):
        assert f"Headline {i}" in html_out
    for i in range(5, 8):
        assert f"Headline {i}" not in html_out


def test_from_state_shows_merge_badge_for_deduped_card() -> None:
    html_out = render_brief_page_from_state(_state([_card(1, dup=3)]), "2026-07-08")
    assert "3 sources" in html_out


def test_from_state_card_vs_thesis_contract() -> None:
    thesis = LivingThesis(
        thesis_id=7, competitor_id=1, competitor_name="Constructor",
        thesis="Constructor is repositioning as AI-native search.",
        status="active", confidence=0.7,
        supporting_delta_count=4, contradicting_delta_count=1,
    )
    html_out = render_brief_page_from_state(_state([_card(1)], theses=[thesis]), "2026-07-08")
    # Distinct sections with distinct copy contracts.
    assert 'class="brief-cards"' in html_out
    assert 'class="brief-theses"' in html_out
    assert "Read daily" in html_out          # card contract: now + action
    assert "Read weekly" in html_out         # thesis contract: orient
    assert "Constructor is repositioning as AI-native search." in html_out
    assert "4 supporting" in html_out
    assert "1 contradicting" in html_out


def test_from_state_back_navigation_to_cockpit() -> None:
    html_out = render_brief_page_from_state(_state([_card(1)]), "2026-07-08")
    assert 'class="brief-backnav"' in html_out
    assert 'href="./"' in html_out


def test_from_state_plays_section() -> None:
    play = PrescriptionSummary(
        title="Publish comparison page", team="Marketing",
        play=["Draft page", "Brief SEO"], urgency_window="act_now",
        expected_effect="Blunt the launch narrative",
    )
    html_out = render_brief_page_from_state(_state([_card(1)], plays=[play]), "2026-07-08")
    assert "Publish comparison page" in html_out
    assert "act now" in html_out.lower()


def test_from_state_empty_is_honest_never_blue_template() -> None:
    html_out = render_brief_page_from_state(_state([]), "2026-07-08")
    assert "--gold: #d4af37;" in html_out         # Luxury Editorial tokens
    # Never the legacy blue template (its distinctive canvas/soft tokens).
    assert "#f6f8fc" not in html_out
    assert "#eef3ff" not in html_out
    assert "Algolia Competitive Intelligence" not in html_out
    assert "No material signals" in html_out
    assert 'class="brief-backnav"' in html_out


def test_from_state_uses_luxury_editorial_tokens() -> None:
    html_out = render_brief_page_from_state(_state([_card(1)]), "2026-07-08")
    assert '--font-display: "Playfair Display", Georgia, serif;' in html_out
    assert "Playfair+Display" in html_out
