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
