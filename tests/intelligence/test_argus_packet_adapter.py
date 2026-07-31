"""Adapter contract tests for converting existing Argus objects into packets."""

from __future__ import annotations

from importlib import import_module
from typing import Any

import pytest


def _contract_module():
    try:
        return import_module("cios.intelligence.argus_packet")
    except ModuleNotFoundError:
        pytest.fail(
            "Missing cios.intelligence.argus_packet. "
            "Phase 2/3 must implement packet adapters from the approved contract."
        )


def _base_components(**overrides: Any) -> dict[str, Any]:
    components: dict[str, Any] = {
        "tenant": {"tenant_id": 1, "slug": "algolia", "display_name": "Algolia"},
        "run": {
            "run_id": "daily-algolia-20260730T130000Z",
            "generated_at": "2026-07-30T13:00:00Z",
            "package_commit": "e02d680",
            "package_release_id": "cios-20260730T130000Z",
            "produced_by_user": "cios",
            "source": "hermes_cron",
        },
        "cadence": "daily",
        "time_window": {
            "label": "today",
            "start_at": "2026-07-30T00:00:00Z",
            "end_at": "2026-07-30T13:00:00Z",
            "grain": "daily",
            "movement_basis": "rising",
        },
        "intelligence_brief": {
            "verdict": "actionable",
            "top_insight": "Agent Studio is a product-without-market-conversation opportunity.",
            "primary_action": "Turn Agent Studio into an evidence-backed market narrative.",
            "watchlist": ["Google Vertex AI Search is adjacent."],
            "evidence_urls": ["https://www.algolia.com/doc/agent-studio"],
            "confidence_limits": ["Audience Demand is based on a Looker export."],
            "next_questions": ["Which competitors react next?"],
            "next_monitoring_actions": [
                {
                    "action_id": "monitor-agent-studio",
                    "summary": "Recheck Agent Studio demand next run.",
                    "owner": "Argus",
                    "evidence_needed": ["fresh Looker export"],
                }
            ],
        },
        "decision_read": {
            "status": "actionable",
            "market_direction": "Agent Studio is heating up around Algolia and Google Vertex AI Search.",
            "priority_reason": "Product proof and audience demand are present.",
            "strategic_insights": [
                {
                    "insight_type": "product_without_market_conversation",
                    "summary": "Algolia has product proof but the market story is lagging.",
                    "involved_companies": ["Algolia", "Google Vertex AI Search"],
                    "evidence_urls": ["https://www.algolia.com/doc/agent-studio"],
                }
            ],
            "tactical_actions": [
                {
                    "owner": "PMM",
                    "action": "Turn Agent Studio into an evidence-backed market narrative.",
                    "why_now": "Demand and product proof overlap.",
                    "urgency": "this_week",
                    "confidence": 0.68,
                    "score": 68,
                    "scorecard_verdict": "promote",
                    "evidence_urls": ["https://www.algolia.com/doc/agent-studio"],
                }
            ],
            "confidence_basis": [
                {
                    "plane": "product_reality",
                    "status": "present",
                    "evidence_count": 1,
                    "summary": "Product proof exists.",
                    "evidence_urls": ["https://www.algolia.com/doc/agent-studio"],
                },
                {
                    "plane": "audience_demand",
                    "status": "present",
                    "evidence_count": 1,
                    "summary": "Audience Demand exists.",
                    "evidence_urls": ["looker://algolia/agent-studio"],
                },
            ],
            "blockers": [],
            "evidence_urls": ["https://www.algolia.com/doc/agent-studio", "looker://algolia/agent-studio"],
        },
        "movement_map": {
            "direction_summary": "Agent Studio is heating up across AI search.",
            "hot_capabilities": ["Agent Studio"],
            "heat_cells": [
                {
                    "company_name": "Algolia",
                    "capability": "Agent Studio",
                    "heat_level": "hot",
                    "signal_count": 2,
                    "recent_count": 2,
                    "prior_count": 0,
                    "confidence": 0.68,
                    "evidence_urls": ["https://www.algolia.com/doc/agent-studio"],
                }
            ],
            "entity_velocity": [
                {
                    "company_name": "Algolia",
                    "heat_level": "hot",
                    "signal_count": 2,
                    "hot_capabilities": ["Agent Studio"],
                    "summary": "Algolia has rising Agent Studio signals.",
                    "evidence_urls": ["https://www.algolia.com/doc/agent-studio"],
                }
            ],
            "evidence_urls": ["https://www.algolia.com/doc/agent-studio"],
            "confidence_limits": ["Movement depends on captured product-market pattern memory."],
        },
        "recommendations": [
            {
                "id": 2,
                "owner": "PMM",
                "action": "Turn Agent Studio into an evidence-backed market narrative.",
                "why_now": "Demand and product proof overlap.",
                "urgency": "this_week",
                "confidence": 0.68,
                "status": "open",
                "scorecard": {
                    "total_score": 68,
                    "verdict": "promote",
                    "dimension_scores": [
                        {"dimension": "product_reality", "score": 20, "evidence_urls": ["https://www.algolia.com/doc/agent-studio"]},
                        {"dimension": "audience_demand", "score": 18, "evidence_urls": ["looker://algolia/agent-studio"]},
                    ],
                },
                "evidence_refs": [
                    {"source_url": "https://www.algolia.com/doc/agent-studio"},
                    {"source_url": "looker://algolia/agent-studio"},
                ],
            }
        ],
        "source_health": {
            "active": 42,
            "checked": 42,
            "failed": 0,
            "stale": 0,
            "confidence_impact": "source coverage supports current packet",
        },
        "consumer_state": {
            "dashboard": {
                "status": "published",
                "run_id": "daily-algolia-20260730T130000Z",
                "artifact_url": "https://ci.chowmes.com/",
            }
        },
    }
    components.update(overrides)
    return components


def _build_packet(**components: Any):
    contract = _contract_module()
    return contract.build_argus_packet_from_components(**_base_components(**components))


def test_product_market_brief_maps_into_packet_without_losing_existing_fields() -> None:
    packet = _build_packet()

    assert packet.status == "actionable"
    assert packet.executive_read.headline
    assert packet.executive_read.plain_read.startswith("Agent Studio")
    assert "https://www.algolia.com/doc/agent-studio" in {
        node.url for node in packet.proof_graph.nodes if getattr(node, "url", None)
    }
    assert packet.next_monitoring_actions[0].summary.startswith("Recheck Agent Studio")


def test_decision_read_maps_status_action_blockers_and_confidence_basis() -> None:
    components = _base_components()
    components["decision_read"]["status"] = "watch"
    components["decision_read"]["tactical_actions"] = []
    components["decision_read"]["blockers"] = ["Audience Demand is missing."]
    components["recommendations"] = []

    contract = _contract_module()
    packet = contract.build_argus_packet_from_components(**components)

    assert packet.status == "watch"
    assert packet.recommendations == []
    assert packet.blocked_actions[0].blocked_reason == "Audience Demand is missing."
    assert {plane.plane for plane in packet.evidence_planes} >= {"product_reality", "audience_demand"}


def test_movement_map_maps_heat_cells_into_market_movements() -> None:
    packet = _build_packet()

    assert packet.market_movements[0].label == "Agent Studio"
    assert packet.market_movements[0].direction == "rising"
    assert packet.market_movements[0].velocity == "high"
    assert packet.market_movements[0].field_graph_ref_id


def test_movement_map_collapses_duplicate_capability_cells_into_one_movement() -> None:
    components = _base_components()
    components["movement_map"]["direction_summary"] = (
        "Shopping Assistant is heating up across Luigi's Box, Constructor, and Bloomreach."
    )
    components["movement_map"]["heat_cells"] = [
        {
            "company_name": "Luigi's Box",
            "capability": "Shopping Assistant",
            "heat_level": "hot",
            "signal_count": 2,
            "recent_count": 2,
            "prior_count": 0,
            "confidence": 0.72,
            "evidence_urls": ["https://example.com/luigis-box-shopping-assistant"],
        },
        {
            "company_name": "Constructor",
            "capability": "Shopping Assistant",
            "heat_level": "hot",
            "signal_count": 1,
            "recent_count": 1,
            "prior_count": 0,
            "confidence": 0.68,
            "evidence_urls": ["https://example.com/constructor-shopping-assistant"],
        },
        {
            "company_name": "Bloomreach",
            "capability": "Shopping Assistant",
            "heat_level": "hot",
            "signal_count": 1,
            "recent_count": 1,
            "prior_count": 0,
            "confidence": 0.67,
            "evidence_urls": ["https://example.com/bloomreach-shopping-assistant"],
        },
    ]

    packet = _build_packet(movement_map=components["movement_map"])

    shopping_movements = [
        movement for movement in packet.market_movements if movement.label == "Shopping Assistant"
    ]
    assert len(shopping_movements) == 1
    assert shopping_movements[0].entities == ["Bloomreach", "Constructor", "Luigi's Box"]
    assert len(shopping_movements[0].proof_ref_ids) == 3


def test_recommendation_rows_map_to_packet_recommendations() -> None:
    packet = _build_packet()

    recommendation = packet.recommendations[0]
    assert recommendation.recommendation_id == "argus-recommendation-2"
    assert recommendation.owner == "PMM"
    assert recommendation.scorecard.total_score == 68
    assert recommendation.proof_ref_ids
