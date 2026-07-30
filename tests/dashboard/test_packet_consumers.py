"""Dashboard/public-status consumer contract tests for Argus packets."""

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
            "Dashboard/public-status consumers must render from the canonical packet."
        )


def _consumer_module():
    try:
        return import_module("cios.dashboard.packet_consumers")
    except ModuleNotFoundError:
        pytest.fail(
            "Missing cios.dashboard.packet_consumers. "
            "Dashboard, Market Field, and public status must consume ArgusIntelligencePacket."
        )


def _packet_payload(**overrides: Any) -> dict[str, Any]:
    packet: dict[str, Any] = {
        "schema_version": 1,
        "packet_id": "packet-daily-algolia-20260730",
        "tenant": {"tenant_id": 1, "slug": "algolia", "display_name": "Algolia"},
        "run": {
            "run_id": "daily-algolia-20260730T130000Z",
            "generated_at": "2026-07-30T13:00:00Z",
            "package_commit": "e02d680",
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
        "status": "actionable",
        "executive_read": {
            "headline": "Agent Studio demand is creating a PMM timing window.",
            "plain_read": "Algolia has product proof and Audience Demand, but its story is lagging.",
            "why_it_matters_to_algolia": "Competitors can define the category before Algolia does.",
            "market_belief_implied": "AI search is being judged by workflow ownership.",
            "what_may_happen_next": "Competitors will package AI search as shopping-agent infrastructure.",
            "decision_posture": "act",
            "primary_movement_id": "movement-agent-studio",
            "primary_recommendation_id": "rec-pmm-agent-studio",
            "proof_ref_ids": ["proof-doc", "proof-demand"],
            "confidence_ref_ids": ["plane-product", "plane-demand"],
        },
        "market_movements": [
            {
                "movement_id": "movement-agent-studio",
                "label": "Agent Studio attention window",
                "summary": "Agent Studio has product proof and Audience Demand.",
                "movement_type": "mixed",
                "direction": "rising",
                "velocity": "high",
                "materiality": "high",
                "time_window": "today",
                "entities": ["Algolia", "Google Vertex AI Search"],
                "capabilities": ["Agent Studio"],
                "themes": ["agentic search"],
                "evidence_plane_refs": ["plane-product", "plane-demand"],
                "proof_ref_ids": ["proof-doc", "proof-demand"],
                "contradiction_ref_ids": [],
                "unknown_ref_ids": [],
                "recommendation_ref_ids": ["rec-pmm-agent-studio"],
                "field_graph_ref_id": "field-agent-studio",
            }
        ],
        "attention_state": {"now": ["movement-agent-studio"], "monitor": [], "quiet": [], "blocked": []},
        "recommendations": [
            {
                "recommendation_id": "rec-pmm-agent-studio",
                "owner": "PMM",
                "action": "Turn Agent Studio into an evidence-backed market narrative.",
                "why_now": "Product proof and Audience Demand overlap.",
                "expected_outcome": "Algolia controls the AI-search workflow narrative.",
                "urgency": "this_week",
                "confidence": 0.68,
                "priority_rank": 1,
                "status": "open",
                "movement_ref_ids": ["movement-agent-studio"],
                "proof_ref_ids": ["proof-doc", "proof-demand"],
                "scorecard": {"total_score": 68, "verdict": "promote", "dimensions": []},
                "next_review_at": "2026-08-06T13:00:00Z",
            }
        ],
        "blocked_actions": [],
        "evidence_planes": [
            {
                "plane": "product_reality",
                "status": "present",
                "summary": "Agent Studio docs are present.",
                "signal_count": 1,
                "evidence_count": 1,
                "coverage": {"checked": 1, "active": 1, "failed": 0},
                "proof_ref_ids": ["proof-doc"],
                "confidence_impact": "supports action",
            },
            {
                "plane": "audience_demand",
                "status": "present",
                "summary": "Audience Demand exists.",
                "signal_count": 1,
                "evidence_count": 1,
                "coverage": {"checked": 1, "active": 1, "failed": 0},
                "proof_ref_ids": ["proof-demand"],
                "confidence_impact": "supports action",
            },
        ],
        "proof_graph": {
            "root_claim_ids": ["claim-window"],
            "nodes": [
                {"node_id": "proof-doc", "node_type": "source_event", "label": "Docs", "url": "https://www.algolia.com/doc/agent-studio"},
                {"node_id": "proof-demand", "node_type": "source_event", "label": "Audience Demand", "url": "looker://algolia/agent-studio"},
                {"node_id": "movement-agent-studio", "node_type": "pattern", "label": "Agent Studio attention window"},
                {"node_id": "rec-pmm-agent-studio", "node_type": "recommendation", "label": "PMM action"},
            ],
            "edges": [
                {"source_node_id": "proof-doc", "target_node_id": "movement-agent-studio", "edge_type": "supports"},
                {"source_node_id": "proof-demand", "target_node_id": "movement-agent-studio", "edge_type": "supports"},
                {"source_node_id": "movement-agent-studio", "target_node_id": "rec-pmm-agent-studio", "edge_type": "supports"},
            ],
        },
        "contradictions": [],
        "unknowns": [],
        "source_health": {"active": 42, "checked": 42, "failed": 0, "stale": 0, "confidence_impact": "healthy"},
        "next_monitoring_actions": [],
        "consumer_state": {
            "dashboard": {"status": "published", "run_id": "daily-algolia-20260730T130000Z", "packet_id": "packet-daily-algolia-20260730"},
            "market_field": {"status": "rendered", "run_id": "daily-algolia-20260730T130000Z", "packet_id": "packet-daily-algolia-20260730"},
            "public_status": {"status": "published", "run_id": "daily-algolia-20260730T130000Z", "packet_id": "packet-daily-algolia-20260730"},
        },
        "quality": {
            "quality_review_status": "passed",
            "freshness_status": "current",
            "redaction_status": "passed",
            "source_coverage_status": "passed",
            "run_identity_status": "passed",
            "consumer_parity_status": "passed",
            "known_failures": [],
            "residual_risks": [],
        },
        "lineage": {"upstream_objects": ["ProductMarketIntelligenceBrief"], "source_artifacts": []},
    }
    packet.update(overrides)
    return packet


def _packet(**overrides: Any):
    contract = _contract_module()
    return contract.ArgusIntelligencePacket.model_validate(_packet_payload(**overrides))


def test_dashboard_state_is_generated_from_packet() -> None:
    consumers = _consumer_module()
    state = consumers.build_dashboard_state_from_packet(_packet())

    assert state.run_health.run_id == "daily-algolia-20260730T130000Z"
    assert state.intelligence_spine.top_insight == "Agent Studio demand is creating a PMM timing window."
    assert state.intelligence_spine.primary_action == "Turn Agent Studio into an evidence-backed market narrative."


def test_market_field_hotspots_reference_packet_movements() -> None:
    consumers = _consumer_module()
    state = consumers.build_market_field_from_packet(_packet())

    assert state.hotspots[0].hotspot_id == "movement-agent-studio"
    assert state.hotspots[0].argus_read == "Agent Studio has product proof and Audience Demand."
    assert state.actions[0].action == "Turn Agent Studio into an evidence-backed market narrative."
    assert {item.node_type for item in state.nodes} >= {"theme", "recommendation"}


def test_public_status_recommendation_count_comes_from_packet() -> None:
    consumers = _consumer_module()
    public_status = consumers.build_public_status_from_packet(_packet())

    assert public_status["run_id"] == "daily-algolia-20260730T130000Z"
    assert public_status["packet_id"] == "packet-daily-algolia-20260730"
    assert public_status["current_recommendation_count"] == 1
    assert public_status["status"] == "actionable"


def test_latest_json_cannot_publish_stale_packet_as_current() -> None:
    stale_packet = _packet(status="stale")
    consumers = _consumer_module()
    latest = consumers.build_latest_json_from_packet(stale_packet)

    assert latest["status"] == "stale"
    assert latest["freshness_status"] != "current"
    assert latest["generated_at"] == "2026-07-30T13:00:00Z"
