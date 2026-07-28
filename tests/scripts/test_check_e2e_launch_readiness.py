from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "check_e2e_launch_readiness.py"
PLAN_PATH = ROOT / "docs" / "plan" / "e2e-validation.md"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_e2e_launch_readiness", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _published_status() -> dict:
    return {
        "schema_version": 1,
        "tenant_slug": "algolia",
        "generated_at": "2026-07-13T00:00:00Z",
        "publish_status": "published",
        "status": "published",
        "public_dashboard_updated": True,
        "source_coverage": {
            "active_source_count": 48,
            "checked_source_count": 48,
            "failed_source_count": 0,
        },
        "product_market_run": {
            "status": "ran",
            "product_event_count": 120,
            "conversation_theme_count": 30,
            "demand_signal_count": 12,
            "pattern_count": 8,
            "recommendation_count": 3,
        },
        "planes": {
            "audience_demand": {
                "status": "processed",
                "blocks_action": False,
                "counts": {"demand_signal_count": 12},
            },
            "product_reality": {
                "status": "present",
                "blocks_action": False,
                "counts": {"product_event_count": 120},
            },
            "registry_coverage": {
                "status": "complete",
                "blocks_action": False,
                "counts": {"active_source_count": 48, "checked_source_count": 48},
            },
        },
        "blockers": [],
        "safety": {
            "artifact_paths_redacted": True,
            "secret_values_included": False,
            "public_safe": True,
        },
    }


def _public_redaction() -> dict:
    return {
        "status": "redacted",
        "public_safe_for_scan": True,
        "redaction_count": 3,
        "redacted_file_count": 2,
        "findings": [],
    }


def _public_safety_scan() -> dict:
    return {
        "status": "passed",
        "public_safe": True,
        "finding_count": 0,
        "findings": [],
    }


def _operational_safety() -> dict:
    return {
        "gate": "cios_live_operational_safety",
        "status": "passed",
        "operational_safe": True,
        "current_release_exists": True,
        "served_release_ready": True,
        "hidden_staging_dir_count": 0,
        "root_owned_artifact_count": 0,
        "orphan_process_count": 0,
        "findings": [],
    }


def test_launch_readiness_passes_only_when_all_e2e_gates_pass() -> None:
    module = _load_module()

    result = module.evaluate_launch_readiness(
        public_status=_published_status(),
        click_validation_log="PASS structure\nPASS dashboard_click_validation\n",
        package_contract_log="PASS: CI-OS Hermes package contract satisfied\n",
        public_redaction=_public_redaction(),
        public_safety_scan=_public_safety_scan(),
        operational_safety=_operational_safety(),
    )

    assert result["gate"] == "cios_e2e_launch_readiness"
    assert result["status"] == "pass"
    assert result["exit_code"] == 0
    assert result["summary"] == "CI-OS launch readiness gate passed."
    assert result["checks"]["public_status_publishable"] is True
    assert result["checks"]["source_coverage_complete"] is True
    assert result["checks"]["source_failure_budget_ok"] is True
    assert result["checks"]["audience_demand_processed"] is True
    assert result["checks"]["dashboard_click_validation_passed"] is True
    assert result["checks"]["hermes_package_contract_passed"] is True
    assert result["checks"]["public_artifact_redaction_passed"] is True
    assert result["checks"]["public_artifact_scan_passed"] is True
    assert result["checks"]["live_operational_safety_passed"] is True
    assert result["blockers"] == []


def test_launch_readiness_fails_with_specific_blockers_for_current_blocked_run() -> None:
    module = _load_module()
    blocked = _published_status()
    blocked.update(
        {
            "publish_status": "blocked",
            "status": "blocked_on_evidence",
            "public_dashboard_updated": False,
            "next_hermes_action": "configure_ga4_or_upload_demand_export",
            "source_coverage": {
                "active_source_count": 48,
                "checked_source_count": 48,
                "failed_source_count": 5,
            },
            "product_market_run": {
                "status": "ran",
                "product_event_count": 120,
                "conversation_theme_count": 30,
                "demand_signal_count": 0,
                "pattern_count": 8,
                "recommendation_count": 0,
            },
            "planes": {
                "audience_demand": {
                    "status": "blocked_missing_demand_source",
                    "blocks_action": True,
                    "counts": {"demand_signal_count": 0},
                },
                "product_reality": {"status": "present", "blocks_action": False},
            },
            "demand_collection_plan": {
                "status": "needs_demand_source",
                "topic_count": 12,
                "source_dashboard_field": "product_market_run.product_feature_comparison_read.rows",
            },
        }
    )

    result = module.evaluate_launch_readiness(
        public_status=blocked,
        click_validation_log="PASS dashboard_click_validation\n",
        package_contract_log="PASS: CI-OS Hermes package contract satisfied\n",
        public_redaction=_public_redaction(),
        public_safety_scan=_public_safety_scan(),
        operational_safety=_operational_safety(),
    )

    assert result["status"] == "fail"
    assert result["exit_code"] == 2
    assert result["checks"]["public_status_publishable"] is False
    assert result["checks"]["source_coverage_complete"] is True
    assert result["checks"]["source_failure_budget_ok"] is False
    assert result["checks"]["audience_demand_processed"] is False
    blockers = {(item["requirement"], item["actual"]) for item in result["blockers"]}
    assert ("public_status_publishable", "publish_status=blocked status=blocked_on_evidence") in blockers
    assert ("source_failure_budget_ok", "failed_source_count=5 max_failed_sources=0") in blockers
    assert ("audience_demand_processed", "audience_demand.status=blocked_missing_demand_source demand_signal_count=0") in blockers
    assert result["next_action"] == "configure_ga4_or_upload_demand_export"
    assert result["demand_collection_plan"]["topic_count"] == 12


def test_launch_readiness_cli_writes_json_and_returns_exit_code(tmp_path) -> None:
    module = _load_module()
    status_path = tmp_path / "argus-latest-run-status.json"
    click_path = tmp_path / "click.log"
    package_path = tmp_path / "package.log"
    redaction_path = tmp_path / "public-artifact-redaction.json"
    scan_path = tmp_path / "public-artifact-safety-scan.json"
    operational_path = tmp_path / "live-operational-safety.json"
    output_path = tmp_path / "launch-readiness.json"
    status_path.write_text(json.dumps(_published_status()), encoding="utf-8")
    click_path.write_text("PASS dashboard_click_validation\n", encoding="utf-8")
    package_path.write_text("PASS: CI-OS Hermes package contract satisfied\n", encoding="utf-8")
    redaction_path.write_text(json.dumps(_public_redaction()), encoding="utf-8")
    scan_path.write_text(json.dumps(_public_safety_scan()), encoding="utf-8")
    operational_path.write_text(json.dumps(_operational_safety()), encoding="utf-8")

    code = module.main(
        [
            "--public-status",
            str(status_path),
            "--click-validation-log",
            str(click_path),
            "--package-contract-log",
            str(package_path),
            "--public-redaction",
            str(redaction_path),
            "--public-safety-scan",
            str(scan_path),
            "--operational-safety",
            str(operational_path),
            "--output",
            str(output_path),
        ]
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert code == 0
    assert payload["status"] == "pass"
    assert payload["checks"]["dashboard_click_validation_passed"] is True
    assert payload["checks"]["live_operational_safety_passed"] is True


def test_launch_readiness_cli_fails_when_required_validation_artifacts_are_missing(tmp_path) -> None:
    module = _load_module()
    status_path = tmp_path / "argus-latest-run-status.json"
    output_path = tmp_path / "launch-readiness.json"
    status_path.write_text(json.dumps(_published_status()), encoding="utf-8")

    code = module.main(
        [
            "--public-status",
            str(status_path),
            "--package-contract-log-text",
            "PASS: CI-OS Hermes package contract satisfied",
            "--output",
            str(output_path),
        ]
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert code == 2
    assert payload["checks"]["dashboard_click_validation_passed"] is False
    assert payload["checks"]["public_artifact_redaction_passed"] is False
    assert payload["checks"]["public_artifact_scan_passed"] is False
    assert payload["checks"]["live_operational_safety_passed"] is False
    assert any(item["requirement"] == "dashboard_click_validation_passed" for item in payload["blockers"])
    assert any(item["requirement"] == "public_artifact_redaction_passed" for item in payload["blockers"])
    assert any(item["requirement"] == "public_artifact_scan_passed" for item in payload["blockers"])
    assert any(item["requirement"] == "live_operational_safety_passed" for item in payload["blockers"])


def test_e2e_validation_plan_is_written_to_disk_and_names_the_real_gates() -> None:
    text = PLAN_PATH.read_text(encoding="utf-8")

    for phrase in (
        "Hermes Execution Gate",
        "Frontend E2E Gate",
        "Backend and Data Gate",
        "Competitor Registry Gate",
        "Demand, GA4, and Looker Gate",
        "Launch Readiness Command",
        "scripts/check_e2e_launch_readiness.py",
        "No launch claim",
    ):
        assert phrase in text
