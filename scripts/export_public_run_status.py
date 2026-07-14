#!/usr/bin/env python3
"""Export a public-safe status for the latest Hermes/Argus run.

The internal data-plane manifest can contain local artifact paths because it is
also a runbook artifact. This public status deliberately keeps only the fields a
dashboard, user, or external monitor needs to understand why the latest run did
or did not publish.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists() or path.stat().st_size == 0:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _counts(value: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for key, raw in _dict_value(value).items():
        try:
            counts[str(key)] = int(raw or 0)
        except (TypeError, ValueError):
            continue
    return counts


def _public_empty_outputs(value: Any, *, limit: int = 8) -> list[dict[str, str]]:
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


def _source_coverage(dashboard: Mapping[str, Any]) -> dict[str, int]:
    health_value = dashboard.get("source_health")
    if isinstance(health_value, list):
        active_rows = [row for row in health_value if isinstance(row, dict) and row.get("status") == "active"]
        checked_rows = [row for row in active_rows if row.get("checked_at")]
        failed_rows = [
            row
            for row in checked_rows
            if str(row.get("latest_event_type") or "").lower() not in {"", "ok", "success"}
        ]
        return {
            "active_source_count": len(active_rows),
            "checked_source_count": len(checked_rows),
            "failed_source_count": len(failed_rows),
        }

    health = _dict_value(health_value)
    return _counts(
        {
            "active_source_count": health.get("active_source_count"),
            "checked_source_count": health.get("checked_source_count"),
            "failed_source_count": health.get("failed_source_count"),
        }
    )


def _product_market_run(dashboard: Mapping[str, Any]) -> dict[str, Any]:
    run = _dict_value(dashboard.get("product_market_run"))
    fields = (
        "status",
        "product_event_count",
        "conversation_theme_count",
        "demand_signal_count",
        "pattern_count",
        "recommendation_count",
    )
    payload: dict[str, Any] = {}
    for field in fields:
        value = run.get(field)
        if value is None:
            continue
        if field.endswith("_count"):
            try:
                payload[field] = int(value or 0)
            except (TypeError, ValueError):
                continue
        else:
            payload[field] = value
    return payload


def _public_demand_plan_topics(topics: Any, *, limit: int = 5) -> list[dict[str, Any]]:
    public: list[dict[str, Any]] = []
    for topic in _list_value(topics):
        if not isinstance(topic, dict):
            continue
        row: dict[str, Any] = {}
        for field in ("topic", "capability_key", "assessment"):
            value = topic.get(field)
            if value not in (None, "", []):
                row[field] = value
        competitors = _list_value(topic.get("related_competitors"))
        if competitors:
            row["related_competitors"] = [str(item) for item in competitors[:5] if str(item).strip()]
        filters = _list_value(topic.get("suggested_filter_terms"))
        if filters:
            row["suggested_filter_terms"] = [str(item) for item in filters[:8] if str(item).strip()]
        evidence_urls = _list_value(topic.get("evidence_urls"))
        if topic.get("evidence_url_count") is not None:
            try:
                row["evidence_url_count"] = int(topic.get("evidence_url_count") or 0)
            except (TypeError, ValueError):
                pass
        elif evidence_urls:
            row["evidence_url_count"] = len(evidence_urls)
        if row:
            public.append(row)
        if len(public) >= limit:
            break
    return public


def _public_demand_collection_plan(plane: Mapping[str, Any]) -> dict[str, Any]:
    details = _dict_value(plane.get("details"))
    plan = _dict_value(details.get("demand_collection_plan"))
    if not plan:
        return {}
    public: dict[str, Any] = {}
    for field in ("status", "topic_count", "source_dashboard_field"):
        value = plan.get(field)
        if value not in (None, "", []):
            public[field] = value
    topics = _public_demand_plan_topics(plan.get("topics"))
    if topics:
        public["topics"] = topics
    return public


def _public_demand_plan_template(plane: Mapping[str, Any]) -> dict[str, Any]:
    details = _dict_value(plane.get("details"))
    template = _dict_value(details.get("demand_plan_template"))
    if not template:
        return {}
    public: dict[str, Any] = {}
    for field in ("status", "format", "filename"):
        value = template.get(field)
        if value not in (None, "", []):
            public[field] = value
    return public


def _public_product_surface_execution(plane: Mapping[str, Any]) -> dict[str, Any]:
    details = _dict_value(plane.get("details"))
    execution = _dict_value(details.get("product_surface_execution"))
    if not execution:
        return {}
    public: dict[str, Any] = {}
    for field in (
        "product_plane_status",
        "planned",
        "succeeded",
        "empty",
        "failed",
        "timed_out",
        "not_started",
        "batch_timed_out",
        "batch_timeout_seconds",
        "product_row_count",
    ):
        value = execution.get(field)
        if value not in (None, "", []):
            public[field] = value
    empty_outputs = _public_empty_outputs(execution.get("empty_outputs"))
    if empty_outputs:
        public["empty_outputs"] = empty_outputs
    for field in ("company_row_counts", "surface_family_row_counts"):
        if isinstance(execution.get(field), dict):
            public[field] = _counts(execution.get(field))
    return public


def _public_product_muscle_work_queue(plane: Mapping[str, Any], *, limit: int = 8) -> dict[str, Any]:
    details = _dict_value(plane.get("details"))
    queue = _dict_value(details.get("product_muscle_work_queue"))
    if not queue:
        return {}
    public: dict[str, Any] = {}
    for field in ("status", "work_item_count", "blocking_count", "limiting_count"):
        value = queue.get(field)
        if value in (None, "", []):
            continue
        if field.endswith("_count"):
            try:
                public[field] = int(value or 0)
            except (TypeError, ValueError):
                continue
        else:
            public[field] = value
    items: list[dict[str, Any]] = []
    for item in _list_value(queue.get("items")):
        if not isinstance(item, dict):
            continue
        row: dict[str, Any] = {}
        for field in (
            "work_item_id",
            "severity",
            "title",
            "next_step",
            "company_name",
            "surface_family",
            "operator_surface",
        ):
            value = item.get(field)
            if value not in (None, "", []):
                row[field] = str(value)
        commands = _public_operator_commands(item.get("operator_commands"))
        if commands:
            row["operator_commands"] = commands
        if row:
            items.append(row)
        if len(items) >= limit:
            break
    if items:
        public["items"] = items
    return public


def _public_plane(plane: Any) -> dict[str, Any]:
    value = _dict_value(plane)
    payload: dict[str, Any] = {
        "status": value.get("status"),
        "summary": value.get("summary"),
        "blocks_action": bool(value.get("blocks_action")),
        "counts": _counts(value.get("counts")),
    }
    if value.get("next_hermes_action"):
        payload["next_hermes_action"] = value.get("next_hermes_action")
    demand_plan = _public_demand_collection_plan(value)
    if demand_plan:
        payload["demand_collection_plan"] = demand_plan
    demand_plan_template = _public_demand_plan_template(value)
    if demand_plan_template:
        payload["demand_plan_template"] = demand_plan_template
    product_surface_execution = _public_product_surface_execution(value)
    if product_surface_execution:
        payload["product_surface_execution"] = product_surface_execution
    product_muscle_work_queue = _public_product_muscle_work_queue(value)
    if product_muscle_work_queue:
        payload["product_muscle_work_queue"] = product_muscle_work_queue
    return {key: item for key, item in payload.items() if item not in (None, "", {})}


def _public_planes(manifest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    planes: dict[str, dict[str, Any]] = {}
    for key, plane in _dict_value(manifest.get("planes")).items():
        public_plane = _public_plane(plane)
        if public_plane:
            planes[str(key)] = public_plane
    return planes


def _public_operator_commands(commands: Any) -> list[dict[str, str]]:
    public: list[dict[str, str]] = []
    for command in _list_value(commands):
        if not isinstance(command, dict):
            continue
        row = {
            "label": str(command.get("label") or "").strip(),
            "method": str(command.get("method") or "get").strip().lower(),
            "surface": str(command.get("surface") or "").strip(),
            "route_kind": str(command.get("route_kind") or "unknown").strip(),
        }
        if row["label"] and row["surface"]:
            public.append(row)
    return public


def _public_next_monitoring_actions(actions: Any, *, limit: int = 8) -> list[dict[str, Any]]:
    public: list[dict[str, Any]] = []
    for action in _list_value(actions):
        if not isinstance(action, dict):
            continue
        row: dict[str, Any] = {}
        for field in ("owner", "plane", "priority", "instruction", "reason"):
            value = str(action.get(field) or "").strip()
            if value:
                row[field] = value
        if any(field not in row for field in ("owner", "plane", "priority", "instruction", "reason")):
            continue
        source_families = [
            str(source_family).strip()
            for source_family in _list_value(action.get("source_families"))
            if str(source_family).strip()
        ]
        if source_families:
            row["source_families"] = source_families[:8]
        evidence_urls = [
            str(url).strip()
            for url in _list_value(action.get("evidence_urls"))
            if str(url).strip()
        ]
        row["evidence_url_count"] = len(evidence_urls)
        public.append(row)
        if len(public) >= limit:
            break
    return public


def _public_blockers(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for blocker in _list_value(manifest.get("blockers")):
        if not isinstance(blocker, dict):
            continue
        row: dict[str, Any] = {}
        for field in (
            "plane",
            "severity",
            "title",
            "next_step",
            "work_item_id",
            "demand_source_contract_status",
        ):
            value = blocker.get(field)
            if value not in (None, "", []):
                row[field] = value
        if blocker.get("planned_topic_count") not in (None, "", []):
            try:
                row["planned_topic_count"] = int(blocker.get("planned_topic_count") or 0)
            except (TypeError, ValueError):
                pass
        planned_topics = _public_demand_plan_topics(blocker.get("planned_topics"))
        if planned_topics:
            row["planned_topics"] = planned_topics
        commands = _public_operator_commands(blocker.get("operator_commands"))
        if commands:
            row["operator_commands"] = commands
        empty_outputs = _public_empty_outputs(blocker.get("empty_outputs"))
        if empty_outputs:
            row["empty_outputs"] = empty_outputs
        if row:
            blockers.append(row)
    return blockers


def build_public_run_status_payload(
    *,
    tenant_slug: str,
    manifest: dict[str, Any],
    dashboard: dict[str, Any] | None = None,
    publish_status: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    dashboard = dashboard or {}
    status = str(manifest.get("status") or "unknown")
    next_monitoring_actions = _public_next_monitoring_actions(
        manifest.get("next_monitoring_actions")
    )
    planes = _public_planes(manifest)
    payload = {
        "schema_version": 1,
        "tenant_slug": tenant_slug,
        "generated_at": generated_at or _now(),
        "manifest_generated_at": manifest.get("generated_at"),
        "dashboard_generated_at": dashboard.get("generated_at") or manifest.get("dashboard_generated_at"),
        "publish_status": publish_status,
        "status": status,
        "next_hermes_action": manifest.get("next_hermes_action"),
        "public_dashboard_updated": publish_status == "published",
        "source_coverage": _source_coverage(dashboard),
        "product_market_run": _product_market_run(dashboard),
        "planes": planes,
        "blockers": _public_blockers(manifest),
        "safety": {
            "artifact_paths_redacted": True,
            "secret_values_included": False,
            "public_safe": True,
        },
    }
    demand_plane = planes.get("audience_demand") or {}
    for key in ("demand_collection_plan", "demand_plan_template"):
        value = demand_plane.get(key)
        if value not in (None, "", {}, []):
            payload[key] = value
    if next_monitoring_actions:
        payload["next_monitoring_actions"] = next_monitoring_actions
    return {key: value for key, value in payload.items() if value not in (None, "", {})}


def write_payload(payload: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(f"{json.dumps(payload, indent=2, sort_keys=True)}\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export public-safe Argus run status.")
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--dashboard", type=Path)
    parser.add_argument("--publish-status", choices=("blocked", "published"), required=True)
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = build_public_run_status_payload(
        tenant_slug=args.tenant,
        manifest=_load_json(args.manifest),
        dashboard=_load_json(args.dashboard),
        publish_status=args.publish_status,
    )
    if args.output:
        write_payload(payload, args.output)
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
