"""Tests for the HTML email digest renderer: escaping and template embedding."""

from __future__ import annotations

from cios.delivery.email_format import render_email_html


def test_renders_title_and_markdown_body():
    out = render_email_html("Weekly Readout", body_markdown="**Coveo** shipped a *feature*.")
    assert "Weekly Readout" in out
    assert "<strong>Coveo</strong>" in out
    assert "<em>feature</em>" in out


def test_script_injection_in_markdown_body_is_escaped():
    out = render_email_html("Brief", body_markdown="<script>alert(1)</script>")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_dashboard_link_included_when_provided():
    out = render_email_html("Brief", body_markdown="body", dashboard_url="https://dash.example.com")
    assert 'href="https://dash.example.com"' in out


def test_no_dashboard_link_when_not_provided():
    out = render_email_html("Brief", body_markdown="body")
    assert "View on the dashboard" not in out


def test_rendered_html_body_embedded_as_is_when_given():
    trusted_html = "<div class='report'>already rendered</div>"
    out = render_email_html("Brief", rendered_html_body=trusted_html)
    assert trusted_html in out
