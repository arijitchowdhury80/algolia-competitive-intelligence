"""Tests for Argus market-movement intelligence maps."""

from __future__ import annotations

from datetime import datetime, timezone

from cios.intelligence.market_movement import build_market_movement_map
from cios.intelligence.types import EvidenceRef, PatternObservation, SourceMethod


NOW = datetime(2026, 7, 11, 4, 50, tzinfo=timezone.utc)


def evidence(url: str) -> EvidenceRef:
    return EvidenceRef(
        source_url=url,
        captured_at=NOW,
        method=SourceMethod.SCOUT_CHANGELOG,
        excerpt="proof",
    )


def pattern(
    capability: str,
    companies: list[str],
    *,
    summary: str | None = None,
    confidence: float = 0.78,
) -> PatternObservation:
    return PatternObservation(
        tenant_id=1,
        pattern_type="own_product_gap",
        capability=capability,
        summary=summary or f"{', '.join(companies)} is moving on {capability}.",
        involved_companies=companies,
        confidence=confidence,
        evidence=[evidence(f"https://example.com/{capability.replace(' ', '-')}")],
    )


def test_market_movement_map_derives_heat_and_entity_velocity_from_current_and_history() -> None:
    movement = build_market_movement_map(
        current_patterns=[
            pattern("agentic product discovery", ["Constructor", "Algolia"]),
            pattern("agentic product discovery", ["Coveo", "Algolia"]),
        ],
        historical_patterns=[
            {
                "capability_text": "agentic product discovery",
                "summary": "Constructor pushed agentic product discovery last week.",
                "involved_companies": ["Constructor"],
                "confidence": 0.72,
                "evidence_refs": [{"source_url": "https://constructor.com/changelog/agent"}],
                "created_at": "2026-07-08T04:50:00+00:00",
            },
            {
                "capability_text": "hybrid search ranking",
                "summary": "Elastic moved on hybrid search ranking earlier in the month.",
                "involved_companies": ["Elastic"],
                "confidence": 0.64,
                "evidence_refs": [{"source_url": "https://elastic.co/guide/hybrid"}],
                "created_at": "2026-06-25T04:50:00+00:00",
            },
        ],
        as_of=NOW,
    )

    assert movement.direction_summary.startswith("agentic product discovery is heating up")
    assert movement.hot_capabilities == ["agentic product discovery"]
    assert ("Constructor", "agentic product discovery", "hot") in [
        (cell.company_name, cell.capability, cell.heat_level) for cell in movement.heat_cells
    ]
    assert ("Algolia", "agentic product discovery", "hot") in [
        (cell.company_name, cell.capability, cell.heat_level) for cell in movement.heat_cells
    ]
    assert movement.entity_velocity[0].company_name in {"Algolia", "Constructor"}
    assert movement.entity_velocity[0].signal_count >= 2
    assert "https://constructor.com/changelog/agent" in movement.evidence_urls
    assert movement.confidence_limits == [
        "Movement is derived from captured product-market pattern memory; missing sources can still hide market activity."
    ]


def test_market_movement_map_is_honest_when_no_patterns_exist() -> None:
    movement = build_market_movement_map(
        current_patterns=[],
        historical_patterns=[],
        as_of=NOW,
    )

    assert movement.direction_summary == "No product-market movement map is available for this run."
    assert movement.hot_capabilities == []
    assert movement.heat_cells == []
    assert movement.entity_velocity == []
    assert movement.evidence_urls == []
    assert movement.confidence_limits == [
        "No product-market patterns were available to score movement."
    ]
