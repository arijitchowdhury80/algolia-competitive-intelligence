from __future__ import annotations

import json

from cios.dashboard.publisher import (
    default_filename,
    publish_to_file,
    to_json_dict,
    to_json_str,
)
from cios.dashboard.state_builder import DashboardStateBuilder
from cios.dashboard.types import DASHBOARD_STATE_SCHEMA_VERSION

from .conftest import (
    FakeCoverageRepository,
    FakeMonitoredCompetitorsRepository,
    FakeProductMarketRepository,
    FakeRunRepository,
    FakeSignalsRepository,
    FakeThesesRepository,
    argus_recommendation_row,
    delta,
    demand_signal_row,
    feature_position_row,
    full_coverage,
    monitored_competitor_row,
    product_market_pattern_row,
    product_market_run_history_row,
)


def _sample_state(tenant_id: int = 7):
    builder = DashboardStateBuilder(
        signals=FakeSignalsRepository({tenant_id: [delta(id=1, materiality_score=0.6)]}),
        theses=FakeThesesRepository({}),
        coverage=FakeCoverageRepository({tenant_id: full_coverage()}),
        runs=FakeRunRepository({}),
    )
    return builder.build(tenant_id=tenant_id, cadence="daily")


def test_to_json_dict_includes_schema_version_and_quiet_flag():
    state = _sample_state()
    payload = to_json_dict(state)
    assert payload["schema_version"] == DASHBOARD_STATE_SCHEMA_VERSION
    assert payload["is_quiet"] is False
    assert payload["tenant_id"] == 7
    assert "product_market_history" in payload
    assert "product_market_trends" in payload
    assert "product_market_heatmap" in payload
    assert "product_market_entity_velocity" in payload
    assert "product_market_theme_heatmap" in payload
    assert "product_market_window_deltas" in payload
    assert "product_market_run" in payload
    assert "intelligence_spine" in payload
    assert "product_market_run_history" in payload
    assert "argus_evidence_needs" in payload
    assert "product_feature_comparison" in payload
    assert "demand_feature_alignment" in payload
    # Bug-4 fix: attention level now derives from the composite attention
    # score (materiality + capped signal volume + capped evidence breadth),
    # not raw materiality alone. A single delta/single evidence url at
    # materiality 0.6 composites to 33/100 -> "monitor", not "watch".
    assert payload["top_attention_level"] == "monitor"


def test_to_json_dict_redacts_local_artifact_paths_from_public_payload():
    state = _sample_state()
    state.product_market_run.next_sweep_plan_path = "/tmp/cios-product-market/algolia/next-sweep-learning-plan.json"
    state.product_market_run.learning_apply_plan_path = "/tmp/cios-product-market/algolia/learning-apply-plan.json"
    state.product_market_run.looker_manifest_path = "/tmp/cios-product-market/algolia/looker-export-manifest.json"
    state.product_market_run.demand_readiness = {
        "status": "blocked_missing_configuration",
        "manual_import": {
            "drop_folder": "/root/.hermes/apps/cios/data/looker/algolia",
            "safe_instruction": "Upload a GA / Looker export.",
        },
        "demand_source_contract": {
            "contract_path": "/tmp/cios-product-market/algolia/demand-source-contract.json",
            "sources": [
                {
                    "source": "manual_csv",
                    "landing_zone": "/root/.hermes/apps/cios/data/looker/algolia",
                }
            ],
        },
        "demand_collection_plan": {
            "topics": [
                {
                    "topic": "Shopping Assistant",
                    "evidence_urls": ["https://constructor.com/changelog/shopping-assistant"],
                }
            ]
        },
    }
    state.operator_handoff.artifact_refs = {
        "dashboard": "/root/.hermes/apps/cios/out/argus-dashboard.json",
        "demand_readiness": "/root/.hermes/apps/cios/out/argus-demand-readiness.json",
    }
    state.operator_handoff.artifact_path = "/tmp/cios-product-market/algolia/argus-operator-handoff.json"
    state.operator_handoff.demand_collection_plan = {
        "drop_folder": "/root/.hermes/apps/cios/data/looker/algolia",
        "topics": [
            {
                "topic": "Shopping Assistant",
                "evidence_urls": ["https://constructor.com/changelog/shopping-assistant"],
            }
        ],
    }
    state.intelligence_spine.evidence_urls = [
        "https://constructor.com/changelog/shopping-assistant",
        "looker://algolia/ga4/topics/shopping-assistant",
    ]

    payload = to_json_dict(state)
    serialized = json.dumps(payload, sort_keys=True)

    assert "/root/" not in serialized
    assert "/tmp/" not in serialized
    assert "https://constructor.com/changelog/shopping-assistant" in serialized
    assert "looker://algolia/ga4/topics/shopping-assistant" in serialized
    assert payload["product_market_run"]["demand_readiness"]["manual_import"] == {
        "safe_instruction": "Upload a GA / Looker export."
    }
    assert payload["product_market_run"]["demand_readiness"]["demand_source_contract"]["sources"] == [
        {"source": "manual_csv"}
    ]
    assert payload["operator_handoff"]["artifact_refs"] == {}
    assert "artifact_path" not in payload["operator_handoff"]


def test_to_json_dict_includes_monitored_source_rows_for_product_muscle_planning():
    builder = DashboardStateBuilder(
        signals=FakeSignalsRepository({1: []}),
        theses=FakeThesesRepository({}),
        coverage=FakeCoverageRepository({1: full_coverage()}),
        runs=FakeRunRepository({}),
        monitored_competitors=FakeMonitoredCompetitorsRepository(
            {
                1: [
                    monitored_competitor_row(
                        competitor_id=7,
                        competitor_name="Algonomy",
                        domain=None,
                        active_source_count=1,
                        monitored_sources=[
                            {
                                "source_id": 71,
                                "source_family": "docs",
                                "url": "https://algonomy.com/docs/commerce-search",
                                "normalized_url": "https://algonomy.com/docs/commerce-search",
                                "status": "active",
                            }
                        ],
                    )
                ]
            }
        ),
    )

    payload = to_json_dict(builder.build(tenant_id=1, cadence="daily"))

    assert payload["monitored_competitors"][0]["monitored_sources"] == [
        {
            "source_id": 71,
            "source_family": "docs",
            "url": "https://algonomy.com/docs/commerce-search",
            "normalized_url": "https://algonomy.com/docs/commerce-search",
            "status": "active",
        }
    ]


def test_to_json_dict_serializes_intelligence_spine_contract():
    repo = FakeProductMarketRepository(
        patterns={1: [product_market_pattern_row()]},
        recommendations={1: [argus_recommendation_row()]},
        demand_signals={1: [demand_signal_row()]},
        feature_positions={1: [feature_position_row()]},
        run_history={
            1: [
                product_market_run_history_row(
                    verdict="actionable",
                    primary_action="Create an AI shopping agent narrative.",
                    evidence_urls=[
                        "https://constructor.com/changelog",
                        "looker://algolia/ga4/topics",
                    ],
                    product_event_count=4,
                    conversation_theme_count=3,
                    demand_signal_count=1,
                    recommendation_count=1,
                    learning_instruction_count=0,
                    learning_instruction_improvement_ids=[],
                )
            ]
        },
    )
    builder = DashboardStateBuilder(
        signals=FakeSignalsRepository({1: []}),
        theses=FakeThesesRepository({}),
        coverage=FakeCoverageRepository({1: full_coverage()}),
        runs=FakeRunRepository({}),
        product_market=repo,
    )

    payload = to_json_dict(builder.build(tenant_id=1, cadence="daily"))

    spine = payload["intelligence_spine"]
    assert spine["verdict"] == "actionable"
    assert spine["can_recommend"] is True
    assert spine["planes"][0]["plane"] == "product_reality"
    assert spine["planes"][1]["plane"] == "market_conversation"
    assert spine["planes"][2]["plane"] == "audience_demand"
    assert spine["planes"][2]["status"] == "present"
    assert spine["evidence_urls"] == [
        "https://constructor.com/changelog",
        "looker://algolia/ga4/topics",
    ]


def test_to_json_dict_serializes_product_market_run_trace():
    builder = DashboardStateBuilder(
        signals=FakeSignalsRepository({1: []}),
        theses=FakeThesesRepository({}),
        coverage=FakeCoverageRepository({1: full_coverage()}),
        runs=FakeRunRepository({
            1: {
                "product_market_summary": {
                    "status": "ran",
                    "product_surface_plan_summary": {
                        "target_count": 2,
                        "target_company_count": 2,
                        "target_companies": ["Constructor", "Coveo"],
                        "surface_family_counts": {"changelog": 1, "docs": 1},
                        "learning_prioritized_count": 1,
                        "prioritized_targets": [{"company_name": "Coveo"}],
                    },
                    "product_muscle_gap_plan": {
                        "monitored_company_count": 4,
                        "covered_company_count": 2,
                        "missing_company_count": 2,
                        "candidate_url_count": 12,
                        "candidate_surface_family_counts": {"docs": 2, "pricing": 2},
                        "missing_companies": [
                            {"company_name": "Elastic", "candidate_surface_urls": []},
                            {"company_name": "Bloomreach", "candidate_surface_urls": []},
                        ],
                    },
                    "runner_summary": {
                        "verdict": "watch",
                        "product_event_count": 4,
                        "conversation_theme_count": 3,
                        "demand_signal_count": 1,
                        "pattern_count": 2,
                        "recommendation_count": 0,
                        "learning_instruction_count": 1,
                        "learning_instruction_improvement_ids": [202],
                        "intelligence_brief": {
                            "verdict": "watch",
                            "top_insight": "Constructor moved first, but coverage learning demoted the action.",
                            "primary_action": None,
                            "watchlist": ["Re-audit Coveo before restoring Constructor priority."],
                            "evidence_urls": ["https://constructor.com/changelog/ai-shopping-agent"],
                            "confidence_limits": ["Recommendation withheld by approved coverage learning."],
                            "next_questions": ["Did Coveo ship a competing capability in docs?"],
                            "next_monitoring_actions": [
                                {
                                    "owner": "Hermes",
                                    "plane": "source_coverage",
                                    "priority": "medium",
                                    "instruction": (
                                        "Recheck Constructor and Algolia source coverage for "
                                        "agentic product discovery."
                                    ),
                                    "reason": "Coverage learning demoted the action.",
                                    "source_families": ["scout_changelog", "web_scan", "ga4_api_export"],
                                    "evidence_urls": [
                                        "https://constructor.com/changelog/ai-shopping-agent"
                                    ],
                                }
                            ],
                            "decision_read": {
                                "status": "watch",
                                "market_direction": (
                                    "agentic product discovery is heating up around Constructor and Algolia."
                                ),
                                "priority_reason": (
                                    "Watch Constructor because coverage learning demoted the action."
                                ),
                                "confidence_basis": [
                                    {
                                        "plane": "product_reality",
                                        "status": "present",
                                        "evidence_count": 4,
                                        "summary": "4 product-reality event(s) captured.",
                                    }
                                ],
                                "tactical_actions": [],
                                "blockers": ["Coverage recheck learning gate is active."],
                            },
                            "demand_read": {
                                "summary": (
                                    "1 rising demand topic found; 1 matched product proof and 0 still need product proof."
                                ),
                                "rising_topic_count": 1,
                                "matched_product_topic_count": 1,
                                "unmatched_demand_topic_count": 0,
                                "top_topics": [
                                    {
                                        "topic": "agentic product discovery",
                                        "matched_product_proof": True,
                                        "missing_planes": [],
                                    }
                                ],
                            },
                            "product_feature_comparison": {
                                "summary": (
                                    "1 capability compared; 0 product gaps, 1 narrative gap, "
                                    "1 demand-backed row."
                                ),
                                "row_count": 1,
                                "product_gap_count": 0,
                                "narrative_gap_count": 1,
                                "demand_backed_count": 1,
                                "rows": [
                                    {
                                        "capability": "agentic product discovery",
                                        "capability_key": "shopping agent",
                                        "assessment": "own_narrative_gap",
                                        "own_company_name": "Algolia",
                                        "own_status": "proven",
                                        "competitors_with_product_proof": ["Constructor"],
                                        "competitors_with_conversation": ["Constructor"],
                                        "has_rising_demand": True,
                                        "demand_signal_count": 1,
                                        "top_demand_change_pct": 0.23,
                                        "recommended_action": (
                                            "Create an Algolia narrative for agentic product discovery "
                                            "using existing product proof."
                                        ),
                                        "evidence_urls": [
                                            "https://constructor.com/changelog/ai-shopping-agent",
                                            "https://constructor.com/blog/ai-shopping-agent",
                                            "https://www.algolia.com/changelog/agentic-discovery",
                                            "looker://algolia/ga4/topics",
                                        ],
                                        "confidence_limits": [],
                                    }
                                ],
                            },
                            "movement_map": {
                                "direction_summary": "agentic product discovery is heating up across Constructor and Algolia.",
                                "hot_capabilities": ["agentic product discovery"],
                                "heat_cells": [
                                    {
                                        "company_name": "Constructor",
                                        "capability": "agentic product discovery",
                                        "heat_level": "hot",
                                        "signal_count": 2,
                                        "recent_count": 2,
                                        "prior_count": 0,
                                        "confidence": 0.78,
                                        "evidence_urls": [
                                            "https://constructor.com/changelog/ai-shopping-agent"
                                        ],
                                    }
                                ],
                                "entity_velocity": [
                                    {
                                        "company_name": "Constructor",
                                        "heat_level": "hot",
                                        "signal_count": 2,
                                        "hot_capabilities": ["agentic product discovery"],
                                        "summary": "Constructor has 2 movement signals, led by agentic product discovery.",
                                        "evidence_urls": [
                                            "https://constructor.com/changelog/ai-shopping-agent"
                                        ],
                                    }
                                ],
                                "evidence_urls": [
                                    "https://constructor.com/changelog/ai-shopping-agent"
                                ],
                                "confidence_limits": [
                                    "Movement is derived from captured product-market pattern memory."
                                ],
                            },
                        },
                    },
                    "stage_ledger": [
                        {
                            "tenant": "algolia",
                            "stage": "product_surface_export",
                            "status": "completed",
                            "started_at": "2026-07-11T22:35:00Z",
                            "ended_at": "2026-07-11T22:35:05Z",
                            "elapsed_s": 5.1,
                        }
                    ],
                    "scout_paths": ["/tmp/cios-product-market/algolia/surface-exports/000030-coveo-docs.json"],
                    "looker_discovered_count": 0,
                    "looker_ready_count": 0,
                    "looker_error_count": 0,
                    "looker_normalized_row_count": 0,
                    "demand_readiness": {
                        "status": "ready_to_export_ga4",
                        "next_hermes_action": "run_ga4_export_then_prepare_demand",
                    },
                }
            }
        }),
    )
    payload = to_json_dict(builder.build(tenant_id=1, cadence="daily"))

    assert payload["product_market_run"]["status"] == "ran"
    assert payload["product_market_run"]["target_company_count"] == 2
    assert payload["product_market_run"]["target_companies"] == ["Constructor", "Coveo"]
    assert payload["product_market_run"]["surface_family_counts"] == {"changelog": 1, "docs": 1}
    assert payload["product_market_run"]["product_muscle_gap_plan"]["missing_company_count"] == 2
    assert payload["product_market_run"]["product_muscle_gap_plan"]["candidate_url_count"] == 12
    assert payload["product_market_run"]["learning_prioritized_count"] == 1
    assert payload["product_market_run"]["runner_verdict"] == "watch"
    assert payload["product_market_run"]["product_event_count"] == 4
    assert payload["product_market_run"]["conversation_theme_count"] == 3
    assert payload["product_market_run"]["demand_signal_count"] == 1
    assert payload["product_market_run"]["pattern_count"] == 2
    assert payload["product_market_run"]["recommendation_count"] == 0
    assert payload["product_market_run"]["consumed_learning_ids"] == [202]
    assert payload["product_market_run"]["demand_plane_status"] == "processed"
    assert payload["product_market_run"]["demand_readiness"]["status"] == "ready_to_export_ga4"
    assert (
        payload["product_market_run"]["demand_readiness"]["next_hermes_action"]
        == "run_ga4_export_then_prepare_demand"
    )
    assert payload["product_market_run"]["looker_discovered_count"] == 0
    assert payload["product_market_run"]["looker_normalized_row_count"] == 0
    assert payload["product_market_run"]["intelligence_brief"]["top_insight"].startswith("Constructor moved first")
    assert payload["product_market_run"]["intelligence_brief"]["evidence_urls"] == [
        "https://constructor.com/changelog/ai-shopping-agent"
    ]
    assert payload["product_market_run"]["next_monitoring_actions"] == [
        {
            "owner": "Hermes",
            "plane": "source_coverage",
            "priority": "medium",
            "instruction": "Recheck Constructor and Algolia source coverage for agentic product discovery.",
            "reason": "Coverage learning demoted the action.",
            "source_families": ["scout_changelog", "web_scan", "ga4_api_export"],
            "evidence_urls": ["https://constructor.com/changelog/ai-shopping-agent"],
        }
    ]
    assert payload["product_market_run"]["decision_read"]["status"] == "watch"
    assert payload["product_market_run"]["decision_read"]["priority_reason"].startswith("Watch Constructor")
    assert payload["product_market_run"]["intelligence_brief"]["demand_read"]["summary"].startswith(
        "1 rising demand topic"
    )
    assert payload["product_market_run"]["product_feature_comparison_read"]["summary"].startswith(
        "1 capability compared"
    )
    assert payload["product_market_run"]["product_feature_comparison_read"]["rows"][0]["assessment"] == (
        "own_narrative_gap"
    )
    assert payload["product_market_run"]["movement_map"]["direction_summary"].startswith(
        "agentic product discovery is heating up"
    )
    assert payload["product_market_run"]["movement_map"]["hot_capabilities"] == [
        "agentic product discovery"
    ]
    assert payload["product_market_run"]["stage_ledger"] == [
        {
            "tenant": "algolia",
            "stage": "product_surface_export",
            "status": "completed",
            "started_at": "2026-07-11T22:35:00Z",
            "ended_at": "2026-07-11T22:35:05Z",
            "elapsed_s": 5.1,
        }
    ]


def test_serialization_is_stable_across_calls():
    state = _sample_state()
    first = to_json_str(state)
    second = to_json_str(state)
    assert first == second


def test_serialization_is_json_parseable_and_round_trips_key_fields():
    state = _sample_state()
    parsed = json.loads(to_json_str(state))
    assert parsed["competitor_cards"][0]["competitor_id"] == 1
    assert parsed["coverage"]["lanes"]


def test_publish_to_file_writes_readable_json(tmp_path):
    state = _sample_state()
    out = publish_to_file(state, tmp_path / "sub" / default_filename(state))
    assert out.exists()
    parsed = json.loads(out.read_text(encoding="utf-8"))
    assert parsed["schema_version"] == DASHBOARD_STATE_SCHEMA_VERSION


def test_default_filename_is_versioned_and_tenant_scoped():
    state = _sample_state(tenant_id=42)
    name = default_filename(state)
    assert f"v{DASHBOARD_STATE_SCHEMA_VERSION}" in name
    assert "42" in name
    assert "daily" in name
