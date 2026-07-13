"""Regression checks for publishing the product-market intelligence spine.

The synthesizer/repository can exist and still not reach the live screen if
the production scripts forget to inject the repository into DashboardStateBuilder.
These checks keep the Hermes-run daily path and the no-fetch rerender path
wired to the same product-market ledger.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DAILY_RUN = ROOT / "scripts" / "daily_production_run.py"
RERENDER = ROOT / "scripts" / "rerender_dashboard.py"


def _load_rerender_module():
    spec = importlib.util.spec_from_file_location("rerender_dashboard", RERENDER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_daily_runner_wires_product_market_repository_into_dashboard_builder() -> None:
    source = DAILY_RUN.read_text(encoding="utf-8")

    assert "from cios.db.repos.product_market import PgProductMarketRepository" in source
    assert "product_market=PgProductMarketRepository(app_conn)" in source


def test_rerender_dashboard_wires_product_market_repository_into_dashboard_builder() -> None:
    source = RERENDER.read_text(encoding="utf-8")

    assert "from cios.db.repos.product_market import PgProductMarketRepository" in source
    assert "product_market=PgProductMarketRepository(conn)" in source


def test_rerender_dashboard_recovers_product_market_summary_from_report_metadata() -> None:
    source = RERENDER.read_text(encoding="utf-8")

    assert "from cios.db.session import tenant_context" in source
    assert "def latest_product_market_summary_from_reports" in source
    assert "with tenant_context(conn, tenant_id):" in source
    assert "metadata->'product_market_summary'" in source
    assert "latest_summary = latest_product_market_summary_from_reports(conn, tenant_id)" in source
    assert "latest_product_market_summary=latest_summary" in source


def test_rerender_dashboard_preserves_last_product_market_run_trace() -> None:
    rerender = _load_rerender_module()

    run = rerender.run_dict_from_saved_dashboard(
        {
            "run_health": {
                "run_id": "daily-algolia-123",
                "quality_review_status": "passed",
                "material_delta_count": 1,
            },
            "product_market_run": {
                "status": "ran",
                "next_sweep_plan_path": "/tmp/next-sweep-learning-plan.json",
                "target_count": 3,
                "target_company_count": 2,
                "target_companies": ["Constructor", "Coveo"],
                "surface_family_counts": {"docs": 2, "changelog": 1},
                "product_muscle_gap_plan": {
                    "missing_company_count": 1,
                    "candidate_url_count": 6,
                    "missing_companies": [{"company_name": "Elastic"}],
                },
                "post_run_product_muscle_gap_discovery": {
                    "status": "completed",
                    "stored_candidate_count": 5,
                    "rejected_count": 1,
                },
                "post_run_product_surface_promotion": {
                    "status": "completed",
                    "promoted_count": 2,
                },
                "post_run_next_sweep_status": (
                    "Hermes queued 5 candidate product surfaces and activated 2 validated sources "
                    "for the next sweep."
                ),
                "learning_prioritized_count": 1,
                "prioritized_targets": [{"company_name": "Coveo"}],
                "runner_verdict": "quiet",
                "learning_instruction_count": 2,
                "consumed_learning_ids": [202, 303],
                "scout_artifact_count": 2,
                "looker_discovered_count": 1,
                "looker_ready_count": 1,
                "looker_error_count": 0,
                "looker_normalized_row_count": 12,
                "looker_skipped_row_count": 3,
                "looker_archived_count": 1,
                "looker_manifest_path": "/tmp/cios-product-market/algolia/looker-export-manifest.json",
                "intelligence_brief": {
                    "top_insight": "No cross-plane product-market pattern qualified.",
                    "conversion_diagnostics": {"product_event_count": 21},
                },
                "conversion_diagnostics": {
                    "conversation_record_count": 80,
                    "product_event_count": 21,
                    "demand_signal_count": 0,
                },
                "errors": ["no demand plane"],
            },
        }
    )

    summary = run["product_market_summary"]
    assert summary["status"] == "ran"
    assert summary["product_surface_plan_summary"]["target_count"] == 3
    assert summary["product_surface_plan_summary"]["target_company_count"] == 2
    assert summary["product_surface_plan_summary"]["target_companies"] == ["Constructor", "Coveo"]
    assert summary["product_surface_plan_summary"]["surface_family_counts"] == {"docs": 2, "changelog": 1}
    assert summary["product_muscle_gap_plan"]["missing_company_count"] == 1
    assert summary["product_muscle_gap_plan"]["candidate_url_count"] == 6
    assert summary["post_run_product_muscle_gap_discovery"]["stored_candidate_count"] == 5
    assert summary["post_run_product_surface_promotion"]["promoted_count"] == 2
    assert summary["post_run_next_sweep_status"].startswith("Hermes queued 5")
    assert summary["runner_summary"]["verdict"] == "quiet"
    assert summary["runner_summary"]["learning_instruction_improvement_ids"] == [202, 303]
    assert summary["runner_summary"]["conversion_diagnostics"]["conversation_record_count"] == 80
    assert summary["looker_discovered_count"] == 1
    assert summary["looker_ready_count"] == 1
    assert summary["looker_normalized_row_count"] == 12
    assert summary["looker_skipped_row_count"] == 3
    assert summary["looker_archived_count"] == 1
    assert summary["looker_manifest_path"].endswith("looker-export-manifest.json")
    assert len(summary["scout_paths"]) == 2


def test_rerender_dashboard_prefers_latest_report_product_market_summary_over_saved_trace() -> None:
    rerender = _load_rerender_module()

    run = rerender.run_dict_from_saved_dashboard(
        {
            "run_health": {"run_id": "daily-algolia-stale"},
            "product_market_run": {
                "status": "ran",
                "runner_verdict": "actionable",
                "learning_instruction_count": 0,
                "consumed_learning_ids": [],
                "intelligence_brief": {
                    "top_insight": "Stale public JSON preserved this older read.",
                },
            },
        },
        latest_product_market_summary={
            "status": "ran",
            "runner_summary": {
                "verdict": "actionable",
                "intelligence_brief": {
                    "top_insight": "Initial runner read before ledger replay.",
                },
            },
            "ledger_refresh_status": "ran",
            "ledger_refresh_summary": {
                "verdict": "watch",
                "learning_instruction_count": 1,
                "learning_instruction_improvement_ids": [202],
                "demand_signal_count": 2,
                "intelligence_brief": {
                    "top_insight": "Fresh report metadata contains the final ledger replay read.",
                },
            },
        },
    )

    summary = run["product_market_summary"]
    assert summary["ledger_refresh_status"] == "ran"
    assert summary["ledger_refresh_summary"]["verdict"] == "watch"
    assert (
        summary["ledger_refresh_summary"]["intelligence_brief"]["top_insight"]
        == "Fresh report metadata contains the final ledger replay read."
    )


def test_rerender_dashboard_preserves_post_run_sidecars_when_latest_report_lacks_them() -> None:
    rerender = _load_rerender_module()

    run = rerender.run_dict_from_saved_dashboard(
        {
            "run_health": {"run_id": "daily-algolia-post-run"},
            "product_market_run": {
                "status": "ran",
                "runner_verdict": "quiet",
                "post_run_product_muscle_gap_discovery": {
                    "status": "completed",
                    "candidate_url_count": 47,
                    "duplicate_source_count": 47,
                    "stored_candidate_count": 0,
                },
                "post_run_product_surface_promotion": {
                    "status": "completed",
                    "promoted_count": 0,
                },
                "post_run_next_sweep_status": (
                    "Hermes rechecked 47 already-monitored product surfaces; no new "
                    "sweepable sources were added for the next sweep."
                ),
                "demand_readiness": {
                    "status": "blocked_missing_configuration",
                    "next_hermes_action": "configure_ga4_or_upload_demand_export",
                },
                "intelligence_brief": {
                    "top_insight": "Saved public JSON had the post-run source loop.",
                },
            },
        },
        latest_product_market_summary={
            "status": "ran",
            "runner_summary": {
                "verdict": "watch",
                "intelligence_brief": {
                    "top_insight": "Latest report metadata has the final Argus read.",
                },
            },
        },
    )

    summary = run["product_market_summary"]
    assert (
        summary["runner_summary"]["intelligence_brief"]["top_insight"]
        == "Latest report metadata has the final Argus read."
    )
    assert summary["post_run_product_muscle_gap_discovery"]["candidate_url_count"] == 47
    assert summary["post_run_product_muscle_gap_discovery"]["duplicate_source_count"] == 47
    assert summary["post_run_product_surface_promotion"]["promoted_count"] == 0
    assert summary["post_run_next_sweep_status"].startswith(
        "Hermes rechecked 47 already-monitored product surfaces"
    )
    assert summary["demand_readiness"]["status"] == "blocked_missing_configuration"
    assert summary["demand_readiness"]["next_hermes_action"] == "configure_ga4_or_upload_demand_export"
