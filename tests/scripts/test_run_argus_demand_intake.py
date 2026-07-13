"""Contract for the Hermes-callable inward-demand intake coordinator."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "run_argus_demand_intake.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_argus_demand_intake", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_run_argus_demand_intake_imports_queued_manual_export(tmp_path) -> None:
    module = _load_module()
    calls: list[dict] = []

    def readiness_builder(**kwargs):
        return {
            "tenant_slug": kwargs["tenant_slug"],
            "status": "queued_manual_exports",
            "next_hermes_action": "prepare_demand_and_refresh_argus",
            "summary": "A manual GA / Looker export is queued and has usable rows.",
        }

    def importer(**kwargs):
        calls.append(kwargs)
        return {
            "status": "refreshed",
            "tenant": kwargs["tenant"],
            "copied_inputs": [],
            "prepare": {"ready_count": 1, "normalized_row_count": 3},
            "demand_ledger": {"demand_signal_count": 3},
        }

    result = module.run_demand_intake(
        tenant="algolia",
        app_dir=tmp_path / "app",
        work_root=tmp_path / "work",
        readiness_builder=readiness_builder,
        importer=importer,
        persist_demand=False,
        demand_change_floor=0.03,
        demand_value_floor=25,
    )

    assert result["status"] == "demand_imported_and_argus_refreshed"
    assert result["exit_code"] == 0
    assert result["mode"] == "queued_manual_export"
    assert result["ga4_export"] is None
    assert result["demand_import"]["status"] == "refreshed"
    assert calls[0]["tenant"] == "algolia"
    assert calls[0]["inputs"] == []
    assert calls[0]["require_ready"] is True
    assert calls[0]["persist_demand"] is False
    assert calls[0]["demand_change_floor"] == 0.03
    assert calls[0]["demand_value_floor"] == 25


def test_run_argus_demand_intake_passes_readiness_plan_into_manual_import(tmp_path) -> None:
    module = _load_module()
    calls: list[dict] = []
    demand_plan = {
        "status": "needs_demand_source",
        "topic_count": 1,
        "topics": [
            {
                "topic": "AI Assistant",
                "capability_key": "ai assistant",
                "suggested_filter_terms": ["AI Assistant"],
            }
        ],
    }

    def readiness_builder(**kwargs):
        return {
            "tenant_slug": kwargs["tenant_slug"],
            "status": "queued_manual_exports",
            "next_hermes_action": "prepare_demand_and_refresh_argus",
            "demand_collection_plan": demand_plan,
        }

    def importer(**kwargs):
        calls.append(kwargs)
        return {
            "status": "refreshed",
            "tenant": kwargs["tenant"],
            "prepare": {"ready_count": 1, "normalized_row_count": 1},
        }

    result = module.run_demand_intake(
        tenant="algolia",
        app_dir=tmp_path / "app",
        work_root=tmp_path / "work",
        readiness_builder=readiness_builder,
        importer=importer,
    )

    assert result["status"] == "demand_imported_and_argus_refreshed"
    assert calls[0]["demand_plan"] == demand_plan


def test_run_argus_demand_intake_uses_dashboard_for_fresh_collection_plan(tmp_path) -> None:
    module = _load_module()
    calls: list[dict] = []
    dashboard = {
        "product_market_run": {
            "product_feature_comparison_read": {
                "rows": [
                    {
                        "capability": "AI Assistant",
                        "capability_key": "ai assistant",
                        "assessment": "own_product_gap",
                    }
                ]
            }
        }
    }

    def readiness_builder(**kwargs):
        calls.append(kwargs)
        assert kwargs["dashboard"] == dashboard
        return {
            "tenant_slug": kwargs["tenant_slug"],
            "status": "blocked_missing_demand_source",
            "next_hermes_action": "configure_ga4_or_upload_demand_export",
            "demand_collection_plan": {
                "status": "needs_demand_source",
                "topic_count": 1,
                "topics": [{"topic": "AI Assistant", "capability_key": "ai assistant"}],
            },
        }

    result = module.run_demand_intake(
        tenant="algolia",
        app_dir=tmp_path / "app",
        work_root=tmp_path / "work",
        dashboard=dashboard,
        readiness_builder=readiness_builder,
    )

    assert result["status"] == "blocked_missing_demand_source"
    assert result["readiness"]["demand_collection_plan"]["topic_count"] == 1
    assert calls[0]["dashboard"] == dashboard


def test_run_argus_demand_intake_exports_ga4_then_imports_queued_output(tmp_path) -> None:
    module = _load_module()
    calls: list[dict] = []

    class FakeGa4Control:
        def run(self, tenant_slug, demand_plan=None):
            return {
                "tenant_slug": tenant_slug,
                "output_path": str(tmp_path / "app" / "data" / "looker" / tenant_slug / "ga4-demand.json"),
                "record_count": 5,
                "credentials_configured": True,
                "demand_plan_topic_count": 0,
            }

    def readiness_builder(**kwargs):
        return {
            "tenant_slug": kwargs["tenant_slug"],
            "status": "ready_to_export_ga4",
            "next_hermes_action": "run_ga4_export_then_prepare_demand",
            "summary": "GA4 connector configuration is ready; Hermes can export demand evidence.",
        }

    def importer(**kwargs):
        calls.append(kwargs)
        return {
            "status": "published",
            "tenant": kwargs["tenant"],
            "prepare": {"ready_count": 1, "normalized_row_count": 5},
            "publish": {"status": "published"},
        }

    result = module.run_demand_intake(
        tenant="algolia",
        app_dir=tmp_path / "app",
        work_root=tmp_path / "work",
        publish=True,
        public_dir=tmp_path / "public",
        readiness_builder=readiness_builder,
        ga4_control=FakeGa4Control(),
        importer=importer,
    )

    assert result["status"] == "ga4_exported_demand_imported_and_argus_refreshed"
    assert result["exit_code"] == 0
    assert result["mode"] == "ga4_export"
    assert result["ga4_export"]["record_count"] == 5
    assert result["demand_import"]["status"] == "published"
    assert calls[0]["publish"] is True
    assert calls[0]["public_dir"] == tmp_path / "public"
    assert calls[0]["require_ready"] is True


def test_run_argus_demand_intake_passes_readiness_plan_into_ga4_export(tmp_path) -> None:
    module = _load_module()
    calls: list[dict] = []

    class FakeGa4Control:
        def run(self, tenant_slug, demand_plan=None):
            calls.append({"tenant_slug": tenant_slug, "demand_plan": demand_plan})
            return {
                "tenant_slug": tenant_slug,
                "output_path": str(tmp_path / "app" / "data" / "looker" / tenant_slug / "ga4-demand.json"),
                "record_count": 1,
                "credentials_configured": True,
                "demand_plan_status": "partial_coverage",
                "demand_plan_topic_count": 1,
                "matched_plan_topic_count": 1,
                "off_plan_record_count": 0,
            }

    def readiness_builder(**kwargs):
        return {
            "tenant_slug": kwargs["tenant_slug"],
            "status": "ready_to_export_ga4",
            "next_hermes_action": "run_ga4_export_then_prepare_demand",
            "demand_collection_plan": {
                "status": "ready_to_collect",
                "topics": [
                    {
                        "topic": "AI Assistant",
                        "capability_key": "ai assistant",
                        "suggested_filter_terms": ["AI Shopping Agent"],
                    }
                ],
            },
        }

    def importer(**kwargs):
        return {"status": "refreshed", "tenant": kwargs["tenant"]}

    result = module.run_demand_intake(
        tenant="algolia",
        app_dir=tmp_path / "app",
        work_root=tmp_path / "work",
        readiness_builder=readiness_builder,
        ga4_control=FakeGa4Control(),
        importer=importer,
    )

    assert calls == [
        {
            "tenant_slug": "algolia",
            "demand_plan": {
                "status": "ready_to_collect",
                "topics": [
                    {
                        "topic": "AI Assistant",
                        "capability_key": "ai assistant",
                        "suggested_filter_terms": ["AI Shopping Agent"],
                    }
                ],
            },
        }
    ]
    assert result["ga4_export"]["demand_plan_status"] == "partial_coverage"
    assert result["ga4_export"]["matched_plan_topic_count"] == 1


def test_run_argus_demand_intake_fails_when_no_source_is_ready(tmp_path) -> None:
    module = _load_module()

    def readiness_builder(**kwargs):
        return {
            "tenant_slug": kwargs["tenant_slug"],
            "status": "blocked_missing_demand_source",
            "next_hermes_action": "configure_ga4_or_upload_demand_export",
            "summary": "No tenant-side demand source is ready.",
        }

    def importer(**kwargs):
        raise AssertionError("importer must not be called when no source is ready")

    result = module.run_demand_intake(
        tenant="algolia",
        app_dir=tmp_path / "app",
        work_root=tmp_path / "work",
        readiness_builder=readiness_builder,
        importer=importer,
    )

    assert result["status"] == "blocked_missing_demand_source"
    assert result["exit_code"] == 2
    assert result["mode"] == "blocked"
    assert result["next_hermes_action"] == "configure_ga4_or_upload_demand_export"


def test_run_argus_demand_intake_surfaces_bad_manual_export_as_operator_repair(tmp_path) -> None:
    module = _load_module()

    def readiness_builder(**kwargs):
        return {
            "tenant_slug": kwargs["tenant_slug"],
            "status": "blocked_bad_manual_export",
            "next_hermes_action": "repair_queued_demand_export",
            "summary": "A queued demand export exists but cannot be normalized.",
        }

    result = module.run_demand_intake(
        tenant="algolia",
        app_dir=tmp_path / "app",
        work_root=tmp_path / "work",
        readiness_builder=readiness_builder,
    )

    assert result["status"] == "blocked_bad_manual_export"
    assert result["exit_code"] == 3
    assert result["mode"] == "blocked"
    assert result["next_hermes_action"] == "repair_queued_demand_export"


def test_run_argus_demand_intake_main_writes_summary_and_uses_exit_code(tmp_path, monkeypatch) -> None:
    module = _load_module()
    output = tmp_path / "summary.json"
    calls: list[dict] = []

    def fake_run_demand_intake(**kwargs):
        calls.append(kwargs)
        return {
            "status": "blocked_missing_demand_source",
            "exit_code": 2,
            "tenant": kwargs["tenant"],
            "mode": "blocked",
        }

    monkeypatch.setattr(module, "run_demand_intake", fake_run_demand_intake)

    code = module.main(
        [
            "--tenant",
            "algolia",
            "--app-dir",
            str(tmp_path / "app"),
            "--work-root",
            str(tmp_path / "work"),
            "--demand-change-floor",
            "0.03",
            "--demand-value-floor",
            "25",
            "--output",
            str(output),
        ]
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert code == 2
    assert payload["status"] == "blocked_missing_demand_source"
    assert payload["tenant"] == "algolia"
    assert calls[0]["demand_change_floor"] == 0.03
    assert calls[0]["demand_value_floor"] == 25.0


def test_run_argus_demand_intake_main_records_history_copy_for_blocked_attempt(
    tmp_path,
    monkeypatch,
) -> None:
    module = _load_module()
    output = tmp_path / "out" / "argus-demand-intake.json"
    work_root = tmp_path / "work"

    def fake_run_demand_intake(**kwargs):
        return {
            "status": "blocked_missing_demand_source",
            "exit_code": 2,
            "tenant": kwargs["tenant"],
            "mode": "blocked",
            "next_hermes_action": "configure_ga4_or_upload_demand_export",
            "readiness": {"status": "blocked_missing_demand_source"},
        }

    monkeypatch.setattr(module, "run_demand_intake", fake_run_demand_intake)

    code = module.main(
        [
            "--tenant",
            "algolia",
            "--app-dir",
            str(tmp_path / "app"),
            "--work-root",
            str(work_root),
            "--output",
            str(output),
            "--record-history",
        ]
    )

    sidecar = json.loads(output.read_text(encoding="utf-8"))
    history_path = Path(sidecar["summary_path"])
    history = json.loads(history_path.read_text(encoding="utf-8"))
    assert code == 2
    assert history_path.name == "demand-intake-summary.json"
    assert history_path.parent.parent == work_root / "algolia" / "demand-intake-runs"
    assert sidecar["status"] == "blocked_missing_demand_source"
    assert sidecar["generated_at"] == history["generated_at"]
    assert sidecar["summary_path"] == str(history_path)
    assert sidecar["run_output_dir"] == str(history_path.parent)
    assert history["status"] == "blocked_missing_demand_source"
    assert history["exit_code"] == 2
    assert history["mode"] == "blocked"
