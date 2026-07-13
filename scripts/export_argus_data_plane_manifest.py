#!/usr/bin/env python3
"""Export the Hermes-facing Argus data-plane manifest.

This sidecar answers the operating question behind the dashboard: what data
planes fed Argus, what stores back them, what is missing, and what blocks
action. It is intentionally derived from the current dashboard state plus
Hermes sidecars; it does not make new intelligence claims.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


PRODUCT_STORAGE = [
    "product_surfaces",
    "feature_capabilities",
    "product_change_events",
    "company_feature_positions",
    "feature_evidence_links",
]

CONVERSATION_STORAGE = [
    "semantic_facts",
    "semantic_deltas",
    "claims",
    "claim_observations",
    "conversation_themes",
]

DEMAND_STORAGE = ["demand_signals"]

REGISTRY_STORAGE = [
    "tenants",
    "competitors",
    "sources",
    "product_surfaces",
    "source_health_events",
    "source_scan_runs",
    "source_observations",
    "competitor_scan_rollups",
]

LEARNING_STORAGE = [
    "learning_events",
    "improvement_queue",
    "quality_reviews",
    "false_negative_audits",
]

RUN_TRUTH_STORAGE = ["run_stage_ledgers", "run_stage_events", "product_market_run_intelligence"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists() or path.stat().st_size == 0:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _route_kind_from_href(href: Any) -> str:
    value = _clean_text(href)
    if value.startswith("/api/"):
        return "api"
    if value.startswith("/admin"):
        return "admin"
    return "unknown"


def _product_muscle_operator_commands(item: Mapping[str, Any]) -> list[dict[str, str]]:
    commands: list[dict[str, str]] = []
    surface = _clean_text(item.get("operator_surface")) or "Product muscle"
    for prefix in ("primary", "secondary"):
        label = _clean_text(item.get(f"{prefix}_action_label"))
        if not label:
            continue
        commands.append(
            {
                "label": label,
                "method": (_clean_text(item.get(f"{prefix}_action_method")) or "get").lower(),
                "surface": surface,
                "route_kind": _route_kind_from_href(item.get(f"{prefix}_action_href")),
            }
        )
    return commands


def _product_muscle_work_order(product_muscle_work_queue: Mapping[str, Any]) -> dict[str, Any]:
    work_item_count = _int_value(product_muscle_work_queue.get("work_item_count"))
    blocking_count = _int_value(product_muscle_work_queue.get("blocking_count"))
    limiting_count = _int_value(product_muscle_work_queue.get("limiting_count"))
    items = _list_value(product_muscle_work_queue.get("items"))
    if work_item_count <= 0 and not items:
        return {}
    status = "blocked" if blocking_count > 0 else "limited" if limiting_count > 0 else "attention_needed"
    public_items: list[dict[str, Any]] = []
    for item in items[:10]:
        if not isinstance(item, Mapping):
            continue
        row = {
            "work_item_id": _clean_text(item.get("work_item_id")),
            "severity": _clean_text(item.get("severity")),
            "title": _clean_text(item.get("title")),
            "next_step": _clean_text(item.get("next_step")),
            "company_name": _clean_text(item.get("company_name")),
            "surface_family": _clean_text(item.get("surface_family")),
            "operator_surface": _clean_text(item.get("operator_surface")),
        }
        commands = _product_muscle_operator_commands(item)
        sanitized = {key: value for key, value in row.items() if value not in (None, "", [])}
        if commands:
            sanitized["operator_commands"] = commands
        if sanitized:
            public_items.append(sanitized)
    return {
        "status": status,
        "work_item_count": work_item_count or len(public_items),
        "blocking_count": blocking_count,
        "limiting_count": limiting_count,
        "items": public_items,
    }


def _demand_plan_template_summary(artifact_refs: Mapping[str, str | None]) -> dict[str, Any]:
    artifact_ref = artifact_refs.get("demand_plan_template")
    if not artifact_ref:
        return {}
    filename = Path(str(artifact_ref)).name
    return {
        "status": "generated",
        "format": "csv",
        "filename": filename,
        "artifact_ref": str(artifact_ref),
    }


def _dashboard_run(dashboard: Mapping[str, Any]) -> dict[str, Any]:
    return _dict_value(dashboard.get("product_market_run"))


def _argus_decision(run: Mapping[str, Any]) -> dict[str, Any]:
    decision = _dict_value(run.get("decision_read"))
    if not decision:
        brief = _dict_value(run.get("intelligence_brief"))
        decision = _dict_value(brief.get("decision_read"))
    if not decision:
        return {}

    basis_rows: list[dict[str, Any]] = []
    for row in _list_value(decision.get("confidence_basis"))[:5]:
        if not isinstance(row, Mapping):
            continue
        plane = str(row.get("plane") or "").strip()
        status = str(row.get("status") or "").strip()
        if not plane or not status:
            continue
        basis_rows.append(
            {
                "plane": plane,
                "status": status,
                "evidence_count": _int_value(row.get("evidence_count")),
            }
        )

    return {
        "status": str(decision.get("status") or "unknown"),
        "market_direction": str(decision.get("market_direction") or ""),
        "priority_reason": str(decision.get("priority_reason") or ""),
        "tactical_action_count": len(_list_value(decision.get("tactical_actions"))),
        "blocker_count": len(_list_value(decision.get("blockers"))),
        "evidence_url_count": len(_list_value(decision.get("evidence_urls"))),
        "confidence_basis": basis_rows,
    }


def _next_monitoring_actions(run: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Expose the run-native Argus monitoring agenda for Hermes inspection."""

    brief = _dict_value(run.get("intelligence_brief"))
    raw_actions = _list_value(run.get("next_monitoring_actions")) or _list_value(
        brief.get("next_monitoring_actions")
    )
    actions: list[dict[str, Any]] = []
    for item in raw_actions:
        if not isinstance(item, Mapping):
            continue
        row = {
            "owner": str(item.get("owner") or "").strip(),
            "plane": str(item.get("plane") or "").strip(),
            "priority": str(item.get("priority") or "").strip(),
            "instruction": str(item.get("instruction") or "").strip(),
            "reason": str(item.get("reason") or "").strip(),
            "source_families": [
                str(source_family).strip()
                for source_family in _list_value(item.get("source_families"))
                if str(source_family).strip()
            ],
            "evidence_urls": [
                str(url).strip()
                for url in _list_value(item.get("evidence_urls"))
                if str(url).strip()
            ],
        }
        required = ("owner", "plane", "priority", "instruction", "reason")
        if all(row[field] for field in required):
            actions.append(row)
    return actions[:8]


def _source_health(dashboard: Mapping[str, Any]) -> dict[str, Any]:
    health = dashboard.get("source_health")
    if isinstance(health, list):
        active_rows = [
            row
            for row in health
            if isinstance(row, Mapping) and str(row.get("status") or "").strip() == "active"
        ]
        checked_rows = [row for row in active_rows if row.get("checked_at")]
        failed_rows = [
            row
            for row in checked_rows
            if str(row.get("latest_event_type") or "").strip().lower()
            not in {"", "ok", "success"}
        ]
        return {
            "active_source_count": len(active_rows),
            "checked_source_count": len(checked_rows),
            "failed_source_count": len(failed_rows),
        }
    return _dict_value(health)


def _monitored_competitors(dashboard: Mapping[str, Any]) -> list[Any]:
    return _list_value(dashboard.get("monitored_competitors"))


def _plane(
    *,
    status: str,
    summary: str,
    storage: list[str],
    counts: dict[str, int],
    blocks_action: bool = False,
    next_hermes_action: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": status,
        "summary": summary,
        "blocks_action": blocks_action,
        "storage": storage,
        "counts": counts,
    }
    if next_hermes_action:
        payload["next_hermes_action"] = next_hermes_action
    if details:
        payload["details"] = details
    return payload


def _sanitized_empty_outputs(value: Any, *, limit: int = 8) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in _list_value(value):
        if not isinstance(item, Mapping):
            continue
        row = {
            "company_name": str(item.get("company_name") or "").strip(),
            "surface_family": str(item.get("surface_family") or "").strip(),
        }
        if row["company_name"] or row["surface_family"]:
            rows.append({key: val for key, val in row.items() if val})
        if len(rows) >= limit:
            break
    return rows


def _product_surface_execution_summary(run: Mapping[str, Any]) -> dict[str, Any]:
    raw = _dict_value(run.get("product_surface_execution_summary"))
    if not raw:
        return {}
    summary: dict[str, Any] = {
        "product_plane_status": str(raw.get("product_plane_status") or ""),
        "planned": _int_value(raw.get("planned")),
        "succeeded": _int_value(raw.get("succeeded")),
        "empty": _int_value(raw.get("empty")),
        "failed": _int_value(raw.get("failed")),
        "product_row_count": _int_value(raw.get("product_row_count")),
        "empty_outputs": _sanitized_empty_outputs(raw.get("empty_outputs")),
    }
    if isinstance(raw.get("company_row_counts"), dict):
        summary["company_row_counts"] = _dict_value(raw.get("company_row_counts"))
    if isinstance(raw.get("surface_family_row_counts"), dict):
        summary["surface_family_row_counts"] = _dict_value(raw.get("surface_family_row_counts"))
    preserved_empty_maps = {"company_row_counts", "surface_family_row_counts"}
    return {
        key: value
        for key, value in summary.items()
        if key in preserved_empty_maps or value not in (None, "", [], {})
    }


def _empty_output_labels(empty_outputs: list[dict[str, str]]) -> list[str]:
    labels: list[str] = []
    for item in empty_outputs:
        company = str(item.get("company_name") or "").strip()
        family = str(item.get("surface_family") or "").strip()
        label = " ".join(part for part in (company, family) if part)
        if label:
            labels.append(label)
    return labels


def _product_surface_execution_next_step(execution: Mapping[str, Any]) -> str:
    labels = _empty_output_labels(_list_value(execution.get("empty_outputs")))
    if labels:
        return f"Repair or replace empty product-surface targets: {', '.join(labels[:5])}."
    return "Repair product-surface extraction and rerun the product-market chain."


def _registry_plane(dashboard: Mapping[str, Any]) -> dict[str, Any]:
    health = _source_health(dashboard)
    monitored = _monitored_competitors(dashboard)
    active_sources = _int_value(health.get("active_source_count"))
    failed_sources = _int_value(health.get("failed_source_count"))
    checked_sources = _int_value(health.get("checked_source_count"))
    if failed_sources > 0:
        status = "degraded"
        summary = "Registry is active, but source failures limit quiet-day confidence."
    elif active_sources > 0 or monitored:
        status = "present"
        summary = "Registry and source coverage are represented in the current dashboard state."
    else:
        status = "missing"
        summary = "No monitored competitors or source health were exposed in the current dashboard state."
    return _plane(
        status=status,
        summary=summary,
        storage=REGISTRY_STORAGE,
        counts={
            "monitored_competitor_count": len(monitored),
            "active_source_count": active_sources,
            "checked_source_count": checked_sources,
            "failed_source_count": failed_sources,
        },
        blocks_action=False,
    )


def _product_plane(run: Mapping[str, Any], product_muscle_work_queue: Mapping[str, Any]) -> dict[str, Any]:
    product_events = _int_value(run.get("product_event_count"))
    target_count = _int_value(run.get("target_count"))
    target_company_count = _int_value(run.get("target_company_count"))
    product_surface_execution = _product_surface_execution_summary(run)
    execution_status = str(product_surface_execution.get("product_plane_status") or "")
    execution_product_rows = _int_value(product_surface_execution.get("product_row_count"))
    gap_plan = _dict_value(run.get("product_muscle_gap_plan"))
    product_muscle_blocking_count = _int_value(product_muscle_work_queue.get("blocking_count"))
    product_muscle_limiting_count = _int_value(product_muscle_work_queue.get("limiting_count"))
    product_muscle_items = _list_value(product_muscle_work_queue.get("items"))
    product_muscle_next_action = _first_next_step(product_muscle_items)
    product_muscle_work_order = _product_muscle_work_order(product_muscle_work_queue)
    if product_muscle_blocking_count > 0:
        status = "blocked_missing_product_surfaces"
        summary = "Product reality coverage is blocking Argus from trusting the feature matrix."
    elif product_muscle_limiting_count > 0:
        status = "limited_by_product_surface_evidence"
        summary = "Product reality evidence is present but still limiting feature-matrix confidence."
    elif execution_status == "empty":
        status = "empty_product_surface_outputs"
        summary = "Product surfaces ran, but produced no product proof for the feature matrix."
    elif execution_status in {"failed", "failed_empty"}:
        status = "failed_product_surface_execution"
        summary = "Product-surface execution failed before Argus could trust product reality."
    elif execution_status == "degraded":
        status = "degraded_product_surface_outputs"
        summary = "Some product-surface targets produced product proof, but others were empty or failed."
    elif product_events > 0 or execution_product_rows > 0:
        status = "present"
        summary = "Product reality evidence fed the feature matrix and product-market read."
    elif target_count > 0:
        status = "configured"
        summary = "Product surfaces are configured, but no product events were persisted for this run."
    else:
        status = "missing"
        summary = "No product-surface coverage was visible in the current run state."
    return _plane(
        status=status,
        summary=summary,
        storage=PRODUCT_STORAGE,
        counts={
            "product_event_count": product_events,
            "product_surface_target_count": target_count,
            "target_company_count": target_company_count,
            "product_surface_planned_count": _int_value(product_surface_execution.get("planned")),
            "product_surface_succeeded_count": _int_value(product_surface_execution.get("succeeded")),
            "product_surface_empty_count": _int_value(product_surface_execution.get("empty")),
            "product_surface_failed_count": _int_value(product_surface_execution.get("failed")),
            "product_surface_extracted_row_count": execution_product_rows,
            "product_muscle_missing_company_count": _int_value(gap_plan.get("missing_company_count")),
            "product_muscle_candidate_url_count": _int_value(gap_plan.get("candidate_url_count")),
            "product_muscle_work_item_count": _int_value(product_muscle_work_queue.get("work_item_count")),
            "product_muscle_blocking_count": product_muscle_blocking_count,
            "product_muscle_limiting_count": product_muscle_limiting_count,
        },
        blocks_action=product_muscle_blocking_count > 0
        or execution_status in {"empty", "failed", "failed_empty"},
        next_hermes_action=product_muscle_next_action,
        details={
            "target_companies": _list_value(run.get("target_companies")),
            "surface_family_counts": _dict_value(run.get("surface_family_counts")),
            **(
                {"product_surface_execution": product_surface_execution}
                if product_surface_execution
                else {}
            ),
            "work_item_ids": [
                str(item.get("work_item_id"))
                for item in product_muscle_items
                if isinstance(item, dict) and item.get("work_item_id")
            ],
            **(
                {"product_muscle_work_queue": product_muscle_work_order}
                if product_muscle_work_order
                else {}
            ),
        },
    )


def _conversation_plane(run: Mapping[str, Any]) -> dict[str, Any]:
    themes = _int_value(run.get("conversation_theme_count"))
    patterns = _int_value(run.get("pattern_count"))
    if themes > 0:
        status = "present"
        summary = "Market conversation evidence fed the current Argus read."
    else:
        status = "quiet_or_missing"
        summary = "No conversation themes were exposed in the current product-market run state."
    return _plane(
        status=status,
        summary=summary,
        storage=CONVERSATION_STORAGE,
        counts={
            "conversation_theme_count": themes,
            "pattern_count": patterns,
        },
        blocks_action=False,
    )


def _demand_intake_summary(demand_intake: Mapping[str, Any]) -> dict[str, Any]:
    if not demand_intake:
        return {}
    demand_import = _dict_value(demand_intake.get("demand_import"))
    prepare = _dict_value(demand_import.get("prepare"))
    demand_ledger = _dict_value(demand_import.get("demand_ledger"))
    ga4_export = _dict_value(demand_intake.get("ga4_export"))
    argus_read = _dict_value(demand_import.get("argus_read"))
    summary: dict[str, Any] = {
        "status": demand_intake.get("status"),
        "command_status": demand_intake.get("command_status"),
        "exit_code": demand_intake.get("exit_code"),
        "mode": demand_intake.get("mode"),
        "next_hermes_action": demand_intake.get("next_hermes_action"),
        "summary_path": demand_intake.get("summary_path"),
    }
    if ga4_export:
        summary["ga4_record_count"] = _int_value(ga4_export.get("record_count"))
    if prepare:
        summary["normalized_row_count"] = _int_value(prepare.get("normalized_row_count"))
        summary["ready_count"] = _int_value(prepare.get("ready_count"))
    if demand_ledger:
        summary["demand_signal_count"] = _int_value(demand_ledger.get("demand_signal_count"))
    if argus_read.get("top_insight"):
        summary["argus_top_insight"] = argus_read.get("top_insight")
    return {key: value for key, value in summary.items() if value is not None}


def _route_kind(href: Any) -> str:
    value = str(href or "")
    if value.startswith("/api/"):
        return "api"
    if value.startswith("/admin"):
        return "admin"
    if value.startswith("http://") or value.startswith("https://"):
        return "external"
    return "unknown"


def _operator_commands(actions: Any) -> list[dict[str, str]]:
    commands: list[dict[str, str]] = []
    for action in _list_value(actions):
        if not isinstance(action, dict):
            continue
        label = str(action.get("label") or "").strip()
        surface = str(action.get("surface") or "").strip()
        if not label or not surface:
            continue
        commands.append(
            {
                "label": label,
                "method": str(action.get("method") or "get").lower(),
                "surface": surface,
                "route_kind": _route_kind(action.get("href")),
            }
        )
    return commands


def _demand_plane(
    run: Mapping[str, Any],
    demand_readiness: Mapping[str, Any],
    demand_intake: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    demand_intake = demand_intake or {}
    intake = _demand_intake_summary(demand_intake)
    demand_signal_count = max(
        _int_value(run.get("demand_signal_count")),
        _int_value(intake.get("demand_signal_count")),
    )
    normalized_row_count = max(
        _int_value(run.get("looker_normalized_row_count")),
        _int_value(intake.get("normalized_row_count")),
    )
    readiness_status = str(demand_readiness.get("status") or run.get("demand_plane_status") or "not_recorded")
    intake_status = str(intake.get("status") or "")
    next_action = intake.get("next_hermes_action") or demand_readiness.get("next_hermes_action")
    processed_statuses = {
        "demand_imported_and_argus_refreshed",
        "ga4_exported_demand_imported_and_argus_refreshed",
    }
    blocking_statuses = {
        "missing",
        "not_recorded",
        "blocked_missing_demand_source",
        "blocked_missing_configuration",
        "blocked_bad_manual_export",
        "demand_import_failed",
        "ga4_export_failed",
        "queued_manual_export",
        "queued_manual_exports",
        "ready_to_export_ga4",
        "ready_for_manual_import",
    }
    plan_blocking_statuses = {
        "processed_partial_plan_coverage",
        "processed_off_plan_demand",
        "processed_unmapped_demand",
    }
    if readiness_status in plan_blocking_statuses:
        status = readiness_status
    elif demand_signal_count > 0 or intake_status in processed_statuses:
        status = "processed"
    elif intake_status in blocking_statuses:
        status = intake_status
    else:
        status = readiness_status
    blocks_action = status in plan_blocking_statuses or (demand_signal_count == 0 and status in blocking_statuses)
    if blocks_action:
        summary = str(
            demand_readiness.get("summary")
            or "Tenant-side demand is missing, so Argus cannot promote outward movement to confident action."
        )
    elif demand_signal_count > 0:
        summary = "Tenant-side demand evidence is present for the current product-market read."
    else:
        summary = str(demand_readiness.get("summary") or "Demand plane is available but has no imported rows yet.")
    details = {
        "manual_import": _dict_value(demand_readiness.get("manual_import")),
        "ga4_connector": _dict_value(demand_readiness.get("ga4_connector")),
        "demand_intake": intake,
    }
    demand_source_contract = _dict_value(demand_readiness.get("demand_source_contract"))
    if demand_source_contract:
        details["demand_source_contract"] = demand_source_contract
    demand_collection_plan = _dict_value(demand_readiness.get("demand_collection_plan"))
    if demand_collection_plan:
        details["demand_collection_plan"] = demand_collection_plan
    operator_commands = _operator_commands(demand_readiness.get("operator_actions"))
    if operator_commands:
        details["operator_commands"] = operator_commands
    return _plane(
        status=status,
        summary=summary,
        storage=DEMAND_STORAGE,
        counts={
            "demand_signal_count": demand_signal_count,
            "looker_discovered_count": _int_value(run.get("looker_discovered_count")),
            "looker_ready_count": _int_value(run.get("looker_ready_count")),
            "looker_error_count": _int_value(run.get("looker_error_count")),
            "looker_normalized_row_count": normalized_row_count,
        },
        blocks_action=blocks_action,
        next_hermes_action=str(next_action) if next_action else None,
        details=details,
    )


def _learning_plane(run: Mapping[str, Any]) -> dict[str, Any]:
    consumed = _list_value(run.get("consumed_learning_ids"))
    instruction_count = _int_value(run.get("learning_instruction_count"))
    status = "present" if consumed or instruction_count > 0 or run.get("next_sweep_plan_path") else "not_applied"
    summary = (
        "Approved learning was consumed or prepared for this run."
        if status == "present"
        else "No approved learning instructions were visible in the current run state."
    )
    return _plane(
        status=status,
        summary=summary,
        storage=LEARNING_STORAGE,
        counts={
            "consumed_learning_count": len(consumed),
            "learning_instruction_count": instruction_count,
        },
        blocks_action=False,
        details={"next_sweep_plan_path": run.get("next_sweep_plan_path")},
    )


def _run_truth_plane(run: Mapping[str, Any]) -> dict[str, Any]:
    stage_ledger = _list_value(run.get("stage_ledger"))
    status = "present" if stage_ledger else "not_recorded"
    summary = (
        "Run-stage ledger is present for Hermes and Argus inspection."
        if stage_ledger
        else "No run-stage ledger was exposed in the current dashboard state."
    )
    failed_stages = [entry for entry in stage_ledger if isinstance(entry, dict) and entry.get("status") == "failed"]
    return _plane(
        status=status,
        summary=summary,
        storage=RUN_TRUTH_STORAGE,
        counts={
            "stage_count": len(stage_ledger),
            "failed_stage_count": len(failed_stages),
        },
        blocks_action=False,
        details={"run_status": run.get("status"), "runner_verdict": run.get("runner_verdict")},
    )


def _first_next_step(items: list[Any]) -> str | None:
    for item in items:
        if isinstance(item, dict) and item.get("next_step"):
            return str(item["next_step"])
    return None


def _topic_label(topic: Mapping[str, Any]) -> str:
    return str(topic.get("topic") or topic.get("capability_key") or "").strip()


def _planned_demand_topics_from_plane(
    demand_plane: Mapping[str, Any],
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    details = _dict_value(demand_plane.get("details"))
    demand_collection_plan = _dict_value(details.get("demand_collection_plan"))
    planned_topics: list[dict[str, Any]] = []
    for topic in _list_value(demand_collection_plan.get("topics")):
        if not isinstance(topic, dict):
            continue
        row: dict[str, Any] = {}
        for field in ("topic", "capability_key", "assessment"):
            if topic.get(field) not in (None, "", []):
                row[field] = topic[field]
        competitors = _list_value(topic.get("related_competitors"))
        if competitors:
            row["related_competitors"] = competitors[:5]
        evidence_urls = _list_value(topic.get("evidence_urls"))
        if evidence_urls:
            row["evidence_url_count"] = len(evidence_urls)
        if row:
            planned_topics.append(row)
        if len(planned_topics) >= limit:
            break
    return planned_topics


def _sanitized_plan_topics(topics: Any, *, fields: tuple[str, ...]) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    for topic in _list_value(topics):
        if not isinstance(topic, dict):
            continue
        row = {field: topic[field] for field in fields if topic.get(field) not in (None, "", [])}
        if row:
            sanitized.append(row)
    return sanitized


def _demand_plan_gap_blocker(
    *,
    demand_plane: Mapping[str, Any],
    operator_commands: list[Any],
) -> dict[str, Any]:
    details = _dict_value(demand_plane.get("details"))
    demand_collection_plan = _dict_value(details.get("demand_collection_plan"))
    demand_source_contract = _dict_value(details.get("demand_source_contract"))
    coverage = _dict_value(demand_collection_plan.get("coverage"))
    missing_topics = _sanitized_plan_topics(
        coverage.get("missing_topics"),
        fields=("topic", "capability_key", "why_collect", "suggested_filter_terms"),
    )
    off_plan_topics = _sanitized_plan_topics(
        coverage.get("off_plan_topics"),
        fields=("topic", "capability_key", "evidence_urls", "source_files", "source_row_numbers"),
    )
    missing_labels = [_topic_label(topic) for topic in missing_topics if _topic_label(topic)]

    if missing_labels:
        next_step = f"Collect demand for missing planned topics: {', '.join(missing_labels[:5])}."
    elif off_plan_topics:
        next_step = "Map imported demand to Argus planned topics or collect the planned demand export."
    else:
        next_step = str(demand_plane.get("next_hermes_action") or "Configure GA4 or upload a GA / Looker export.")

    title = (
        "Demand plan coverage incomplete"
        if missing_topics or off_plan_topics
        else "Demand plane missing"
    )
    blocker: dict[str, Any] = {
        "plane": "audience_demand",
        "severity": "blocks_action",
        "title": title,
        "next_step": next_step,
        "work_item_id": None,
    }
    planned_topics = _planned_demand_topics_from_plane(demand_plane)
    if planned_topics:
        blocker["planned_topic_count"] = _int_value(demand_collection_plan.get("topic_count")) or len(
            planned_topics
        )
        blocker["planned_topics"] = planned_topics
    if operator_commands:
        blocker["operator_commands"] = operator_commands
    if demand_source_contract.get("status"):
        blocker["demand_source_contract_status"] = str(demand_source_contract["status"])
    if missing_topics:
        blocker["missing_topics"] = missing_topics
    if off_plan_topics:
        blocker["off_plan_topics"] = off_plan_topics
    return blocker


def _product_surface_execution_blocker(product_plane: Mapping[str, Any]) -> dict[str, Any]:
    execution = _dict_value(_dict_value(product_plane.get("details")).get("product_surface_execution"))
    execution_status = str(execution.get("product_plane_status") or "")
    title = (
        "Product surface extraction failed"
        if execution_status in {"failed", "failed_empty"}
        else "Product surface extraction returned no product proof"
    )
    blocker: dict[str, Any] = {
        "plane": "product_reality",
        "severity": "blocks_feature_matrix",
        "title": title,
        "next_step": _product_surface_execution_next_step(execution),
        "work_item_id": f"product-surface-execution:{execution_status or 'blocked'}",
    }
    empty_outputs = _list_value(execution.get("empty_outputs"))
    if empty_outputs:
        blocker["empty_outputs"] = empty_outputs
    return blocker


def _blockers(
    evidence_work_queue: Mapping[str, Any],
    product_muscle_work_queue: Mapping[str, Any],
    demand_plane: Mapping[str, Any],
    product_plane: Mapping[str, Any],
) -> list[dict[str, Any]]:
    items = _list_value(evidence_work_queue.get("items"))
    blockers: list[dict[str, Any]] = []
    demand_operator_commands = _list_value(_dict_value(demand_plane.get("details")).get("operator_commands"))
    demand_source_contract = _dict_value(_dict_value(demand_plane.get("details")).get("demand_source_contract"))
    for item in items:
        if not isinstance(item, dict) or item.get("severity") != "blocks_action":
            continue
        raw_plane = str(item.get("evidence_plane") or "unknown")
        plane = "audience_demand" if raw_plane == "demand" else raw_plane
        blocker = {
            "plane": plane,
            "severity": "blocks_action",
            "title": str(item.get("title") or "Evidence gap"),
            "next_step": str(item.get("next_step") or "Repair the evidence gap."),
            "work_item_id": item.get("work_item_id"),
        }
        if plane == "audience_demand" and demand_operator_commands:
            blocker["operator_commands"] = demand_operator_commands
        if plane == "audience_demand" and demand_source_contract.get("status"):
            blocker["demand_source_contract_status"] = str(demand_source_contract["status"])
        if plane == "audience_demand":
            planned_topics = _planned_demand_topics_from_plane(demand_plane)
            if planned_topics:
                demand_collection_plan = _dict_value(
                    _dict_value(demand_plane.get("details")).get("demand_collection_plan")
                )
                blocker["planned_topic_count"] = _int_value(
                    demand_collection_plan.get("topic_count")
                ) or len(planned_topics)
                blocker["planned_topics"] = planned_topics
        blockers.append(blocker)
    for item in _list_value(product_muscle_work_queue.get("items")):
        if not isinstance(item, dict) or item.get("severity") != "blocks_feature_matrix":
            continue
        blockers.append(
            {
                "plane": "product_reality",
                "severity": "blocks_feature_matrix",
                "title": str(item.get("title") or "Product muscle evidence gap"),
                "next_step": str(item.get("next_step") or "Add product-surface evidence."),
                "work_item_id": item.get("work_item_id"),
            }
        )
    has_product_reality_blocker = any(
        blocker.get("plane") == "product_reality" and blocker.get("severity") == "blocks_feature_matrix"
        for blocker in blockers
    )
    if product_plane.get("blocks_action") and not has_product_reality_blocker:
        blockers.append(_product_surface_execution_blocker(product_plane))
    if not blockers and demand_plane.get("blocks_action"):
        blockers.append(
            _demand_plan_gap_blocker(
                demand_plane=demand_plane,
                operator_commands=demand_operator_commands,
            )
        )
    return blockers


def _overall_status(
    *,
    blockers: list[dict[str, Any]],
    evidence_work_queue: Mapping[str, Any],
    product_muscle_work_queue: Mapping[str, Any],
    operator_handoff: Mapping[str, Any],
) -> str:
    if (
        blockers
        or _int_value(evidence_work_queue.get("blocking_count")) > 0
        or _int_value(product_muscle_work_queue.get("blocking_count")) > 0
    ):
        return "blocked_on_evidence"
    handoff_status = str(operator_handoff.get("status") or "")
    if handoff_status:
        return handoff_status
    if (
        _int_value(evidence_work_queue.get("limiting_count")) > 0
        or _int_value(product_muscle_work_queue.get("limiting_count")) > 0
    ):
        return "limited_by_evidence"
    return "ready_for_operator_review"


def _next_hermes_action(
    *,
    status: str,
    demand_plane: Mapping[str, Any],
    operator_handoff: Mapping[str, Any],
    blockers: list[dict[str, Any]],
) -> str:
    if demand_plane.get("blocks_action") and demand_plane.get("next_hermes_action"):
        return str(demand_plane["next_hermes_action"])
    if blockers:
        return str(blockers[0].get("next_step") or "repair_evidence_gap")
    if operator_handoff.get("next_operator_action"):
        return str(operator_handoff["next_operator_action"])
    if status == "ready_for_operator_review":
        return "review_scored_recommendations"
    return "review_argus_evidence_queue"


def build_data_plane_manifest_payload(
    *,
    tenant_slug: str,
    dashboard: dict[str, Any],
    demand_readiness: dict[str, Any] | None = None,
    demand_intake: dict[str, Any] | None = None,
    evidence_work_queue: dict[str, Any] | None = None,
    product_muscle_work_queue: dict[str, Any] | None = None,
    operator_handoff: dict[str, Any] | None = None,
    artifact_refs: dict[str, str | None] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    demand_readiness = demand_readiness or {}
    demand_intake = demand_intake or {}
    evidence_work_queue = evidence_work_queue or {}
    product_muscle_work_queue = product_muscle_work_queue or {}
    operator_handoff = operator_handoff or {}
    run = _dashboard_run(dashboard)

    cleaned_artifact_refs = artifact_refs or {}
    planes = {
        "registry_coverage": _registry_plane(dashboard),
        "product_reality": _product_plane(run, product_muscle_work_queue),
        "market_conversation": _conversation_plane(run),
        "audience_demand": _demand_plane(run, demand_readiness, demand_intake),
        "operator_learning": _learning_plane(run),
        "run_truth": _run_truth_plane(run),
    }
    demand_plan_template = _demand_plan_template_summary(cleaned_artifact_refs)
    if demand_plan_template:
        planes["audience_demand"].setdefault("details", {})["demand_plan_template"] = demand_plan_template
    blockers = _blockers(
        evidence_work_queue,
        product_muscle_work_queue,
        planes["audience_demand"],
        planes["product_reality"],
    )
    status = _overall_status(
        blockers=blockers,
        evidence_work_queue=evidence_work_queue,
        product_muscle_work_queue=product_muscle_work_queue,
        operator_handoff=operator_handoff,
    )

    return {
        "schema_version": 1,
        "tenant_slug": tenant_slug,
        "generated_at": generated_at or _now(),
        "dashboard_generated_at": dashboard.get("generated_at"),
        "status": status,
        "argus_readiness": str(operator_handoff.get("argus_readiness") or "unknown"),
        "argus_decision": _argus_decision(run),
        "next_monitoring_actions": _next_monitoring_actions(run),
        "next_hermes_action": _next_hermes_action(
            status=status,
            demand_plane=planes["audience_demand"],
            operator_handoff=operator_handoff,
            blockers=blockers,
        ),
        "source_of_truth": {
            "runtime": "Hermes",
            "domain_package": "CI-OS",
            "database": "Postgres evidence ledger",
            "ui_role": "derived readout only",
        },
        "artifact_refs": cleaned_artifact_refs,
        "planes": planes,
        "blockers": blockers,
        "safety": {
            "ui_must_not_invent_semantics": True,
            "recommendations_require_backend_scorecards": True,
            "empty_or_missing_plane_blocks_promotion": True,
        },
    }


def write_payload(payload: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(f"{json.dumps(payload, indent=2, sort_keys=True)}\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Argus data-plane manifest.")
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--dashboard", type=Path, required=True)
    parser.add_argument("--demand-readiness", type=Path)
    parser.add_argument("--demand-plan-template", type=Path)
    parser.add_argument("--demand-intake", type=Path)
    parser.add_argument("--evidence-work-queue", type=Path)
    parser.add_argument("--product-muscle-work-queue", type=Path)
    parser.add_argument("--operator-handoff", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    artifact_refs = {
        "dashboard": str(args.dashboard),
        "demand_readiness": str(args.demand_readiness) if args.demand_readiness else None,
        "demand_plan_template": str(args.demand_plan_template) if args.demand_plan_template else None,
        "demand_intake": str(args.demand_intake) if args.demand_intake else None,
        "evidence_work_queue": str(args.evidence_work_queue) if args.evidence_work_queue else None,
        "product_muscle_work_queue": (
            str(args.product_muscle_work_queue) if args.product_muscle_work_queue else None
        ),
        "operator_handoff": str(args.operator_handoff) if args.operator_handoff else None,
    }
    payload = build_data_plane_manifest_payload(
        tenant_slug=args.tenant,
        dashboard=_load_json(args.dashboard),
        demand_readiness=_load_json(args.demand_readiness),
        demand_intake=_load_json(args.demand_intake),
        evidence_work_queue=_load_json(args.evidence_work_queue),
        product_muscle_work_queue=_load_json(args.product_muscle_work_queue),
        operator_handoff=_load_json(args.operator_handoff),
        artifact_refs=artifact_refs,
    )
    if args.output:
        write_payload(payload, args.output)
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
