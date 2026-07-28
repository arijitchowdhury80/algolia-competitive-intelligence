#!/usr/bin/env python3
"""Evaluate Looker exports against the active Argus demand plan.

This is a phase-gate helper, not a generic analytics report. It answers one
question: do the available exports contain action-grade seven-day demand for the
topics Argus explicitly asked us to validate?
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cios.intelligence.demand_quality import DEMAND_CHANGE_FLOOR, DEMAND_VALUE_FLOOR


CURRENT_START = "2026-07-07"
CURRENT_END = "2026-07-13"
PREVIOUS_START = "2026-06-30"
PREVIOUS_END = "2026-07-06"

DIMENSION_FIELDS = (
    "Session manual campaign name",
    "Landing page",
    "Page",
    "Page path",
    "topic",
    "page_path",
)

OFF_PLAN_TERMS = (
    ("Agent Studio", ("agent studio", "agentic ai", "ai agent", "ai agents")),
    ("AI Recommendations", ("recommendations", "ai recommendations")),
    ("Generative experiences", ("generative", "genai")),
    ("Commerce", ("commerce",)),
)


@dataclass
class DemandPlanTopic:
    topic: str
    capability_key: str
    assessment: str = ""
    suggested_filters: list[str] = field(default_factory=list)
    related_competitors: list[str] = field(default_factory=list)

    @property
    def terms(self) -> list[str]:
        candidates = [self.topic, self.capability_key, *self.suggested_filters]
        return _dedupe_terms(candidates)


@dataclass
class MetricRow:
    source_file: str
    export_kind: str
    period_label: str
    dimension_name: str
    dimension_value: str
    sessions: float
    row_number: int


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold())).strip()


def _float(value: Any) -> float:
    try:
        return float(str(value or "0").replace(",", ""))
    except ValueError:
        return 0.0


def _split_list(value: Any) -> list[str]:
    if value is None:
        return []
    parts = re.split(r"\s*\|\s*|,", str(value))
    return [part.strip() for part in parts if part.strip()]


def _dedupe_terms(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        norm = _norm(text)
        if len(norm) < 4 or len(norm.split()) < 2 or norm in seen:
            continue
        seen.add(norm)
        result.append(text)
    return result


def _contains_term(haystack: str, term: str) -> bool:
    haystack_norm = f" {_norm(haystack)} "
    term_norm = _norm(term)
    if not term_norm:
        return False
    return f" {term_norm} " in haystack_norm


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def load_plan(path: Path) -> list[DemandPlanTopic]:
    rows = read_csv_rows(path)
    topics: list[DemandPlanTopic] = []
    for row in rows:
        topic = row.get("Argus topic") or row.get("topic") or row.get("Topic") or row.get("Page title") or ""
        capability_key = row.get("Capability key") or row.get("capability_key") or row.get("capability key") or topic
        if not str(topic).strip() and not str(capability_key).strip():
            continue
        topics.append(
            DemandPlanTopic(
                topic=str(topic).strip(),
                capability_key=str(capability_key).strip(),
                assessment=str(row.get("Assessment") or row.get("assessment") or "").strip(),
                suggested_filters=_split_list(row.get("Suggested filters") or row.get("suggested filters")),
                related_competitors=_split_list(row.get("Related competitors") or row.get("related_competitors")),
            )
        )
    return topics


def _period_from_name(path: Path) -> str:
    name = path.name
    if f"{CURRENT_START}_{CURRENT_END}" in name:
        return "current"
    if f"{PREVIOUS_START}_{PREVIOUS_END}" in name:
        return "previous"
    return "unknown"


def _export_kind(path: Path, headers: set[str]) -> str:
    name = path.name
    if "campaign-metrics" in name and "Session manual campaign name" in headers:
        return "campaign_metrics"
    if "landing-page-device-sessions" in name and "Landing page" in headers:
        return "landing_page_device_sessions"
    if "landing-page-metrics" in name and "Landing page" in headers:
        return "landing_page_metrics"
    if "page-metrics" in name and "Page" in headers:
        return "page_metrics"
    if "looker-demand" in name and {"topic", "value"}.issubset(headers):
        return "prepared_demand"
    return "unsupported"


def load_metric_rows(data_dir: Path) -> list[MetricRow]:
    rows: list[MetricRow] = []
    for path in sorted(data_dir.glob("*.csv")):
        raw_rows = read_csv_rows(path)
        if not raw_rows:
            continue
        headers = set(raw_rows[0])
        kind = _export_kind(path, headers)
        if kind == "unsupported":
            continue
        period = _period_from_name(path)
        for index, row in enumerate(raw_rows, start=2):
            dimension_name = next((field for field in DIMENSION_FIELDS if field in row), "")
            if not dimension_name:
                continue
            metric_value = row.get("Sessions") if "Sessions" in row else row.get("value")
            rows.append(
                MetricRow(
                    source_file=path.name,
                    export_kind=kind,
                    period_label=period,
                    dimension_name=dimension_name,
                    dimension_value=str(row.get(dimension_name) or "").strip(),
                    sessions=_float(metric_value),
                    row_number=index,
                )
            )
    return rows


def _matching_rows(rows: list[MetricRow], terms: list[str]) -> list[MetricRow]:
    return [row for row in rows if any(_contains_term(row.dimension_value, term) for term in terms)]


def _sum(rows: Iterable[MetricRow]) -> float:
    return sum(row.sessions for row in rows)


def _row_refs(rows: Iterable[MetricRow], *, limit: int = 8) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for row in rows:
        refs.append(
            {
                "source_file": row.source_file,
                "source_row_number": row.row_number,
                "export_kind": row.export_kind,
                "dimension": row.dimension_value,
                "sessions": row.sessions,
            }
        )
        if len(refs) >= limit:
            break
    return refs


def _change_pct(current: float, previous: float) -> float | None:
    if previous <= 0:
        return None
    return round((current - previous) / previous, 4)


def _status(*, current: float, previous: float, change_pct: float | None, comparison_quality: str) -> str:
    if current <= 0:
        return "no_matching_current_rows"
    if previous <= 0:
        return "missing_previous_period"
    if change_pct is None:
        return "missing_change_pct"
    if change_pct >= DEMAND_CHANGE_FLOOR and current >= DEMAND_VALUE_FLOOR:
        if comparison_quality == "comparable_limited":
            return "action_grade_limited"
        return "action_grade"
    return "not_action_grade"


def evaluate_topic(topic: DemandPlanTopic, rows: list[MetricRow]) -> dict[str, Any]:
    matches = _matching_rows(rows, topic.terms)
    current_campaign = [r for r in matches if r.period_label == "current" and r.export_kind == "campaign_metrics"]
    previous_campaign = [r for r in matches if r.period_label == "previous" and r.export_kind == "campaign_metrics"]
    current_landing = [r for r in matches if r.period_label == "current" and r.export_kind == "landing_page_metrics"]
    if not current_landing:
        current_landing = [r for r in matches if r.period_label == "current" and r.export_kind == "page_metrics"]
    previous_landing = [
        r for r in matches if r.period_label == "previous" and r.export_kind == "landing_page_device_sessions"
    ]
    current_prepared = [r for r in matches if r.period_label == "current" and r.export_kind == "prepared_demand"]

    candidates: list[tuple[str, str, list[MetricRow], list[MetricRow]]] = [
        ("campaign_metrics", "exact_same_export", current_campaign, previous_campaign),
        ("landing_page_sessions", "comparable_limited", current_landing, previous_landing),
        ("prepared_demand", "current_only", current_prepared, []),
    ]
    best = max(candidates, key=lambda item: (_sum(item[2]) > 0 and _sum(item[3]) > 0, _sum(item[2])))
    comparison_basis, comparison_quality, current_rows, previous_rows = best
    current = _sum(current_rows)
    previous = _sum(previous_rows)
    change = _change_pct(current, previous)
    status = _status(
        current=current,
        previous=previous,
        change_pct=change,
        comparison_quality=comparison_quality,
    )
    return {
        "topic": topic.topic,
        "capability_key": topic.capability_key,
        "assessment": topic.assessment,
        "terms": topic.terms,
        "status": status,
        "action_grade": status == "action_grade",
        "comparison_basis": comparison_basis,
        "comparison_quality": comparison_quality,
        "current_sessions": current,
        "previous_sessions": previous,
        "change_pct": change,
        "current_rows": _row_refs(current_rows),
        "previous_rows": _row_refs(previous_rows),
        "matched_current_row_count": len(current_rows),
        "matched_previous_row_count": len(previous_rows),
    }


def evaluate_off_plan(rows: list[MetricRow]) -> list[dict[str, Any]]:
    opportunities: list[dict[str, Any]] = []
    for label, terms in OFF_PLAN_TERMS:
        pseudo_topic = DemandPlanTopic(topic=label, capability_key=label, suggested_filters=list(terms))
        result = evaluate_topic(pseudo_topic, rows)
        if result["current_sessions"] <= 0:
            continue
        result["phase4_gate_evidence"] = False
        result["reason"] = "Matched available demand exports but is not in the active Argus demand plan."
        opportunities.append(result)
    return sorted(opportunities, key=lambda item: item["current_sessions"], reverse=True)


def build_report(*, plan_path: Path, data_dir: Path, generated_at: str | None = None) -> dict[str, Any]:
    plan = load_plan(plan_path)
    rows = load_metric_rows(data_dir)
    topic_results = [evaluate_topic(topic, rows) for topic in plan]
    action_grade_topics = [row for row in topic_results if row["action_grade"]]
    limited_topics = [row for row in topic_results if row["status"] == "action_grade_limited"]
    status = "passed" if action_grade_topics else "blocked_no_action_grade_planned_demand"
    return {
        "schema_version": 1,
        "generated_at": generated_at or _now(),
        "status": status,
        "phase4_gate_passed": bool(action_grade_topics),
        "demand_change_floor": DEMAND_CHANGE_FLOOR,
        "demand_value_floor": DEMAND_VALUE_FLOOR,
        "plan_path": str(plan_path),
        "data_dir": str(data_dir),
        "plan_topic_count": len(plan),
        "metric_row_count": len(rows),
        "summary": (
            "At least one active Argus demand-plan topic has action-grade comparable movement."
            if action_grade_topics
            else "No active Argus demand-plan topic has strong comparable seven-day demand movement."
        ),
        "next_required_action": (
            "Promote the planned demand rows into the Argus demand import."
            if action_grade_topics
            else "Export current and previous seven-day Looker rows for the active Argus topics, or amend the demand plan explicitly."
        ),
        "topics": topic_results,
        "action_grade_topics": action_grade_topics,
        "limited_action_grade_topics": limited_topics,
        "off_plan_opportunities": evaluate_off_plan(rows),
    }


def write_json(payload: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_prepared_csv(topic_results: list[dict[str, Any]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "topic",
        "metric",
        "value",
        "period_start",
        "period_end",
        "source_label",
        "source_url",
        "excerpt",
        "capability_key",
        "change_pct",
    ]
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in topic_results:
            if not row.get("action_grade"):
                continue
            writer.writerow(
                {
                    "topic": row["topic"],
                    "metric": "sessions",
                    "value": row["current_sessions"],
                    "period_start": f"{CURRENT_START}T00:00:00+00:00",
                    "period_end": f"{CURRENT_END}T23:59:59+00:00",
                    "source_label": "Looker Studio GA4 export: planned demand evaluator",
                    "source_url": "https://datastudio.google.com/",
                    "excerpt": (
                        f"Current sessions: {row['current_sessions']}; previous sessions: "
                        f"{row['previous_sessions']}; change_pct: {row['change_pct']}"
                    ),
                    "capability_key": row["capability_key"],
                    "change_pct": row["change_pct"],
                }
            )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate Looker exports against the active Argus demand plan.")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prepared-output", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(plan_path=args.plan, data_dir=args.data_dir)
    write_json(report, args.output)
    if args.prepared_output is not None:
        write_prepared_csv(report["action_grade_topics"], args.prepared_output)
    return 0 if report["phase4_gate_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
