"""Workflow tests for turning evidence inputs into stored Argus intelligence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from cios.intelligence.product_market import ProductMarketSynthesizer
from cios.intelligence.types import (
    ConversationTheme,
    DemandSignal,
    EvidenceRef,
    PatternObservation,
    ProductChangeEvent,
    Recommendation,
    SourceMethod,
    FeaturePosition,
)
from cios.intelligence.workflow import ProductMarketIntelligenceWorkflow


NOW = datetime(2026, 7, 10, 16, 0, tzinfo=timezone.utc)


class FakeProductMarketLedger:
    def __init__(self) -> None:
        self.product_events: list[ProductChangeEvent] = []
        self.conversation_themes: list[ConversationTheme] = []
        self.demand_signals: list[DemandSignal] = []
        self.feature_positions: list[FeaturePosition] = []
        self.patterns: list[PatternObservation] = []
        self.recommendations: list[tuple[Recommendation, int | None]] = []
        self.run_intelligence_summaries: list[Any] = []

    def save_product_change_event(self, event: ProductChangeEvent) -> int:
        self.product_events.append(event)
        return len(self.product_events)

    def save_conversation_theme(self, theme: ConversationTheme) -> int:
        self.conversation_themes.append(theme)
        return len(self.conversation_themes)

    def save_demand_signal(self, signal: DemandSignal) -> int:
        self.demand_signals.append(signal)
        return len(self.demand_signals)

    def save_feature_position(self, position: FeaturePosition) -> int:
        self.feature_positions.append(position)
        return len(self.feature_positions)

    def save_pattern_observation(self, pattern: PatternObservation) -> int:
        self.patterns.append(pattern)
        return 100 + len(self.patterns)

    def save_recommendation(
        self,
        recommendation: Recommendation,
        *,
        pattern_observation_id: int | None = None,
    ) -> int:
        self.recommendations.append((recommendation, pattern_observation_id))
        return 200 + len(self.recommendations)

    def save_run_intelligence_summary(self, summary: Any) -> int:
        self.run_intelligence_summaries.append(summary)
        return 300 + len(self.run_intelligence_summaries)


def evidence(url: str, method: SourceMethod = SourceMethod.SCOUT_CHANGELOG) -> EvidenceRef:
    return EvidenceRef(source_url=url, captured_at=NOW, method=method, excerpt="proof")


def product_event(company_name: str, capability: str, *, role: str = "competitor") -> ProductChangeEvent:
    return ProductChangeEvent(
        tenant_id=1,
        company_id=10 if role == "own" else 20,
        company_name=company_name,
        company_role=role,
        capability=capability,
        change_type="release",
        summary=f"{company_name} shipped {capability}",
        observed_at=NOW,
        evidence=[evidence(f"https://{company_name.lower()}.example/changelog")],
    )


def conversation(company_name: str, capability: str) -> ConversationTheme:
    return ConversationTheme(
        tenant_id=1,
        company_id=20,
        company_name=company_name,
        theme=capability,
        summary=f"{company_name} is positioning around {capability}",
        intensity=0.82,
        observed_at=NOW,
        evidence=[evidence(f"https://{company_name.lower()}.example/blog", SourceMethod.WEB_SCAN)],
    )


def demand(topic: str) -> DemandSignal:
    return DemandSignal(
        tenant_id=1,
        topic=topic,
        metric="engaged_sessions",
        value=1234,
        change_pct=0.23,
        period_start=NOW,
        period_end=NOW,
        source_label="Looker Studio GA4 export",
        evidence=[evidence("looker://algolia/ga4/topics", SourceMethod.LOOKER_EXPORT)],
    )


def test_workflow_persists_inputs_then_patterns_and_linked_recommendations() -> None:
    ledger = FakeProductMarketLedger()
    workflow = ProductMarketIntelligenceWorkflow(
        repository=ledger,
        synthesizer=ProductMarketSynthesizer(),
    )

    result = workflow.run(
        tenant_id=1,
        own_company_name="Algolia",
        product_events=[
            product_event("Constructor", "agentic product discovery"),
            product_event("Algolia", "agentic product discovery", role="own"),
        ],
        conversation_themes=[conversation("Constructor", "agentic product discovery")],
        demand_signals=[demand("agentic product discovery")],
    )

    assert result.verdict == "actionable"
    assert [event.company_name for event in ledger.product_events] == ["Constructor", "Algolia"]
    assert [theme.company_name for theme in ledger.conversation_themes] == ["Constructor"]
    assert [signal.topic for signal in ledger.demand_signals] == ["agentic product discovery"]
    assert [(p.company_name, p.capability, p.position_status) for p in ledger.feature_positions] == [
        ("Constructor", "agentic product discovery", "proven"),
        ("Algolia", "agentic product discovery", "proven"),
    ]
    assert ledger.patterns[0].pattern_type == "own_narrative_gap"
    assert ledger.recommendations[0][0].owner == "PMM"
    assert ledger.recommendations[0][1] == 101


def test_workflow_uses_coverage_recheck_learning_to_hold_recommendations() -> None:
    ledger = FakeProductMarketLedger()
    workflow = ProductMarketIntelligenceWorkflow(
        repository=ledger,
        synthesizer=ProductMarketSynthesizer(),
    )

    result = workflow.run(
        tenant_id=1,
        own_company_name="Algolia",
        product_events=[
            product_event("Constructor", "agentic product discovery"),
            product_event("Algolia", "agentic product discovery", role="own"),
        ],
        conversation_themes=[conversation("Constructor", "agentic product discovery")],
        demand_signals=[demand("agentic product discovery")],
        learning_instructions=[
            {
                "kind": "coverage_recheck",
                "instruction": "Re-audit source coverage before ranking Constructor again.",
                "source_improvement_ids": [202],
                "evidence_event_ids": [101],
            }
        ],
    )

    assert result.verdict == "watch"
    assert result.patterns[0].pattern_type == "own_narrative_gap"
    assert result.recommendations == []
    assert ledger.patterns[0].pattern_type == "own_narrative_gap"
    assert ledger.recommendations == []


def test_workflow_persists_outward_watch_pattern_when_demand_is_missing() -> None:
    ledger = FakeProductMarketLedger()
    workflow = ProductMarketIntelligenceWorkflow(
        repository=ledger,
        synthesizer=ProductMarketSynthesizer(),
    )

    result = workflow.run(
        tenant_id=1,
        own_company_name="Algolia",
        product_events=[product_event("Constructor", "AI shopping agent")],
        conversation_themes=[conversation("Constructor", "AI shopping agent")],
        demand_signals=[],
    )

    assert result.verdict == "watch"
    assert result.patterns[0].pattern_type == "competitive_pressure"
    assert "no tenant-side demand" in result.patterns[0].summary
    assert result.recommendations == []
    assert ledger.patterns[0].pattern_type == "competitive_pressure"
    assert ledger.recommendations == []


def test_workflow_uses_scoring_review_learning_to_hold_under_threshold_recommendations() -> None:
    ledger = FakeProductMarketLedger()
    workflow = ProductMarketIntelligenceWorkflow(
        repository=ledger,
        synthesizer=ProductMarketSynthesizer(),
    )

    result = workflow.run(
        tenant_id=1,
        own_company_name="Algolia",
        product_events=[
            product_event("Constructor", "agentic product discovery"),
            product_event("Algolia", "agentic product discovery", role="own"),
        ],
        conversation_themes=[conversation("Constructor", "agentic product discovery")],
        demand_signals=[demand("agentic product discovery")],
        learning_instructions=[
            {
                "kind": "scoring_review",
                "instruction": "Require stronger scorecard evidence before promoting the next recommendation.",
                "source_improvement_ids": [303],
                "evidence_event_ids": [101],
            }
        ],
    )

    assert result.verdict == "watch"
    assert result.patterns[0].pattern_type == "own_narrative_gap"
    assert result.recommendations == []
    assert ledger.patterns[0].pattern_type == "own_narrative_gap"
    assert ledger.recommendations == []


def test_workflow_honors_learning_instruction_action_threshold() -> None:
    ledger = FakeProductMarketLedger()
    workflow = ProductMarketIntelligenceWorkflow(
        repository=ledger,
        synthesizer=ProductMarketSynthesizer(),
    )

    result = workflow.run(
        tenant_id=1,
        own_company_name="Algolia",
        product_events=[
            product_event("Constructor", "agentic product discovery"),
            product_event("Algolia", "agentic product discovery", role="own"),
        ],
        conversation_themes=[conversation("Constructor", "agentic product discovery")],
        demand_signals=[demand("agentic product discovery")],
        learning_instructions=[
            {
                "kind": "scoring_review",
                "instruction": "Allow promotion at the configured learned threshold.",
                "change": {"action_threshold": 78},
                "source_improvement_ids": [304],
                "evidence_event_ids": [102],
            }
        ],
    )

    assert result.verdict == "actionable"
    assert result.recommendations[0].scorecard.total_score == 78
    assert ledger.recommendations[0][0].scorecard.total_score == 78


def test_workflow_rejects_cross_tenant_inputs_before_saving_anything() -> None:
    ledger = FakeProductMarketLedger()
    workflow = ProductMarketIntelligenceWorkflow(repository=ledger)
    cross_tenant_signal = demand("agentic product discovery").model_copy(update={"tenant_id": 2})

    with pytest.raises(ValueError, match="tenant_id"):
        workflow.run(
            tenant_id=1,
            own_company_name="Algolia",
            product_events=[product_event("Constructor", "agentic product discovery")],
            conversation_themes=[conversation("Constructor", "agentic product discovery")],
            demand_signals=[cross_tenant_signal],
        )

    assert ledger.product_events == []
    assert ledger.conversation_themes == []
    assert ledger.demand_signals == []
    assert ledger.feature_positions == []
    assert ledger.patterns == []
    assert ledger.recommendations == []
