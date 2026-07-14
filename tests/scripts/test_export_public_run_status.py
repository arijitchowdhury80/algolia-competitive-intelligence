"""Contract tests for the public-safe Argus run status artifact."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "export_public_run_status.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("export_public_run_status", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_public_status_binds_explicit_manifest_run_id() -> None:
    module = _load_module()
    run_id = "cios-20260714T090000Z-12345"

    payload = module.build_public_run_status_payload(
        tenant_slug="algolia",
        manifest={"run_id": run_id, "status": "blocked_on_evidence", "planes": {}},
        dashboard={},
        publish_status="blocked",
        run_id=run_id,
        generated_at="2026-07-14T09:00:00Z",
    )

    assert payload["schema_version"] == 2
    assert payload["run_id"] == run_id


def test_public_status_rejects_manifest_run_id_mismatch() -> None:
    module = _load_module()

    with pytest.raises(ValueError, match="manifest run_id mismatch"):
        module.build_public_run_status_payload(
            tenant_slug="algolia",
            manifest={"run_id": "cios-20260714T090000Z-other", "status": "blocked", "planes": {}},
            dashboard={},
            publish_status="blocked",
            run_id="cios-20260714T090000Z-12345",
        )


def test_public_run_status_strips_local_paths_and_preserves_blocker_summary() -> None:
    module = _load_module()

    payload = module.build_public_run_status_payload(
        tenant_slug="algolia",
        manifest={
            "schema_version": 1,
            "tenant_slug": "algolia",
            "generated_at": "2026-07-12T14:44:19Z",
            "dashboard_generated_at": "2026-07-12T14:44:17Z",
            "status": "blocked_on_evidence",
            "next_hermes_action": "configure_ga4_or_upload_demand_export",
            "artifact_refs": {
                "dashboard": "/root/.hermes/apps/cios/out/argus-dashboard.json",
                "demand_intake": "/tmp/cios-product-market/algolia/demand-intake-runs/run.json",
            },
            "planes": {
                "audience_demand": {
                    "status": "blocked_missing_demand_source",
                    "summary": "No tenant-side demand source is ready.",
                    "blocks_action": True,
                    "next_hermes_action": "configure_ga4_or_upload_demand_export",
                    "counts": {
                        "demand_signal_count": 0,
                        "looker_ready_count": 0,
                    },
                    "details": {
                        "manual_import": {
                            "drop_folder": "/root/.hermes/apps/cios/data/looker/algolia",
                        },
                        "demand_source_contract": {
                            "contract_path": "/tmp/cios-product-market/algolia/demand-source-contract.json",
                            "status": "blocked_no_ready_source",
                        },
                    },
                },
                "product_reality": {
                    "status": "present",
                    "summary": "Product reality evidence fed the feature matrix.",
                    "blocks_action": False,
                    "counts": {"product_event_count": 4},
                },
            },
            "blockers": [
                {
                    "plane": "audience_demand",
                    "severity": "blocks_action",
                    "title": "Demand plane missing",
                    "next_step": "Configure GA4 or upload demand.",
                    "work_item_id": "argus-evidence:17:demand",
                    "operator_commands": [
                        {
                            "label": "Download demand template",
                            "method": "get",
                            "surface": "Demand imports",
                            "route_kind": "api",
                        }
                    ],
                    "internal_path": "/root/.hermes/private",
                }
            ],
        },
        dashboard={
            "generated_at": "2026-07-12T14:44:17Z",
            "source_health": {
                "active_source_count": 48,
                "checked_source_count": 48,
                "failed_source_count": 6,
            },
            "product_market_run": {
                "status": "ran",
                "product_event_count": 4,
                "conversation_theme_count": 3,
                "demand_signal_count": 0,
                "pattern_count": 2,
                "recommendation_count": 0,
            },
        },
        publish_status="blocked",
        generated_at="2026-07-12T14:45:00Z",
    )

    assert payload == {
        "schema_version": 1,
        "tenant_slug": "algolia",
        "generated_at": "2026-07-12T14:45:00Z",
        "manifest_generated_at": "2026-07-12T14:44:19Z",
        "dashboard_generated_at": "2026-07-12T14:44:17Z",
        "publish_status": "blocked",
        "status": "blocked_on_evidence",
        "next_hermes_action": "configure_ga4_or_upload_demand_export",
        "public_dashboard_updated": False,
        "source_coverage": {
            "active_source_count": 48,
            "checked_source_count": 48,
            "failed_source_count": 6,
        },
        "product_market_run": {
            "status": "ran",
            "product_event_count": 4,
            "conversation_theme_count": 3,
            "demand_signal_count": 0,
            "pattern_count": 2,
            "recommendation_count": 0,
        },
        "planes": {
            "audience_demand": {
                "status": "blocked_missing_demand_source",
                "summary": "No tenant-side demand source is ready.",
                "blocks_action": True,
                "next_hermes_action": "configure_ga4_or_upload_demand_export",
                "counts": {
                    "demand_signal_count": 0,
                    "looker_ready_count": 0,
                },
            },
            "product_reality": {
                "status": "present",
                "summary": "Product reality evidence fed the feature matrix.",
                "blocks_action": False,
                "counts": {"product_event_count": 4},
            },
        },
        "blockers": [
            {
                "plane": "audience_demand",
                "severity": "blocks_action",
                "title": "Demand plane missing",
                "next_step": "Configure GA4 or upload demand.",
                "work_item_id": "argus-evidence:17:demand",
                "operator_commands": [
                    {
                        "label": "Download demand template",
                        "method": "get",
                        "surface": "Demand imports",
                        "route_kind": "api",
                    }
                ],
            }
        ],
        "safety": {
            "artifact_paths_redacted": True,
            "secret_values_included": False,
            "public_safe": True,
        },
    }
    serialized = json.dumps(payload, sort_keys=True)
    assert "/root/" not in serialized
    assert "/tmp/" not in serialized


def test_public_run_status_cli_writes_json(tmp_path) -> None:
    module = _load_module()
    manifest = tmp_path / "manifest.json"
    dashboard = tmp_path / "dashboard.json"
    output = tmp_path / "status.json"
    manifest.write_text(
        json.dumps(
            {
                "tenant_slug": "algolia",
                "generated_at": "2026-07-12T14:44:19Z",
                "status": "blocked_on_evidence",
                "next_hermes_action": "configure_ga4_or_upload_demand_export",
                "planes": {},
                "blockers": [],
                "artifact_refs": {"dashboard": "/root/.hermes/apps/cios/out/argus-dashboard.json"},
            }
        ),
        encoding="utf-8",
    )
    dashboard.write_text(
        json.dumps({"generated_at": "2026-07-12T14:44:17Z", "product_market_run": {"status": "ran"}}),
        encoding="utf-8",
    )

    code = module.main(
        [
            "--tenant",
            "algolia",
            "--manifest",
            str(manifest),
            "--dashboard",
            str(dashboard),
            "--publish-status",
            "blocked",
            "--output",
            str(output),
        ]
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert code == 0
    assert payload["publish_status"] == "blocked"
    assert payload["public_dashboard_updated"] is False
    assert "/root/" not in output.read_text(encoding="utf-8")


def test_public_run_status_counts_list_shaped_source_health() -> None:
    module = _load_module()

    payload = module.build_public_run_status_payload(
        tenant_slug="algolia",
        manifest={"status": "blocked_on_evidence", "planes": {}, "blockers": []},
        dashboard={
            "source_health": [
                {
                    "source_id": 1,
                    "status": "active",
                    "checked_at": "2026-07-12T16:01:47Z",
                    "latest_event_type": "ok",
                },
                {
                    "source_id": 2,
                    "status": "active",
                    "checked_at": "2026-07-12T16:01:48Z",
                    "latest_event_type": "fetch_error",
                },
                {
                    "source_id": 3,
                    "status": "paused",
                    "checked_at": None,
                    "latest_event_type": "skipped",
                },
            ],
        },
        publish_status="blocked",
        generated_at="2026-07-12T16:14:00Z",
    )

    assert payload["source_coverage"] == {
        "active_source_count": 2,
        "checked_source_count": 2,
        "failed_source_count": 1,
    }


def test_public_run_status_prefers_current_run_coverage_and_extraction_accounting() -> None:
    module = _load_module()
    run_id = "cios-20260714T090000Z-1234"

    payload = module.build_public_run_status_payload(
        tenant_slug="algolia",
        manifest={
            "run_id": run_id,
            "status": "published",
            "planes": {},
            "blockers": [],
        },
        dashboard={
            "run_health": {
                "run_id": run_id,
                "source_coverage": {
                    "run_id": run_id,
                    "active_source_count": 4,
                    "checked_source_count": 3,
                    "failed_source_count": 1,
                    "disposed_source_count": 1,
                    "dispositions": [
                        {
                            "source_ref": "3995b87e38e234fe",
                            "competitor_name": "Klevu",
                            "reason": "source_id_missing",
                            "internal_path": "/root/private",
                        }
                    ],
                },
            },
            "product_market_run": {
                "run_id": run_id,
                "status": "ran",
                "product_event_count": 120,
                "product_surface_execution_summary": {
                    "planned": 3,
                    "succeeded": 1,
                    "empty": 1,
                    "failed": 0,
                    "timed_out": 1,
                    "not_started": 0,
                },
            },
        },
        publish_status="published",
        run_id=run_id,
        generated_at="2026-07-14T09:05:00Z",
    )

    assert payload["source_coverage"] == {
        "run_id": run_id,
        "active_source_count": 4,
        "checked_source_count": 3,
        "failed_source_count": 1,
        "disposed_source_count": 1,
        "dispositions": [
            {
                "source_ref": "3995b87e38e234fe",
                "competitor_name": "Klevu",
                "reason": "source_id_missing",
            }
        ],
    }
    assert payload["product_market_run"]["run_id"] == run_id
    assert payload["product_extraction"] == {
        "run_id": run_id,
        "planned": 3,
        "attempted": 3,
        "terminal": 3,
        "successful": 1,
        "failed": 2,
        "timed_out": 1,
        "not_started": 0,
        "accounting_complete": True,
        "all_planned_terminal": True,
    }


def test_public_run_status_exposes_sanitized_demand_collection_plan() -> None:
    module = _load_module()

    payload = module.build_public_run_status_payload(
        tenant_slug="algolia",
        manifest={
            "status": "blocked_on_evidence",
            "planes": {
                "audience_demand": {
                    "status": "blocked_missing_demand_source",
                    "summary": "No tenant-side demand source is ready.",
                    "blocks_action": True,
                    "counts": {"demand_signal_count": 0},
                    "details": {
                        "demand_plan_template": {
                            "status": "generated",
                            "format": "csv",
                            "filename": "argus-demand-plan-template.csv",
                            "artifact_ref": "/root/.hermes/apps/cios/out/argus-demand-plan-template.csv",
                        },
                        "demand_collection_plan": {
                            "status": "needs_demand_source",
                            "topic_count": 2,
                            "source_dashboard_field": "product_market_run.product_feature_comparison_read.rows",
                            "drop_folder": "/root/.hermes/apps/cios/data/looker/algolia",
                            "topics": [
                                {
                                    "topic": "AI Assistant",
                                    "capability_key": "ai assistant",
                                    "assessment": "competitive_pressure",
                                    "related_competitors": ["Constructor"],
                                    "suggested_filter_terms": ["AI Assistant", "assistant"],
                                    "evidence_urls": [
                                        "https://constructor.com/changelog/ai-assistant",
                                        "https://elastic.co/blog/ai-assistant",
                                    ],
                                    "why_collect": "Internal action rationale should not be public.",
                                }
                            ],
                        }
                    },
                }
            },
            "blockers": [
                {
                    "plane": "audience_demand",
                    "severity": "blocks_action",
                    "title": "Demand plane missing",
                    "next_step": "Configure GA4 or upload demand.",
                    "planned_topic_count": 2,
                    "planned_topics": [
                        {
                            "topic": "AI Assistant",
                            "capability_key": "ai assistant",
                            "assessment": "competitive_pressure",
                            "related_competitors": ["Constructor"],
                            "evidence_url_count": 2,
                            "why_collect": "Internal action rationale should not be public.",
                        }
                    ],
                }
            ],
        },
        dashboard={},
        publish_status="blocked",
        generated_at="2026-07-12T16:45:00Z",
    )

    demand = payload["planes"]["audience_demand"]
    assert demand["demand_plan_template"] == {
        "status": "generated",
        "format": "csv",
        "filename": "argus-demand-plan-template.csv",
    }
    assert demand["demand_collection_plan"] == {
        "status": "needs_demand_source",
        "topic_count": 2,
        "source_dashboard_field": "product_market_run.product_feature_comparison_read.rows",
        "topics": [
            {
                "topic": "AI Assistant",
                "capability_key": "ai assistant",
                "assessment": "competitive_pressure",
                "related_competitors": ["Constructor"],
                "suggested_filter_terms": ["AI Assistant", "assistant"],
                "evidence_url_count": 2,
            }
        ],
    }
    assert payload["demand_plan_template"] == {
        "status": "generated",
        "format": "csv",
        "filename": "argus-demand-plan-template.csv",
    }
    assert payload["demand_collection_plan"] == demand["demand_collection_plan"]
    assert payload["blockers"][0]["planned_topic_count"] == 2
    assert payload["blockers"][0]["planned_topics"] == [
        {
            "topic": "AI Assistant",
            "capability_key": "ai assistant",
            "assessment": "competitive_pressure",
            "related_competitors": ["Constructor"],
            "evidence_url_count": 2,
        }
    ]
    serialized = json.dumps(payload, sort_keys=True)
    assert "/root/" not in serialized
    assert "why_collect" not in serialized
    assert "Internal action rationale" not in serialized


def test_public_run_status_exposes_sanitized_product_surface_execution_summary() -> None:
    module = _load_module()

    payload = module.build_public_run_status_payload(
        tenant_slug="algolia",
        manifest={
            "status": "blocked_on_evidence",
            "planes": {
                "product_reality": {
                    "status": "empty_product_surface_outputs",
                    "summary": "Product surfaces ran, but produced no product proof.",
                    "blocks_action": True,
                    "counts": {
                        "product_surface_planned_count": 2,
                        "product_surface_empty_count": 2,
                        "product_surface_extracted_row_count": 0,
                    },
                    "details": {
                        "product_surface_execution": {
                            "product_plane_status": "empty",
                            "planned": 2,
                            "succeeded": 0,
                            "empty": 2,
                            "failed": 0,
                            "timed_out": 1,
                            "not_started": 1,
                            "batch_timed_out": True,
                            "batch_timeout_seconds": 600,
                            "product_row_count": 0,
                            "empty_scout_paths": [
                                "/tmp/cios-product-market/algolia/surface-exports/000031-coveo-docs.json"
                            ],
                            "empty_outputs": [
                                {
                                    "output_path": "/tmp/cios-product-market/algolia/surface-exports/000031-coveo-docs.json",
                                    "company_name": "Coveo",
                                    "surface_family": "docs",
                                }
                            ],
                            "company_row_counts": {},
                            "surface_family_row_counts": {},
                        }
                    },
                }
            },
            "blockers": [
                {
                    "plane": "product_reality",
                    "severity": "blocks_feature_matrix",
                    "title": "Product surface extraction returned no product proof",
                    "next_step": "Repair or replace empty product-surface targets: Coveo docs.",
                    "work_item_id": "product-surface-execution:empty",
                    "empty_outputs": [
                        {
                            "output_path": "/tmp/cios-product-market/algolia/surface-exports/000031-coveo-docs.json",
                            "company_name": "Coveo",
                            "surface_family": "docs",
                        }
                    ],
                }
            ],
        },
        dashboard={},
        publish_status="blocked",
        generated_at="2026-07-12T18:35:00Z",
    )

    assert payload["planes"]["product_reality"]["product_surface_execution"] == {
        "product_plane_status": "empty",
        "planned": 2,
        "succeeded": 0,
        "empty": 2,
        "failed": 0,
        "timed_out": 1,
        "not_started": 1,
        "batch_timed_out": True,
        "batch_timeout_seconds": 600,
        "product_row_count": 0,
        "empty_outputs": [{"company_name": "Coveo", "surface_family": "docs"}],
        "company_row_counts": {},
        "surface_family_row_counts": {},
    }
    assert payload["blockers"] == [
        {
            "plane": "product_reality",
            "severity": "blocks_feature_matrix",
            "title": "Product surface extraction returned no product proof",
            "next_step": "Repair or replace empty product-surface targets: Coveo docs.",
            "work_item_id": "product-surface-execution:empty",
            "empty_outputs": [{"company_name": "Coveo", "surface_family": "docs"}],
        }
    ]
    serialized = json.dumps(payload, sort_keys=True)
    assert "/tmp/" not in serialized
    assert "output_path" not in serialized


def test_public_run_status_exposes_sanitized_product_muscle_work_order() -> None:
    module = _load_module()

    payload = module.build_public_run_status_payload(
        tenant_slug="algolia",
        manifest={
            "schema_version": 1,
            "tenant_slug": "algolia",
            "generated_at": "2026-07-12T20:31:00Z",
            "dashboard_generated_at": "2026-07-12T20:30:00Z",
            "status": "degraded",
            "next_hermes_action": "configure_ga4_or_upload_demand_export",
            "planes": {
                "product_reality": {
                    "status": "limited_by_product_surface_evidence",
                    "summary": "Product reality evidence is present but still limiting feature-matrix confidence.",
                    "blocks_action": False,
                    "next_hermes_action": (
                        "Run Scout product-surface extraction for the active surfaces, then refresh Argus "
                        "from the evidence ledger."
                    ),
                    "counts": {
                        "product_event_count": 500,
                        "product_muscle_work_item_count": 1,
                        "product_muscle_limiting_count": 1,
                    },
                    "details": {
                        "product_muscle_work_queue": {
                            "status": "limited",
                            "work_item_count": 1,
                            "blocking_count": 0,
                            "limiting_count": 1,
                            "artifact_ref": "/root/.hermes/apps/cios/out/argus-product-muscle-work-queue.json",
                            "items": [
                                {
                                    "work_item_id": "product-muscle:competitor:9:no-feature-evidence",
                                    "severity": "limits_confidence",
                                    "title": "Klevu has product surfaces but no feature evidence",
                                    "next_step": (
                                        "Run Scout product-surface extraction for the active surfaces, then "
                                        "refresh Argus from the evidence ledger."
                                    ),
                                    "company_name": "Klevu",
                                    "operator_surface": "Product surfaces",
                                    "operator_commands": [
                                        {
                                            "label": "Open product surfaces",
                                            "method": "get",
                                            "surface": "Product surfaces",
                                            "route_kind": "admin",
                                            "href": "/admin?tenant=algolia#add-product-surface",
                                        }
                                    ],
                                    "debug_path": "/tmp/cios-product-market/algolia/surface.json",
                                }
                            ],
                        }
                    },
                }
            },
            "blockers": [],
        },
        dashboard={
            "generated_at": "2026-07-12T20:30:00Z",
            "source_health": {
                "active_source_count": 48,
                "checked_source_count": 48,
                "failed_source_count": 5,
            },
            "product_market_run": {
                "status": "ran",
                "product_event_count": 500,
                "conversation_theme_count": 3,
                "demand_signal_count": 0,
                "pattern_count": 4,
                "recommendation_count": 0,
            },
        },
        publish_status="blocked",
        generated_at="2026-07-12T20:31:10Z",
    )

    assert payload["planes"]["product_reality"]["product_muscle_work_queue"] == {
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
    serialized = json.dumps(payload, sort_keys=True)
    assert "/root/" not in serialized
    assert "/tmp/" not in serialized
    assert "href" not in serialized
    assert "debug_path" not in serialized


def test_public_run_status_exposes_sanitized_next_monitoring_actions() -> None:
    module = _load_module()

    payload = module.build_public_run_status_payload(
        tenant_slug="algolia",
        manifest={
            "status": "blocked_on_evidence",
            "next_monitoring_actions": [
                {
                    "owner": "Hermes",
                    "plane": "audience_demand",
                    "priority": "critical",
                    "instruction": "Collect GA / Looker demand evidence for Support before promoting this market movement.",
                    "reason": "Argus found a product-market pattern, but recommendations require tenant-side demand evidence.",
                    "source_families": ["ga4_api_export", "ga_looker_manual_export"],
                    "evidence_urls": [
                        "https://constructor.com/solutions/ai-shopping-agent",
                        "https://www.luigisbox.com/pricing/",
                    ],
                    "internal_artifact_path": "/root/.hermes/apps/cios/out/private.json",
                },
                {
                    "owner": "",
                    "plane": "product_reality",
                    "priority": "medium",
                    "instruction": "This malformed row should not be public.",
                    "reason": "Missing owner.",
                },
            ],
            "planes": {},
            "blockers": [],
        },
        dashboard={},
        publish_status="blocked",
        generated_at="2026-07-12T20:30:00Z",
    )

    assert payload["next_monitoring_actions"] == [
        {
            "owner": "Hermes",
            "plane": "audience_demand",
            "priority": "critical",
            "instruction": "Collect GA / Looker demand evidence for Support before promoting this market movement.",
            "reason": "Argus found a product-market pattern, but recommendations require tenant-side demand evidence.",
            "source_families": ["ga4_api_export", "ga_looker_manual_export"],
            "evidence_url_count": 2,
        }
    ]
    serialized = json.dumps(payload, sort_keys=True)
    assert "/root/" not in serialized
    assert "internal_artifact_path" not in serialized
    assert "constructor.com" not in serialized
