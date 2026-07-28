from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "check_pilot_monitoring.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_pilot_monitoring", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _public_status() -> dict:
    return {
        "tenant_slug": "algolia",
        "status": "limited_by_evidence",
        "publish_status": "published",
        "public_dashboard_updated": True,
        "generated_at": "2026-07-28T13:45:09.425489Z",
        "next_hermes_action": "monitor_missing_plan_demand",
        "source_coverage": {
            "active_source_count": 42,
            "checked_source_count": 42,
            "failed_source_count": 4,
        },
        "product_market_run": {
            "demand_signal_count": 101,
            "pattern_count": 4,
            "recommendation_count": 0,
        },
        "next_monitoring_actions": ["repair failed source", "review demand debt"],
        "planes": {
            "audience_demand": {
                "status": "processed_limited_plan_coverage",
                "blocks_action": False,
                "counts": {"demand_signal_count": 101},
                "demand_collection_plan": {
                    "coverage": {
                        "covered_topic_count": 1,
                        "planned_topic_count": 12,
                        "missing_topic_count": 11,
                    }
                },
            },
            "product_reality": {
                "status": "limited_by_evidence",
                "blocks_action": False,
                "counts": {"product_event_count": 524, "product_surface_failed_count": 3},
            },
            "registry_coverage": {
                "status": "complete",
                "blocks_action": False,
                "counts": {"active_source_count": 42, "checked_source_count": 42, "failed_source_count": 4},
            },
        },
    }


def _launch_readiness() -> dict:
    return {
        "gate": "cios_e2e_launch_readiness",
        "status": "pass",
        "source_coverage": {
            "active_source_count": 42,
            "checked_source_count": 42,
            "failed_source_count": 4,
            "failed_source_ratio": 0.0952,
            "max_failed_source_ratio": 0.1,
        },
        "checks": {
            "public_status_publishable": True,
            "source_coverage_complete": True,
            "source_failure_budget_ok": True,
            "audience_demand_processed": True,
            "product_reality_present": True,
        },
    }


def test_pilot_monitor_passes_with_visible_controlled_limitations() -> None:
    module = _load_module()

    payload = module.evaluate_pilot_monitoring(
        public_status=_public_status(),
        launch_readiness=_launch_readiness(),
        release_id="cios-pilot-algolia-20260728-2f7385f",
        package_commit="2f7385f4afdcdd2af771e34d8e92bdc629a990fa",
        max_failed_source_ratio=0.10,
    )

    assert payload["status"] == "pass"
    assert payload["release_id"] == "cios-pilot-algolia-20260728-2f7385f"
    assert payload["checks"]["publication_current"] is True
    assert payload["checks"]["launch_readiness_passed"] is True
    assert payload["checks"]["source_failure_ratio_ok"] is True
    assert payload["checks"]["audience_demand_present"] is True
    assert payload["checks"]["decision_activity_present"] is True
    assert payload["monitoring"]["source_coverage"]["failed_source_ratio"] == 0.0952
    assert payload["monitoring"]["audience_demand"]["planned_topic_coverage"] == "1/12"
    assert payload["monitoring"]["recommendations"]["recommendation_count"] == 0
    assert payload["monitoring"]["recommendations"]["pattern_count"] == 4
    assert payload["monitoring_debt"]
    assert "no current recommendation in public run status" in payload["monitoring_debt"]


def test_pilot_monitor_blocks_when_publication_is_not_current() -> None:
    module = _load_module()
    public_status = _public_status()
    public_status["publish_status"] = "blocked"

    payload = module.evaluate_pilot_monitoring(
        public_status=public_status,
        launch_readiness=_launch_readiness(),
        release_id="cios-pilot-algolia-20260728-2f7385f",
        package_commit="2f7385f4afdcdd2af771e34d8e92bdc629a990fa",
        max_failed_source_ratio=0.10,
    )

    assert payload["status"] == "fail"
    blockers = {(item["requirement"], item["actual"]) for item in payload["blockers"]}
    assert ("publication_current", "publish_status=blocked dashboard_updated=True") in blockers


def test_pilot_monitor_cli_writes_json_and_exit_code(tmp_path) -> None:
    module = _load_module()
    public_status_path = tmp_path / "argus-latest-run-status.json"
    launch_readiness_path = tmp_path / "cios-e2e-launch-readiness.json"
    output_path = tmp_path / "pilot-monitoring.json"
    public_status_path.write_text(json.dumps(_public_status()), encoding="utf-8")
    launch_readiness_path.write_text(json.dumps(_launch_readiness()), encoding="utf-8")

    code = module.main(
        [
            "--public-status",
            str(public_status_path),
            "--launch-readiness",
            str(launch_readiness_path),
            "--release-id",
            "cios-pilot-algolia-20260728-2f7385f",
            "--package-commit",
            "2f7385f4afdcdd2af771e34d8e92bdc629a990fa",
            "--max-failed-source-ratio",
            "0.10",
            "--output",
            str(output_path),
        ]
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert code == 0
    assert payload["status"] == "pass"
    assert payload["exit_code"] == 0


def test_pilot_monitor_reads_top_level_demand_plan_coverage() -> None:
    module = _load_module()
    public_status = _public_status()
    public_status["planes"]["audience_demand"].pop("demand_collection_plan")
    public_status["demand_collection_plan"] = {
        "coverage": {
            "covered_topic_count": 1,
            "planned_topic_count": 12,
            "missing_topic_count": 11,
        }
    }

    payload = module.evaluate_pilot_monitoring(
        public_status=public_status,
        launch_readiness=_launch_readiness(),
        release_id="cios-pilot-algolia-20260728-2f7385f",
        package_commit="2f7385f4afdcdd2af771e34d8e92bdc629a990fa",
        max_failed_source_ratio=0.10,
    )

    assert payload["monitoring"]["audience_demand"]["planned_topic_coverage"] == "1/12"
    assert "demand plan missing 11 of 12 planned topics" in payload["monitoring_debt"]


def test_pilot_monitor_reads_demand_plan_coverage_from_summary() -> None:
    module = _load_module()
    public_status = _public_status()
    public_status["planes"]["audience_demand"]["demand_collection_plan"] = {
        "status": "partial_coverage",
        "topic_count": 12,
    }
    public_status["planes"]["audience_demand"]["summary"] = (
        "Tenant demand evidence is sufficient for the controlled pilot, but only covers "
        "1 of 12 Argus-prioritized demand topics; missing topics remain monitoring debt."
    )

    payload = module.evaluate_pilot_monitoring(
        public_status=public_status,
        launch_readiness=_launch_readiness(),
        release_id="cios-pilot-algolia-20260728-2f7385f",
        package_commit="2f7385f4afdcdd2af771e34d8e92bdc629a990fa",
        max_failed_source_ratio=0.10,
    )

    assert payload["monitoring"]["audience_demand"]["planned_topic_coverage"] == "1/12"
    assert payload["monitoring"]["audience_demand"]["missing_topic_count"] == 11
