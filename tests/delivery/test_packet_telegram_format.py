"""Telegram rendering contract tests for Argus packets."""

from __future__ import annotations

from copy import deepcopy
from importlib import import_module
from typing import Any

import pytest


def _contract_module():
    try:
        return import_module("cios.intelligence.argus_packet")
    except ModuleNotFoundError:
        pytest.fail(
            "Missing cios.intelligence.argus_packet. "
            "Telegram must render from the canonical ArgusIntelligencePacket."
        )


def _telegram_module():
    try:
        return import_module("cios.delivery.packet_telegram_format")
    except ModuleNotFoundError:
        pytest.fail(
            "Missing cios.delivery.packet_telegram_format. "
            "Daily and weekly Telegram briefs must consume ArgusIntelligencePacket."
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
            "plain_read": "Algolia has product proof and Audience Demand, but its market story is lagging.",
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
            ],
            "edges": [
                {"source_node_id": "proof-doc", "target_node_id": "claim-window", "edge_type": "supports"},
                {"source_node_id": "proof-demand", "target_node_id": "claim-window", "edge_type": "supports"},
            ],
        },
        "contradictions": [],
        "unknowns": [],
        "source_health": {"active": 42, "checked": 42, "failed": 0, "stale": 0, "confidence_impact": "healthy"},
        "next_monitoring_actions": [
            {
                "action_id": "monitor-agent-studio",
                "summary": "Recheck Agent Studio demand and competitor response.",
                "owner": "Argus",
                "evidence_needed": ["fresh Audience Demand export"],
            }
        ],
        "consumer_state": {
            "telegram_daily": {"status": "sent", "run_id": "daily-algolia-20260730T130000Z", "packet_id": "packet-daily-algolia-20260730", "delivery_id": 100},
            "dashboard": {"status": "published", "run_id": "daily-algolia-20260730T130000Z", "packet_id": "packet-daily-algolia-20260730", "artifact_url": "https://ci.chowmes.com/"},
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


def test_daily_telegram_brief_uses_packet_headline_action_and_proof() -> None:
    renderer = _telegram_module()
    text = renderer.render_daily_packet_brief_html(_packet(), dashboard_url="https://ci.chowmes.com/")

    assert "Agent Studio demand is creating a PMM timing window" in text
    assert "PMM" in text
    assert "Turn Agent Studio into an evidence-backed market narrative" in text
    assert "Audience Demand" in text
    assert "https://ci.chowmes.com/" in text
    assert "daily-algolia-20260730T130000Z" in text


def test_weekly_telegram_brief_uses_weekly_pattern_not_daily_recap() -> None:
    weekly_payload = _packet_payload(cadence="weekly")
    weekly_payload["time_window"] = {
        "label": "weekly",
        "start_at": "2026-07-24T00:00:00Z",
        "end_at": "2026-07-30T23:59:59Z",
        "grain": "weekly",
        "movement_basis": "persistent",
    }
    weekly_payload["market_movements"][0]["summary"] = "Agent Studio persisted across three evidence days."
    weekly_payload["market_movements"][0]["direction"] = "steady"
    contract = _contract_module()
    packet = contract.ArgusIntelligencePacket.model_validate(weekly_payload)

    renderer = _telegram_module()
    text = renderer.render_weekly_packet_brief_html(packet, dashboard_url="https://ci.chowmes.com/")

    assert "weekly" in text.lower()
    assert "persisted across three evidence days" in text
    assert "today's brief" not in text.lower()


def test_failed_packet_renders_failure_not_fake_intelligence() -> None:
    failed_payload = _packet_payload(status="failed")
    failed_payload["recommendations"] = []
    failed_payload["market_movements"] = []
    failed_payload["executive_read"] = {
        **deepcopy(failed_payload["executive_read"]),
        "headline": "CI-OS did not produce a trustworthy packet.",
        "plain_read": "The run failed before packet generation completed.",
        "decision_posture": "blocked",
        "primary_movement_id": None,
        "primary_recommendation_id": None,
    }
    failed_payload["quality"]["quality_review_status"] = "failed"
    failed_payload["quality"]["known_failures"] = ["CI-OS queue operation failed: Permission denied"]
    contract = _contract_module()
    packet = contract.ArgusIntelligencePacket.model_validate(failed_payload)

    renderer = _telegram_module()
    text = renderer.render_daily_packet_brief_html(packet, dashboard_url="https://ci.chowmes.com/")

    assert "did not produce a trustworthy packet" in text
    assert "Permission denied" in text
    assert "PMM" not in text
    assert "Turn Agent Studio" not in text
