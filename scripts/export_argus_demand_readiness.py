#!/usr/bin/env python3
"""Export the Hermes-facing inward-demand readiness contract.

Argus cannot make product-market recommendations from outward evidence alone.
This artifact tells Hermes whether the tenant-side demand plane can run, what
manual export is queued, what GA4 configuration is missing, and the next safe
operator action. It deliberately emits booleans and field names, never secret
values.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cios.admin.demand_imports import (
    DEMAND_IMPORT_TEMPLATE_FIELDS,
    DemandImportStore,
    Ga4DemandExportControl,
)
from cios.admin.demand_sources import build_demand_source_contract, write_demand_source_contract
from cios.intelligence.capabilities import capability_key as canonical_capability_key


ASSESSMENT_PRIORITY = {
    "own_product_gap": 1,
    "own_narrative_gap": 2,
    "competitive_pressure": 3,
    "demand_without_product_proof": 4,
    "conversation_without_product_proof": 5,
    "competitive_parity": 6,
    "watch": 7,
}
MAX_COLLECTION_TOPICS = 12


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists() or path.stat().st_size == 0:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _dashboard_path(explicit: Path | None, *, app_dir: Path) -> Path | None:
    if explicit is not None:
        return explicit
    default = app_dir / "out" / "argus-dashboard.json"
    return default if default.exists() else None


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _truthy(value: Any) -> bool:
    return str(value or "").strip().casefold() in {"1", "true", "yes", "on"}


def _number_value(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _text_value(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _capability_key(value: Any) -> str:
    return canonical_capability_key(_text_value(value))


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: Any, *, limit: int = 12) -> list[str]:
    if isinstance(value, str):
        candidates: list[Any] = [value]
    else:
        candidates = _list_value(value)
    seen: set[str] = set()
    results: list[str] = []
    for item in candidates:
        text = _text_value(item)
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        results.append(text)
        if len(results) >= limit:
            break
    return results


def _dashboard_run(dashboard: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(dashboard, dict):
        return {}
    run = dashboard.get("product_market_run")
    return run if isinstance(run, dict) else {}


def _demand_plane_summary(dashboard: dict[str, Any] | None) -> dict[str, Any]:
    run = _dashboard_run(dashboard)
    return {
        "status": str(run.get("demand_plane_status") or "not_recorded"),
        "looker_discovered_count": _int_value(run.get("looker_discovered_count")),
        "looker_ready_count": _int_value(run.get("looker_ready_count")),
        "looker_error_count": _int_value(run.get("looker_error_count")),
        "looker_normalized_row_count": _int_value(run.get("looker_normalized_row_count")),
        "demand_signal_count": _int_value(run.get("demand_signal_count")),
    }


def _product_feature_comparison_rows(dashboard: dict[str, Any] | None) -> list[dict[str, Any]]:
    run = _dashboard_run(dashboard)
    comparison = run.get("product_feature_comparison_read")
    if not isinstance(comparison, dict):
        brief = run.get("intelligence_brief")
        if isinstance(brief, dict):
            comparison = brief.get("product_feature_comparison")
    if not isinstance(comparison, dict):
        return []
    return [row for row in _list_value(comparison.get("rows")) if isinstance(row, dict)]


def _evidence_urls_from_refs(value: Any, *, limit: int = 8) -> list[str]:
    refs = value if isinstance(value, list) else []
    urls: list[str] = []
    for ref in refs:
        if isinstance(ref, str):
            urls.append(ref)
        elif isinstance(ref, dict):
            urls.append(ref.get("source_url") or ref.get("url") or ref.get("href") or "")
    return _string_list(urls, limit=limit)


def _product_market_pattern_rows(
    dashboard: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], str]:
    run = _dashboard_run(dashboard)
    candidates = run.get("pattern_observations")
    source_field = "product_market_run.pattern_observations"
    if not isinstance(candidates, list) and isinstance(dashboard, dict):
        candidates = dashboard.get("product_market_patterns")
        source_field = "product_market_patterns"
    if not isinstance(candidates, list):
        brief = run.get("intelligence_brief")
        if isinstance(brief, dict):
            candidates = brief.get("patterns")
            source_field = "product_market_run.intelligence_brief.patterns"
    rows = [row for row in _list_value(candidates) if isinstance(row, dict)]
    return rows, source_field


def _collection_filter_terms(row: dict[str, Any]) -> list[str]:
    terms: list[Any] = [
        row.get("capability"),
        row.get("capability_key"),
    ]
    capability_key = _text_value(row.get("capability_key"))
    for token in re.split(r"[^A-Za-z0-9]+", capability_key):
        if len(token) >= 4:
            terms.append(token)
    return _string_list(terms, limit=8)


def _decision_action_text(dashboard: dict[str, Any] | None) -> str:
    run = _dashboard_run(dashboard)
    decision_read = run.get("decision_read")
    if not isinstance(decision_read, dict):
        brief = run.get("intelligence_brief")
        if isinstance(brief, dict):
            decision_read = brief.get("decision_read")
    if not isinstance(decision_read, dict):
        return ""
    for action in _list_value(decision_read.get("tactical_actions")):
        if not isinstance(action, dict):
            continue
        text = _text_value(action.get("action") or action.get("recommendation"))
        if text:
            return text
    return _text_value(decision_read.get("priority_reason"))


def _collection_topic(row: dict[str, Any], *, rank: int) -> dict[str, Any] | None:
    capability = _text_value(row.get("capability") or row.get("capability_key"))
    capability_key = _text_value(row.get("capability_key") or capability).casefold()
    if not capability or not capability_key:
        return None
    assessment = _text_value(row.get("assessment") or "watch")
    related_competitors = _string_list(
        _string_list(row.get("competitors_with_product_proof"))
        + _string_list(row.get("competitors_with_conversation")),
        limit=8,
    )
    why_collect = _text_value(row.get("recommended_action")) or (
        f"Collect tenant demand for {capability} before Argus promotes outward market movement to action."
    )
    return {
        "rank": rank,
        "priority": ASSESSMENT_PRIORITY.get(assessment, 99),
        "topic": capability,
        "capability_key": capability_key,
        "assessment": assessment,
        "why_collect": why_collect,
        "suggested_filter_terms": _collection_filter_terms(row),
        "related_competitors": related_competitors,
        "evidence_urls": _string_list(row.get("evidence_urls"), limit=8),
    }


def _pattern_collection_topic(
    row: dict[str, Any],
    *,
    rank: int,
    dashboard: dict[str, Any] | None,
) -> dict[str, Any] | None:
    capability = _text_value(
        row.get("capability")
        or row.get("capability_text")
        or row.get("theme")
        or row.get("capability_key")
    )
    capability_key = _text_value(row.get("capability_key") or capability).casefold()
    if not capability or not capability_key:
        return None
    assessment = _text_value(row.get("assessment") or row.get("pattern_type") or "watch")
    action_text = _decision_action_text(dashboard)
    why_collect = action_text or _text_value(row.get("summary")) or (
        f"Collect tenant demand for {capability} before Argus promotes this observed market pattern."
    )
    evidence_urls = _string_list(row.get("evidence_urls"), limit=8)
    if not evidence_urls:
        evidence_urls = _evidence_urls_from_refs(row.get("evidence_refs"), limit=8)
    return {
        "rank": rank,
        "priority": ASSESSMENT_PRIORITY.get(assessment, 99),
        "topic": capability,
        "capability_key": capability_key,
        "assessment": assessment,
        "why_collect": why_collect,
        "suggested_filter_terms": _collection_filter_terms(
            {"capability": capability, "capability_key": capability_key}
        ),
        "related_competitors": _string_list(row.get("involved_companies"), limit=8),
        "evidence_urls": evidence_urls,
    }


def _collection_topics_from_feature_rows(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    ranked_rows = sorted(
        enumerate(rows),
        key=lambda item: (
            ASSESSMENT_PRIORITY.get(_text_value(item[1].get("assessment") or "watch"), 99),
            item[0],
        ),
    )
    topics: list[dict[str, Any]] = []
    for _, row in ranked_rows:
        topic = _collection_topic(row, rank=len(topics) + 1)
        if topic:
            topics.append(topic)
        if len(topics) >= MAX_COLLECTION_TOPICS:
            break
    return topics


def _collection_topics_from_patterns(
    *,
    rows: list[dict[str, Any]],
    dashboard: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    ranked_rows = sorted(
        enumerate(rows),
        key=lambda item: (
            ASSESSMENT_PRIORITY.get(
                _text_value(item[1].get("assessment") or item[1].get("pattern_type") or "watch"),
                99,
            ),
            item[0],
        ),
    )
    topics: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for _, row in ranked_rows:
        topic = _pattern_collection_topic(row, rank=len(topics) + 1, dashboard=dashboard)
        if not topic:
            continue
        key = _capability_key(topic.get("capability_key") or topic.get("topic"))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        topics.append(topic)
        if len(topics) >= MAX_COLLECTION_TOPICS:
            break
    return topics


def _collection_topics_with_source(
    dashboard: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], str]:
    rows = _product_feature_comparison_rows(dashboard)
    topics = _collection_topics_from_feature_rows(rows)
    if topics:
        return topics, "product_market_run.product_feature_comparison_read.rows"
    pattern_rows, source_field = _product_market_pattern_rows(dashboard)
    topics = _collection_topics_from_patterns(rows=pattern_rows, dashboard=dashboard)
    if topics:
        return topics, source_field
    return [], "product_market_run.product_feature_comparison_read.rows"


def _demand_read_topics(dashboard: dict[str, Any] | None) -> list[dict[str, Any]]:
    run = _dashboard_run(dashboard)
    brief = run.get("intelligence_brief")
    if not isinstance(brief, dict):
        return []
    demand_read = brief.get("demand_read")
    if not isinstance(demand_read, dict):
        return []
    return [topic for topic in _list_value(demand_read.get("top_topics")) if isinstance(topic, dict)]


def _actual_demand_topic(topic: dict[str, Any]) -> dict[str, Any] | None:
    label = _text_value(topic.get("topic") or topic.get("capability_key"))
    key = _capability_key(topic.get("capability_key") or label)
    if not key:
        return None
    return {
        "topic": label or key,
        "capability_key": key,
        "value": topic.get("value"),
        "change_pct": topic.get("change_pct"),
        "source_files": _string_list(topic.get("source_files"), limit=8),
        "source_row_numbers": [
            number
            for number in _list_value(topic.get("source_row_numbers"))
            if isinstance(number, int) or (isinstance(number, str) and number.isdigit())
        ][:8],
        "evidence_urls": _string_list(topic.get("evidence_urls"), limit=8),
    }


def _demand_plan_coverage(
    *,
    planned_topics: list[dict[str, Any]],
    demand_plane: dict[str, Any],
    dashboard: dict[str, Any] | None,
) -> dict[str, Any]:
    planned_by_key = {
        _capability_key(topic.get("capability_key") or topic.get("topic")): topic
        for topic in planned_topics
        if _capability_key(topic.get("capability_key") or topic.get("topic"))
    }
    actual_by_key: dict[str, dict[str, Any]] = {}
    for raw_topic in _demand_read_topics(dashboard):
        actual = _actual_demand_topic(raw_topic)
        if not actual:
            continue
        actual_by_key.setdefault(actual["capability_key"], actual)

    planned_keys = set(planned_by_key)
    actual_keys = set(actual_by_key)
    covered_keys = planned_keys & actual_keys
    missing_keys = planned_keys - actual_keys
    off_plan_keys = actual_keys - planned_keys
    planned_count = len(planned_keys)
    covered_count = len(covered_keys)
    demand_rows = _int_value(demand_plane.get("looker_normalized_row_count")) + _int_value(
        demand_plane.get("demand_signal_count")
    )

    if planned_count == 0:
        status = "no_planned_topics"
    elif demand_rows <= 0:
        status = "not_evaluated"
    elif not actual_keys:
        status = "unmapped_demand"
    elif covered_count == planned_count:
        status = "covered"
    elif covered_count > 0:
        status = "partial_coverage"
    else:
        status = "off_plan"

    return {
        "status": status,
        "planned_topic_count": planned_count,
        "covered_topic_count": covered_count,
        "missing_topic_count": len(missing_keys),
        "off_plan_topic_count": len(off_plan_keys),
        "actual_topic_count": len(actual_keys),
        "coverage_ratio": round(covered_count / planned_count, 4) if planned_count else 0,
        "covered_topics": [actual_by_key[key] for key in sorted(covered_keys)],
        "missing_topics": [
            {
                "topic": planned_by_key[key].get("topic"),
                "capability_key": planned_by_key[key].get("capability_key") or key,
                "assessment": planned_by_key[key].get("assessment"),
                "why_collect": planned_by_key[key].get("why_collect"),
                "suggested_filter_terms": planned_by_key[key].get("suggested_filter_terms") or [],
            }
            for key in sorted(missing_keys)
        ],
        "off_plan_topics": [actual_by_key[key] for key in sorted(off_plan_keys)],
    }


def _demand_comparison_coverage(dashboard: dict[str, Any] | None) -> dict[str, Any]:
    topics = [_actual_demand_topic(topic) for topic in _demand_read_topics(dashboard)]
    actual_topics = [topic for topic in topics if topic]
    with_change = [
        topic
        for topic in actual_topics
        if _number_value(topic.get("change_pct")) is not None
    ]
    return {
        "topic_count": len(actual_topics),
        "topics_with_change_pct": len(with_change),
        "missing_change_pct_count": len(actual_topics) - len(with_change),
    }


def _demand_action_grade_coverage(dashboard: dict[str, Any] | None) -> dict[str, Any]:
    demand_read = {}
    run = _dashboard_run(dashboard)
    brief = run.get("intelligence_brief")
    if isinstance(brief, dict) and isinstance(brief.get("demand_read"), dict):
        demand_read = brief["demand_read"]
    return {
        "demand_signal_count": _int_value(run.get("demand_signal_count")),
        "rising_topic_count": _int_value(demand_read.get("rising_topic_count")),
        "top_topic_count": len(_list_value(demand_read.get("top_topics"))),
        "summary": _text_value(demand_read.get("summary")),
    }


def _demand_collection_plan(
    *,
    status: str,
    demand_plane: dict[str, Any],
    manual_import: dict[str, Any],
    ga4_connector: dict[str, Any],
    dashboard: dict[str, Any] | None,
) -> dict[str, Any]:
    topics, source_dashboard_field = _collection_topics_with_source(dashboard)
    coverage = _demand_plan_coverage(
        planned_topics=topics,
        demand_plane=demand_plane,
        dashboard=dashboard,
    )
    if _int_value(demand_plane.get("demand_signal_count")) > 0:
        plan_status = str(coverage.get("status") or "demand_already_present")
    elif status in {"queued_manual_exports", "ready_to_export_ga4"}:
        plan_status = "ready_to_collect"
    else:
        plan_status = "needs_demand_source"
    topic_count = len(topics)
    summary = (
        f"Collect GA / Looker demand for {topic_count} Argus-prioritized capability topic"
        f"{'' if topic_count == 1 else 's'} before promoting recommendations."
        if topic_count
        else "Collect GA / Looker demand before Argus can validate whether outward market movement matters to Algolia."
    )
    return {
        "status": plan_status,
        "summary": summary,
        "source_dashboard_field": source_dashboard_field,
        "topic_count": topic_count,
        "topics": topics,
        "coverage": coverage,
        "drop_folder": manual_import.get("drop_folder"),
        "accepted_suffixes": list(manual_import.get("accepted_suffixes") or []),
        "template_fields": list(DEMAND_IMPORT_TEMPLATE_FIELDS),
        "ga4_query_shape": {
            "dimensions": ["Page title", "Page path"],
            "metric": ga4_connector.get("metric") or "engagedSessions",
            "current_window": ga4_connector.get("current_window"),
            "previous_window": ga4_connector.get("previous_window"),
        },
    }


def _refine_status_with_plan_coverage(
    *,
    status: str,
    next_action: str,
    summary: str,
    demand_collection_plan: dict[str, Any],
    comparison_coverage: dict[str, Any],
    action_grade_coverage: dict[str, Any],
    allow_controlled_pilot_partial_demand: bool = False,
) -> tuple[str, str, str]:
    if status != "processed":
        return status, next_action, summary
    topic_count = _int_value(comparison_coverage.get("topic_count"))
    topics_with_change = _int_value(comparison_coverage.get("topics_with_change_pct"))
    if topic_count > 0 and topics_with_change == 0:
        return (
            "processed_no_comparison_period",
            "upload_trended_planned_demand_export",
            (
                "Tenant demand evidence exists, but the imported export only has current-period values. "
                "Argus needs a previous-period or change_pct column before it can score movement."
            ),
        )
    demand_signal_count = _int_value(action_grade_coverage.get("demand_signal_count"))
    rising_topic_count = _int_value(action_grade_coverage.get("rising_topic_count"))
    top_topic_count = _int_value(action_grade_coverage.get("top_topic_count"))
    if demand_signal_count > 0 and rising_topic_count == 0 and top_topic_count == 0:
        return (
            "processed_no_action_grade_demand",
            "upload_trended_planned_demand_export",
            (
                "Tenant demand evidence exists, but no topic crossed the rising-demand threshold. "
                "Argus needs planned topic mapping plus previous-period or change_pct values before it can promote action."
            ),
        )
    coverage = demand_collection_plan.get("coverage")
    if not isinstance(coverage, dict):
        return status, next_action, summary
    planned = _int_value(coverage.get("planned_topic_count"))
    covered = _int_value(coverage.get("covered_topic_count"))
    if planned <= 0:
        return status, next_action, summary
    coverage_status = str(coverage.get("status") or "")
    if coverage_status == "covered":
        return status, next_action, summary
    if coverage_status == "partial_coverage":
        if allow_controlled_pilot_partial_demand and rising_topic_count > 0 and demand_signal_count > 0:
            return (
                "processed_limited_plan_coverage",
                "monitor_missing_plan_demand",
                (
                    "Tenant demand evidence is sufficient for the controlled pilot, but only covers "
                    f"{covered} of {planned} Argus-prioritized demand topics; missing topics remain "
                    "monitoring debt."
                ),
            )
        return (
            "processed_partial_plan_coverage",
            "collect_missing_plan_demand",
            (
                "Tenant demand evidence exists, but it only covers "
                f"{covered} of {planned} Argus-prioritized demand topics."
            ),
        )
    if coverage_status == "off_plan":
        return (
            "processed_off_plan_demand",
            "collect_planned_demand",
            (
                "Tenant demand evidence exists, but it does not cover any of "
                f"{planned} Argus-prioritized demand topics."
            ),
        )
    if coverage_status == "unmapped_demand":
        return (
            "processed_unmapped_demand",
            "inspect_demand_mapping",
            "Tenant demand evidence exists, but Argus could not map it to planned capability topics.",
        )
    return status, next_action, summary


def _ensure_manual_drop_folder(store: DemandImportStore, tenant_slug: str) -> None:
    drop_folder = store.drop_folder(tenant_slug)
    drop_folder.mkdir(parents=True, exist_ok=True)
    try:
        owner = store.app_dir.stat()
    except OSError:
        return
    for path in (drop_folder.parent.parent, drop_folder.parent, drop_folder):
        try:
            if path.exists():
                os.chown(path, owner.st_uid, owner.st_gid)
        except (PermissionError, OSError):
            # Non-root runs create the folder as the app user already. If
            # ownership cannot be adjusted, the readiness payload still reports
            # the path and tests/admin can surface the permission issue.
            continue


def _manual_import_summary(store: DemandImportStore, tenant_slug: str) -> dict[str, Any]:
    # This artifact is an operator handoff, not a passive report. If we tell
    # Hermes or a human to upload a demand export to a folder, that folder must
    # exist by the time the handoff is published.
    _ensure_manual_drop_folder(store, tenant_slug)
    status = store.status(tenant_slug)
    ready_preview_count = sum(1 for preview in status.inbox_previews if preview.status == "ready")
    error_preview_count = sum(1 for preview in status.inbox_previews if preview.status == "error")
    normalized_preview_row_count = sum(preview.normalized_row_count for preview in status.inbox_previews)
    skipped_preview_row_count = sum(preview.skipped_row_count for preview in status.inbox_previews)
    topics = sorted({topic for preview in status.inbox_previews for topic in preview.topics if topic})
    return {
        "drop_folder": status.drop_folder,
        "manifest_path": status.manifest_path,
        "manifest_exists": status.manifest_exists,
        "accepted_suffixes": list(status.accepted_suffixes),
        "template_fields": list(DEMAND_IMPORT_TEMPLATE_FIELDS),
        "inbox_file_count": len(status.inbox_files),
        "ready_preview_count": ready_preview_count,
        "error_preview_count": error_preview_count,
        "normalized_preview_row_count": normalized_preview_row_count,
        "skipped_preview_row_count": skipped_preview_row_count,
        "archived_file_count": len(status.archived_files),
        "rejected_file_count": len(status.rejected_files),
        "manifest_discovered_count": status.discovered_count,
        "manifest_ready_count": status.ready_count,
        "manifest_error_count": status.error_count,
        "manifest_normalized_row_count": status.normalized_row_count,
        "manifest_skipped_row_count": status.skipped_row_count,
        "preview_topics": topics[:12],
        "inbox_files": [
            {
                "name": item.name,
                "size_bytes": item.size_bytes,
                "modified_at": item.modified_at.isoformat() if item.modified_at else None,
            }
            for item in status.inbox_files[:20]
        ],
    }


def _ga4_summary(control: Ga4DemandExportControl, tenant_slug: str) -> dict[str, Any]:
    status = control.status(tenant_slug)
    output_name = Path(status.output_path).name if status.output_path else "ga4-demand.json"
    return {
        "enabled": status.enabled,
        "ready": status.ready,
        "status": status.status,
        "missing_required": list(status.missing_required),
        "setup_required": list(status.setup_required),
        "property_configured": status.property_configured,
        "credentials_configured": status.credentials_configured,
        "credentials_path_exists": status.credentials_path_exists,
        "application_default_credentials_configured": status.application_default_credentials_configured,
        "script_path_exists": status.script_path_exists,
        "current_window": {"start": status.current_start, "end": status.current_end},
        "previous_window": {"start": status.previous_start, "end": status.previous_end},
        "topic_dimension": status.topic_dimension,
        "url_dimension": status.url_dimension,
        "metric": status.metric,
        "limit": status.limit,
        "source_url_configured": status.source_url_configured,
        "output_name": output_name,
        "message": status.message,
    }


def _status_and_action(
    *,
    demand_plane: dict[str, Any],
    manual_import: dict[str, Any],
    ga4_connector: dict[str, Any],
) -> tuple[str, str, str]:
    demand_rows = _int_value(demand_plane.get("looker_normalized_row_count")) + _int_value(
        demand_plane.get("demand_signal_count")
    )
    if demand_plane.get("status") in {"processed", "degraded"} and demand_rows > 0:
        return (
            "processed",
            "continue_product_market_synthesis",
            "Tenant demand evidence is already present in the latest Argus run.",
        )
    if _int_value(manual_import.get("ready_preview_count")) > 0:
        return (
            "queued_manual_exports",
            "prepare_demand_and_refresh_argus",
            "A manual GA / Looker export is queued and has usable rows.",
        )
    if _int_value(manual_import.get("error_preview_count")) > 0:
        return (
            "blocked_bad_manual_export",
            "repair_queued_demand_export",
            "A queued demand export exists but cannot be normalized.",
        )
    if bool(ga4_connector.get("ready")):
        return (
            "ready_to_export_ga4",
            "run_ga4_export_then_prepare_demand",
            "GA4 connector configuration is ready; Hermes can export demand evidence.",
        )
    if bool(ga4_connector.get("enabled")):
        return (
            "blocked_missing_configuration",
            "configure_ga4_or_upload_demand_export",
            "GA4 export is enabled but missing required configuration; no usable manual export is queued.",
        )
    return (
        "blocked_missing_demand_source",
        "configure_ga4_or_upload_demand_export",
        "No tenant-side demand source is ready. Configure GA4 or upload a GA / Looker export.",
    )


def _operator_actions(tenant_slug: str, *, status: str) -> list[dict[str, Any]]:
    refresh = {
        "label": "Prepare demand and refresh Argus",
        "href": f"/admin/{tenant_slug}/argus/demand-imports/refresh",
        "method": "post",
        "surface": "Demand imports",
    }
    template = {
        "label": "Download demand template",
        "href": f"/api/tenants/{tenant_slug}/argus/demand-imports/template",
        "method": "get",
        "surface": "Demand imports",
    }
    planned_template = {
        "label": "Download demand plan template",
        "href": f"/api/tenants/{tenant_slug}/argus/demand-imports/template?planned=1",
        "method": "get",
        "surface": "Demand imports",
    }
    ga4 = {
        "label": "Run GA4 export now",
        "href": f"/admin/{tenant_slug}/argus/ga4-export",
        "method": "post",
        "surface": "GA4 connector",
    }
    ga4_refresh = {
        "label": "Run GA4 export and refresh Argus",
        "href": f"/admin/{tenant_slug}/argus/ga4-export/refresh",
        "method": "post",
        "surface": "GA4 connector",
    }
    configure_ga4 = {
        "label": "Configure GA4 connector",
        "href": f"/admin?tenant={tenant_slug}#inward-demand",
        "method": "get",
        "surface": "GA4 connector",
    }
    admin = {
        "label": "Open demand admin",
        "href": f"/admin?tenant={tenant_slug}#inward-demand",
        "method": "get",
        "surface": "Admin",
    }
    if status == "queued_manual_exports":
        return [refresh, planned_template, template, admin]
    if status == "ready_to_export_ga4":
        return [ga4_refresh, ga4, planned_template, refresh, admin]
    if status == "blocked_bad_manual_export":
        return [admin, planned_template, template, refresh]
    if status == "processed":
        return [admin]
    return [planned_template, template, admin, configure_ga4]


def build_demand_readiness_payload(
    *,
    tenant_slug: str,
    app_dir: Path,
    work_root: Path,
    env: dict[str, str] | None = None,
    dashboard: dict[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    effective_env = dict(os.environ if env is None else env)
    store = DemandImportStore(app_dir=app_dir, work_root=work_root)
    ga4_control = Ga4DemandExportControl(app_dir=app_dir, env=effective_env)
    demand_plane = _demand_plane_summary(dashboard)
    manual_import = _manual_import_summary(store, tenant_slug)
    ga4_connector = _ga4_summary(ga4_control, tenant_slug)
    generated = generated_at or _now()
    status, next_action, summary = _status_and_action(
        demand_plane=demand_plane,
        manual_import=manual_import,
        ga4_connector=ga4_connector,
    )
    demand_collection_plan = _demand_collection_plan(
        status=status,
        demand_plane=demand_plane,
        manual_import=manual_import,
        ga4_connector=ga4_connector,
        dashboard=dashboard,
    )
    comparison_coverage = _demand_comparison_coverage(dashboard)
    action_grade_coverage = _demand_action_grade_coverage(dashboard)
    status, next_action, summary = _refine_status_with_plan_coverage(
        status=status,
        next_action=next_action,
        summary=summary,
        demand_collection_plan=demand_collection_plan,
        comparison_coverage=comparison_coverage,
        action_grade_coverage=action_grade_coverage,
        allow_controlled_pilot_partial_demand=_truthy(
            effective_env.get("CIOS_CONTROLLED_PILOT_ALLOW_PARTIAL_DEMAND")
        ),
    )
    demand_source_contract = build_demand_source_contract(
        tenant_slug=tenant_slug,
        work_root=work_root,
        demand_plane=demand_plane,
        manual_import=manual_import,
        ga4_connector=ga4_connector,
        generated_at=generated,
        demand_collection_plan=demand_collection_plan,
    )
    write_demand_source_contract(demand_source_contract)
    return {
        "tenant_slug": tenant_slug,
        "generated_at": generated,
        "status": status,
        "summary": summary,
        "next_hermes_action": next_action,
        "demand_plane": demand_plane,
        "manual_import": manual_import,
        "ga4_connector": ga4_connector,
        "demand_source_contract": demand_source_contract,
        "demand_collection_plan": demand_collection_plan,
        "comparison_coverage": comparison_coverage,
        "action_grade_coverage": action_grade_coverage,
        "operator_actions": _operator_actions(tenant_slug, status=status),
        "safety": {
            "secret_values_included": False,
            "credentials_reported_as_booleans_only": True,
        },
    }


def write_payload(payload: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(f"{json.dumps(payload, indent=2, sort_keys=True)}\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Argus inward-demand readiness.")
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--app-dir", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--work-root", type=Path, default=Path("/tmp/cios-product-market"))
    parser.add_argument("--dashboard", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = build_demand_readiness_payload(
        tenant_slug=args.tenant,
        app_dir=args.app_dir.expanduser(),
        work_root=args.work_root.expanduser(),
        dashboard=_load_json(_dashboard_path(args.dashboard, app_dir=args.app_dir.expanduser())),
    )
    if args.output:
        write_payload(payload, args.output)
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
