"""Tests for markdown -> Telegram HTML rendering: injection-safe escaping,
supported tag rendering, and section-boundary splitting at the 4096 limit.
"""

from __future__ import annotations

from cios.delivery.telegram_format import (
    TELEGRAM_HTML_LIMIT,
    markdown_to_telegram_html,
    render_brief_html,
    split_on_sections,
)


def test_bold_italic_code_and_links_render_as_safe_tags():
    out = markdown_to_telegram_html("**bold** and *italic* and `code` and [link](https://x.com)")
    assert "<b>bold</b>" in out
    assert "<i>italic</i>" in out
    assert "<code>code</code>" in out
    assert '<a href="https://x.com">link</a>' in out


def test_script_injection_in_content_arrives_escaped_not_as_a_tag():
    out = markdown_to_telegram_html("<script>alert(1)</script>")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_ampersand_and_angle_brackets_are_escaped():
    out = markdown_to_telegram_html("A vs B & 3 < 5")
    assert "&amp;" in out
    assert "&lt;" in out
    assert "<" not in out.replace("&lt;", "")


def test_link_url_with_quote_is_escaped_in_href():
    out = markdown_to_telegram_html('[click](https://x.com/"onmouseover="alert(1))')
    assert "&quot;" in out or "&#34;" in out


def test_render_brief_html_includes_title_and_dashboard_link():
    out = render_brief_html("Daily Brief", "Coveo shipped a feature.", dashboard_url="https://dash.example.com")
    assert "<b>Daily Brief</b>" in out
    assert 'href="https://dash.example.com"' in out


def test_split_on_sections_respects_limit():
    body = "\n\n".join([f"Section {i} " + ("x" * 200) for i in range(60)])
    chunks = split_on_sections(body, limit=1000)
    assert all(len(c) <= 1000 for c in chunks)
    assert "".join(chunks).replace("", "") != ""


def test_split_on_sections_single_chunk_when_under_limit():
    body = "short brief"
    chunks = split_on_sections(body)
    assert chunks == [body]


def test_split_on_sections_hard_splits_a_single_oversized_block():
    block = "x" * (TELEGRAM_HTML_LIMIT + 500)
    chunks = split_on_sections(block, limit=TELEGRAM_HTML_LIMIT)
    assert len(chunks) == 2
    assert all(len(c) <= TELEGRAM_HTML_LIMIT for c in chunks)
