"""Smoke contract for the Hermes-facing Argus operator handoff artifact."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "build_argus_operator_handoff.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("build_argus_operator_handoff", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _work_queue_payload() -> dict:
    return {
        "tenant_slug": "algolia",
        "tenant_id": 1,
        "generated_at": "2026-07-11T20:00:00Z",
        "work_item_count": 1,
        "blocking_count": 1,
        "limiting_count": 0,
        "items": [
            {
                "work_item_id": "argus-evidence:17:demand",
                "evidence_plane": "demand",
                "severity": "blocks_action",
                "title": "Demand plane missing",
                "why_needed": "Demand evidence is missing, so Argus withheld owner recommendations.",
                "blocks": ["owner recommendations", "priority ranking", "action promotion"],
                "next_step": "Upload GA4 / Looker demand export for the current and previous periods.",
                "operator_surface": "Demand imports",
                "primary_action_label": "Download demand template",
                "primary_action_href": "/api/tenants/algolia/argus/demand-imports/template",
                "primary_action_method": "get",
                "secondary_action_label": "Prepare demand and refresh Argus",
                "secondary_action_href": "/admin/algolia/argus/demand-imports/refresh",
                "secondary_action_method": "post",
                "accepted_input_formats": ["csv", "json"],
                "required_fields": ["date", "url", "sessions"],
                "observed_state": {"demand_plane_status": "missing"},
                "related_run_intelligence_id": 17,
                "observed_pattern_count": 1,
            }
        ],
    }


def _product_muscle_queue_payload() -> dict:
    return {
        "tenant_slug": "algolia",
        "tenant_id": 1,
        "generated_at": "2026-07-12T05:20:00Z",
        "work_item_count": 1,
        "blocking_count": 1,
        "limiting_count": 0,
        "items": [
            {
                "work_item_id": "product-muscle:competitor:2:missing-surfaces",
                "company_id": 2,
                "company_name": "Bloomreach",
                "company_role": "competitor",
                "severity": "blocks_feature_matrix",
                "title": "Bloomreach has no active product surfaces",
                "why_needed": "Argus cannot compare Bloomreach's shipped product reality.",
                "blocks": ["feature comparison", "product gap scoring", "product-backed recommendations"],
                "next_step": "Add a changelog, docs, release notes, API docs, pricing, integration, or product page source.",
                "operator_surface": "Product surfaces",
                "primary_action_label": "Add product surface",
                "primary_action_href": "/admin?tenant=algolia#add-product-surface",
                "primary_action_method": "get",
                "secondary_action_label": "Refresh Argus from evidence ledger",
                "secondary_action_href": "/admin/algolia/argus/ledger-refresh",
                "secondary_action_method": "post",
                "observed_state": {
                    "active_product_surface_count": 0,
                    "known_capability_cell_count": 0,
                },
            }
        ],
    }


def _demand_readiness_payload() -> dict:
    return {
        "tenant_slug": "algolia",
        "status": "blocked_missing_demand_source",
        "next_hermes_action": "configure_ga4_or_upload_demand_export",
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
    }


def test_build_argus_operator_handoff_script_exists_and_imports() -> None:
    module = _load_module()

    assert hasattr(module, "main")
    assert hasattr(module, "build_operator_handoff_payload")
    assert hasattr(module, "write_payload")


def test_build_operator_handoff_payload_turns_blocking_queue_into_argus_next_action() -> None:
    module = _load_module()

    payload = module.build_operator_handoff_payload(
        tenant_slug="algolia",
        work_queue=_work_queue_payload(),
        dashboard={
            "generated_at": "2026-07-11T20:01:00Z",
            "spine": {"primary_action": "Do not promote recommendations until demand is imported."},
        },
        work_queue_path="/tmp/cios/algolia/argus-evidence-work-queue.json",
        dashboard_path="/tmp/cios/algolia/argus-dashboard.json",
        generated_at="2026-07-11T20:02:00Z",
    )

    assert payload["tenant_slug"] == "algolia"
    assert payload["generated_at"] == "2026-07-11T20:02:00Z"
    assert payload["status"] == "blocked_on_evidence"
    assert payload["argus_readiness"] == "not_actionable"
    assert payload["summary"] == "Argus is blocked by 1 evidence gap before it can promote this run to action."
    assert payload["next_operator_action"] == "Upload GA4 / Looker demand export for the current and previous periods."
    assert payload["top_blocker"]["work_item_id"] == "argus-evidence:17:demand"
    assert payload["top_blocker"]["evidence_plane"] == "demand"
    assert payload["primary_command"]["label"] == "Download demand template"
    assert payload["primary_command"]["href"] == "/api/tenants/algolia/argus/demand-imports/template"
    assert payload["secondary_command"]["label"] == "Prepare demand and refresh Argus"
    assert payload["artifact_refs"]["work_queue"] == "/tmp/cios/algolia/argus-evidence-work-queue.json"
    assert payload["artifact_refs"]["dashboard"] == "/tmp/cios/algolia/argus-dashboard.json"
    assert payload["operator_brief"][0].startswith("Argus withheld action")
    assert payload["work_queue"]["blocking_count"] == 1


def test_build_operator_handoff_payload_includes_product_muscle_queue_as_blocking_work() -> None:
    module = _load_module()

    payload = module.build_operator_handoff_payload(
        tenant_slug="algolia",
        work_queue={
            "tenant_slug": "algolia",
            "tenant_id": 1,
            "generated_at": "2026-07-11T20:00:00Z",
            "work_item_count": 0,
            "blocking_count": 0,
            "limiting_count": 0,
            "items": [],
        },
        product_muscle_queue=_product_muscle_queue_payload(),
        dashboard={},
        work_queue_path="/tmp/cios/algolia/argus-evidence-work-queue.json",
        product_muscle_queue_path="/tmp/cios/algolia/argus-product-muscle-work-queue.json",
        generated_at="2026-07-12T05:25:00Z",
    )

    assert payload["status"] == "blocked_on_evidence"
    assert payload["argus_readiness"] == "not_actionable"
    assert payload["summary"] == "Argus is blocked by 1 evidence gap before it can promote this run to action."
    assert payload["next_operator_action"].startswith("Add a changelog")
    assert payload["top_blocker"]["work_item_id"] == "product-muscle:competitor:2:missing-surfaces"
    assert payload["top_blocker"]["evidence_plane"] == "product_muscle"
    assert payload["top_blocker"]["company_name"] == "Bloomreach"
    assert payload["primary_command"]["label"] == "Add product surface"
    assert payload["artifact_refs"]["product_muscle_work_queue"] == (
        "/tmp/cios/algolia/argus-product-muscle-work-queue.json"
    )
    assert payload["work_queue"]["product_muscle_blocking_count"] == 1
    assert payload["work_queue"]["item_ids"] == ["product-muscle:competitor:2:missing-surfaces"]


def test_build_operator_handoff_includes_sanitized_demand_operator_commands() -> None:
    module = _load_module()

    payload = module.build_operator_handoff_payload(
        tenant_slug="algolia",
        work_queue=_work_queue_payload(),
        demand_readiness=_demand_readiness_payload(),
        generated_at="2026-07-12T10:40:00Z",
    )

    assert payload["operator_commands"] == [
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
    assert "href" not in json.dumps(payload["operator_commands"])


def test_build_operator_handoff_uses_plan_aware_demand_action_as_primary_command() -> None:
    module = _load_module()
    demand_readiness = _demand_readiness_payload()
    demand_readiness["operator_actions"].insert(
        0,
        {
            "href": "/api/tenants/algolia/argus/demand-imports/template?planned=1",
            "label": "Download demand plan template",
            "method": "get",
            "surface": "Demand imports",
        },
    )

    payload = module.build_operator_handoff_payload(
        tenant_slug="algolia",
        work_queue=_work_queue_payload(),
        demand_readiness=demand_readiness,
        generated_at="2026-07-12T10:45:00Z",
    )

    assert payload["top_blocker"]["evidence_plane"] == "demand"
    assert payload["primary_command"] == {
        "label": "Download demand plan template",
        "href": "/api/tenants/algolia/argus/demand-imports/template?planned=1",
        "method": "get",
        "surface": "Demand imports",
    }
    assert payload["secondary_command"]["label"] == "Prepare demand and refresh Argus"
    assert payload["operator_commands"][0] == {
        "label": "Download demand plan template",
        "method": "get",
        "surface": "Demand imports",
        "route_kind": "api",
    }


def test_build_operator_handoff_includes_demand_collection_plan() -> None:
    module = _load_module()
    demand_readiness = _demand_readiness_payload()
    demand_readiness["demand_collection_plan"] = {
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
    }

    payload = module.build_operator_handoff_payload(
        tenant_slug="algolia",
        work_queue=_work_queue_payload(),
        demand_readiness=demand_readiness,
        generated_at="2026-07-12T10:50:00Z",
    )

    assert payload["demand_collection_plan"]["status"] == "needs_demand_source"
    assert payload["demand_collection_plan"]["topic_count"] == 1
    assert payload["demand_collection_plan"]["topics"][0]["capability_key"] == "ai assistant"
    assert "href" not in json.dumps(payload["demand_collection_plan"])


def test_build_operator_handoff_includes_public_safe_demand_plan_template_summary() -> None:
    module = _load_module()

    payload = module.build_operator_handoff_payload(
        tenant_slug="algolia",
        work_queue=_work_queue_payload(),
        demand_readiness=_demand_readiness_payload(),
        demand_plan_template_path="/tmp/cios/algolia/out/argus-demand-plan-template.csv",
        generated_at="2026-07-12T17:35:00Z",
    )

    assert payload["demand_plan_template"] == {
        "status": "generated",
        "format": "csv",
        "filename": "argus-demand-plan-template.csv",
    }
    assert "/tmp/" not in json.dumps(payload["demand_plan_template"])
    assert payload["artifact_refs"]["demand_plan_template"] == (
        "/tmp/cios/algolia/out/argus-demand-plan-template.csv"
    )


def test_build_operator_handoff_promotes_blocking_demand_readiness_over_limiting_conversation_queue() -> None:
    module = _load_module()
    demand_readiness = _demand_readiness_payload()
    demand_readiness["summary"] = "No tenant-side demand export is ready for this Argus run."
    demand_readiness["demand_collection_plan"] = {
        "status": "needs_demand_source",
        "topic_count": 12,
    }

    payload = module.build_operator_handoff_payload(
        tenant_slug="algolia",
        work_queue={
            "tenant_slug": "algolia",
            "tenant_id": 1,
            "generated_at": "2026-07-12T22:20:00Z",
            "work_item_count": 1,
            "blocking_count": 0,
            "limiting_count": 1,
            "items": [
                {
                    "work_item_id": "argus-evidence:conversation:coverage",
                    "evidence_plane": "conversation",
                    "severity": "limits_confidence",
                    "title": "Conversation coverage is thin",
                    "why_needed": "Some public conversation sources still need repair.",
                    "blocks": ["confidence"],
                    "next_step": "Add or repair outward conversation sources.",
                    "operator_surface": "Sources",
                }
            ],
        },
        demand_readiness=demand_readiness,
        demand_plan_template_path="/tmp/cios/algolia/out/argus-demand-plan-template.csv",
        generated_at="2026-07-12T22:21:00Z",
    )

    assert payload["status"] == "blocked_on_evidence"
    assert payload["argus_readiness"] == "not_actionable"
    assert payload["top_blocker"]["evidence_plane"] == "demand"
    assert payload["top_blocker"]["severity"] == "blocks_action"
    assert payload["top_blocker"]["title"] == "Demand plane missing"
    assert payload["next_operator_action"] == "Configure GA4 or upload a GA / Looker export."
    assert payload["primary_command"]["label"] == "Download demand template"
    assert payload["work_queue"]["demand_blocking_count"] == 1
    assert payload["work_queue"]["evidence_blocking_count"] == 0
    assert payload["work_queue"]["blocking_count"] == 1
    assert payload["work_queue"]["limiting_count"] == 1
    assert payload["work_queue"]["item_ids"][0].startswith("argus-demand-readiness:")


def test_build_operator_handoff_names_missing_demand_trend_window() -> None:
    module = _load_module()
    demand_readiness = _demand_readiness_payload()
    demand_readiness["status"] = "processed_no_comparison_period"
    demand_readiness["summary"] = (
        "Tenant demand evidence exists, but the imported export only has current-period values. "
        "Argus needs a previous-period or change_pct column before it can score movement."
    )
    demand_readiness["next_hermes_action"] = "upload_trended_planned_demand_export"

    payload = module.build_operator_handoff_payload(
        tenant_slug="algolia",
        work_queue={
            "tenant_slug": "algolia",
            "tenant_id": 1,
            "generated_at": "2026-07-12T22:20:00Z",
            "work_item_count": 0,
            "blocking_count": 0,
            "limiting_count": 0,
            "items": [],
        },
        demand_readiness=demand_readiness,
        generated_at="2026-07-12T22:22:00Z",
    )

    assert payload["status"] == "blocked_on_evidence"
    assert payload["top_blocker"]["title"] == "Demand trend window missing"
    assert payload["next_operator_action"] == (
        "Upload a planned demand export with previous-period or change_pct values, then refresh Argus."
    )


def test_build_argus_operator_handoff_cli_accepts_demand_plan_template(tmp_path) -> None:
    module = _load_module()
    work_queue = tmp_path / "argus-evidence-work-queue.json"
    demand_readiness = tmp_path / "argus-demand-readiness.json"
    demand_plan_template = tmp_path / "argus-demand-plan-template.csv"
    output = tmp_path / "argus-operator-handoff.json"
    work_queue.write_text(json.dumps(_work_queue_payload()), encoding="utf-8")
    demand_readiness.write_text(json.dumps(_demand_readiness_payload()), encoding="utf-8")
    demand_plan_template.write_text("Page title,Page path\n", encoding="utf-8")

    code = module.main(
        [
            "--tenant",
            "algolia",
            "--work-queue",
            str(work_queue),
            "--demand-readiness",
            str(demand_readiness),
            "--demand-plan-template",
            str(demand_plan_template),
            "--output",
            str(output),
        ]
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert code == 0
    assert payload["demand_plan_template"]["filename"] == "argus-demand-plan-template.csv"
    assert payload["artifact_refs"]["demand_plan_template"] == str(demand_plan_template)


def test_build_operator_handoff_payload_marks_run_ready_when_queue_is_empty() -> None:
    module = _load_module()

    payload = module.build_operator_handoff_payload(
        tenant_slug="algolia",
        work_queue={
            "tenant_slug": "algolia",
            "tenant_id": 1,
            "generated_at": "2026-07-11T20:00:00Z",
            "work_item_count": 0,
            "blocking_count": 0,
            "limiting_count": 0,
            "items": [],
        },
        dashboard={},
        generated_at="2026-07-11T20:02:00Z",
    )

    assert payload["status"] == "ready_for_operator_review"
    assert payload["argus_readiness"] == "actionable"
    assert payload["next_operator_action"] == "Review Argus recommendations and challenge any weak claim."
    assert payload["top_blocker"] is None
    assert payload["primary_command"]["label"] == "Open Argus command"


def test_build_operator_handoff_blocks_empty_product_surface_execution_from_dashboard() -> None:
    module = _load_module()

    payload = module.build_operator_handoff_payload(
        tenant_slug="algolia",
        work_queue={
            "tenant_slug": "algolia",
            "tenant_id": 1,
            "generated_at": "2026-07-12T18:50:00Z",
            "work_item_count": 0,
            "blocking_count": 0,
            "limiting_count": 0,
            "items": [],
        },
        product_muscle_queue={
            "tenant_slug": "algolia",
            "tenant_id": 1,
            "generated_at": "2026-07-12T18:50:00Z",
            "work_item_count": 0,
            "blocking_count": 0,
            "limiting_count": 0,
            "items": [],
        },
        dashboard={
            "generated_at": "2026-07-12T18:51:00Z",
            "product_market_run": {
                "product_surface_execution_summary": {
                    "product_plane_status": "empty",
                    "planned": 2,
                    "succeeded": 0,
                    "empty": 2,
                    "failed": 0,
                    "product_row_count": 0,
                    "empty_scout_paths": ["/tmp/cios/surface-exports/000031-coveo-docs.json"],
                    "empty_outputs": [
                        {
                            "output_path": "/tmp/cios/surface-exports/000031-coveo-docs.json",
                            "company_name": "Coveo",
                            "surface_family": "docs",
                        },
                        {
                            "output_path": "/tmp/cios/surface-exports/000032-elastic-changelog.json",
                            "company_name": "Elastic",
                            "surface_family": "changelog",
                        },
                    ],
                    "company_row_counts": {},
                    "surface_family_row_counts": {},
                }
            },
        },
        generated_at="2026-07-12T18:52:00Z",
    )

    assert payload["status"] == "blocked_on_evidence"
    assert payload["argus_readiness"] == "not_actionable"
    assert payload["next_operator_action"] == (
        "Repair or replace empty product-surface targets: Coveo docs, Elastic changelog."
    )
    assert payload["top_blocker"] == {
        "work_item_id": "product-surface-execution:empty",
        "evidence_plane": "product_muscle",
        "severity": "blocks_feature_matrix",
        "title": "Product surface extraction returned no product proof",
        "why_needed": "Scout/product-surface execution ran, but did not extract product proof for the feature matrix.",
        "blocks": ["feature comparison", "product gap scoring", "product-backed recommendations"],
        "observed_state": {
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
        },
        "company_name": None,
    }
    assert payload["primary_command"] == {
        "label": "Open product surface repair",
        "href": "/admin?tenant=algolia#product-surface-repair",
        "method": "get",
        "surface": "Product surface repair",
    }
    assert payload["work_queue"]["product_surface_execution_blocking_count"] == 1
    assert payload["work_queue"]["blocking_count"] == 1
    assert payload["work_queue"]["item_ids"] == ["product-surface-execution:empty"]
    assert "/tmp/" not in json.dumps(payload["top_blocker"])
    assert "output_path" not in json.dumps(payload["top_blocker"])


def test_build_operator_handoff_rejects_mismatched_tenant_slug() -> None:
    module = _load_module()
    work_queue = _work_queue_payload()
    work_queue["tenant_slug"] = "constructor"

    try:
        module.build_operator_handoff_payload(
            tenant_slug="algolia",
            work_queue=work_queue,
            dashboard={},
        )
    except ValueError as exc:
        assert "work queue tenant constructor does not match algolia" in str(exc)
    else:
        raise AssertionError("expected mismatched tenant to fail")


def test_build_argus_operator_handoff_writes_output_file(tmp_path) -> None:
    module = _load_module()
    payload = {"tenant_slug": "algolia", "status": "ready_for_operator_review"}
    output = tmp_path / "work" / "argus-operator-handoff.json"

    module.write_payload(payload, output)

    assert json.loads(output.read_text(encoding="utf-8")) == payload
