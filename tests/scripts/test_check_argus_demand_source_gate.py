from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "check_argus_demand_source_gate.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_argus_demand_source_gate", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_gate_fails_when_no_manual_or_ga4_demand_source_is_ready(tmp_path) -> None:
    module = _load_module()

    readiness = module.build_readiness(
        tenant_slug="algolia",
        app_dir=tmp_path / "app",
        work_root=tmp_path / "work",
        env={"CIOS_GA4_EXPORT_ENABLED": "0"},
        dashboard={},
    )
    gate = module.evaluate_gate(readiness)

    assert gate["status"] == "fail"
    assert gate["exit_code"] == 2
    assert gate["readiness_status"] == "blocked_missing_demand_source"
    assert gate["next_hermes_action"] == "configure_ga4_or_upload_demand_export"
    assert gate["checks"]["source_ready"] is False
    assert gate["checks"]["current_demand_processed"] is False
    assert gate["readiness_summary"]["ga4_missing_required"] == []
    assert gate["readiness_summary"]["ga4_setup_required"] == [
        "CIOS_GA4_EXPORT_ENABLED",
        "CIOS_GA4_PROPERTY_ID",
        "CIOS_GA4_CREDENTIALS_JSON or GOOGLE_APPLICATION_CREDENTIALS",
        "CIOS_GA4_EXPORT_SCRIPT",
    ]
    assert gate["readiness_summary"]["demand_source_contract_status"] == "blocked_no_ready_source"
    assert gate["readiness_summary"]["ready_demand_source_count"] == 0
    assert gate["readiness_summary"]["demand_source_ids"] == [
        "manual_looker_export",
        "ga4_connector",
    ]
    assert gate["readiness_summary"]["demand_plan_status"] == "needs_demand_source"
    assert gate["readiness_summary"]["demand_plan_topic_count"] == 0
    assert gate["readiness_summary"]["demand_plan_top_topics"] == []


def test_gate_summary_carries_argus_demand_plan_topics(tmp_path) -> None:
    module = _load_module()
    readiness = module.build_readiness(
        tenant_slug="algolia",
        app_dir=tmp_path / "app",
        work_root=tmp_path / "work",
        env={"CIOS_GA4_EXPORT_ENABLED": "0"},
        dashboard={
            "product_market_run": {
                "demand_plane_status": "missing",
                "looker_normalized_row_count": 0,
                "demand_signal_count": 0,
                "product_feature_comparison_read": {
                    "rows": [
                        {
                            "capability": "AI Assistant",
                            "capability_key": "ai assistant",
                            "assessment": "own_product_gap",
                            "competitors_with_product_proof": ["Constructor"],
                            "competitors_with_conversation": ["Constructor", "Elastic"],
                            "recommended_action": "Collect tenant demand for AI Assistant.",
                            "evidence_urls": [
                                "https://constructor.com/changelog/ai-assistant",
                                "https://elastic.co/blog/ai-assistant",
                            ],
                        }
                    ]
                },
            }
        },
    )

    gate = module.evaluate_gate(readiness)

    assert gate["status"] == "fail"
    assert gate["readiness_summary"]["demand_plan_status"] == "needs_demand_source"
    assert gate["readiness_summary"]["demand_plan_topic_count"] == 1
    assert gate["readiness_summary"]["demand_plan_top_topics"] == [
        {
            "topic": "AI Assistant",
            "capability_key": "ai assistant",
            "assessment": "own_product_gap",
            "related_competitors": ["Constructor", "Elastic"],
            "suggested_filter_terms": ["AI Assistant", "assistant"],
            "evidence_url_count": 2,
        }
    ]
    rendered = json.dumps(gate["readiness_summary"]["demand_plan_top_topics"], sort_keys=True)
    assert str(tmp_path / "app") not in rendered
    assert "/admin" not in rendered
    assert "href" not in rendered


def test_gate_passes_when_manual_export_is_queued(tmp_path) -> None:
    module = _load_module()
    app_dir = tmp_path / "app"
    drop = app_dir / "data" / "looker" / "algolia"
    drop.mkdir(parents=True)
    (drop / "ga-pages.csv").write_text(
        "Page title,Page path,Engaged sessions,Engaged sessions previous period,Period start,Period end,Looker Studio URL\n"
        "AI Shopping Agent guide,/solutions/ai-shopping-agent,240,160,2026-07-01,2026-07-08,https://lookerstudio.google.com/reporting/abc\n",
        encoding="utf-8",
    )

    readiness = module.build_readiness(
        tenant_slug="algolia",
        app_dir=app_dir,
        work_root=tmp_path / "work",
        env={"CIOS_GA4_EXPORT_ENABLED": "0"},
        dashboard={},
    )
    gate = module.evaluate_gate(readiness)

    assert gate["status"] == "pass"
    assert gate["exit_code"] == 0
    assert gate["readiness_status"] == "queued_manual_exports"
    assert gate["checks"]["source_ready"] is True
    assert gate["checks"]["manual_export_ready"] is True


def test_gate_passes_when_ga4_export_is_ready(tmp_path) -> None:
    module = _load_module()
    app_dir = tmp_path / "app"
    credentials = tmp_path / "credentials.json"
    credentials.write_text("{}", encoding="utf-8")
    script = app_dir / "scripts" / "export_ga4_demand.py"
    script.parent.mkdir(parents=True)
    script.write_text("# fake export script\n", encoding="utf-8")

    readiness = module.build_readiness(
        tenant_slug="algolia",
        app_dir=app_dir,
        work_root=tmp_path / "work",
        env={
            "CIOS_GA4_EXPORT_ENABLED": "1",
            "CIOS_GA4_PROPERTY_ID": "properties/123456",
            "CIOS_GA4_CURRENT_START": "2026-07-01",
            "CIOS_GA4_CURRENT_END": "2026-07-08",
            "CIOS_GA4_PREVIOUS_START": "2026-06-24",
            "CIOS_GA4_PREVIOUS_END": "2026-06-30",
            "CIOS_GA4_CREDENTIALS_JSON": str(credentials),
        },
        dashboard={},
    )
    gate = module.evaluate_gate(readiness)

    assert gate["status"] == "pass"
    assert gate["exit_code"] == 0
    assert gate["readiness_status"] == "ready_to_export_ga4"
    assert gate["checks"]["source_ready"] is True
    assert gate["checks"]["ga4_ready"] is True


def test_strict_gate_requires_current_processed_demand(tmp_path) -> None:
    module = _load_module()
    app_dir = tmp_path / "app"
    drop = app_dir / "data" / "looker" / "algolia"
    drop.mkdir(parents=True)
    (drop / "ga-pages.csv").write_text(
        "Page title,Page path,Engaged sessions,Engaged sessions previous period,Period start,Period end,Looker Studio URL\n"
        "AI Shopping Agent guide,/solutions/ai-shopping-agent,240,160,2026-07-01,2026-07-08,https://lookerstudio.google.com/reporting/abc\n",
        encoding="utf-8",
    )
    readiness = module.build_readiness(
        tenant_slug="algolia",
        app_dir=app_dir,
        work_root=tmp_path / "work",
        env={"CIOS_GA4_EXPORT_ENABLED": "0"},
        dashboard={},
    )

    gate = module.evaluate_gate(readiness, require_current_demand=True)

    assert gate["status"] == "fail"
    assert gate["exit_code"] == 2
    assert gate["readiness_status"] == "queued_manual_exports"
    assert gate["checks"]["source_ready"] is True
    assert gate["checks"]["current_demand_processed"] is False


def test_strict_gate_passes_when_dashboard_has_processed_demand(tmp_path) -> None:
    module = _load_module()
    readiness = module.build_readiness(
        tenant_slug="algolia",
        app_dir=tmp_path / "app",
        work_root=tmp_path / "work",
        env={"CIOS_GA4_EXPORT_ENABLED": "0"},
        dashboard={
            "product_market_run": {
                "demand_plane_status": "processed",
                "looker_normalized_row_count": 2,
                "demand_signal_count": 2,
            }
        },
    )

    gate = module.evaluate_gate(readiness, require_current_demand=True)

    assert gate["status"] == "pass"
    assert gate["exit_code"] == 0
    assert gate["readiness_status"] == "processed"
    assert gate["checks"]["current_demand_processed"] is True


def test_main_loads_default_dashboard_from_app_out_when_omitted(tmp_path, monkeypatch) -> None:
    module = _load_module()
    monkeypatch.setenv("CIOS_GA4_EXPORT_ENABLED", "0")
    app_dir = tmp_path / "app"
    dashboard = app_dir / "out" / "argus-dashboard.json"
    dashboard.parent.mkdir(parents=True)
    dashboard.write_text(
        json.dumps(
            {
                "product_market_run": {
                    "demand_plane_status": "missing",
                    "demand_signal_count": 0,
                    "product_feature_comparison_read": {
                        "rows": [
                            {
                                "capability": "AI Assistant",
                                "capability_key": "ai assistant",
                                "assessment": "own_product_gap",
                                "competitors_with_product_proof": ["Constructor"],
                                "competitors_with_conversation": ["Elastic"],
                                "evidence_urls": ["https://constructor.com/changelog/ai-assistant"],
                            }
                        ]
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "gate.json"

    code = module.main(
        [
            "--tenant",
            "algolia",
            "--app-dir",
            str(app_dir),
            "--work-root",
            str(tmp_path / "work"),
            "--output",
            str(output),
        ]
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert code == 2
    assert payload["readiness_summary"]["demand_plan_topic_count"] == 1
    assert payload["readiness_summary"]["demand_plan_top_topics"][0]["topic"] == "AI Assistant"


def test_main_writes_gate_payload_and_returns_exit_code(tmp_path) -> None:
    module = _load_module()
    output = tmp_path / "gate.json"

    code = module.main(
        [
            "--tenant",
            "algolia",
            "--app-dir",
            str(tmp_path / "app"),
            "--work-root",
            str(tmp_path / "work"),
            "--output",
            str(output),
        ]
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert code == 2
    assert payload["gate"] == "argus_demand_source"
    assert payload["status"] == "fail"
    assert payload["exit_code"] == 2
