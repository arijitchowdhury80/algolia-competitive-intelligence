from __future__ import annotations

import importlib.util
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "check_e2e_launch_readiness.py"
PLAN_PATH = ROOT / "docs" / "plan" / "e2e-validation.md"
RUN_ID = "cios-20260714T090000Z-1234"
NOW = datetime(2026, 7, 14, 9, 5, tzinfo=timezone.utc)


def _load_module():
    spec = importlib.util.spec_from_file_location("check_e2e_launch_readiness", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _published_status() -> dict:
    return {
        "schema_version": 2,
        "run_id": RUN_ID,
        "tenant_slug": "algolia",
        "generated_at": "2026-07-14T09:00:00Z",
        "publish_status": "published",
        "status": "published",
        "public_dashboard_updated": True,
        "source_coverage": {
            "run_id": RUN_ID,
            "active_source_count": 48,
            "checked_source_count": 48,
            "failed_source_count": 0,
            "disposed_source_count": 0,
            "dispositions": [],
        },
        "product_extraction": {
            "run_id": RUN_ID,
            "planned": 12,
            "attempted": 12,
            "terminal": 12,
            "successful": 12,
            "failed": 0,
            "timed_out": 0,
            "not_started": 0,
            "accounting_complete": True,
            "all_planned_terminal": True,
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


def _verdict(gate: str) -> dict:
    verdict = {
        "schema_version": 1,
        "gate": gate,
        "run_id": RUN_ID,
        "generated_at": "2026-07-14T09:03:00Z",
        "status": "pass",
        "exit_code": 0,
        "checks": {"required_contract": True},
    }
    if gate == "publication_integrity":
        verdict["manifest_sha256"] = "a" * 64
    return verdict


def _publication_manifest() -> dict:
    return {
        "schema_version": 1,
        "run_id": RUN_ID,
        "tenant_slug": "algolia",
        "kind": "decision",
        "generated_at": "2026-07-14T09:00:00Z",
        "files": [{"path": "index.html"}],
        "safety": {
            "artifact_paths_redacted": True,
            "secret_values_included": False,
            "public_safe": True,
        },
    }


def _required_publication_args() -> dict:
    return {
        "publication_verdict": _verdict("publication_integrity"),
        "publication_manifest": _publication_manifest(),
        "publication_manifest_sha256": "a" * 64,
    }


def test_launch_readiness_passes_only_when_all_e2e_gates_pass() -> None:
    module = _load_module()

    result = module.evaluate_launch_readiness(
        public_status=_published_status(),
        click_verdict=_verdict("dashboard_click_validation"),
        package_verdict=_verdict("hermes_package_contract"),
        **_required_publication_args(),
        now=NOW,
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
    assert result["checks"]["publication_integrity_passed"] is True
    assert result["checks"]["publication_manifest_bound"] is True
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
                    "run_id": RUN_ID,
                    "active_source_count": 48,
                    "checked_source_count": 48,
                    "failed_source_count": 5,
                    "disposed_source_count": 0,
                    "dispositions": [],
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
        click_verdict=_verdict("dashboard_click_validation"),
        package_verdict=_verdict("hermes_package_contract"),
        **_required_publication_args(),
        now=NOW,
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


def test_launch_readiness_accepts_limited_nonblocking_product_reality() -> None:
    module = _load_module()
    status = _published_status()
    status["planes"]["product_reality"] = {
        "status": "limited_by_product_surface_evidence",
        "blocks_action": False,
        "counts": {
            "product_event_count": 500,
            "product_surface_extracted_row_count": 522,
            "product_surface_succeeded_count": 47,
            "product_surface_failed_count": 3,
        },
    }
    status["product_market_run"]["product_event_count"] = 500

    result = module.evaluate_launch_readiness(
        public_status=status,
        click_verdict=_verdict("dashboard_click_validation"),
        package_verdict=_verdict("hermes_package_contract"),
        **_required_publication_args(),
        now=NOW,
    )

    assert result["checks"]["product_reality_present"] is True
    assert result["status"] == "pass"


def test_launch_readiness_cli_writes_json_and_returns_exit_code(tmp_path) -> None:
    module = _load_module()
    status_path = tmp_path / "argus-latest-run-status.json"
    click_path = tmp_path / "click-verdict.json"
    package_path = tmp_path / "package-verdict.json"
    publication_path = tmp_path / "publication-verdict.json"
    publication_manifest_path = tmp_path / "publication-manifest.json"
    output_path = tmp_path / "launch-readiness.json"
    status_path.write_text(json.dumps(_published_status()), encoding="utf-8")
    click_path.write_text(json.dumps(_verdict("dashboard_click_validation")), encoding="utf-8")
    package_path.write_text(json.dumps(_verdict("hermes_package_contract")), encoding="utf-8")
    manifest_bytes = json.dumps(_publication_manifest()).encode()
    publication_manifest_path.write_bytes(manifest_bytes)
    publication_verdict = _verdict("publication_integrity")
    publication_verdict["manifest_sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
    publication_path.write_text(json.dumps(publication_verdict), encoding="utf-8")

    code = module.main(
        [
            "--public-status",
            str(status_path),
            "--click-verdict",
            str(click_path),
            "--package-verdict",
            str(package_path),
            "--publication-verdict",
            str(publication_path),
            "--publication-manifest",
            str(publication_manifest_path),
            "--now",
            NOW.isoformat(),
            "--output",
            str(output_path),
        ]
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert code == 0
    assert payload["status"] == "pass"
    assert payload["checks"]["dashboard_click_validation_passed"] is True


def test_launch_readiness_cli_fails_when_click_validation_is_missing(tmp_path) -> None:
    module = _load_module()
    status_path = tmp_path / "argus-latest-run-status.json"
    output_path = tmp_path / "launch-readiness.json"
    status_path.write_text(json.dumps(_published_status()), encoding="utf-8")

    code = module.main(
        [
            "--public-status",
            str(status_path),
            "--click-verdict",
            str(tmp_path / "missing-click-verdict.json"),
            "--package-verdict",
            str(tmp_path / "missing-package-verdict.json"),
            "--publication-verdict",
            str(tmp_path / "missing-publication-verdict.json"),
            "--publication-manifest",
            str(tmp_path / "missing-publication-manifest.json"),
            "--now",
            NOW.isoformat(),
            "--output",
            str(output_path),
        ]
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert code == 2
    assert payload["checks"]["dashboard_click_validation_passed"] is False
    assert any(item["requirement"] == "dashboard_click_validation_passed" for item in payload["blockers"])


def test_launch_readiness_does_not_trust_pass_strings() -> None:
    module = _load_module()

    result = module.evaluate_launch_readiness(
        public_status=_published_status(),
        click_verdict={"status": "PASS dashboard_click_validation"},
        package_verdict={"status": "PASS: CI-OS Hermes package contract satisfied"},
        publication_verdict={"status": "PASS"},
        publication_manifest=_publication_manifest(),
        publication_manifest_sha256="a" * 64,
        now=NOW,
    )

    assert result["status"] == "fail"
    assert result["checks"]["dashboard_click_validation_passed"] is False
    assert result["checks"]["hermes_package_contract_passed"] is False


def test_launch_readiness_rejects_stale_or_different_run_verdicts() -> None:
    module = _load_module()
    stale_click = _verdict("dashboard_click_validation")
    stale_click["generated_at"] = "2026-07-14T07:00:00Z"
    wrong_package = _verdict("hermes_package_contract")
    wrong_package["run_id"] = "cios-20260714T090000Z-other"

    result = module.evaluate_launch_readiness(
        public_status=_published_status(),
        click_verdict=stale_click,
        package_verdict=wrong_package,
        **_required_publication_args(),
        now=NOW,
        max_verdict_age_seconds=600,
    )

    assert result["status"] == "fail"
    assert result["checks"]["dashboard_click_validation_passed"] is False
    assert result["checks"]["hermes_package_contract_passed"] is False


def test_launch_readiness_rejects_publication_manifest_digest_mismatch() -> None:
    module = _load_module()

    result = module.evaluate_launch_readiness(
        public_status=_published_status(),
        click_verdict=_verdict("dashboard_click_validation"),
        package_verdict=_verdict("hermes_package_contract"),
        publication_verdict=_verdict("publication_integrity"),
        publication_manifest=_publication_manifest(),
        publication_manifest_sha256="b" * 64,
        now=NOW,
    )

    assert result["status"] == "fail"
    assert result["checks"]["publication_integrity_passed"] is True
    assert result["checks"]["publication_manifest_bound"] is False


def test_launch_readiness_rejects_unsafe_run_id() -> None:
    module = _load_module()
    status = _published_status()
    status["run_id"] = "../escape"

    result = module.evaluate_launch_readiness(
        public_status=status,
        click_verdict=_verdict("dashboard_click_validation"),
        package_verdict=_verdict("hermes_package_contract"),
        **_required_publication_args(),
        now=NOW,
    )

    assert result["status"] == "fail"
    assert result["checks"]["public_status_current_run"] is False


def test_launch_readiness_requires_unique_disposition_source_refs() -> None:
    module = _load_module()
    status = _published_status()
    status["source_coverage"].update(
        {
            "checked_source_count": 46,
            "disposed_source_count": 2,
            "dispositions": [
                {"source_ref": "0123456789abcdef", "reason": "paused"},
                {"source_ref": "0123456789abcdef", "reason": "retired"},
            ],
        }
    )

    result = module.evaluate_launch_readiness(
        public_status=status,
        click_verdict=_verdict("dashboard_click_validation"),
        package_verdict=_verdict("hermes_package_contract"),
        **_required_publication_args(),
        now=NOW,
    )

    assert result["status"] == "fail"
    assert result["checks"]["source_coverage_complete"] is False


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
