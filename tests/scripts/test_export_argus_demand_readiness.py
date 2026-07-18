"""Tests for the Hermes-facing inward-demand readiness artifact."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "export_argus_demand_readiness.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("export_argus_demand_readiness", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_export_argus_demand_readiness_reports_missing_inward_contract_without_secrets(tmp_path) -> None:
    module = _load_module()
    app_dir = tmp_path / "app"
    work_root = tmp_path / "work"
    secret_path = tmp_path / "credentials.json"
    dashboard = {
        "product_market_run": {
            "demand_plane_status": "missing",
            "looker_discovered_count": 0,
            "looker_ready_count": 0,
            "looker_error_count": 0,
            "looker_normalized_row_count": 0,
            "demand_signal_count": 0,
        }
    }

    payload = module.build_demand_readiness_payload(
        tenant_slug="algolia",
        app_dir=app_dir,
        work_root=work_root,
        env={
            "CIOS_GA4_EXPORT_ENABLED": "1",
            "CIOS_GA4_CREDENTIALS_JSON": str(secret_path),
        },
        dashboard=dashboard,
        generated_at="2026-07-12T02:00:00Z",
    )

    rendered = json.dumps(payload, sort_keys=True)
    assert payload["status"] == "blocked_missing_configuration"
    assert payload["next_hermes_action"] == "configure_ga4_or_upload_demand_export"
    assert payload["demand_plane"]["status"] == "missing"
    assert payload["manual_import"]["inbox_file_count"] == 0
    assert payload["manual_import"]["template_fields"] == [
        "Page title",
        "Page path",
        "Engaged sessions",
        "Engaged sessions previous period",
        "Period start",
        "Period end",
        "Looker Studio URL",
    ]
    assert payload["ga4_connector"]["enabled"] is True
    assert payload["ga4_connector"]["ready"] is False
    assert "CIOS_GA4_PROPERTY_ID" in payload["ga4_connector"]["missing_required"]
    assert "CIOS_GA4_PROPERTY_ID" in payload["ga4_connector"]["setup_required"]
    assert "CIOS_GA4_CREDENTIALS_JSON or GOOGLE_APPLICATION_CREDENTIALS" in (
        payload["ga4_connector"]["setup_required"]
    )
    assert payload["operator_actions"][0] == {
        "label": "Download demand plan template",
        "href": "/api/tenants/algolia/argus/demand-imports/template?planned=1",
        "method": "get",
        "surface": "Demand imports",
    }
    contract = payload["demand_source_contract"]
    assert contract["schema_version"] == 1
    assert contract["tenant_slug"] == "algolia"
    assert contract["status"] == "blocked_missing_configuration"
    assert contract["ready_source_count"] == 0
    assert contract["contract_path"] == str(work_root / "algolia" / "demand-source-contract.json")
    assert [source["source_id"] for source in contract["sources"]] == [
        "manual_looker_export",
        "ga4_connector",
    ]
    assert contract["sources"][0]["status"] == "waiting_for_upload"
    assert contract["sources"][0]["landing_zone"] == str(app_dir / "data" / "looker" / "algolia")
    assert contract["sources"][1]["status"] == "not_ready"
    assert "CIOS_GA4_PROPERTY_ID" in contract["sources"][1]["setup_required"]
    assert (work_root / "algolia" / "demand-source-contract.json").exists()
    assert str(secret_path) not in rendered
    assert str(secret_path) not in (work_root / "algolia" / "demand-source-contract.json").read_text(
        encoding="utf-8"
    )


def test_export_argus_demand_readiness_builds_collection_plan_from_product_feature_read(tmp_path) -> None:
    module = _load_module()
    app_dir = tmp_path / "app"
    work_root = tmp_path / "work"
    dashboard = {
        "product_market_run": {
            "demand_plane_status": "missing",
            "looker_discovered_count": 0,
            "looker_ready_count": 0,
            "looker_error_count": 0,
            "looker_normalized_row_count": 0,
            "demand_signal_count": 0,
            "product_feature_comparison_read": {
                "summary": "2 capabilities compared; 1 product gap, 1 narrative gap, 0 demand-backed rows.",
                "rows": [
                    {
                        "capability": "AI Assistant",
                        "capability_key": "ai assistant",
                        "assessment": "own_product_gap",
                        "recommended_action": "Decide whether Algolia needs product proof for AI Assistant.",
                        "competitors_with_product_proof": ["Constructor"],
                        "competitors_with_conversation": ["Constructor", "Elastic"],
                        "evidence_urls": [
                            "https://constructor.com/changelog/ai-assistant",
                            "https://elastic.co/blog/search-ai-assistant",
                        ],
                    },
                    {
                        "capability": "Context engineering",
                        "capability_key": "context engineering",
                        "assessment": "own_narrative_gap",
                        "recommended_action": "Create an Algolia narrative for context engineering.",
                        "competitors_with_product_proof": ["Elastic"],
                        "competitors_with_conversation": ["Elastic"],
                        "evidence_urls": ["https://elastic.co/blog/context-engineering"],
                    },
                ],
            },
        }
    }

    payload = module.build_demand_readiness_payload(
        tenant_slug="algolia",
        app_dir=app_dir,
        work_root=work_root,
        env={"CIOS_GA4_EXPORT_ENABLED": "0"},
        dashboard=dashboard,
        generated_at="2026-07-12T02:00:00Z",
    )

    plan = payload["demand_collection_plan"]
    rendered = json.dumps(plan, sort_keys=True)
    assert plan["status"] == "needs_demand_source"
    assert plan["source_dashboard_field"] == "product_market_run.product_feature_comparison_read.rows"
    assert plan["drop_folder"] == str(app_dir / "data" / "looker" / "algolia")
    assert plan["template_fields"] == [
        "Page title",
        "Page path",
        "Engaged sessions",
        "Engaged sessions previous period",
        "Period start",
        "Period end",
        "Looker Studio URL",
    ]
    assert plan["topic_count"] == 2
    assert [topic["capability_key"] for topic in plan["topics"]] == [
        "ai assistant",
        "context engineering",
    ]
    assert plan["topics"][0]["priority"] == 1
    assert plan["topics"][0]["assessment"] == "own_product_gap"
    assert "AI Assistant" in plan["topics"][0]["suggested_filter_terms"]
    assert "Constructor" in plan["topics"][0]["related_competitors"]
    assert plan["topics"][0]["why_collect"] == "Decide whether Algolia needs product proof for AI Assistant."
    assert "/admin" not in rendered
    assert "credentials" not in rendered.lower()
    contract_plan = payload["demand_source_contract"]["demand_plan"]
    assert contract_plan["status"] == "needs_demand_source"
    assert contract_plan["topic_count"] == 2
    assert contract_plan["template"] == {
        "format": "csv",
        "filename": "argus-demand-plan-template.csv",
    }
    assert contract_plan["top_topics"][0] == {
        "topic": "AI Assistant",
        "capability_key": "ai assistant",
        "assessment": "own_product_gap",
        "related_competitors": ["Constructor", "Elastic"],
        "suggested_filter_terms": ["AI Assistant", "assistant"],
        "evidence_url_count": 2,
    }
    contract_plan_rendered = json.dumps(contract_plan, sort_keys=True)
    assert str(app_dir) not in contract_plan_rendered
    assert "why_collect" not in contract_plan_rendered


def test_export_argus_demand_readiness_falls_back_to_patterns_when_feature_read_is_empty(
    tmp_path,
) -> None:
    module = _load_module()
    app_dir = tmp_path / "app"
    work_root = tmp_path / "work"
    dashboard = {
        "product_market_run": {
            "demand_plane_status": "missing",
            "looker_discovered_count": 0,
            "looker_ready_count": 0,
            "looker_error_count": 0,
            "looker_normalized_row_count": 0,
            "demand_signal_count": 0,
            "pattern_observations": [
                {
                    "pattern_type": "competitive_pressure",
                    "capability_text": "Agentic merchandising",
                    "summary": "Constructor and Elastic are converging on agentic merchandising language.",
                    "involved_companies": ["Constructor", "Elastic"],
                    "evidence_refs": [
                        {
                            "source_url": "https://constructor.com/blog/agentic-merchandising",
                        },
                        {
                            "source_url": "https://elastic.co/blog/agentic-commerce",
                        },
                    ],
                }
            ],
            "intelligence_brief": {
                "decision_read": {
                    "priority_reason": "Watch agentic merchandising because two competitors now use it.",
                    "tactical_actions": [
                        {
                            "owner": "PMM",
                            "action": "Check whether Algolia demand exists for agentic merchandising pages.",
                        }
                    ],
                }
            },
        }
    }

    payload = module.build_demand_readiness_payload(
        tenant_slug="algolia",
        app_dir=app_dir,
        work_root=work_root,
        env={"CIOS_GA4_EXPORT_ENABLED": "0"},
        dashboard=dashboard,
        generated_at="2026-07-12T02:00:00Z",
    )

    plan = payload["demand_collection_plan"]
    assert plan["status"] == "needs_demand_source"
    assert plan["source_dashboard_field"] == "product_market_run.pattern_observations"
    assert plan["topic_count"] == 1
    assert plan["topics"][0]["topic"] == "Agentic merchandising"
    assert plan["topics"][0]["capability_key"] == "agentic merchandising"
    assert plan["topics"][0]["assessment"] == "competitive_pressure"
    assert plan["topics"][0]["related_competitors"] == ["Constructor", "Elastic"]
    assert plan["topics"][0]["evidence_urls"] == [
        "https://constructor.com/blog/agentic-merchandising",
        "https://elastic.co/blog/agentic-commerce",
    ]
    assert plan["topics"][0]["why_collect"] == (
        "Check whether Algolia demand exists for agentic merchandising pages."
    )


def test_export_argus_demand_readiness_scores_imported_demand_against_collection_plan(tmp_path) -> None:
    module = _load_module()
    app_dir = tmp_path / "app"
    work_root = tmp_path / "work"
    dashboard = {
        "product_market_run": {
            "demand_plane_status": "processed",
            "looker_discovered_count": 3,
            "looker_ready_count": 1,
            "looker_error_count": 0,
            "looker_normalized_row_count": 3,
            "demand_signal_count": 3,
            "product_feature_comparison_read": {
                "rows": [
                    {
                        "capability": "AI Assistant",
                        "capability_key": "ai assistant",
                        "assessment": "own_product_gap",
                        "recommended_action": "Decide whether Algolia needs product proof for AI Assistant.",
                    },
                    {
                        "capability": "Context engineering",
                        "capability_key": "context engineering",
                        "assessment": "own_narrative_gap",
                        "recommended_action": "Create an Algolia narrative for context engineering.",
                    },
                ]
            },
            "intelligence_brief": {
                "demand_read": {
                    "top_topics": [
                        {
                            "topic": "Context engineering",
                            "capability_key": "context engineering",
                            "value": 180,
                            "change_pct": 0.41,
                            "source_files": ["ga-pages.csv"],
                            "source_row_numbers": [2],
                            "evidence_urls": ["https://lookerstudio.google.com/reporting/context"],
                        },
                        {
                            "topic": "Pricing",
                            "capability_key": "pricing",
                            "value": 240,
                            "change_pct": 0.33,
                            "source_files": ["ga-pages.csv"],
                            "source_row_numbers": [3],
                            "evidence_urls": ["https://lookerstudio.google.com/reporting/pricing"],
                        },
                    ]
                }
            },
        }
    }

    payload = module.build_demand_readiness_payload(
        tenant_slug="algolia",
        app_dir=app_dir,
        work_root=work_root,
        env={"CIOS_GA4_EXPORT_ENABLED": "0"},
        dashboard=dashboard,
        generated_at="2026-07-12T02:00:00Z",
    )

    coverage = payload["demand_collection_plan"]["coverage"]
    assert payload["status"] == "processed_partial_plan_coverage"
    assert payload["next_hermes_action"] == "collect_missing_plan_demand"
    assert payload["summary"] == (
        "Tenant demand evidence exists, but it only covers 1 of 2 Argus-prioritized demand topics."
    )
    assert payload["demand_collection_plan"]["status"] == "partial_coverage"
    assert coverage["planned_topic_count"] == 2
    assert coverage["covered_topic_count"] == 1
    assert coverage["missing_topic_count"] == 1
    assert coverage["off_plan_topic_count"] == 1
    assert coverage["coverage_ratio"] == 0.5
    assert coverage["covered_topics"][0]["capability_key"] == "context engineering"
    assert coverage["missing_topics"][0]["capability_key"] == "ai assistant"
    assert coverage["off_plan_topics"][0]["capability_key"] == "pricing"
    assert coverage["off_plan_topics"][0]["evidence_urls"] == ["https://lookerstudio.google.com/reporting/pricing"]


def test_export_argus_demand_readiness_does_not_block_processed_non_rising_demand(
    tmp_path,
) -> None:
    module = _load_module()
    app_dir = tmp_path / "app"
    work_root = tmp_path / "work"
    dashboard = {
        "product_market_run": {
            "demand_plane_status": "processed",
            "looker_discovered_count": 1,
            "looker_ready_count": 0,
            "looker_error_count": 0,
            "looker_normalized_row_count": 1,
            "demand_signal_count": 1,
            "product_feature_comparison_read": {
                "rows": [
                    {
                        "capability": "AI Assistant",
                        "capability_key": "ai assistant",
                        "assessment": "competitive_pressure",
                        "recommended_action": "Watch AI Assistant until demand changes.",
                    }
                ]
            },
            "intelligence_brief": {
                "demand_read": {
                    "summary": "1 demand signal captured, but none crossed the rising-demand threshold.",
                    "demand_signal_count": 1,
                    "rising_topic_count": 0,
                    "top_topics": [],
                    "source_files": ["algolia-looker-agent-search-sessions.csv"],
                    "evidence_urls": ["https://lookerstudio.google.com/reporting/abc"],
                }
            },
        }
    }

    payload = module.build_demand_readiness_payload(
        tenant_slug="algolia",
        app_dir=app_dir,
        work_root=work_root,
        env={"CIOS_GA4_EXPORT_ENABLED": "0"},
        dashboard=dashboard,
        generated_at="2026-07-12T02:00:00Z",
    )

    coverage = payload["demand_collection_plan"]["coverage"]
    assert payload["status"] == "processed"
    assert payload["next_hermes_action"] == "continue_product_market_synthesis"
    assert payload["summary"] == "Tenant demand evidence is already present in the latest Argus run."
    assert payload["demand_collection_plan"]["status"] == "processed_no_rising_demand"
    assert coverage["status"] == "processed_no_rising_demand"
    assert coverage["planned_topic_count"] == 1
    assert coverage["covered_topic_count"] == 0
    assert coverage["actual_topic_count"] == 0
    assert coverage["missing_topic_count"] == 0
    assert coverage["off_plan_topic_count"] == 0
    assert coverage["coverage_ratio"] == 0


def test_export_argus_demand_readiness_prefers_queued_manual_exports(tmp_path) -> None:
    module = _load_module()
    app_dir = tmp_path / "app"
    work_root = tmp_path / "work"
    drop = app_dir / "data" / "looker" / "algolia"
    drop.mkdir(parents=True)
    (drop / "ga-pages.csv").write_text(
        "Page title,Page path,Engaged sessions,Engaged sessions previous period,Period start,Period end,Looker Studio URL\n"
        "AI Shopping Agent guide,/solutions/ai-shopping-agent,240,160,2026-07-01,2026-07-08,https://lookerstudio.google.com/reporting/abc\n",
        encoding="utf-8",
    )

    payload = module.build_demand_readiness_payload(
        tenant_slug="algolia",
        app_dir=app_dir,
        work_root=work_root,
        env={"CIOS_GA4_EXPORT_ENABLED": "0"},
        dashboard={},
        generated_at="2026-07-12T02:00:00Z",
    )

    assert payload["status"] == "queued_manual_exports"
    assert payload["next_hermes_action"] == "prepare_demand_and_refresh_argus"
    assert payload["manual_import"]["inbox_file_count"] == 1
    assert payload["manual_import"]["ready_preview_count"] == 1
    assert payload["manual_import"]["normalized_preview_row_count"] == 1
    assert payload["demand_source_contract"]["status"] == "ready"
    assert payload["demand_source_contract"]["ready_source_count"] == 1
    assert payload["demand_source_contract"]["sources"][0]["status"] == "queued_ready"
    assert payload["operator_actions"][0]["label"] == "Prepare demand and refresh Argus"


def test_export_argus_demand_readiness_creates_manual_drop_folder(tmp_path) -> None:
    module = _load_module()
    app_dir = tmp_path / "app"
    work_root = tmp_path / "work"
    drop = app_dir / "data" / "looker" / "algolia"

    assert not drop.exists()

    payload = module.build_demand_readiness_payload(
        tenant_slug="algolia",
        app_dir=app_dir,
        work_root=work_root,
        env={"CIOS_GA4_EXPORT_ENABLED": "0"},
        dashboard={},
        generated_at="2026-07-12T02:00:00Z",
    )

    assert drop.is_dir()
    assert payload["manual_import"]["drop_folder"] == str(drop)
    assert payload["manual_import"]["inbox_file_count"] == 0
    assert payload["ga4_connector"]["status"] == "disabled"
    assert payload["ga4_connector"]["missing_required"] == []
    assert payload["ga4_connector"]["setup_required"] == [
        "CIOS_GA4_EXPORT_ENABLED",
        "CIOS_GA4_PROPERTY_ID",
        "CIOS_GA4_CREDENTIALS_JSON or GOOGLE_APPLICATION_CREDENTIALS",
        "CIOS_GA4_EXPORT_SCRIPT",
    ]
    action_labels = [action["label"] for action in payload["operator_actions"]]
    assert "Configure GA4 connector" in action_labels
    assert "Run GA4 export now" not in action_labels


def test_export_argus_demand_readiness_marks_ga4_ready_to_export(tmp_path) -> None:
    module = _load_module()
    app_dir = tmp_path / "app"
    work_root = tmp_path / "work"
    credentials = tmp_path / "credentials.json"
    credentials.write_text("{}", encoding="utf-8")
    script = app_dir / "scripts" / "export_ga4_demand.py"
    script.parent.mkdir(parents=True)
    script.write_text("# fake export script\n", encoding="utf-8")

    payload = module.build_demand_readiness_payload(
        tenant_slug="algolia",
        app_dir=app_dir,
        work_root=work_root,
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
        generated_at="2026-07-12T02:00:00Z",
    )

    assert payload["status"] == "ready_to_export_ga4"
    assert payload["next_hermes_action"] == "run_ga4_export_then_prepare_demand"
    assert payload["demand_source_contract"]["status"] == "ready"
    assert payload["demand_source_contract"]["ready_source_count"] == 1
    assert payload["demand_source_contract"]["sources"][1]["status"] == "ready"
    assert payload["ga4_connector"]["property_configured"] is True
    assert payload["ga4_connector"]["credentials_configured"] is True
    assert payload["ga4_connector"]["current_window"] == {"start": "2026-07-01", "end": "2026-07-08"}
    assert payload["ga4_connector"]["previous_window"] == {"start": "2026-06-24", "end": "2026-06-30"}
    assert payload["operator_actions"][0] == {
        "label": "Run GA4 export and refresh Argus",
        "href": "/admin/algolia/argus/ga4-export/refresh",
        "method": "post",
        "surface": "GA4 connector",
    }
    assert payload["operator_actions"][1]["label"] == "Run GA4 export now"


def test_export_argus_demand_readiness_main_loads_default_dashboard_from_app_out(
    tmp_path, monkeypatch
) -> None:
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
                                "capability": "Channel Assistant",
                                "capability_key": "channel assistant",
                                "assessment": "watch",
                                "competitors_with_product_proof": ["Klevu"],
                                "evidence_urls": ["https://klevu.com/channel-assistant"],
                            }
                        ]
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "readiness.json"

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
    assert code == 0
    assert payload["demand_collection_plan"]["topic_count"] == 1
    assert payload["demand_collection_plan"]["topics"][0]["topic"] == "Channel Assistant"
    assert payload["demand_source_contract"]["demand_plan"]["top_topics"][0]["topic"] == "Channel Assistant"
