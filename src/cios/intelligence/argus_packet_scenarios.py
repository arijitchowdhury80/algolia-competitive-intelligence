"""Deterministic Argus packet scenarios for intelligence-spine validation.

These fixtures are not runtime sample data. They are executable expectations
for how the packet should behave across the market states CI-OS must explain.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .argus_packet import ArgusIntelligencePacket


SCENARIO_NAMES = [
    "actionable_day",
    "quiet_verified_day",
    "degraded_day",
    "contradiction_day",
    "stale_evidence_day",
    "missing_demand_day",
    "weekly_trend_day",
    "noisy_duplicate_day",
]


def list_argus_packet_scenarios() -> list[str]:
    """Return Phase 2 scenarios in gate order."""

    return list(SCENARIO_NAMES)


def build_argus_packet_scenario(name: str) -> ArgusIntelligencePacket:
    """Build one named Phase 2 packet fixture."""

    if name not in SCENARIO_NAMES:
        raise ValueError(f"Unknown Argus packet scenario: {name}")

    payload = _base_payload(name)
    if name == "quiet_verified_day":
        _apply_quiet_verified_day(payload)
    elif name == "degraded_day":
        _apply_degraded_day(payload)
    elif name == "contradiction_day":
        _apply_contradiction_day(payload)
    elif name == "stale_evidence_day":
        _apply_stale_evidence_day(payload)
    elif name == "missing_demand_day":
        _apply_missing_demand_day(payload)
    elif name == "weekly_trend_day":
        _apply_weekly_trend_day(payload)
    elif name == "noisy_duplicate_day":
        _apply_noisy_duplicate_day(payload)

    return ArgusIntelligencePacket.model_validate(payload)


def _base_payload(name: str) -> dict[str, Any]:
    run_id = f"{name}-algolia-20260730T130000Z"
    packet_id = f"packet-{run_id}"
    payload: dict[str, Any] = {
        "schema_version": 1,
        "packet_id": packet_id,
        "tenant": {"tenant_id": 1, "slug": "algolia", "display_name": "Algolia"},
        "run": {
            "run_id": run_id,
            "generated_at": "2026-07-30T13:00:00Z",
            "started_at": "2026-07-30T12:58:00Z",
            "completed_at": "2026-07-30T13:00:00Z",
            "hermes_job_id": f"hermes-{name}",
            "hermes_profile": "argus",
            "package_commit": "ae1f3ed",
            "package_release_id": f"cios-{name}-20260730",
            "package_sha256": "b" * 64,
            "produced_by_user": "cios",
            "source": "local_test",
        },
        "cadence": "daily",
        "time_window": {
            "label": "today",
            "start_at": "2026-07-30T00:00:00Z",
            "end_at": "2026-07-30T13:00:00Z",
            "grain": "daily",
            "movement_basis": "new movement against prior daily run",
        },
        "status": "actionable",
        "executive_read": {
            "headline": "Agent Studio demand is creating a PMM timing window.",
            "plain_read": "Algolia has product proof, Audience Demand is visible, and competitor framing is moving toward agentic search.",
            "why_it_matters_to_algolia": "The market can define AI search workflow ownership before Algolia does.",
            "market_belief_implied": "Buyers are comparing AI search through workflow ownership, not only relevance.",
            "what_may_happen_next": "Competitors will keep tying AI search to shopping, assistants, and agent workflows.",
            "decision_posture": "act",
            "primary_movement_id": "movement-agent-studio",
            "primary_recommendation_id": "rec-pmm-agent-studio",
            "proof_ref_ids": ["proof-algolia-agent-studio", "proof-audience-demand", "proof-google-agent-commerce"],
            "confidence_ref_ids": ["product_reality", "market_conversation", "audience_demand"],
        },
        "market_movements": [
            {
                "movement_id": "movement-agent-studio",
                "label": "Agent Studio attention window",
                "summary": "Product proof and Audience Demand overlap while Google frames agentic commerce.",
                "movement_type": "product_and_demand_overlap",
                "direction": "rising",
                "velocity": "high",
                "materiality": "high",
                "time_window": "today",
                "entities": ["Algolia", "Google Vertex AI Search"],
                "capabilities": ["Agent Studio", "AI Search"],
                "themes": ["agentic search", "AI commerce"],
                "evidence_plane_refs": ["product_reality", "market_conversation", "audience_demand"],
                "proof_ref_ids": ["proof-algolia-agent-studio", "proof-audience-demand", "proof-google-agent-commerce"],
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
                "confidence": 0.72,
                "priority_rank": 1,
                "status": "open",
                "movement_ref_ids": ["movement-agent-studio"],
                "proof_ref_ids": ["proof-algolia-agent-studio", "proof-audience-demand", "proof-google-agent-commerce"],
                "scorecard": {
                    "total_score": 72,
                    "verdict": "promote",
                    "dimensions": [
                        {
                            "dimension": "product_reality",
                            "score": 22,
                            "proof_ref_ids": ["proof-algolia-agent-studio"],
                            "evidence_urls": ["https://www.algolia.com/doc/agent-studio"],
                        },
                        {
                            "dimension": "audience_demand",
                            "score": 20,
                            "proof_ref_ids": ["proof-audience-demand"],
                            "evidence_urls": ["looker://algolia/agent-studio"],
                        },
                        {
                            "dimension": "market_conversation",
                            "score": 16,
                            "proof_ref_ids": ["proof-google-agent-commerce"],
                            "evidence_urls": ["https://cloud.google.com/retail/docs"],
                        },
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
                "summary": "Algolia product proof exists for Agent Studio.",
                "signal_count": 2,
                "evidence_count": 2,
                "coverage": {"active": 12, "checked": 12, "failed": 0},
                "proof_ref_ids": ["proof-algolia-agent-studio"],
                "confidence_impact": "supports action",
            },
            {
                "plane": "market_conversation",
                "status": "present",
                "summary": "Google and commerce-search narratives are moving toward agentic workflows.",
                "signal_count": 3,
                "evidence_count": 3,
                "coverage": {"active": 18, "checked": 18, "failed": 0, "raw_signal_count": 3, "duplicates_suppressed": 0},
                "proof_ref_ids": ["proof-google-agent-commerce"],
                "confidence_impact": "supports movement read",
            },
            {
                "plane": "audience_demand",
                "status": "present",
                "summary": "Audience Demand exists for Agent Studio and agentic search topics.",
                "signal_count": 4,
                "evidence_count": 4,
                "coverage": {"active": 8, "checked": 8, "failed": 0},
                "proof_ref_ids": ["proof-audience-demand"],
                "confidence_impact": "supports action timing",
            },
            {
                "plane": "source_health",
                "status": "present",
                "summary": "All required sources were checked for the scenario window.",
                "signal_count": 38,
                "evidence_count": 9,
                "coverage": {"active": 38, "checked": 38, "failed": 0, "stale": 0},
                "proof_ref_ids": [],
                "confidence_impact": "coverage supports current packet",
            },
        ],
        "proof_graph": {
            "root_claim_ids": ["claim-agent-studio-window"],
            "nodes": [
                {
                    "node_id": "proof-algolia-agent-studio",
                    "node_type": "source_event",
                    "label": "Algolia Agent Studio docs",
                    "url": "https://www.algolia.com/doc/agent-studio",
                },
                {
                    "node_id": "proof-audience-demand",
                    "node_type": "audience_demand",
                    "label": "Audience Demand export: Agent Studio",
                    "url": "looker://algolia/agent-studio",
                },
                {
                    "node_id": "proof-google-agent-commerce",
                    "node_type": "source_event",
                    "label": "Google agentic commerce positioning",
                    "url": "https://cloud.google.com/retail/docs",
                },
                {"node_id": "claim-agent-studio-window", "node_type": "claim", "label": "Agent Studio timing window"},
                {"node_id": "movement-agent-studio", "node_type": "pattern", "label": "Agent Studio attention window"},
                {"node_id": "rec-pmm-agent-studio", "node_type": "recommendation", "label": "PMM action"},
            ],
            "edges": [
                {"source_node_id": "proof-algolia-agent-studio", "target_node_id": "claim-agent-studio-window", "edge_type": "supports"},
                {"source_node_id": "proof-audience-demand", "target_node_id": "claim-agent-studio-window", "edge_type": "supports"},
                {"source_node_id": "proof-google-agent-commerce", "target_node_id": "movement-agent-studio", "edge_type": "supports"},
                {"source_node_id": "claim-agent-studio-window", "target_node_id": "movement-agent-studio", "edge_type": "derived_from"},
                {"source_node_id": "movement-agent-studio", "target_node_id": "rec-pmm-agent-studio", "edge_type": "supports"},
            ],
        },
        "contradictions": [],
        "unknowns": [],
        "source_health": {
            "active": 38,
            "checked": 38,
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
        "consumer_state": _consumer_state(packet_id=packet_id, run_id=run_id),
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
            "upstream_objects": ["phase2_fixture"],
            "source_artifacts": [f"phase2/{name}.json"],
            "rejected_reads": [],
        },
    }
    return payload


def _consumer_state(*, packet_id: str, run_id: str) -> dict[str, dict[str, Any]]:
    return {
        "telegram_daily": {"status": "rendered", "run_id": run_id, "packet_id": packet_id},
        "telegram_weekly": {"status": "not_applicable", "run_id": run_id, "packet_id": packet_id},
        "dashboard": {"status": "rendered", "run_id": run_id, "packet_id": packet_id},
        "market_field": {"status": "rendered", "run_id": run_id, "packet_id": packet_id},
        "evidence_lab": {"status": "rendered", "run_id": run_id, "packet_id": packet_id},
        "admin": {"status": "rendered", "run_id": run_id, "packet_id": packet_id},
        "public_status": {"status": "rendered", "run_id": run_id, "packet_id": packet_id},
    }


def _apply_quiet_verified_day(payload: dict[str, Any]) -> None:
    payload["status"] = "quiet_verified"
    payload["executive_read"] = {
        **payload["executive_read"],
        "headline": "No material competitive movement survived verification.",
        "plain_read": "Argus checked the required sources and found no material movement in this window.",
        "why_it_matters_to_algolia": "A quiet day is useful only because coverage was actually checked.",
        "market_belief_implied": "The monitored market did not materially change in the current window.",
        "what_may_happen_next": "Argus will keep watching for fresh competitor, partner, and demand movement.",
        "decision_posture": "quiet",
        "primary_movement_id": None,
        "primary_recommendation_id": None,
        "proof_ref_ids": [],
    }
    payload["market_movements"] = []
    payload["attention_state"] = {"now": [], "monitor": [], "quiet": ["monitored-market"], "blocked": []}
    payload["recommendations"] = []
    payload["proof_graph"] = {"root_claim_ids": [], "nodes": [], "edges": []}
    for plane in payload["evidence_planes"]:
        plane["status"] = "present"
        plane["signal_count"] = 0 if plane["plane"] != "source_health" else payload["source_health"]["checked"]
        plane["proof_ref_ids"] = []


def _apply_degraded_day(payload: dict[str, Any]) -> None:
    payload["status"] = "degraded"
    payload["executive_read"] = {
        **payload["executive_read"],
        "headline": "Argus found movement, but source failures lower trust.",
        "plain_read": "A possible AI commerce movement appeared, but failed source coverage keeps it out of action mode.",
        "why_it_matters_to_algolia": "Acting from partial coverage risks overreading one noisy corner of the market.",
        "decision_posture": "investigate",
        "primary_recommendation_id": None,
    }
    payload["recommendations"] = []
    payload["attention_state"]["monitor"] = ["movement-agent-studio"]
    payload["attention_state"]["now"] = []
    payload["source_health"] = {
        "active": 38,
        "checked": 31,
        "failed": 7,
        "stale": 0,
        "confidence_impact": "source failures reduce confidence; action blocked until recheck",
    }
    payload["quality"]["source_coverage_status"] = "degraded"
    payload["quality"]["known_failures"] = ["7 active sources failed during collection."]
    payload["quality"]["residual_risks"] = ["Competitor movement may be undercounted."]
    payload["evidence_planes"][3]["status"] = "failed"
    payload["evidence_planes"][3]["summary"] = "Seven active sources failed during collection."
    payload["next_monitoring_actions"] = [
        {
            "action_id": "recheck-failed-sources",
            "summary": "Retry failed source collection before promoting any recommendation.",
            "owner": "Argus",
            "evidence_needed": ["successful source recheck"],
        }
    ]


def _apply_contradiction_day(payload: dict[str, Any]) -> None:
    contradiction_id = "contra-demand-vs-product-proof"
    payload["status"] = "watch"
    payload["executive_read"] = {
        **payload["executive_read"],
        "headline": "Audience Demand rose, but product proof conflicts with the claim.",
        "plain_read": "Audience Demand rose for agentic search, but product evidence does not yet prove the matching capability.",
        "why_it_matters_to_algolia": "PMM should not claim a product gap or advantage until the conflict is resolved.",
        "what_may_happen_next": "Argus will recheck product proof and demand quality in the next window.",
        "decision_posture": "wait_for_proof",
        "primary_recommendation_id": None,
    }
    payload["market_movements"][0]["contradiction_ref_ids"] = [contradiction_id]
    payload["recommendations"] = []
    payload["blocked_actions"] = [
        {
            "blocked_action_id": "blocked-pmm-contradiction",
            "owner": "PMM",
            "proposed_action": "Promote the Agent Studio market narrative.",
            "blocked_reason": "Audience Demand rose, but matching product proof is contradictory.",
            "needed_evidence": ["resolved product evidence", "fresh Audience Demand export"],
            "next_monitoring_action_ref_ids": ["resolve-agent-studio-contradiction"],
            "movement_ref_ids": ["movement-agent-studio"],
        }
    ]
    payload["attention_state"] = {"now": [], "monitor": ["movement-agent-studio"], "quiet": [], "blocked": ["blocked-pmm-contradiction"]}
    payload["contradictions"] = [
        {
            "contradiction_id": contradiction_id,
            "summary": "Audience Demand rose while product evidence remains conflicting.",
            "weakens_ref_ids": ["movement-agent-studio", "rec-pmm-agent-studio"],
            "proof_ref_ids": ["proof-audience-demand", "proof-algolia-agent-studio"],
        }
    ]
    payload["unknowns"] = [
        {
            "unknown_id": "unknown-product-proof-resolution",
            "summary": "Argus has not resolved whether the product proof supports the demanded use case.",
            "limits_ref_ids": ["movement-agent-studio"],
            "needed_evidence": ["validated product capability evidence"],
        }
    ]


def _apply_stale_evidence_day(payload: dict[str, Any]) -> None:
    payload["status"] = "stale"
    payload["executive_read"] = {
        **payload["executive_read"],
        "headline": "The latest market read is stale.",
        "plain_read": "Argus has prior movement evidence, but the evidence is too old to publish as current.",
        "why_it_matters_to_algolia": "Stale intelligence can create false urgency.",
        "decision_posture": "wait_for_proof",
        "primary_recommendation_id": None,
    }
    payload["recommendations"] = []
    payload["source_health"]["stale"] = 9
    payload["source_health"]["confidence_impact"] = "stale evidence blocks current publication"
    payload["quality"]["freshness_status"] = "stale"
    payload["quality"]["known_failures"] = ["9 evidence refs are outside the accepted freshness window."]
    payload["consumer_state"]["public_status"]["status"] = "stale"
    for plane in payload["evidence_planes"]:
        if plane["plane"] in {"product_reality", "market_conversation"}:
            plane["status"] = "stale"
            plane["confidence_impact"] = "blocks current action"


def _apply_missing_demand_day(payload: dict[str, Any]) -> None:
    payload["status"] = "watch"
    payload["executive_read"] = {
        **payload["executive_read"],
        "headline": "Product movement exists, but Audience Demand is missing.",
        "plain_read": "Argus sees product proof and conversation movement, but Audience Demand is absent, so no action is promoted.",
        "why_it_matters_to_algolia": "The system should not treat competitor proof as audience response.",
        "decision_posture": "wait_for_proof",
        "primary_recommendation_id": None,
    }
    payload["recommendations"] = []
    payload["attention_state"] = {"now": [], "monitor": ["movement-agent-studio"], "quiet": [], "blocked": ["blocked-demand-missing"]}
    for plane in payload["evidence_planes"]:
        if plane["plane"] == "audience_demand":
            plane["status"] = "missing"
            plane["summary"] = "Audience Demand is missing for this movement."
            plane["signal_count"] = 0
            plane["evidence_count"] = 0
            plane["proof_ref_ids"] = []
            plane["confidence_impact"] = "blocks action promotion"
    payload["blocked_actions"] = [
        {
            "blocked_action_id": "blocked-demand-missing",
            "owner": "PMM",
            "proposed_action": "Turn Agent Studio into an evidence-backed market narrative.",
            "blocked_reason": "Audience Demand is missing.",
            "needed_evidence": ["fresh Audience Demand export"],
            "next_monitoring_action_ref_ids": ["collect-audience-demand"],
            "movement_ref_ids": ["movement-agent-studio"],
        }
    ]
    payload["next_monitoring_actions"] = [
        {
            "action_id": "collect-audience-demand",
            "summary": "Import a fresh Looker or GA4 export for Agent Studio topics.",
            "owner": "Argus",
            "evidence_needed": ["fresh Audience Demand export"],
        }
    ]


def _apply_weekly_trend_day(payload: dict[str, Any]) -> None:
    payload["cadence"] = "weekly"
    payload["time_window"] = {
        "label": "7D",
        "start_at": "2026-07-24T00:00:00Z",
        "end_at": "2026-07-30T13:00:00Z",
        "comparison_start_at": "2026-07-17T00:00:00Z",
        "comparison_end_at": "2026-07-23T23:59:59Z",
        "grain": "weekly",
        "movement_basis": "pattern across three evidence days versus prior week",
    }
    payload["executive_read"] = {
        **payload["executive_read"],
        "headline": "Agentic search pressure persisted across the week.",
        "plain_read": "Agent Studio demand and Google agentic-commerce positioning repeated across the week, turning one daily signal into a market pattern.",
        "what_may_happen_next": "The pattern may become a launch-defense narrative if it persists into the next weekly window.",
    }
    payload["market_movements"][0]["summary"] = "Agent Studio demand and adjacent competitor framing persisted across three evidence days."
    payload["market_movements"][0]["direction"] = "steady"
    payload["market_movements"][0]["velocity"] = "medium"
    payload["market_movements"][0]["time_window"] = "7D"
    payload["consumer_state"]["telegram_daily"]["status"] = "not_applicable"
    payload["consumer_state"]["telegram_weekly"]["status"] = "rendered"


def _apply_noisy_duplicate_day(payload: dict[str, Any]) -> None:
    payload["status"] = "watch"
    payload["executive_read"] = {
        **payload["executive_read"],
        "headline": "Repeated source chatter is not a fresh market movement.",
        "plain_read": "Argus found repeated agentic-search mentions, but duplicate suppression reduced them to one market signal.",
        "why_it_matters_to_algolia": "Repeated syndication should not be mistaken for new competitive pressure.",
        "decision_posture": "watch",
        "primary_recommendation_id": None,
    }
    payload["recommendations"] = []
    payload["market_movements"][0]["velocity"] = "low"
    payload["market_movements"][0]["materiality"] = "medium"
    payload["market_movements"][0]["recommendation_ref_ids"] = []
    payload["attention_state"] = {"now": [], "monitor": ["movement-agent-studio"], "quiet": [], "blocked": []}
    for plane in payload["evidence_planes"]:
        if plane["plane"] == "market_conversation":
            plane["signal_count"] = 1
            plane["evidence_count"] = 1
            plane["coverage"] = {"active": 18, "checked": 18, "failed": 0, "raw_signal_count": 8, "duplicates_suppressed": 7}
            plane["confidence_impact"] = "duplicate suppression prevents false urgency"
    payload["lineage"]["rejected_reads"] = [
        {
            "read_id": "rejected-duplicate-urgency",
            "reason": "Duplicate source chatter cannot promote a recommendation.",
            "proof_ref_ids": ["proof-google-agent-commerce"],
        }
    ]


def build_all_argus_packet_scenarios() -> dict[str, ArgusIntelligencePacket]:
    """Build every Phase 2 fixture keyed by scenario name."""

    return {name: build_argus_packet_scenario(name) for name in SCENARIO_NAMES}


def clone_argus_packet_scenario_payload(name: str) -> dict[str, Any]:
    """Return a mutable scenario payload for tests that need local mutation."""

    payload = _base_payload(name)
    if name != "actionable_day":
        scenario_packet = build_argus_packet_scenario(name)
        return scenario_packet.model_dump(mode="json")
    return deepcopy(payload)


__all__ = [
    "SCENARIO_NAMES",
    "build_all_argus_packet_scenarios",
    "build_argus_packet_scenario",
    "clone_argus_packet_scenario_payload",
    "list_argus_packet_scenarios",
]
