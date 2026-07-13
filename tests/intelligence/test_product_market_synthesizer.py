"""Tests for the product-market intelligence spine behind Argus.

These tests define the first real "muscle + brain" contract: product reality
from Scout-style changelog/docs evidence, market conversation evidence, and
Algolia demand evidence are fused into patterns and actions. No evidence, no
claim.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from cios.intelligence.product_market import ProductMarketSynthesizer
from cios.intelligence.types import (
    ConversationTheme,
    DemandSignal,
    EvidenceRef,
    ProductChangeEvent,
    Recommendation,
    RecommendationScorecard,
    RubricDimensionScore,
    SourceMethod,
)


NOW = datetime(2026, 7, 10, 13, 0, tzinfo=timezone.utc)


def evidence(url: str, method: SourceMethod = SourceMethod.SCOUT_CHANGELOG) -> EvidenceRef:
    return EvidenceRef(source_url=url, captured_at=NOW, method=method, excerpt="source excerpt")


def product_event(
    company_name: str,
    capability: str,
    *,
    role: str = "competitor",
    url: str | None = None,
) -> ProductChangeEvent:
    return ProductChangeEvent(
        tenant_id=1,
        company_id=10 if role == "own" else 20,
        company_name=company_name,
        company_role=role,
        capability=capability,
        change_type="release",
        summary=f"{company_name} shipped {capability}",
        observed_at=NOW,
        evidence=[evidence(url or f"https://{company_name.lower()}.example/changelog")],
    )


def conversation(company_name: str, capability: str, intensity: float = 0.7) -> ConversationTheme:
    return ConversationTheme(
        tenant_id=1,
        company_id=20,
        company_name=company_name,
        theme=capability,
        summary=f"{company_name} is positioning around {capability}",
        intensity=intensity,
        observed_at=NOW,
        evidence=[evidence(f"https://{company_name.lower()}.example/blog", SourceMethod.WEB_SCAN)],
    )


def demand(topic: str, change_pct: float = 0.23, value: float = 1234) -> DemandSignal:
    return DemandSignal(
        tenant_id=1,
        topic=topic,
        metric="engaged_sessions",
        value=value,
        change_pct=change_pct,
        period_start=NOW,
        period_end=NOW,
        source_label="Looker Studio GA4 export",
        evidence=[evidence("looker://algolia/ga4/topics", SourceMethod.LOOKER_EXPORT)],
    )


def test_product_change_requires_evidence() -> None:
    with pytest.raises(ValueError, match="evidence"):
        ProductChangeEvent(
            tenant_id=1,
            company_id=20,
            company_name="Constructor",
            company_role="competitor",
            capability="agentic product discovery",
            change_type="release",
            summary="Constructor shipped agentic product discovery",
            observed_at=NOW,
            evidence=[],
        )


def test_shipping_saying_and_rising_demand_produces_narrative_gap_action() -> None:
    result = ProductMarketSynthesizer().synthesize(
        tenant_id=1,
        own_company_name="Algolia",
        product_events=[
            product_event("Constructor", "agentic product discovery"),
            product_event(
                "Algolia",
                "agentic product discovery",
                role="own",
                url="https://www.algolia.com/changelog/agentic-discovery",
            ),
        ],
        conversation_themes=[conversation("Constructor", "agentic product discovery")],
        demand_signals=[demand("agentic product discovery", change_pct=0.23)],
    )

    assert result.verdict == "actionable"
    assert result.patterns[0].pattern_type == "own_narrative_gap"
    assert "Constructor" in result.patterns[0].summary
    assert "Algolia" in result.patterns[0].summary
    assert result.recommendations[0].owner == "PMM"
    assert "agentic product discovery" in result.recommendations[0].action
    assert {item.source_url for item in result.recommendations[0].evidence} >= {
        "https://constructor.example/changelog",
        "https://constructor.example/blog",
        "looker://algolia/ga4/topics",
        "https://www.algolia.com/changelog/agentic-discovery",
    }
    assert result.recommendations[0].scorecard.total_score == 78
    assert result.recommendations[0].scorecard.verdict == "actionable"
    assert {
        dimension.dimension
        for dimension in result.recommendations[0].scorecard.dimension_scores
    } == {
        "product_reality",
        "market_conversation",
        "audience_demand",
        "own_response_gap",
        "evidence_breadth",
    }
    product_dimension = next(
        dimension
        for dimension in result.recommendations[0].scorecard.dimension_scores
        if dimension.dimension == "product_reality"
    )
    assert "Constructor" in product_dimension.rationale
    assert "https://constructor.example/changelog" in product_dimension.evidence_urls


def test_synonymous_capability_labels_match_across_product_conversation_and_demand() -> None:
    result = ProductMarketSynthesizer().synthesize(
        tenant_id=1,
        own_company_name="Algolia",
        product_events=[product_event("Constructor", "AI Shopping Agent")],
        conversation_themes=[conversation("Constructor", "commerce AI agent")],
        demand_signals=[demand("agentic product discovery", change_pct=0.27)],
    )

    assert result.verdict == "actionable"
    assert result.patterns[0].pattern_type == "own_product_gap"
    assert result.patterns[0].capability == "AI Shopping Agent"
    assert result.recommendations[0].owner == "Product"
    assert {item.source_url for item in result.recommendations[0].evidence} >= {
        "https://constructor.example/changelog",
        "https://constructor.example/blog",
        "looker://algolia/ga4/topics",
    }


def test_recommendation_requires_explicit_backend_scorecard() -> None:
    with pytest.raises(ValueError, match="scorecard"):
        Recommendation(
            tenant_id=1,
            owner="PMM",
            action="Create the agentic product discovery narrative.",
            why_now="Competitor product proof, conversation, and demand align.",
            urgency="this_week",
            confidence=0.78,
            evidence=[evidence("https://constructor.example/changelog")],
        )


def test_scorecard_requires_dimensions_that_add_to_total() -> None:
    with pytest.raises(ValueError, match="dimension score total"):
        RecommendationScorecard(
            total_score=80,
            verdict="actionable",
            summary="Backend rubric",
            dimension_scores=[
                RubricDimensionScore(
                    dimension="product_reality",
                    score=20,
                    max_score=25,
                    rationale="Product proof exists.",
                    evidence_urls=["https://constructor.example/changelog"],
                )
            ],
        )


def test_talk_without_product_proof_is_downgraded_not_actionable() -> None:
    result = ProductMarketSynthesizer().synthesize(
        tenant_id=1,
        own_company_name="Algolia",
        product_events=[],
        conversation_themes=[conversation("Elastic", "context engineering", intensity=0.82)],
        demand_signals=[demand("context engineering", change_pct=0.19)],
    )

    assert result.verdict == "watch"
    assert result.patterns[0].pattern_type == "conversation_without_product_proof"
    assert result.recommendations == []
    assert "not release proof" in result.patterns[0].summary


def test_competitor_shipping_and_saying_without_demand_creates_watch_pattern_only() -> None:
    result = ProductMarketSynthesizer().synthesize(
        tenant_id=1,
        own_company_name="Algolia",
        product_events=[product_event("Constructor", "AI shopping agent")],
        conversation_themes=[conversation("Constructor", "AI shopping agent", intensity=0.82)],
        demand_signals=[],
    )

    assert result.verdict == "watch"
    assert result.patterns[0].pattern_type == "competitive_pressure"
    assert "Constructor" in result.patterns[0].summary
    assert "no tenant-side demand" in result.patterns[0].summary
    assert result.recommendations == []
    assert {item.source_url for item in result.patterns[0].evidence} == {
        "https://constructor.example/changelog",
        "https://constructor.example/blog",
    }


def test_tiny_rising_demand_does_not_promote_action() -> None:
    result = ProductMarketSynthesizer().synthesize(
        tenant_id=1,
        own_company_name="Algolia",
        product_events=[product_event("Constructor", "AI shopping agent")],
        conversation_themes=[conversation("Constructor", "AI shopping agent", intensity=0.82)],
        demand_signals=[demand("AI shopping agent", change_pct=0.90, value=3)],
    )

    assert result.verdict == "watch"
    assert result.patterns[0].pattern_type == "competitive_pressure"
    assert "no tenant-side demand evidence" in result.patterns[0].summary
    assert result.recommendations == []


def test_own_release_and_rising_demand_without_conversation_creates_pmm_gap_action() -> None:
    result = ProductMarketSynthesizer().synthesize(
        tenant_id=1,
        own_company_name="Algolia",
        product_events=[
            product_event(
                "Algolia",
                "neural search personalization",
                role="own",
                url="https://www.algolia.com/changelog/neural-personalization",
            )
        ],
        conversation_themes=[],
        demand_signals=[demand("neural search personalization", change_pct=0.31)],
    )

    assert result.verdict == "actionable"
    assert result.patterns[0].pattern_type == "product_without_market_conversation"
    assert "Algolia has product proof" in result.patterns[0].summary
    assert result.recommendations[0].owner == "PMM"
    assert "neural search personalization" in result.recommendations[0].action
    assert result.recommendations[0].scorecard.verdict == "actionable"
    assert {
        dimension.dimension
        for dimension in result.recommendations[0].scorecard.dimension_scores
    } == {"product_reality", "audience_demand", "own_response_gap", "evidence_breadth"}


def test_competitor_release_and_rising_demand_without_conversation_creates_product_gap_action() -> None:
    result = ProductMarketSynthesizer().synthesize(
        tenant_id=1,
        own_company_name="Algolia",
        product_events=[product_event("Constructor", "AI shopping agent")],
        conversation_themes=[],
        demand_signals=[demand("AI shopping agent", change_pct=0.27)],
    )

    assert result.verdict == "actionable"
    assert result.patterns[0].pattern_type == "own_product_gap"
    assert "Constructor has release proof" in result.patterns[0].summary
    assert "no captured public positioning" in result.patterns[0].summary
    assert result.recommendations[0].owner == "Product"
    assert "AI shopping agent" in result.recommendations[0].action
    assert "market conversation is quiet" in result.recommendations[0].why_now
