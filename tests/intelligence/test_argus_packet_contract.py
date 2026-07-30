"""Contract tests for the canonical Argus Intelligence Packet.

These tests intentionally describe the desired public model before the
implementation exists. They are the Phase 1 RED gate for the intelligence
spine goal.
"""

from __future__ import annotations

from copy import deepcopy
from importlib import import_module
from typing import Any

import pytest


def _contract_module():
    try:
        return import_module("cios.intelligence.argus_packet")
    except ModuleNotFoundError as exc:
        pytest.fail(
            "Missing cios.intelligence.argus_packet. "
            "Phase 2/3 must implement ArgusIntelligencePacket from the approved contract."
        )


def _valid_packet(**overrides: Any) -> dict[str, Any]:
    packet: dict[str, Any] = {
        "schema_version": 1,
        "packet_id": "packet-daily-algolia-20260730",
        "tenant": {"tenant_id": 1, "slug": "algolia", "display_name": "Algolia"},
        "run": {
            "run_id": "daily-algolia-20260730T130000Z",
            "generated_at": "2026-07-30T13:00:00Z",
            "package_commit": "e02d680",
            "package_release_id": "cios-20260730T130000Z",
            "package_sha256": "a" * 64,
            "produced_by_user": "cios",
            "source": "hermes_cron",
        },
        "cadence": "daily",
        "time_window": {
            "label": "today",
            "start_at": "2026-07-30T00:00:00Z",
            "end_at": "2026-07-30T13:00:00Z",
            "grain": "daily",
            "movement_basis": "new",
        },
        "status": "actionable",
        "executive_read": {
            "headline": "Agent Studio demand is creating a PMM timing window.",
            "plain_read": "Algolia has product proof, audience demand is visible, and the public story is lagging.",
            "why_it_matters_to_algolia": "The market can define agentic search before Algolia does.",
            "market_belief_implied": "Buyers are comparing AI search through workflow ownership, not only relevance.",
            "what_may_happen_next": "Competitors will keep tying AI search to shopping and agent workflows.",
            "decision_posture": "act",
            "primary_movement_id": "movement-agent-studio",
            "primary_recommendation_id": "rec-pmm-agent-studio",
            "proof_ref_ids": ["proof-algolia-docs", "proof-demand"],
            "confidence_ref_ids": ["plane-product", "plane-demand"],
        },
        "market_movements": [
            {
                "movement_id": "movement-agent-studio",
                "label": "Agent Studio attention window",
                "summary": "Agent Studio has product proof and audience demand, but public narrative needs acceleration.",
                "movement_type": "mixed",
                "direction": "rising",
                "velocity": "high",
                "materiality": "high",
                "time_window": "today",
                "entities": ["Algolia", "Google Vertex AI Search"],
                "capabilities": ["Agent Studio", "AI Search"],
                "themes": ["agentic search"],
                "evidence_plane_refs": ["plane-product", "plane-demand"],
                "proof_ref_ids": ["proof-algolia-docs", "proof-demand"],
                "contradiction_ref_ids": [],
                "unknown_ref_ids": [],
                "recommendation_ref_ids": ["rec-pmm-agent-studio"],
                "field_graph_ref_id": "field-agent-studio",
            }
        ],
        "attention_state": {
            "now": ["movement-agent-studio"],
            "monitor": [],
            "quiet": [],
            "blocked": [],
        },
        "recommendations": [
            {
                "recommendation_id": "rec-pmm-agent-studio",
                "owner": "PMM",
                "action": "Turn Agent Studio into an evidence-backed market narrative.",
                "why_now": "Product proof and Audience Demand are both present in the same window.",
                "expected_outcome": "Algolia controls the AI-search workflow narrative before competitors define it.",
                "urgency": "this_week",
                "confidence": 0.68,
                "priority_rank": 1,
                "status": "open",
                "movement_ref_ids": ["movement-agent-studio"],
                "proof_ref_ids": ["proof-algolia-docs", "proof-demand"],
                "scorecard": {
                    "total_score": 68,
                    "verdict": "promote",
                    "dimensions": [
                        {"dimension": "product_reality", "score": 20, "proof_ref_ids": ["proof-algolia-docs"]},
                        {"dimension": "audience_demand", "score": 18, "proof_ref_ids": ["proof-demand"]},
                    ],
                },
                "next_review_at": "2026-08-06T13:00:00Z",
            }
        ],
        "blocked_actions": [],
        "evidence_planes": [
            {
                "plane": "product_reality",
                "status": "present",
                "summary": "Product docs prove Agent Studio exists.",
                "signal_count": 1,
                "evidence_count": 1,
                "coverage": {"checked": 1, "active": 1, "failed": 0},
                "proof_ref_ids": ["proof-algolia-docs"],
                "confidence_impact": "supports action",
            },
            {
                "plane": "audience_demand",
                "status": "present",
                "summary": "Audience Demand exists for agentic search pages.",
                "signal_count": 1,
                "evidence_count": 1,
                "coverage": {"checked": 1, "active": 1, "failed": 0},
                "proof_ref_ids": ["proof-demand"],
                "confidence_impact": "supports action",
            },
        ],
        "proof_graph": {
            "root_claim_ids": ["claim-agent-studio-window"],
            "nodes": [
                {"node_id": "proof-algolia-docs", "node_type": "source_event", "label": "Algolia docs", "url": "https://www.algolia.com/doc/"},
                {"node_id": "proof-demand", "node_type": "source_event", "label": "Audience Demand export", "url": "looker://algolia/agent-studio"},
                {"node_id": "claim-agent-studio-window", "node_type": "claim", "label": "Agent Studio demand window"},
                {"node_id": "movement-agent-studio", "node_type": "pattern", "label": "Agent Studio attention window"},
                {"node_id": "rec-pmm-agent-studio", "node_type": "recommendation", "label": "PMM action"},
            ],
            "edges": [
                {"source_node_id": "proof-algolia-docs", "target_node_id": "claim-agent-studio-window", "edge_type": "supports"},
                {"source_node_id": "proof-demand", "target_node_id": "claim-agent-studio-window", "edge_type": "supports"},
                {"source_node_id": "claim-agent-studio-window", "target_node_id": "movement-agent-studio", "edge_type": "derived_from"},
                {"source_node_id": "movement-agent-studio", "target_node_id": "rec-pmm-agent-studio", "edge_type": "supports"},
            ],
        },
        "contradictions": [],
        "unknowns": [],
        "source_health": {
            "active": 42,
            "checked": 42,
            "failed": 0,
            "stale": 0,
            "confidence_impact": "coverage supports current packet",
        },
        "next_monitoring_actions": [
            {
                "action_id": "monitor-agent-studio-demand",
                "summary": "Recheck Agent Studio demand and competitor response.",
                "owner": "Argus",
                "evidence_needed": ["fresh Audience Demand export"],
            }
        ],
        "consumer_state": {
            "telegram_daily": {"status": "sent", "run_id": "daily-algolia-20260730T130000Z", "packet_id": "packet-daily-algolia-20260730", "delivery_id": 100},
            "telegram_weekly": {"status": "not_applicable", "run_id": "daily-algolia-20260730T130000Z", "packet_id": "packet-daily-algolia-20260730"},
            "dashboard": {"status": "published", "run_id": "daily-algolia-20260730T130000Z", "packet_id": "packet-daily-algolia-20260730", "artifact_url": "https://ci.chowmes.com/"},
            "market_field": {"status": "rendered", "run_id": "daily-algolia-20260730T130000Z", "packet_id": "packet-daily-algolia-20260730"},
            "evidence_lab": {"status": "rendered", "run_id": "daily-algolia-20260730T130000Z", "packet_id": "packet-daily-algolia-20260730"},
            "admin": {"status": "rendered", "run_id": "daily-algolia-20260730T130000Z", "packet_id": "packet-daily-algolia-20260730"},
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
        "lineage": {
            "upstream_objects": ["ProductMarketIntelligenceBrief", "ArgusDecisionRead"],
            "source_artifacts": ["semantic-dashboard.json"],
        },
    }
    packet.update(overrides)
    return packet


def _validate(packet: dict[str, Any]):
    contract = _contract_module()
    return contract.ArgusIntelligencePacket.model_validate(packet)


def test_packet_requires_run_identity_and_time_window() -> None:
    valid = _validate(_valid_packet())
    assert valid.run.run_id == "daily-algolia-20260730T130000Z"
    assert valid.time_window.label == "today"

    missing_commit = _valid_packet()
    del missing_commit["run"]["package_commit"]
    with pytest.raises(Exception):
        _validate(missing_commit)

    missing_window = _valid_packet()
    del missing_window["time_window"]
    with pytest.raises(Exception):
        _validate(missing_window)


def test_actionable_packet_requires_recommendation_proof_and_scorecard() -> None:
    no_scorecard = _valid_packet()
    del no_scorecard["recommendations"][0]["scorecard"]
    with pytest.raises(Exception):
        _validate(no_scorecard)

    no_proof = _valid_packet()
    no_proof["recommendations"][0]["proof_ref_ids"] = []
    with pytest.raises(Exception):
        _validate(no_proof)


def test_watch_packet_blocks_action_when_audience_demand_missing() -> None:
    packet = _valid_packet(status="watch")
    packet["recommendations"] = []
    packet["evidence_planes"][1]["status"] = "missing"
    packet["evidence_planes"][1]["signal_count"] = 0
    packet["evidence_planes"][1]["proof_ref_ids"] = []
    packet["blocked_actions"] = [
        {
            "blocked_action_id": "blocked-pmm-agent-studio",
            "owner": "PMM",
            "proposed_action": "Launch Agent Studio positioning campaign.",
            "blocked_reason": "Audience Demand is missing.",
            "needed_evidence": ["GA / Looker demand proof"],
            "next_monitoring_action_ref_ids": ["monitor-agent-studio-demand"],
            "movement_ref_ids": ["movement-agent-studio"],
        }
    ]

    validated = _validate(packet)
    assert validated.status == "watch"
    assert validated.blocked_actions[0].blocked_reason == "Audience Demand is missing."


def test_quiet_verified_requires_checked_source_coverage() -> None:
    packet = _valid_packet(status="quiet_verified")
    packet["market_movements"] = []
    packet["recommendations"] = []
    packet["executive_read"]["decision_posture"] = "quiet"
    packet["source_health"]["checked"] = 0
    packet["source_health"]["active"] = 42

    with pytest.raises(Exception):
        _validate(packet)


def test_degraded_packet_discloses_source_failures_and_freshness() -> None:
    packet = _valid_packet(status="degraded")
    packet["source_health"]["failed"] = 4
    packet["quality"]["freshness_status"] = "stale"
    packet["quality"]["known_failures"] = ["4 active sources failed during collection."]
    validated = _validate(packet)

    assert validated.status == "degraded"
    assert validated.quality.freshness_status == "stale"
    assert validated.source_health.failed == 4


def test_packet_rejects_consumer_run_id_drift() -> None:
    packet = _valid_packet()
    packet["consumer_state"]["dashboard"]["run_id"] = "different-run"

    with pytest.raises(Exception):
        _validate(packet)


def test_packet_carries_contradictions_unknowns_and_rejected_reads() -> None:
    packet = _valid_packet(status="watch")
    packet["recommendations"] = []
    packet["contradictions"] = [
        {
            "contradiction_id": "contra-agent-demand",
            "summary": "Audience Demand rose for docs but not for buying-intent pages.",
            "weakens_ref_ids": ["movement-agent-studio"],
            "proof_ref_ids": ["proof-demand"],
        }
    ]
    packet["unknowns"] = [
        {
            "unknown_id": "unknown-sales-impact",
            "summary": "Sales objection impact is not proven yet.",
            "limits_ref_ids": ["rec-pmm-agent-studio"],
            "needed_evidence": ["field feedback"],
        }
    ]
    packet["lineage"]["rejected_reads"] = [
        {
            "read_id": "reject-sales-action",
            "reason": "No sales-side demand or objection proof.",
            "proof_ref_ids": ["proof-demand"],
        }
    ]

    validated = _validate(packet)
    assert validated.contradictions[0].summary.startswith("Audience Demand rose")
    assert validated.unknowns[0].needed_evidence == ["field feedback"]
    assert validated.lineage.rejected_reads[0].read_id == "reject-sales-action"
