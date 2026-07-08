"""Tests for the daily brief composer (Signal list -> doctrine-shaped markdown)."""

from __future__ import annotations

from datetime import date

from cios.brain.brief import compose_daily_brief
from cios.brain.types import Signal


def _signal(
    headline: str = "Rival cuts entry price 20%",
    materiality_score: float = 0.8,
    team_to_involve: str = "Sales Enablement",
) -> Signal:
    return Signal(
        competitor_id=7,
        signal_type="pricing change",
        headline=headline,
        what_changed="entry tier dropped from 500 to 400",
        why_it_matters="undercuts the mid-market motion",
        implication="expect similar cuts on the next tier",
        recommended_action="Brief the field on the pricing shift.",
        owner="PMM",
        team_to_involve=team_to_involve,
        materiality_score=materiality_score,
        evidence_urls=["https://rival.com/pricing"],
    )


def test_empty_signals_produces_honest_quiet_brief() -> None:
    md = compose_daily_brief([], "Acme Corp", date(2026, 7, 8))
    assert "Your competitive picture" in md
    assert "Acme Corp" in md
    assert "Nothing material" in md


def test_brief_has_doctrine_sections() -> None:
    md = compose_daily_brief([_signal()], "Acme Corp", date(2026, 7, 8))
    assert "## WHAT HAPPENED (24h)" in md
    assert "## WHERE TO PAY ATTENTION TODAY" in md
    assert "## ACTIONS BY TEAM" in md


def test_top_signal_is_highest_materiality() -> None:
    low = _signal(headline="Minor UI tweak", materiality_score=0.4)
    high = _signal(headline="Major price cut", materiality_score=0.9)
    md = compose_daily_brief([low, high], "Acme Corp", date(2026, 7, 8))
    attention_section = md.split("## WHERE TO PAY ATTENTION TODAY")[1].split("## ACTIONS BY TEAM")[0]
    assert "Major price cut" in attention_section
    assert "Minor UI tweak" not in attention_section


def test_actions_grouped_by_team() -> None:
    a = _signal(headline="Signal A", team_to_involve="Marketing")
    b = _signal(headline="Signal B", team_to_involve="Product")
    md = compose_daily_brief([a, b], "Acme Corp", date(2026, 7, 8))
    actions_section = md.split("## ACTIONS BY TEAM")[1]
    assert "**Marketing**" in actions_section
    assert "**Product**" in actions_section


def test_dashboard_link_included_when_given() -> None:
    md = compose_daily_brief([_signal()], "Acme Corp", date(2026, 7, 8), dashboard_url="https://dash.example/acme")
    assert "https://dash.example/acme" in md


def test_no_hardcoded_company_vocabulary_leaks_in() -> None:
    """The composer itself must be domain-agnostic: it must not print any
    fixed vendor/company name that wasn't passed in as tenant_name or inside
    the Signal data (rule 1: not Algolia-specific, or any-other-vendor-
    specific -- the composer is pure template + data)."""
    md = compose_daily_brief([_signal()], "Acme Corp", date(2026, 7, 8))
    assert "algolia" not in md.lower()
