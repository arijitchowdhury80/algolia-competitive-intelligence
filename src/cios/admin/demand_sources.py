"""Tenant demand-source contract helpers for the Argus inward-demand plane."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: Any, *, limit: int = 8) -> list[str]:
    candidates = [value] if isinstance(value, str) else _list_value(value)
    seen: set[str] = set()
    out: list[str] = []
    for item in candidates:
        text = " ".join(str(item or "").split())
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def demand_source_contract_path(*, work_root: Path, tenant_slug: str) -> Path:
    return work_root / tenant_slug / "demand-source-contract.json"


def _demand_row_count(demand_plane: Mapping[str, Any]) -> int:
    return _int_value(demand_plane.get("looker_normalized_row_count")) + _int_value(
        demand_plane.get("demand_signal_count")
    )


def _manual_source(manual_import: Mapping[str, Any]) -> dict[str, Any]:
    ready_count = _int_value(manual_import.get("ready_preview_count"))
    error_count = _int_value(manual_import.get("error_preview_count"))
    inbox_count = _int_value(manual_import.get("inbox_file_count"))
    if error_count > 0:
        status = "blocked_bad_export"
    elif ready_count > 0:
        status = "queued_ready"
    elif inbox_count > 0:
        status = "queued_unusable"
    else:
        status = "waiting_for_upload"
    return {
        "source_id": "manual_looker_export",
        "source_family": "ga_looker_manual_export",
        "label": "Manual GA / Looker export",
        "status": status,
        "ready": status == "queued_ready",
        "landing_zone": manual_import.get("drop_folder"),
        "manifest_path": manual_import.get("manifest_path"),
        "cadence": "operator_uploaded_or_daily_when_queued",
        "owner": "operator",
        "accepted_suffixes": list(manual_import.get("accepted_suffixes") or []),
        "template_fields": list(manual_import.get("template_fields") or []),
        "inbox_file_count": inbox_count,
        "ready_preview_count": ready_count,
        "error_preview_count": error_count,
        "normalized_preview_row_count": _int_value(manual_import.get("normalized_preview_row_count")),
    }


def _ga4_source(ga4_connector: Mapping[str, Any]) -> dict[str, Any]:
    ready = bool(ga4_connector.get("ready"))
    enabled = bool(ga4_connector.get("enabled"))
    status = "ready" if ready else ("not_ready" if enabled else "disabled")
    return {
        "source_id": "ga4_connector",
        "source_family": "ga4_api_export",
        "label": "GA4 API export",
        "status": status,
        "ready": ready,
        "cadence": "daily_when_configured",
        "owner": "Hermes",
        "setup_required": list(ga4_connector.get("setup_required") or []),
        "missing_required": list(ga4_connector.get("missing_required") or []),
        "current_window": ga4_connector.get("current_window"),
        "previous_window": ga4_connector.get("previous_window"),
        "metric": ga4_connector.get("metric"),
        "topic_dimension": ga4_connector.get("topic_dimension"),
        "url_dimension": ga4_connector.get("url_dimension"),
        "output_name": ga4_connector.get("output_name"),
    }


def _contract_status(*, demand_plane: Mapping[str, Any], sources: list[dict[str, Any]]) -> tuple[str, str]:
    if demand_plane.get("status") in {"processed", "degraded"} and _demand_row_count(demand_plane) > 0:
        return "processed_current_demand", "Current tenant demand has already been processed for this run."
    if any(bool(source.get("ready")) for source in sources):
        return "ready", "At least one inward-demand source is ready for Hermes."
    if any(source.get("status") == "blocked_bad_export" for source in sources):
        return "blocked_bad_manual_export", "A queued manual demand export exists, but it cannot be normalized."
    ga4 = next((source for source in sources if source.get("source_id") == "ga4_connector"), {})
    if ga4.get("status") == "not_ready":
        return "blocked_missing_configuration", "GA4 is enabled, but required connector configuration is missing."
    return "blocked_no_ready_source", "No configured inward-demand source is ready for Hermes."


def _coverage_summary(coverage: Mapping[str, Any]) -> dict[str, Any]:
    if not coverage:
        return {}
    return {
        "status": coverage.get("status"),
        "planned_topic_count": _int_value(coverage.get("planned_topic_count")),
        "covered_topic_count": _int_value(coverage.get("covered_topic_count")),
        "missing_topic_count": _int_value(coverage.get("missing_topic_count")),
        "off_plan_topic_count": _int_value(coverage.get("off_plan_topic_count")),
        "coverage_ratio": coverage.get("coverage_ratio", 0),
    }


def _demand_topic_summary(topic: Mapping[str, Any]) -> dict[str, Any]:
    evidence_urls = _string_list(topic.get("evidence_urls"), limit=20)
    return {
        "topic": " ".join(str(topic.get("topic") or "").split()),
        "capability_key": " ".join(str(topic.get("capability_key") or "").split()),
        "assessment": " ".join(str(topic.get("assessment") or "").split()),
        "related_competitors": _string_list(topic.get("related_competitors")),
        "suggested_filter_terms": _string_list(topic.get("suggested_filter_terms")),
        "evidence_url_count": len(evidence_urls),
    }


def _demand_plan_summary(demand_collection_plan: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(demand_collection_plan, Mapping):
        return {
            "status": "not_supplied",
            "summary": "No Argus demand collection plan was supplied with this source contract.",
            "source_dashboard_field": None,
            "topic_count": 0,
            "template": {
                "format": "csv",
                "filename": "argus-demand-plan-template.csv",
            },
            "top_topics": [],
            "coverage": {},
        }
    topics = [
        _demand_topic_summary(topic)
        for topic in _list_value(demand_collection_plan.get("topics"))
        if isinstance(topic, Mapping)
    ]
    return {
        "status": demand_collection_plan.get("status"),
        "summary": demand_collection_plan.get("summary"),
        "source_dashboard_field": demand_collection_plan.get("source_dashboard_field"),
        "topic_count": _int_value(demand_collection_plan.get("topic_count")),
        "template": {
            "format": "csv",
            "filename": "argus-demand-plan-template.csv",
        },
        "top_topics": topics[:8],
        "coverage": _coverage_summary(
            demand_collection_plan.get("coverage")
            if isinstance(demand_collection_plan.get("coverage"), Mapping)
            else {}
        ),
    }


def build_demand_source_contract(
    *,
    tenant_slug: str,
    work_root: Path,
    demand_plane: Mapping[str, Any],
    manual_import: Mapping[str, Any],
    ga4_connector: Mapping[str, Any],
    generated_at: str | None = None,
    demand_collection_plan: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    sources = [_manual_source(manual_import), _ga4_source(ga4_connector)]
    status, summary = _contract_status(demand_plane=demand_plane, sources=sources)
    ready_source_count = sum(1 for source in sources if source.get("ready"))
    return {
        "schema_version": 1,
        "tenant_slug": tenant_slug,
        "generated_at": generated_at,
        "status": status,
        "summary": summary,
        "contract_path": str(demand_source_contract_path(work_root=work_root, tenant_slug=tenant_slug)),
        "source_count": len(sources),
        "ready_source_count": ready_source_count,
        "blocking": status.startswith("blocked"),
        "demand_plan": _demand_plan_summary(demand_collection_plan),
        "sources": sources,
        "storage": {
            "processed_demand_table": "demand_signals",
            "manual_landing_zone": manual_import.get("drop_folder"),
            "manual_manifest_path": manual_import.get("manifest_path"),
            "history_root": str(work_root / tenant_slug / "demand-intake-runs"),
        },
        "safety": {
            "secret_values_included": False,
            "credentials_reported_as_booleans_only": True,
        },
    }


def write_demand_source_contract(contract: Mapping[str, Any]) -> Path:
    path = Path(str(contract["contract_path"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(contract), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def demand_source_ids(contract: Mapping[str, Any]) -> list[str]:
    return [
        str(source.get("source_id"))
        for source in _list_value(contract.get("sources"))
        if isinstance(source, dict) and source.get("source_id")
    ]


__all__ = [
    "build_demand_source_contract",
    "demand_source_contract_path",
    "demand_source_ids",
    "write_demand_source_contract",
]
