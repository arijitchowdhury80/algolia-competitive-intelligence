"""Tests for deriving the product muscle matrix from product evidence."""

from __future__ import annotations

from datetime import datetime, timezone

from cios.intelligence.feature_matrix import (
    build_product_feature_comparison_read,
    derive_feature_positions_from_product_events,
)
from cios.intelligence.types import ConversationTheme, DemandSignal, EvidenceRef, ProductChangeEvent, SourceMethod


NOW = datetime(2026, 7, 10, 18, 0, tzinfo=timezone.utc)


def evidence(url: str) -> EvidenceRef:
    return EvidenceRef(source_url=url, captured_at=NOW, method=SourceMethod.SCOUT_CHANGELOG, excerpt="proof")


def product_event(
    company_name: str,
    capability: str,
    *,
    change_type: str = "release",
    role: str = "competitor",
    summary: str | None = None,
) -> ProductChangeEvent:
    return ProductChangeEvent(
        tenant_id=1,
        company_id=10 if role == "own" else 20,
        company_name=company_name,
        company_role=role,
        capability=capability,
        change_type=change_type,
        summary=summary or f"{company_name} shipped {capability}",
        observed_at=NOW,
        evidence=[evidence(f"https://{company_name.lower()}.example/changelog")],
    )


def conversation(company_name: str, theme: str, *, role_id: int = 20) -> ConversationTheme:
    return ConversationTheme(
        tenant_id=1,
        company_id=role_id,
        company_name=company_name,
        theme=theme,
        summary=f"{company_name} is talking about {theme}",
        intensity=0.82,
        observed_at=NOW,
        evidence=[EvidenceRef(source_url=f"https://{company_name.lower()}.example/blog", captured_at=NOW, method=SourceMethod.WEB_SCAN)],
    )


def demand(topic: str, *, change_pct: float = 0.23, value: float = 1200) -> DemandSignal:
    return DemandSignal(
        tenant_id=1,
        topic=topic,
        metric="engaged_sessions",
        value=value,
        change_pct=change_pct,
        period_start=NOW,
        period_end=NOW,
        source_label="Looker Studio GA4 export",
        evidence=[EvidenceRef(source_url="looker://algolia/ga4/topics", captured_at=NOW, method=SourceMethod.LOOKER_EXPORT)],
    )


def test_product_events_derive_proven_feature_positions() -> None:
    positions = derive_feature_positions_from_product_events(
        [
            product_event("Constructor", "agentic product discovery"),
            product_event("Algolia", "agentic product discovery", role="own"),
        ]
    )

    assert [(p.company_name, p.company_role, p.position_status) for p in positions] == [
        ("Constructor", "competitor", "proven"),
        ("Algolia", "own", "proven"),
    ]
    assert positions[0].capability == "agentic product discovery"
    assert positions[0].evidence[0].source_url == "https://constructor.example/changelog"


def test_latest_product_event_wins_but_evidence_is_merged() -> None:
    older = product_event(
        "Constructor",
        "agentic product discovery",
        summary="Older docs update",
    )
    newer = product_event(
        "Constructor",
        "agentic product discovery",
        summary="Newer release note",
    ).model_copy(update={"observed_at": datetime(2026, 7, 11, 18, 0, tzinfo=timezone.utc)})

    positions = derive_feature_positions_from_product_events([older, newer])

    assert len(positions) == 1
    assert positions[0].summary == "Newer release note"
    assert positions[0].last_seen_at == newer.observed_at
    assert {item.source_url for item in positions[0].evidence} == {
        "https://constructor.example/changelog",
    }


def test_deprecation_derives_disproven_position() -> None:
    positions = derive_feature_positions_from_product_events(
        [
            product_event(
                "Constructor",
                "legacy merchandising rules",
                change_type="deprecation",
                summary="Constructor deprecated legacy merchandising rules",
            )
        ]
    )

    assert positions[0].position_status == "disproven"
    assert "deprecated" in positions[0].summary


def test_product_feature_comparison_marks_demand_backed_competitor_proof_as_own_product_gap() -> None:
    read = build_product_feature_comparison_read(
        own_company_name="Algolia",
        product_events=[
            product_event("Constructor", "AI Shopping Agent"),
        ],
        conversation_themes=[
            conversation("Constructor", "commerce AI agent"),
        ],
        demand_signals=[
            demand("agentic product discovery"),
        ],
    )

    assert read.summary == "1 capability compared; 1 product gap, 0 narrative gaps, 1 demand-backed row."
    assert read.product_gap_count == 1
    assert read.demand_backed_count == 1
    row = read.rows[0]
    assert row.capability == "agentic product discovery"
    assert row.capability_key == "shopping agent"
    assert row.assessment == "own_product_gap"
    assert row.own_status == "gap"
    assert row.competitors_with_product_proof == ["Constructor"]
    assert row.competitors_with_conversation == ["Constructor"]
    assert row.has_rising_demand is True
    assert row.demand_signal_count == 1
    assert row.recommended_action.startswith("Audit whether Algolia has provable")
    assert set(row.evidence_urls) == {
        "https://constructor.example/changelog",
        "https://constructor.example/blog",
        "looker://algolia/ga4/topics",
    }
    assert any("Gap means no captured product proof" in item for item in row.confidence_limits)


def test_product_feature_comparison_summary_uses_capabilities_plural() -> None:
    read = build_product_feature_comparison_read(
        own_company_name="Algolia",
        product_events=[
            product_event("Constructor", "agentic product discovery"),
            product_event("Elastic", "hybrid search"),
        ],
        conversation_themes=[],
        demand_signals=[],
    )

    assert read.summary.startswith("2 capabilities compared;")


def test_product_feature_comparison_marks_parity_without_own_narrative_as_narrative_gap() -> None:
    read = build_product_feature_comparison_read(
        own_company_name="Algolia",
        product_events=[
            product_event("Constructor", "agentic product discovery"),
            product_event("Algolia", "agentic product discovery", role="own"),
        ],
        conversation_themes=[
            conversation("Constructor", "agentic product discovery"),
        ],
        demand_signals=[
            demand("agentic product discovery"),
        ],
    )

    row = read.rows[0]
    assert read.product_gap_count == 0
    assert read.narrative_gap_count == 1
    assert row.assessment == "own_narrative_gap"
    assert row.own_status == "proven"
    assert row.recommended_action == (
        "Create an Algolia narrative for agentic product discovery using existing product proof."
    )
    assert "https://algolia.example/changelog" in row.evidence_urls


def test_product_feature_comparison_does_not_treat_low_demand_as_demand_backed() -> None:
    read = build_product_feature_comparison_read(
        own_company_name="Algolia",
        product_events=[product_event("Constructor", "agentic product discovery")],
        conversation_themes=[conversation("Constructor", "agentic product discovery")],
        demand_signals=[demand("agentic product discovery", change_pct=0.01)],
    )

    row = read.rows[0]
    assert read.demand_backed_count == 0
    assert row.has_rising_demand is False
    assert row.assessment == "competitive_pressure"
    assert row.recommended_action == "Watch agentic product discovery until tenant demand or Algolia response evidence changes."


def test_product_feature_comparison_does_not_treat_tiny_high_growth_as_demand_backed() -> None:
    read = build_product_feature_comparison_read(
        own_company_name="Algolia",
        product_events=[product_event("Constructor", "agentic product discovery")],
        conversation_themes=[conversation("Constructor", "agentic product discovery")],
        demand_signals=[demand("agentic product discovery", change_pct=0.90, value=3)],
    )

    row = read.rows[0]
    assert read.demand_backed_count == 0
    assert row.has_rising_demand is False
    assert row.assessment == "competitive_pressure"
