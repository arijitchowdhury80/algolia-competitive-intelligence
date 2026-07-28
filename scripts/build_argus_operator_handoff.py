#!/usr/bin/env python3
"""Build the Hermes-facing Argus operator handoff artifact.

The evidence work queue names what Argus cannot trust yet. This command turns
that queue into the compact machine-readable handoff Hermes, Telegram, admin,
and the dashboard can all use as the next operating instruction for the run.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEMAND_BLOCKING_STATUSES = {
    "blocked_missing_demand_source",
    "blocked_missing_configuration",
    "blocked_bad_manual_export",
    "queued_manual_export",
    "queued_manual_exports",
    "ready_for_manual_import",
    "ready_to_export_ga4",
    "processed_partial_plan_coverage",
    "processed_off_plan_demand",
    "processed_unmapped_demand",
    "processed_no_comparison_period",
    "processed_no_action_grade_demand",
}

DEMAND_NEXT_ACTION_LABELS = {
    "configure_ga4_or_upload_demand_export": "Configure GA4 or upload a GA / Looker export.",
    "repair_queued_demand_export": "Repair the queued demand export, then rerun demand intake.",
    "prepare_demand_and_refresh_argus": "Prepare queued demand and refresh Argus.",
    "run_ga4_export_then_prepare_demand": "Run GA4 export, then prepare demand and refresh Argus.",
    "collect_missing_plan_demand": "Collect demand for missing planned topics.",
    "collect_planned_demand": "Collect the planned GA / Looker demand export.",
    "inspect_demand_mapping": "Inspect demand mapping and repair topic normalization.",
    "upload_trended_planned_demand_export": "Upload a planned demand export with previous-period or change_pct values, then refresh Argus.",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_payload(payload: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(f"{json.dumps(payload, indent=2, sort_keys=True)}\n", encoding="utf-8")


def build_operator_handoff_payload(
    *,
    tenant_slug: str,
    work_queue: dict[str, Any],
    product_muscle_queue: dict[str, Any] | None = None,
    demand_readiness: dict[str, Any] | None = None,
    demand_plan_template_path: str | None = None,
    demand_plan_amendments: dict[str, Any] | list[Any] | None = None,
    dashboard: dict[str, Any] | None = None,
    work_queue_path: str | None = None,
    product_muscle_queue_path: str | None = None,
    demand_readiness_path: str | None = None,
    demand_plan_amendments_path: str | None = None,
    dashboard_path: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    queue_tenant = work_queue.get("tenant_slug")
    if queue_tenant and queue_tenant != tenant_slug:
        raise ValueError(f"work queue tenant {queue_tenant} does not match {tenant_slug}")
    product_muscle_queue = product_muscle_queue or {}
    muscle_tenant = product_muscle_queue.get("tenant_slug")
    if muscle_tenant and muscle_tenant != tenant_slug:
        raise ValueError(f"product muscle queue tenant {muscle_tenant} does not match {tenant_slug}")
    demand_readiness = demand_readiness or {}
    readiness_tenant = demand_readiness.get("tenant_slug")
    if readiness_tenant and readiness_tenant != tenant_slug:
        raise ValueError(f"demand readiness tenant {readiness_tenant} does not match {tenant_slug}")

    dashboard = dashboard or {}
    evidence_items = list(work_queue.get("items") or [])
    demand_items = (
        []
        if _has_blocking_demand_item(evidence_items)
        else _demand_readiness_items(demand_readiness, tenant_slug=tenant_slug)
    )
    product_muscle_queue_items = [
        _as_product_muscle_item(item) for item in list(product_muscle_queue.get("items") or [])
    ]
    product_surface_execution_items = _product_surface_execution_items(dashboard, tenant_slug=tenant_slug)
    product_muscle_items = product_muscle_queue_items + product_surface_execution_items
    items = demand_items + evidence_items + product_muscle_items
    evidence_blocking_count = int(work_queue.get("blocking_count") or _count_by_severity(evidence_items, "blocks_action"))
    demand_blocking_count = _count_by_severity(demand_items, "blocks_action")
    product_surface_execution_blocking_count = _count_by_severity(
        product_surface_execution_items,
        "blocks_feature_matrix",
    )
    product_muscle_queue_blocking_count = int(
        product_muscle_queue.get("blocking_count")
        or _count_by_severity(product_muscle_queue_items, "blocks_feature_matrix")
    )
    product_muscle_blocking_count = int(
        product_muscle_queue_blocking_count + product_surface_execution_blocking_count
    )
    blocking_count = demand_blocking_count + evidence_blocking_count + product_muscle_blocking_count
    product_muscle_queue_limiting_count = int(
        product_muscle_queue.get("limiting_count")
        or max(len(product_muscle_queue_items) - product_muscle_queue_blocking_count, 0)
    )
    product_surface_execution_limiting_count = max(
        len(product_surface_execution_items) - product_surface_execution_blocking_count,
        0,
    )
    limiting_count = (
        int(work_queue.get("limiting_count") or max(len(evidence_items) - evidence_blocking_count, 0))
        + product_muscle_queue_limiting_count
        + product_surface_execution_limiting_count
    )
    top_item = _top_item(items)
    status, readiness = _status_for_counts(blocking_count, limiting_count, len(items))
    demand_collection_plan = demand_readiness.get("demand_collection_plan")
    demand_plan_amendment_summary = _demand_plan_amendment_summary(demand_plan_amendments)

    return {
        "tenant_slug": tenant_slug,
        "tenant_id": work_queue.get("tenant_id"),
        "generated_at": generated_at or _now(),
        "status": status,
        "argus_readiness": readiness,
        "summary": _summary(blocking_count=blocking_count, limiting_count=limiting_count),
        "next_operator_action": _next_operator_action(top_item),
        "top_blocker": _top_blocker(top_item),
        "primary_command": _primary_command(
            top_item,
            demand_readiness=demand_readiness,
            tenant_slug=tenant_slug,
        ),
        "secondary_command": _command_from_item(top_item, primary=False, tenant_slug=tenant_slug),
        "operator_commands": _operator_commands(demand_readiness.get("operator_actions")),
        "demand_collection_plan": demand_collection_plan if isinstance(demand_collection_plan, dict) else {},
        "demand_plan_template": _demand_plan_template_summary(demand_plan_template_path),
        "demand_plan_amendments": demand_plan_amendment_summary,
        "operator_brief": _operator_brief(
            top_item=top_item,
            blocking_count=blocking_count,
            limiting_count=limiting_count,
            dashboard=dashboard,
        ),
        "artifact_refs": {
            "work_queue": work_queue_path,
            "product_muscle_work_queue": product_muscle_queue_path,
            "demand_readiness": demand_readiness_path,
            "demand_plan_template": demand_plan_template_path,
            "demand_plan_amendments": demand_plan_amendments_path,
            "dashboard": dashboard_path,
        },
        "work_queue": {
            "generated_at": work_queue.get("generated_at"),
            "product_muscle_generated_at": product_muscle_queue.get("generated_at"),
            "work_item_count": len(items),
            "blocking_count": blocking_count,
            "limiting_count": limiting_count,
            "demand_blocking_count": demand_blocking_count,
            "evidence_blocking_count": evidence_blocking_count,
            "product_muscle_blocking_count": product_muscle_blocking_count,
            "product_surface_execution_blocking_count": product_surface_execution_blocking_count,
            "item_ids": [str(item.get("work_item_id")) for item in items if item.get("work_item_id")],
        },
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _count_by_severity(items: list[dict[str, Any]], severity: str) -> int:
    return sum(1 for item in items if item.get("severity") == severity)


def _has_blocking_demand_item(items: list[dict[str, Any]]) -> bool:
    return any(
        item.get("evidence_plane") == "demand" and item.get("severity") == "blocks_action"
        for item in items
    )


def _as_product_muscle_item(item: dict[str, Any]) -> dict[str, Any]:
    copied = dict(item)
    copied.setdefault("evidence_plane", "product_muscle")
    return copied


def _text_value(value: Any) -> str:
    return " ".join(str(value or "").split())


def _first_action(actions: Any, *, index: int = 0) -> dict[str, Any]:
    if not isinstance(actions, list):
        return {}
    seen = 0
    for action in actions:
        if not isinstance(action, dict):
            continue
        label = _text_value(action.get("label"))
        href = _text_value(action.get("href"))
        surface = _text_value(action.get("surface"))
        if not label or not href or not surface:
            continue
        if seen == index:
            return {
                "label": label,
                "href": href,
                "method": _text_value(action.get("method") or "get").lower(),
                "surface": surface,
            }
        seen += 1
    return {}


def _demand_status_blocks_action(status: str) -> bool:
    return status in DEMAND_BLOCKING_STATUSES


def _demand_readiness_title(status: str) -> str:
    if status == "processed_no_comparison_period":
        return "Demand trend window missing"
    if status == "processed_no_action_grade_demand":
        return "Demand movement not action-grade"
    if status in {"processed_partial_plan_coverage", "processed_off_plan_demand", "processed_unmapped_demand"}:
        return "Demand plan coverage incomplete"
    if status == "blocked_bad_manual_export":
        return "Demand export cannot be normalized"
    if status in {"queued_manual_export", "queued_manual_exports", "ready_for_manual_import"}:
        return "Demand export queued but not applied"
    if status == "ready_to_export_ga4":
        return "GA4 demand export is ready but not applied"
    return "Demand plane missing"


def _demand_next_step(demand_readiness: dict[str, Any]) -> str:
    action = _text_value(demand_readiness.get("next_hermes_action"))
    if action in DEMAND_NEXT_ACTION_LABELS:
        return DEMAND_NEXT_ACTION_LABELS[action]
    summary = _text_value(demand_readiness.get("summary"))
    return summary or "Configure GA4 or upload a GA / Looker export."


def _demand_observed_state(demand_readiness: dict[str, Any]) -> dict[str, Any]:
    plan = _dict_value(demand_readiness.get("demand_collection_plan"))
    contract = _dict_value(demand_readiness.get("demand_source_contract"))
    state: dict[str, Any] = {
        "status": _text_value(demand_readiness.get("status")),
        "next_hermes_action": _text_value(demand_readiness.get("next_hermes_action")),
    }
    if contract.get("status"):
        state["demand_source_contract_status"] = _text_value(contract.get("status"))
    if contract.get("ready_source_count") is not None:
        state["ready_source_count"] = _int_value(contract.get("ready_source_count"))
    if plan.get("status"):
        state["demand_collection_plan_status"] = _text_value(plan.get("status"))
    if plan.get("topic_count") is not None:
        state["planned_topic_count"] = _int_value(plan.get("topic_count"))
    return {key: value for key, value in state.items() if value not in ("", None)}


def _demand_plan_amendment_candidates(value: dict[str, Any] | list[Any] | None) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        raw = value.get("plan_amendment_candidates")
        if raw is None:
            raw = value.get("candidates")
    elif isinstance(value, list):
        raw = value
    else:
        raw = []
    candidates: list[dict[str, Any]] = []
    for item in _list_value(raw):
        if not isinstance(item, dict):
            continue
        topic = _text_value(item.get("topic"))
        if not topic:
            continue
        candidates.append(
            {
                "topic": topic,
                "capability_key": _text_value(item.get("capability_key") or topic),
                "assessment": _text_value(item.get("assessment") or "demand_plan_amendment"),
                "current_sessions": _number_text(item.get("current_sessions")),
                "previous_sessions": _number_text(item.get("previous_sessions")),
                "change_pct": _number_text(item.get("change_pct")),
                "comparison_quality": _text_value(item.get("comparison_quality")),
                "suggested_filters": _string_list(item.get("suggested_filters"), limit=6),
                "why_collect": _text_value(item.get("why_collect")),
            }
        )
        if len(candidates) >= 4:
            break
    return candidates


def _demand_plan_amendment_summary(value: dict[str, Any] | list[Any] | None) -> dict[str, Any]:
    candidates = _demand_plan_amendment_candidates(value)
    if not candidates:
        return {}
    return {
        "status": "suggested",
        "candidate_count": len(candidates),
        "candidates": candidates,
    }


def _number_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return _text_value(value)
    return str(int(number)) if number.is_integer() else str(number)


def _string_list(value: Any, *, limit: int = 8) -> list[str]:
    raw = value if isinstance(value, list) else [value]
    results: list[str] = []
    seen: set[str] = set()
    for item in raw:
        text = _text_value(item)
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        results.append(text)
        if len(results) >= limit:
            break
    return results


def _demand_readiness_items(demand_readiness: dict[str, Any], *, tenant_slug: str) -> list[dict[str, Any]]:
    status = _text_value(demand_readiness.get("status"))
    if not _demand_status_blocks_action(status):
        return []
    primary = _first_action(demand_readiness.get("operator_actions"), index=0)
    secondary = _first_action(demand_readiness.get("operator_actions"), index=1)
    item: dict[str, Any] = {
        "work_item_id": f"argus-demand-readiness:{status}",
        "evidence_plane": "demand",
        "severity": "blocks_action",
        "title": _demand_readiness_title(status),
        "why_needed": _text_value(demand_readiness.get("summary"))
        or "Tenant-side demand evidence is missing, so Argus cannot promote outward movement to action.",
        "blocks": ["owner recommendations", "priority ranking", "action promotion"],
        "next_step": _demand_next_step(demand_readiness),
        "operator_surface": "Demand imports",
        "observed_state": _demand_observed_state(demand_readiness),
    }
    if primary:
        item.update(
            {
                "primary_action_label": primary["label"],
                "primary_action_href": primary["href"],
                "primary_action_method": primary["method"],
                "operator_surface": primary["surface"],
            }
        )
    else:
        item.update(
            {
                "primary_action_label": "Open demand admin",
                "primary_action_href": f"/admin?tenant={tenant_slug}#inward-demand",
                "primary_action_method": "get",
            }
        )
    if secondary:
        item.update(
            {
                "secondary_action_label": secondary["label"],
                "secondary_action_href": secondary["href"],
                "secondary_action_method": secondary["method"],
            }
        )
    return [item]


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _sanitized_empty_outputs(value: Any, *, limit: int = 8) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in _list_value(value):
        if not isinstance(item, dict):
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


def _empty_output_labels(empty_outputs: list[dict[str, str]]) -> list[str]:
    labels: list[str] = []
    for item in empty_outputs:
        company = str(item.get("company_name") or "").strip()
        family = str(item.get("surface_family") or "").strip()
        label = " ".join(part for part in (company, family) if part)
        if label:
            labels.append(label)
    return labels


def _product_surface_execution_next_step(execution: dict[str, Any]) -> str:
    labels = _empty_output_labels(_list_value(execution.get("empty_outputs")))
    if labels:
        return f"Repair or replace empty product-surface targets: {', '.join(labels[:5])}."
    return "Repair product-surface extraction and rerun the product-market chain."


def _product_surface_execution_items(dashboard: dict[str, Any], *, tenant_slug: str) -> list[dict[str, Any]]:
    run = _dict_value(dashboard.get("product_market_run"))
    raw_execution = _dict_value(run.get("product_surface_execution_summary"))
    if not raw_execution:
        return []

    execution = {
        "product_plane_status": str(raw_execution.get("product_plane_status") or ""),
        "planned": _int_value(raw_execution.get("planned")),
        "succeeded": _int_value(raw_execution.get("succeeded")),
        "empty": _int_value(raw_execution.get("empty")),
        "failed": _int_value(raw_execution.get("failed")),
        "product_row_count": _int_value(raw_execution.get("product_row_count")),
        "empty_outputs": _sanitized_empty_outputs(raw_execution.get("empty_outputs")),
    }
    status = str(execution.get("product_plane_status") or "")
    if status not in {"empty", "failed", "failed_empty"}:
        return []

    title = (
        "Product surface extraction failed"
        if status in {"failed", "failed_empty"}
        else "Product surface extraction returned no product proof"
    )
    return [
        {
            "work_item_id": f"product-surface-execution:{status}",
            "evidence_plane": "product_muscle",
            "severity": "blocks_feature_matrix",
            "title": title,
            "why_needed": (
                "Scout/product-surface execution ran, but did not extract product proof "
                "for the feature matrix."
            ),
            "blocks": ["feature comparison", "product gap scoring", "product-backed recommendations"],
            "next_step": _product_surface_execution_next_step(execution),
            "operator_surface": "Product surface repair",
            "primary_action_label": "Open product surface repair",
            "primary_action_href": f"/admin?tenant={tenant_slug}#product-surface-repair",
            "primary_action_method": "get",
            "secondary_action_label": "Open product muscle queue",
            "secondary_action_href": f"/admin?tenant={tenant_slug}#product-muscle-work-queue",
            "secondary_action_method": "get",
            "observed_state": {key: value for key, value in execution.items() if value not in (None, "", [], {})},
        }
    ]


def _top_item(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in items:
        if item.get("severity") == "blocks_action":
            return item
    for item in items:
        if item.get("severity") == "blocks_feature_matrix":
            return item
    return items[0] if items else None


def _status_for_counts(blocking_count: int, limiting_count: int, item_count: int) -> tuple[str, str]:
    if blocking_count > 0:
        return "blocked_on_evidence", "not_actionable"
    if item_count > 0 or limiting_count > 0:
        return "limited_by_evidence", "needs_operator_review"
    return "ready_for_operator_review", "actionable"


def _plural(count: int, singular: str, plural: str) -> str:
    return singular if count == 1 else plural


def _summary(*, blocking_count: int, limiting_count: int) -> str:
    if blocking_count > 0:
        noun = _plural(blocking_count, "evidence gap", "evidence gaps")
        return f"Argus is blocked by {blocking_count} {noun} before it can promote this run to action."
    if limiting_count > 0:
        noun = _plural(limiting_count, "evidence gap", "evidence gaps")
        return f"Argus has {limiting_count} {noun} limiting confidence before this run is fully trusted."
    return "Argus has no open evidence work items for this run."


def _next_operator_action(item: dict[str, Any] | None) -> str:
    if item:
        return str(item.get("next_step") or "Open the relevant admin surface and repair the evidence gap.")
    return "Review Argus recommendations and challenge any weak claim."


def _top_blocker(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    return {
        "work_item_id": item.get("work_item_id"),
        "evidence_plane": item.get("evidence_plane") or "product_muscle",
        "severity": item.get("severity"),
        "title": item.get("title"),
        "why_needed": item.get("why_needed"),
        "blocks": item.get("blocks") or [],
        "observed_state": item.get("observed_state") or {},
        "company_name": item.get("company_name"),
    }


def _primary_command(
    item: dict[str, Any] | None,
    *,
    demand_readiness: dict[str, Any],
    tenant_slug: str,
) -> dict[str, Any] | None:
    demand_command = _demand_readiness_primary_command(item, demand_readiness)
    if demand_command:
        return demand_command
    return _command_from_item(item, primary=True, tenant_slug=tenant_slug)


def _demand_readiness_primary_command(
    item: dict[str, Any] | None,
    demand_readiness: dict[str, Any],
) -> dict[str, Any] | None:
    if not item or item.get("evidence_plane") != "demand":
        return None
    actions = demand_readiness.get("operator_actions")
    if not isinstance(actions, list):
        return None
    for action in actions:
        if not isinstance(action, dict):
            continue
        label = str(action.get("label") or "").strip()
        href = str(action.get("href") or "").strip()
        surface = str(action.get("surface") or "").strip()
        if not label or not href or not surface:
            continue
        return {
            "label": label,
            "href": href,
            "method": str(action.get("method") or "get").lower(),
            "surface": surface,
        }
    return None


def _command_from_item(item: dict[str, Any] | None, *, primary: bool, tenant_slug: str) -> dict[str, Any] | None:
    if not item:
        if primary:
            return {
                "label": "Open Argus command",
                "href": f"/admin?tenant={tenant_slug}#argus-command",
                "method": "get",
                "surface": "Argus command",
            }
        return None

    prefix = "primary" if primary else "secondary"
    label = item.get(f"{prefix}_action_label")
    href = item.get(f"{prefix}_action_href")
    method = item.get(f"{prefix}_action_method")
    if not label or not href:
        return None
    return {
        "label": label,
        "href": href,
        "method": method or "get",
        "surface": item.get("operator_surface"),
    }


def _route_kind(href: Any) -> str:
    value = str(href or "")
    if value.startswith("/api/"):
        return "api"
    if value.startswith("/admin"):
        return "admin"
    if value.startswith("http://") or value.startswith("https://"):
        return "external"
    return "unknown"


def _demand_plan_template_summary(path: str | None) -> dict[str, str]:
    if not path:
        return {}
    return {
        "status": "generated",
        "format": "csv",
        "filename": Path(str(path)).name,
    }


def _operator_commands(actions: Any) -> list[dict[str, str]]:
    commands: list[dict[str, str]] = []
    if not isinstance(actions, list):
        return commands
    for action in actions:
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


def _operator_brief(
    *,
    top_item: dict[str, Any] | None,
    blocking_count: int,
    limiting_count: int,
    dashboard: dict[str, Any],
) -> list[str]:
    primary_action = _dashboard_primary_action(dashboard)
    if not top_item:
        brief = ["Argus has no evidence blockers. Review the recommendation set and challenge weak claims."]
        if primary_action:
            brief.append(f"Dashboard action: {primary_action}")
        return brief

    lines = [
        (
            "Argus withheld action because "
            f"{top_item.get('title', 'an evidence gap')} is open on the "
            f"{top_item.get('evidence_plane', 'unknown')} plane."
        ),
        str(top_item.get("why_needed") or "The run is missing evidence needed for a trusted recommendation."),
        f"Next step: {_next_operator_action(top_item)}",
    ]
    if blocking_count > 1 or limiting_count > 0:
        lines.append(f"Open queue: {blocking_count} blocking, {limiting_count} limiting.")
    if primary_action:
        lines.append(f"Dashboard action under review: {primary_action}")
    return lines


def _dashboard_primary_action(dashboard: dict[str, Any]) -> str | None:
    spine = dashboard.get("spine")
    if isinstance(spine, dict) and spine.get("primary_action"):
        return str(spine["primary_action"])
    primary_action = dashboard.get("primary_action")
    if primary_action:
        return str(primary_action)
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build an Argus operator handoff from the evidence work queue.")
    parser.add_argument("--tenant", required=True, help="Tenant slug, for example algolia.")
    parser.add_argument("--work-queue", required=True, type=Path, help="argus-evidence-work-queue.json path.")
    parser.add_argument("--product-muscle-queue", type=Path, help="argus-product-muscle-work-queue.json path.")
    parser.add_argument("--demand-readiness", type=Path, help="argus-demand-readiness.json path.")
    parser.add_argument("--demand-plan-template", type=Path, help="argus-demand-plan-template.csv path.")
    parser.add_argument("--demand-plan-amendments", type=Path, help="planned demand amendment report JSON path.")
    parser.add_argument("--dashboard", type=Path, help="argus-dashboard.json path.")
    parser.add_argument("--output", type=Path, help="Optional JSON artifact path. Prints to stdout when omitted.")
    args = parser.parse_args(argv)

    work_queue = load_json(args.work_queue)
    product_muscle_queue = load_json(args.product_muscle_queue) if args.product_muscle_queue else {}
    demand_readiness = load_json(args.demand_readiness) if args.demand_readiness else {}
    demand_plan_amendments = load_json(args.demand_plan_amendments) if args.demand_plan_amendments else {}
    dashboard = load_json(args.dashboard) if args.dashboard and args.dashboard.exists() else {}
    payload = build_operator_handoff_payload(
        tenant_slug=args.tenant,
        work_queue=work_queue,
        product_muscle_queue=product_muscle_queue,
        demand_readiness=demand_readiness,
        demand_plan_template_path=str(args.demand_plan_template) if args.demand_plan_template else None,
        demand_plan_amendments=demand_plan_amendments,
        dashboard=dashboard,
        work_queue_path=str(args.work_queue),
        product_muscle_queue_path=str(args.product_muscle_queue) if args.product_muscle_queue else None,
        demand_readiness_path=str(args.demand_readiness) if args.demand_readiness else None,
        demand_plan_amendments_path=str(args.demand_plan_amendments) if args.demand_plan_amendments else None,
        dashboard_path=str(args.dashboard) if args.dashboard else None,
    )

    if args.output:
        write_payload(payload, args.output)
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
