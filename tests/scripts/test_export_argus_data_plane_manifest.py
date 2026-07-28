"""Contract tests for the Hermes-facing Argus data-plane manifest."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "export_argus_data_plane_manifest.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("export_argus_data_plane_manifest", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _dashboard_payload() -> dict:
    return {
        "schema_version": 23,
        "generated_at": "2026-07-12T02:50:53Z",
        "monitored_competitors": [
            {"name": "Constructor", "status": "active", "active_source_count": 4},
            {"name": "Coveo", "status": "active", "active_source_count": 6},
        ],
        "source_health": {
            "active_source_count": 48,
            "failed_source_count": 5,
            "checked_source_count": 45,
        },
        "product_market_run": {
            "status": "ran",
            "runner_verdict": "watch",
            "decision_read": {
                "status": "watch",
                "market_direction": "agentic product discovery is heating up around Constructor and Algolia.",
                "priority_reason": "Watch Constructor until tenant-side demand evidence arrives.",
                "confidence_basis": [
                    {
                        "plane": "product_reality",
                        "status": "present",
                        "evidence_count": 4,
                        "summary": "4 product-reality event(s) captured.",
                    },
                    {
                        "plane": "audience_demand",
                        "status": "missing",
                        "evidence_count": 0,
                        "summary": "No tenant-side demand evidence was captured.",
                    },
                ],
                "tactical_actions": [],
                "blockers": ["No tenant-side demand evidence was captured."],
                "evidence_urls": ["https://constructor.com/changelog/ai-shopping-agent"],
            },
            "intelligence_brief": {
                "top_insight": "Constructor moved, but demand evidence is missing.",
                "confidence_limits": ["No tenant-side demand evidence was captured."],
                "next_monitoring_actions": [
                    {
                        "owner": "Hermes",
                        "plane": "audience_demand",
                        "priority": "critical",
                        "instruction": (
                            "Collect GA / Looker demand evidence for agentic product discovery "
                            "before promoting this market movement into a recommendation."
                        ),
                        "reason": (
                            "Argus found a product-market pattern, but recommendations require "
                            "tenant-side demand evidence."
                        ),
                        "source_families": ["ga4_api_export", "ga_looker_manual_export"],
                        "evidence_urls": [
                            "https://constructor.com/changelog/ai-shopping-agent",
                            "https://constructor.com/blog/ai-shopping-agent",
                        ],
                    }
                ],
            },
            "target_count": 33,
            "target_company_count": 12,
            "target_companies": ["Algolia", "Constructor", "Coveo"],
            "surface_family_counts": {"docs": 9, "changelog": 3},
            "product_event_count": 4,
            "conversation_theme_count": 3,
            "demand_signal_count": 0,
            "pattern_count": 2,
            "recommendation_count": 0,
            "demand_plane_status": "missing",
            "learning_instruction_count": 1,
            "consumed_learning_ids": [77],
            "next_sweep_plan_path": "/tmp/cios-product-market/algolia/next-sweep-learning-plan.json",
            "product_muscle_gap_plan": {
                "missing_company_count": 2,
                "candidate_url_count": 12,
            },
            "stage_ledger": [
                {"stage": "product_surface_plan", "status": "succeeded"},
                {"stage": "demand_export", "status": "skipped"},
            ],
        },
    }


def test_data_plane_manifest_explains_brain_muscle_and_blocks_action_without_demand() -> None:
    module = _load_module()

    payload = module.build_data_plane_manifest_payload(
        tenant_slug="algolia",
        dashboard=_dashboard_payload(),
        demand_readiness={
            "status": "blocked_missing_demand_source",
            "next_hermes_action": "configure_ga4_or_upload_demand_export",
            "summary": "No tenant-side demand source is ready.",
            "manual_import": {"drop_folder": "/root/.hermes/apps/cios/data/looker/algolia"},
            "demand_source_contract": {
                "schema_version": 1,
                "tenant_slug": "algolia",
                "status": "blocked_no_ready_source",
                "ready_source_count": 0,
                "contract_path": "/tmp/cios-product-market/algolia/demand-source-contract.json",
                "sources": [
                    {
                        "source_id": "manual_looker_export",
                        "source_family": "ga_looker_manual_export",
                        "label": "Manual GA / Looker export",
                        "status": "waiting_for_upload",
                        "ready": False,
                        "landing_zone": "/root/.hermes/apps/cios/data/looker/algolia",
                        "cadence": "operator_uploaded_or_daily_when_queued",
                        "owner": "operator",
                    },
                    {
                        "source_id": "ga4_connector",
                        "source_family": "ga4_api_export",
                        "label": "GA4 API export",
                        "status": "disabled",
                        "ready": False,
                        "cadence": "daily_when_configured",
                        "owner": "Hermes",
                    },
                ],
            },
        },
        demand_intake={
            "status": "blocked_missing_demand_source",
            "command_status": "blocked",
            "exit_code": 2,
            "mode": "blocked",
            "next_hermes_action": "configure_ga4_or_upload_demand_export",
            "summary_path": "/tmp/cios-product-market/algolia/demand-intake-runs/run/demand-intake-summary.json",
        },
        evidence_work_queue={
            "work_item_count": 1,
            "blocking_count": 1,
            "limiting_count": 0,
            "items": [
                {
                    "work_item_id": "argus-evidence:17:demand",
                    "evidence_plane": "demand",
                    "severity": "blocks_action",
                    "title": "Demand plane missing",
                    "next_step": "Upload GA4 / Looker demand export.",
                }
            ],
        },
        operator_handoff={
            "status": "blocked_on_evidence",
            "argus_readiness": "not_actionable",
            "next_operator_action": "Upload GA4 / Looker demand export.",
        },
        artifact_refs={
            "dashboard": "/app/out/argus-dashboard.json",
            "demand_readiness": "/app/out/argus-demand-readiness.json",
            "demand_intake": "/app/out/argus-demand-intake.json",
            "evidence_work_queue": "/app/out/argus-evidence-work-queue.json",
            "operator_handoff": "/app/out/argus-operator-handoff.json",
        },
        generated_at="2026-07-12T03:00:00Z",
    )

    assert payload["schema_version"] == 1
    assert payload["tenant_slug"] == "algolia"
    assert payload["generated_at"] == "2026-07-12T03:00:00Z"
    assert payload["status"] == "blocked_on_evidence"
    assert payload["argus_readiness"] == "not_actionable"
    assert payload["argus_decision"] == {
        "status": "watch",
        "market_direction": "agentic product discovery is heating up around Constructor and Algolia.",
        "priority_reason": "Watch Constructor until tenant-side demand evidence arrives.",
        "tactical_action_count": 0,
        "blocker_count": 1,
        "evidence_url_count": 1,
        "confidence_basis": [
            {
                "plane": "product_reality",
                "status": "present",
                "evidence_count": 4,
            },
            {
                "plane": "audience_demand",
                "status": "missing",
                "evidence_count": 0,
            },
        ],
    }
    assert payload["next_hermes_action"] == "configure_ga4_or_upload_demand_export"
    assert payload["source_of_truth"] == {
        "runtime": "Hermes",
        "domain_package": "CI-OS",
        "database": "Postgres evidence ledger",
        "ui_role": "derived readout only",
    }
    assert payload["artifact_refs"]["dashboard"] == "/app/out/argus-dashboard.json"
    assert payload["artifact_refs"]["demand_intake"] == "/app/out/argus-demand-intake.json"
    assert payload["next_monitoring_actions"] == [
        {
            "owner": "Hermes",
            "plane": "audience_demand",
            "priority": "critical",
            "instruction": (
                "Collect GA / Looker demand evidence for agentic product discovery "
                "before promoting this market movement into a recommendation."
            ),
            "reason": (
                "Argus found a product-market pattern, but recommendations require "
                "tenant-side demand evidence."
            ),
            "source_families": ["ga4_api_export", "ga_looker_manual_export"],
            "evidence_urls": [
                "https://constructor.com/changelog/ai-shopping-agent",
                "https://constructor.com/blog/ai-shopping-agent",
            ],
        }
    ]

    planes = payload["planes"]
    assert planes["registry_coverage"]["status"] == "degraded"
    assert planes["registry_coverage"]["counts"]["monitored_competitor_count"] == 2
    assert planes["registry_coverage"]["counts"]["active_source_count"] == 48
    assert planes["registry_coverage"]["counts"]["failed_source_count"] == 5
    assert planes["product_reality"]["status"] == "present"
    assert planes["product_reality"]["counts"]["product_event_count"] == 4
    assert planes["product_reality"]["counts"]["product_surface_target_count"] == 33
    assert planes["product_reality"]["storage"] == [
        "product_surfaces",
        "feature_capabilities",
        "product_change_events",
        "company_feature_positions",
        "feature_evidence_links",
    ]
    assert planes["market_conversation"]["status"] == "present"
    assert planes["market_conversation"]["counts"]["conversation_theme_count"] == 3
    assert planes["audience_demand"]["status"] == "blocked_missing_demand_source"
    assert planes["audience_demand"]["blocks_action"] is True
    assert planes["audience_demand"]["next_hermes_action"] == "configure_ga4_or_upload_demand_export"
    assert planes["audience_demand"]["details"]["demand_intake"] == {
        "status": "blocked_missing_demand_source",
        "command_status": "blocked",
        "exit_code": 2,
        "mode": "blocked",
        "next_hermes_action": "configure_ga4_or_upload_demand_export",
        "summary_path": "/tmp/cios-product-market/algolia/demand-intake-runs/run/demand-intake-summary.json",
    }
    assert planes["audience_demand"]["details"]["demand_source_contract"] == {
        "schema_version": 1,
        "tenant_slug": "algolia",
        "status": "blocked_no_ready_source",
        "ready_source_count": 0,
        "contract_path": "/tmp/cios-product-market/algolia/demand-source-contract.json",
        "sources": [
            {
                "source_id": "manual_looker_export",
                "source_family": "ga_looker_manual_export",
                "label": "Manual GA / Looker export",
                "status": "waiting_for_upload",
                "ready": False,
                "landing_zone": "/root/.hermes/apps/cios/data/looker/algolia",
                "cadence": "operator_uploaded_or_daily_when_queued",
                "owner": "operator",
            },
            {
                "source_id": "ga4_connector",
                "source_family": "ga4_api_export",
                "label": "GA4 API export",
                "status": "disabled",
                "ready": False,
                "cadence": "daily_when_configured",
                "owner": "Hermes",
            },
        ],
    }
    assert planes["operator_learning"]["status"] == "present"
    assert planes["operator_learning"]["counts"]["consumed_learning_count"] == 1
    assert planes["run_truth"]["status"] == "present"
    assert planes["run_truth"]["counts"]["stage_count"] == 2

    assert payload["blockers"] == [
        {
            "plane": "audience_demand",
            "severity": "blocks_action",
            "title": "Demand plane missing",
            "next_step": "Upload GA4 / Looker demand export.",
            "work_item_id": "argus-evidence:17:demand",
            "demand_source_contract_status": "blocked_no_ready_source",
        }
    ]
    assert payload["safety"]["ui_must_not_invent_semantics"] is True
    assert payload["safety"]["recommendations_require_backend_scorecards"] is True


def test_data_plane_manifest_includes_product_muscle_work_queue_as_product_reality_blocker() -> None:
    module = _load_module()
    dashboard = _dashboard_payload()
    dashboard["product_market_run"]["demand_signal_count"] = 3
    dashboard["product_market_run"]["demand_plane_status"] = "processed"

    payload = module.build_data_plane_manifest_payload(
        tenant_slug="algolia",
        dashboard=dashboard,
        demand_readiness={"status": "processed"},
        evidence_work_queue={"work_item_count": 0, "blocking_count": 0, "limiting_count": 0, "items": []},
        product_muscle_work_queue={
            "work_item_count": 1,
            "blocking_count": 1,
            "limiting_count": 0,
            "items": [
                {
                    "work_item_id": "product-muscle:competitor:2:missing-surfaces",
                    "severity": "blocks_feature_matrix",
                    "title": "Bloomreach has no active product surfaces",
                    "next_step": "Add a changelog, docs, release notes, API docs, pricing, integration, or product page source.",
                    "company_name": "Bloomreach",
                }
            ],
        },
        operator_handoff={
            "status": "blocked_on_evidence",
            "argus_readiness": "not_actionable",
            "next_operator_action": "Add a changelog, docs, release notes, API docs, pricing, integration, or product page source.",
        },
        artifact_refs={
            "product_muscle_work_queue": "/app/out/argus-product-muscle-work-queue.json",
        },
        generated_at="2026-07-12T05:30:00Z",
    )

    assert payload["status"] == "blocked_on_evidence"
    assert payload["next_hermes_action"].startswith("Add a changelog")
    assert payload["artifact_refs"]["product_muscle_work_queue"] == "/app/out/argus-product-muscle-work-queue.json"
    product_plane = payload["planes"]["product_reality"]
    assert product_plane["status"] == "blocked_missing_product_surfaces"
    assert product_plane["blocks_action"] is True
    assert product_plane["counts"]["product_muscle_work_item_count"] == 1
    assert product_plane["counts"]["product_muscle_blocking_count"] == 1
    assert payload["blockers"] == [
        {
            "plane": "product_reality",
            "severity": "blocks_feature_matrix",
            "title": "Bloomreach has no active product surfaces",
            "next_step": "Add a changelog, docs, release notes, API docs, pricing, integration, or product page source.",
            "work_item_id": "product-muscle:competitor:2:missing-surfaces",
        }
    ]


def test_data_plane_manifest_exposes_product_muscle_work_order_for_limiting_items() -> None:
    module = _load_module()
    dashboard = _dashboard_payload()
    dashboard["product_market_run"]["demand_signal_count"] = 3
    dashboard["product_market_run"]["demand_plane_status"] = "processed"

    payload = module.build_data_plane_manifest_payload(
        tenant_slug="algolia",
        dashboard=dashboard,
        demand_readiness={"status": "processed"},
        evidence_work_queue={"work_item_count": 0, "blocking_count": 0, "limiting_count": 0, "items": []},
        product_muscle_work_queue={
            "work_item_count": 1,
            "blocking_count": 0,
            "limiting_count": 1,
            "items": [
                {
                    "work_item_id": "product-muscle:competitor:9:no-feature-evidence",
                    "severity": "limits_confidence",
                    "title": "Klevu has product surfaces but no feature evidence",
                    "next_step": (
                        "Run Scout product-surface extraction for the active surfaces, then refresh Argus "
                        "from the evidence ledger."
                    ),
                    "company_name": "Klevu",
                    "operator_surface": "Product surfaces",
                    "primary_action_label": "Open product surfaces",
                    "primary_action_href": "/admin?tenant=algolia#add-product-surface",
                    "primary_action_method": "get",
                }
            ],
        },
        operator_handoff={"status": "ready_for_operator_review"},
        artifact_refs={},
        generated_at="2026-07-12T20:30:00Z",
    )

    product_plane = payload["planes"]["product_reality"]
    assert product_plane["status"] == "limited_by_product_surface_evidence"
    assert product_plane["blocks_action"] is False
    assert product_plane["details"]["product_muscle_work_queue"] == {
        "status": "limited",
        "work_item_count": 1,
        "blocking_count": 0,
        "limiting_count": 1,
        "items": [
            {
                "work_item_id": "product-muscle:competitor:9:no-feature-evidence",
                "severity": "limits_confidence",
                "title": "Klevu has product surfaces but no feature evidence",
                "next_step": (
                    "Run Scout product-surface extraction for the active surfaces, then refresh Argus "
                    "from the evidence ledger."
                ),
                "company_name": "Klevu",
                "operator_surface": "Product surfaces",
                "operator_commands": [
                    {
                        "label": "Open product surfaces",
                        "method": "get",
                        "surface": "Product surfaces",
                        "route_kind": "admin",
                    }
                ],
            }
        ],
    }


def test_data_plane_manifest_uses_product_surface_execution_summary_as_product_reality_truth() -> None:
    module = _load_module()
    dashboard = _dashboard_payload()
    dashboard["product_market_run"]["product_event_count"] = 0
    dashboard["product_market_run"]["demand_signal_count"] = 3
    dashboard["product_market_run"]["demand_plane_status"] = "processed"
    dashboard["product_market_run"]["product_surface_execution_summary"] = {
        "product_plane_status": "empty",
        "planned": 2,
        "succeeded": 0,
        "empty": 2,
        "failed": 0,
        "product_row_count": 0,
        "empty_scout_paths": [
            "/tmp/cios-product-market/algolia/surface-exports/000031-coveo-docs.json",
            "/tmp/cios-product-market/algolia/surface-exports/000032-elastic-changelog.json",
        ],
        "empty_outputs": [
            {
                "output_path": "/tmp/cios-product-market/algolia/surface-exports/000031-coveo-docs.json",
                "company_name": "Coveo",
                "surface_family": "docs",
            },
            {
                "output_path": "/tmp/cios-product-market/algolia/surface-exports/000032-elastic-changelog.json",
                "company_name": "Elastic",
                "surface_family": "changelog",
            },
        ],
        "company_row_counts": {},
        "surface_family_row_counts": {},
    }

    payload = module.build_data_plane_manifest_payload(
        tenant_slug="algolia",
        dashboard=dashboard,
        demand_readiness={"status": "processed"},
        evidence_work_queue={"work_item_count": 0, "blocking_count": 0, "limiting_count": 0, "items": []},
        product_muscle_work_queue={"work_item_count": 0, "blocking_count": 0, "limiting_count": 0, "items": []},
        operator_handoff={"status": "ready_for_operator_review", "argus_readiness": "actionable"},
        generated_at="2026-07-12T18:30:00Z",
    )

    product_plane = payload["planes"]["product_reality"]
    assert product_plane["status"] == "empty_product_surface_outputs"
    assert product_plane["blocks_action"] is True
    assert product_plane["counts"]["product_surface_planned_count"] == 2
    assert product_plane["counts"]["product_surface_empty_count"] == 2
    assert product_plane["counts"]["product_surface_extracted_row_count"] == 0
    assert product_plane["details"]["product_surface_execution"] == {
        "product_plane_status": "empty",
        "planned": 2,
        "succeeded": 0,
        "empty": 2,
        "failed": 0,
        "product_row_count": 0,
        "empty_outputs": [
            {"company_name": "Coveo", "surface_family": "docs"},
            {"company_name": "Elastic", "surface_family": "changelog"},
        ],
        "company_row_counts": {},
        "surface_family_row_counts": {},
    }
    assert payload["status"] == "blocked_on_evidence"
    assert payload["next_hermes_action"] == "Repair or replace empty product-surface targets: Coveo docs, Elastic changelog."
    assert payload["blockers"] == [
        {
            "plane": "product_reality",
            "severity": "blocks_feature_matrix",
            "title": "Product surface extraction returned no product proof",
            "next_step": "Repair or replace empty product-surface targets: Coveo docs, Elastic changelog.",
            "work_item_id": "product-surface-execution:empty",
            "empty_outputs": [
                {"company_name": "Coveo", "surface_family": "docs"},
                {"company_name": "Elastic", "surface_family": "changelog"},
            ],
        }
    ]
    assert "/tmp/" not in json.dumps(product_plane, sort_keys=True)


def test_data_plane_manifest_counts_list_shaped_source_health_rows() -> None:
    module = _load_module()
    dashboard = _dashboard_payload()
    dashboard["source_health"] = [
        {
            "source_id": 1,
            "status": "active",
            "checked_at": "2026-07-12T20:00:00Z",
            "latest_event_type": "ok",
        },
        {
            "source_id": 2,
            "status": "active",
            "checked_at": "2026-07-12T20:01:00Z",
            "latest_event_type": "fetch_error",
        },
        {
            "source_id": 3,
            "status": "active",
            "checked_at": None,
            "latest_event_type": None,
        },
        {
            "source_id": 4,
            "status": "paused",
            "checked_at": "2026-07-12T20:02:00Z",
            "latest_event_type": "skipped",
        },
    ]

    payload = module.build_data_plane_manifest_payload(
        tenant_slug="algolia",
        dashboard=dashboard,
        demand_readiness={"status": "processed"},
        generated_at="2026-07-12T20:34:00Z",
    )

    registry = payload["planes"]["registry_coverage"]
    assert registry["status"] == "degraded"
    assert registry["counts"]["active_source_count"] == 3
    assert registry["counts"]["checked_source_count"] == 2
    assert registry["counts"]["failed_source_count"] == 1


def test_data_plane_manifest_marks_actionable_when_all_planes_are_ready() -> None:
    module = _load_module()
    dashboard = _dashboard_payload()
    dashboard["source_health"]["failed_source_count"] = 0
    dashboard["product_market_run"]["demand_signal_count"] = 5
    dashboard["product_market_run"]["demand_plane_status"] = "processed"
    dashboard["product_market_run"]["recommendation_count"] = 2

    payload = module.build_data_plane_manifest_payload(
        tenant_slug="algolia",
        dashboard=dashboard,
        demand_readiness={
            "status": "processed",
            "next_hermes_action": "continue_product_market_synthesis",
        },
        evidence_work_queue={"work_item_count": 0, "blocking_count": 0, "limiting_count": 0, "items": []},
        operator_handoff={"status": "ready_for_operator_review", "argus_readiness": "actionable"},
        generated_at="2026-07-12T03:00:00Z",
    )

    assert payload["status"] == "ready_for_operator_review"
    assert payload["argus_readiness"] == "actionable"
    assert payload["next_hermes_action"] == "review_scored_recommendations"
    assert payload["planes"]["audience_demand"]["status"] == "processed"
    assert payload["planes"]["audience_demand"]["blocks_action"] is False
    assert payload["planes"]["audience_demand"]["counts"]["demand_signal_count"] == 5
    assert payload["blockers"] == []


def test_data_plane_manifest_uses_successful_demand_intake_as_processed_signal() -> None:
    module = _load_module()
    dashboard = _dashboard_payload()
    dashboard["product_market_run"]["demand_signal_count"] = 0
    dashboard["product_market_run"]["demand_plane_status"] = "missing"

    payload = module.build_data_plane_manifest_payload(
        tenant_slug="algolia",
        dashboard=dashboard,
        demand_readiness={"status": "blocked_missing_demand_source"},
        demand_intake={
            "status": "demand_imported_and_argus_refreshed",
            "command_status": "ok",
            "exit_code": 0,
            "mode": "queued_manual_export",
            "next_hermes_action": "continue_product_market_synthesis",
            "demand_import": {
                "prepare": {"normalized_row_count": 4, "ready_count": 1},
                "demand_ledger": {"demand_signal_count": 4},
                "argus_read": {"top_insight": "Demand now supports the agentic commerce read."},
            },
        },
        evidence_work_queue={"work_item_count": 0, "blocking_count": 0, "limiting_count": 0, "items": []},
        operator_handoff={"status": "ready_for_operator_review", "argus_readiness": "actionable"},
        generated_at="2026-07-12T09:05:00Z",
    )

    demand_plane = payload["planes"]["audience_demand"]
    assert demand_plane["status"] == "processed"
    assert demand_plane["blocks_action"] is False
    assert demand_plane["counts"]["demand_signal_count"] == 4
    assert demand_plane["counts"]["looker_normalized_row_count"] == 4
    assert demand_plane["next_hermes_action"] == "continue_product_market_synthesis"
    assert demand_plane["details"]["demand_intake"]["argus_top_insight"] == (
        "Demand now supports the agentic commerce read."
    )


def test_data_plane_manifest_blocks_action_when_demand_intake_fails_without_signals() -> None:
    module = _load_module()
    dashboard = _dashboard_payload()
    dashboard["product_market_run"]["demand_signal_count"] = 0
    dashboard["product_market_run"]["demand_plane_status"] = "queued_manual_export"

    payload = module.build_data_plane_manifest_payload(
        tenant_slug="algolia",
        dashboard=dashboard,
        demand_readiness={
            "status": "queued_manual_export",
            "summary": "A demand export is queued but no rows have been imported yet.",
            "next_hermes_action": "run_argus_demand_intake",
        },
        demand_intake={
            "status": "demand_import_failed",
            "command_status": "failed",
            "exit_code": 1,
            "mode": "manual_export",
            "next_hermes_action": "repair_demand_import_and_rerun_intake",
        },
        evidence_work_queue={"work_item_count": 0, "blocking_count": 0, "limiting_count": 0, "items": []},
        operator_handoff={"status": "ready_for_operator_review", "argus_readiness": "actionable"},
        generated_at="2026-07-12T10:15:00Z",
    )

    demand_plane = payload["planes"]["audience_demand"]
    assert payload["status"] == "blocked_on_evidence"
    assert payload["next_hermes_action"] == "repair_demand_import_and_rerun_intake"
    assert demand_plane["status"] == "demand_import_failed"
    assert demand_plane["blocks_action"] is True
    assert demand_plane["details"]["demand_intake"]["status"] == "demand_import_failed"
    assert payload["blockers"] == [
        {
            "plane": "audience_demand",
            "severity": "blocks_action",
            "title": "Demand plane missing",
            "next_step": "repair_demand_import_and_rerun_intake",
            "work_item_id": None,
        }
    ]


def test_data_plane_manifest_exposes_sanitized_demand_operator_commands_without_admin_hrefs() -> None:
    module = _load_module()

    payload = module.build_data_plane_manifest_payload(
        tenant_slug="algolia",
        dashboard=_dashboard_payload(),
        demand_readiness={
            "status": "blocked_missing_demand_source",
            "next_hermes_action": "configure_ga4_or_upload_demand_export",
            "summary": "No tenant-side demand source is ready.",
            "operator_actions": [
                {
                    "href": "/api/tenants/algolia/argus/demand-imports/template",
                    "label": "Download demand template",
                    "method": "get",
                    "surface": "Demand imports",
                },
                {
                    "href": "/admin?tenant=algolia#inward-demand",
                    "label": "Open demand admin",
                    "method": "get",
                    "surface": "Admin",
                },
                {
                    "href": "/admin/algolia/argus/ga4-export",
                    "label": "Run GA4 export now",
                    "method": "post",
                    "surface": "GA4 connector",
                },
            ],
        },
        demand_intake={
            "status": "blocked_missing_demand_source",
            "command_status": "blocked",
            "exit_code": 2,
        },
        evidence_work_queue={"work_item_count": 0, "blocking_count": 0, "limiting_count": 0, "items": []},
        generated_at="2026-07-12T10:30:00Z",
    )

    commands = payload["planes"]["audience_demand"]["details"]["operator_commands"]
    assert commands == [
        {
            "label": "Download demand template",
            "method": "get",
            "surface": "Demand imports",
            "route_kind": "api",
        },
        {
            "label": "Open demand admin",
            "method": "get",
            "surface": "Admin",
            "route_kind": "admin",
        },
        {
            "label": "Run GA4 export now",
            "method": "post",
            "surface": "GA4 connector",
            "route_kind": "admin",
        },
    ]
    assert "href" not in json.dumps(commands)
    assert payload["blockers"][0]["operator_commands"] == commands


def test_data_plane_manifest_carries_demand_collection_plan_into_audience_plane() -> None:
    module = _load_module()

    payload = module.build_data_plane_manifest_payload(
        tenant_slug="algolia",
        dashboard=_dashboard_payload(),
        demand_readiness={
            "status": "blocked_missing_demand_source",
            "next_hermes_action": "configure_ga4_or_upload_demand_export",
            "summary": "No tenant-side demand source is ready.",
            "demand_collection_plan": {
                "status": "needs_demand_source",
                "topic_count": 1,
                "source_dashboard_field": "product_market_run.product_feature_comparison_read.rows",
                "topics": [
                    {
                        "rank": 1,
                        "topic": "AI Assistant",
                        "capability_key": "ai assistant",
                        "assessment": "own_product_gap",
                        "suggested_filter_terms": ["AI Assistant", "assistant"],
                    }
                ],
                "template_fields": ["Page title", "Page path", "Engaged sessions"],
            },
        },
        artifact_refs={
            "demand_plan_template": "/app/out/argus-demand-plan-template.csv",
        },
        evidence_work_queue={"work_item_count": 0, "blocking_count": 0, "limiting_count": 0, "items": []},
        generated_at="2026-07-12T10:45:00Z",
    )

    demand_plan = payload["planes"]["audience_demand"]["details"]["demand_collection_plan"]
    assert demand_plan["status"] == "needs_demand_source"
    assert demand_plan["topic_count"] == 1
    assert demand_plan["topics"][0]["capability_key"] == "ai assistant"
    assert demand_plan["source_dashboard_field"] == "product_market_run.product_feature_comparison_read.rows"
    assert payload["artifact_refs"]["demand_plan_template"] == "/app/out/argus-demand-plan-template.csv"
    assert payload["planes"]["audience_demand"]["details"]["demand_plan_template"] == {
        "status": "generated",
        "format": "csv",
        "filename": "argus-demand-plan-template.csv",
        "artifact_ref": "/app/out/argus-demand-plan-template.csv",
    }


def test_data_plane_manifest_enriches_existing_demand_blocker_with_collection_plan_topics() -> None:
    module = _load_module()

    payload = module.build_data_plane_manifest_payload(
        tenant_slug="algolia",
        dashboard=_dashboard_payload(),
        demand_readiness={
            "status": "blocked_missing_demand_source",
            "next_hermes_action": "configure_ga4_or_upload_demand_export",
            "summary": "No tenant-side demand source is ready.",
            "demand_collection_plan": {
                "status": "needs_demand_source",
                "topic_count": 2,
                "source_dashboard_field": "product_market_run.product_feature_comparison_read.rows",
                "topics": [
                    {
                        "rank": 1,
                        "topic": "AI Assistant",
                        "capability_key": "ai assistant",
                        "assessment": "competitive_pressure",
                        "related_competitors": ["Constructor", "Doofinder"],
                        "evidence_urls": [
                            "https://constructor.com/changelog/ai-assistant",
                            "https://doofinder.com/ai-search",
                        ],
                        "why_collect": "Internal rationale should stay out of the public blocker summary.",
                    },
                    {
                        "rank": 2,
                        "topic": "Shopping Assistant",
                        "capability_key": "shopping assistant",
                        "assessment": "watch",
                        "related_competitors": ["Bloomreach"],
                        "evidence_urls": ["https://constructor.com/blog/shopping-assistant"],
                    },
                ],
            },
        },
        evidence_work_queue={
            "work_item_count": 1,
            "blocking_count": 1,
            "limiting_count": 0,
            "items": [
                {
                    "work_item_id": "argus-evidence:17:demand",
                    "evidence_plane": "demand",
                    "severity": "blocks_action",
                    "title": "Demand plane missing",
                    "next_step": "Upload GA4 / Looker demand export.",
                }
            ],
        },
        generated_at="2026-07-12T11:00:00Z",
    )

    blocker = payload["blockers"][0]
    assert blocker["planned_topic_count"] == 2
    assert blocker["planned_topics"] == [
        {
            "topic": "AI Assistant",
            "capability_key": "ai assistant",
            "assessment": "competitive_pressure",
            "related_competitors": ["Constructor", "Doofinder"],
            "evidence_url_count": 2,
        },
        {
            "topic": "Shopping Assistant",
            "capability_key": "shopping assistant",
            "assessment": "watch",
            "related_competitors": ["Bloomreach"],
            "evidence_url_count": 1,
        },
    ]
    assert "why_collect" not in json.dumps(blocker)


def test_data_plane_manifest_blocks_action_when_demand_only_partially_covers_plan() -> None:
    module = _load_module()
    dashboard = _dashboard_payload()
    dashboard["product_market_run"]["demand_signal_count"] = 3
    dashboard["product_market_run"]["looker_normalized_row_count"] = 3
    dashboard["product_market_run"]["demand_plane_status"] = "processed"

    payload = module.build_data_plane_manifest_payload(
        tenant_slug="algolia",
        dashboard=dashboard,
        demand_readiness={
            "status": "processed_partial_plan_coverage",
            "next_hermes_action": "collect_missing_plan_demand",
            "summary": "Tenant demand evidence exists, but it only covers 1 of 2 Argus-prioritized demand topics.",
            "demand_collection_plan": {
                "status": "partial_coverage",
                "topic_count": 2,
                "coverage": {
                    "status": "partial_coverage",
                    "planned_topic_count": 2,
                    "covered_topic_count": 1,
                    "missing_topic_count": 1,
                    "off_plan_topic_count": 1,
                },
            },
        },
        evidence_work_queue={"work_item_count": 0, "blocking_count": 0, "limiting_count": 0, "items": []},
        operator_handoff={"status": "ready_for_operator_review", "argus_readiness": "actionable"},
        generated_at="2026-07-12T11:20:00Z",
    )

    demand_plane = payload["planes"]["audience_demand"]
    assert payload["status"] == "blocked_on_evidence"
    assert payload["next_hermes_action"] == "collect_missing_plan_demand"
    assert demand_plane["status"] == "processed_partial_plan_coverage"
    assert demand_plane["blocks_action"] is True
    assert demand_plane["summary"] == (
        "Tenant demand evidence exists, but it only covers 1 of 2 Argus-prioritized demand topics."
    )
    assert payload["blockers"] == [
        {
            "plane": "audience_demand",
            "severity": "blocks_action",
            "title": "Demand plane missing",
            "next_step": "collect_missing_plan_demand",
            "work_item_id": None,
        }
    ]


def test_data_plane_manifest_limits_but_does_not_block_controlled_pilot_partial_demand() -> None:
    module = _load_module()
    dashboard = _dashboard_payload()
    dashboard["product_market_run"]["demand_signal_count"] = 100
    dashboard["product_market_run"]["looker_normalized_row_count"] = 20
    dashboard["product_market_run"]["demand_plane_status"] = "processed"

    payload = module.build_data_plane_manifest_payload(
        tenant_slug="algolia",
        dashboard=dashboard,
        demand_readiness={
            "status": "processed_limited_plan_coverage",
            "next_hermes_action": "monitor_missing_plan_demand",
            "summary": (
                "Controlled pilot has action-grade demand for 1 of 2 planned topics; "
                "missing topics remain monitoring debt."
            ),
            "demand_collection_plan": {
                "status": "partial_coverage",
                "topic_count": 2,
                "coverage": {
                    "status": "partial_coverage",
                    "planned_topic_count": 2,
                    "covered_topic_count": 1,
                    "missing_topic_count": 1,
                },
            },
        },
        evidence_work_queue={"work_item_count": 0, "blocking_count": 0, "limiting_count": 0, "items": []},
        operator_handoff={"status": "ready_for_operator_review", "argus_readiness": "actionable"},
        generated_at="2026-07-28T14:05:00Z",
    )

    demand_plane = payload["planes"]["audience_demand"]
    assert payload["status"] == "ready_for_operator_review"
    assert payload["next_hermes_action"] == "review_scored_recommendations"
    assert payload["blockers"] == []
    assert demand_plane["status"] == "processed_limited_plan_coverage"
    assert demand_plane["blocks_action"] is False
    assert "Controlled pilot" in demand_plane["summary"]


def test_data_plane_manifest_blocker_names_missing_and_off_plan_demand_topics() -> None:
    module = _load_module()
    dashboard = _dashboard_payload()
    dashboard["product_market_run"]["demand_signal_count"] = 3
    dashboard["product_market_run"]["looker_normalized_row_count"] = 3
    dashboard["product_market_run"]["demand_plane_status"] = "processed"

    payload = module.build_data_plane_manifest_payload(
        tenant_slug="algolia",
        dashboard=dashboard,
        demand_readiness={
            "status": "processed_partial_plan_coverage",
            "next_hermes_action": "collect_missing_plan_demand",
            "summary": "Tenant demand evidence exists, but it only covers 1 of 2 Argus-prioritized demand topics.",
            "demand_collection_plan": {
                "status": "partial_coverage",
                "topic_count": 2,
                "coverage": {
                    "status": "partial_coverage",
                    "planned_topic_count": 2,
                    "covered_topic_count": 1,
                    "missing_topic_count": 1,
                    "off_plan_topic_count": 1,
                    "missing_topics": [
                        {
                            "topic": "AI Assistant",
                            "capability_key": "ai assistant",
                            "why_collect": "Decide whether Algolia needs product proof for AI Assistant.",
                        }
                    ],
                    "off_plan_topics": [
                        {
                            "topic": "Pricing",
                            "capability_key": "pricing",
                            "evidence_urls": ["https://lookerstudio.google.com/reporting/pricing"],
                        }
                    ],
                },
            },
        },
        evidence_work_queue={"work_item_count": 0, "blocking_count": 0, "limiting_count": 0, "items": []},
        operator_handoff={"status": "ready_for_operator_review", "argus_readiness": "actionable"},
        generated_at="2026-07-12T11:25:00Z",
    )

    blocker = payload["blockers"][0]
    assert blocker["title"] == "Demand plan coverage incomplete"
    assert blocker["next_step"] == "Collect demand for missing planned topics: AI Assistant."
    assert blocker["missing_topics"] == [
        {
            "topic": "AI Assistant",
            "capability_key": "ai assistant",
            "why_collect": "Decide whether Algolia needs product proof for AI Assistant.",
        }
    ]
    assert blocker["off_plan_topics"] == [
        {
            "topic": "Pricing",
            "capability_key": "pricing",
            "evidence_urls": ["https://lookerstudio.google.com/reporting/pricing"],
        }
    ]


def test_data_plane_manifest_blocks_action_when_demand_lacks_comparison_period() -> None:
    module = _load_module()
    dashboard = _dashboard_payload()
    dashboard["product_market_run"]["demand_signal_count"] = 1
    dashboard["product_market_run"]["looker_normalized_row_count"] = 1
    dashboard["product_market_run"]["demand_plane_status"] = "processed"

    payload = module.build_data_plane_manifest_payload(
        tenant_slug="algolia",
        dashboard=dashboard,
        demand_readiness={
            "status": "processed_no_comparison_period",
            "next_hermes_action": "upload_trended_planned_demand_export",
            "summary": (
                "Tenant demand evidence exists, but the imported export only has current-period values. "
                "Argus needs a previous-period or change_pct column before it can score movement."
            ),
            "comparison_coverage": {
                "topic_count": 1,
                "topics_with_change_pct": 0,
                "missing_change_pct_count": 1,
            },
        },
        evidence_work_queue={"work_item_count": 0, "blocking_count": 0, "limiting_count": 0, "items": []},
        operator_handoff={"status": "ready_for_operator_review", "argus_readiness": "actionable"},
        generated_at="2026-07-12T11:30:00Z",
    )

    demand_plane = payload["planes"]["audience_demand"]
    assert payload["status"] == "blocked_on_evidence"
    assert payload["next_hermes_action"] == "upload_trended_planned_demand_export"
    assert demand_plane["status"] == "processed_no_comparison_period"
    assert demand_plane["blocks_action"] is True
    assert demand_plane["summary"] == (
        "Tenant demand evidence exists, but the imported export only has current-period values. "
        "Argus needs a previous-period or change_pct column before it can score movement."
    )


def test_data_plane_manifest_prefers_current_readiness_action_over_stale_intake_action() -> None:
    module = _load_module()
    dashboard = _dashboard_payload()
    dashboard["product_market_run"]["demand_signal_count"] = 100
    dashboard["product_market_run"]["looker_normalized_row_count"] = 20
    dashboard["product_market_run"]["demand_plane_status"] = "processed"

    payload = module.build_data_plane_manifest_payload(
        tenant_slug="algolia",
        dashboard=dashboard,
        demand_readiness={
            "status": "processed_no_action_grade_demand",
            "next_hermes_action": "upload_trended_planned_demand_export",
            "summary": (
                "Tenant demand evidence exists, but no topic crossed the rising-demand threshold. "
                "Argus needs planned topic mapping plus previous-period or change_pct values before it can promote action."
            ),
        },
        demand_intake={
            "status": "processed_unmapped_demand",
            "next_hermes_action": "inspect_demand_mapping",
        },
        evidence_work_queue={"work_item_count": 0, "blocking_count": 0, "limiting_count": 0, "items": []},
        operator_handoff={"status": "ready_for_operator_review", "argus_readiness": "actionable"},
        generated_at="2026-07-12T11:35:00Z",
    )

    demand_plane = payload["planes"]["audience_demand"]
    assert payload["status"] == "blocked_on_evidence"
    assert payload["next_hermes_action"] == "upload_trended_planned_demand_export"
    assert demand_plane["status"] == "processed_no_action_grade_demand"
    assert demand_plane["next_hermes_action"] == "upload_trended_planned_demand_export"
    assert payload["blockers"][0]["title"] == "Demand movement not action-grade"
    assert payload["blockers"][0]["next_step"] == (
        "Upload a planned demand export with previous-period or change_pct values, then refresh Argus."
    )


def test_data_plane_manifest_writes_output_file(tmp_path) -> None:
    module = _load_module()
    output = tmp_path / "out" / "argus-data-plane-manifest.json"
    payload = {"tenant_slug": "algolia", "status": "blocked_on_evidence"}

    module.write_payload(payload, output)

    assert json.loads(output.read_text(encoding="utf-8")) == payload
