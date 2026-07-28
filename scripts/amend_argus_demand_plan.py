#!/usr/bin/env python3
"""Append explicitly accepted amendment candidates to an Argus demand plan."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cios.admin.demand_imports import demand_collection_plan_template_csv


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists() or path.stat().st_size == 0:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _split_list(value: Any) -> list[str]:
    if value is None:
        return []
    raw = value if isinstance(value, list) else str(value).split("|")
    result: list[str] = []
    seen: set[str] = set()
    for item in raw:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _text(row: dict[str, Any], key: str) -> str:
    return str(row.get(key) or "").strip()


def _topic_key(topic: dict[str, Any]) -> str:
    return str(topic.get("capability_key") or topic.get("topic") or "").strip().casefold()


def _read_amendment_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _candidate_to_topic(row: dict[str, Any]) -> dict[str, Any] | None:
    topic = _text(row, "Argus topic")
    capability_key = _text(row, "Capability key") or topic
    if not topic and not capability_key:
        return None
    return {
        "topic": topic or capability_key,
        "capability_key": capability_key,
        "assessment": _text(row, "Assessment") or "demand_plan_amendment",
        "suggested_filter_terms": _split_list(row.get("Suggested filters")),
        "related_competitors": _split_list(row.get("Related competitors")),
        "why_collect": _text(row, "Why collect"),
        "evidence_urls": _split_list(row.get("Evidence URLs")),
        "amendment_source": "planned_demand_evaluator",
        "amended_at": _now(),
    }


def amend_readiness(
    readiness: dict[str, Any],
    amendment_rows: list[dict[str, Any]],
    *,
    accepted_by: str,
    reason: str,
) -> dict[str, Any]:
    amended = deepcopy(readiness)
    plan = amended.get("demand_collection_plan")
    if not isinstance(plan, dict):
        plan = {}
        amended["demand_collection_plan"] = plan
    topics = plan.get("topics")
    if not isinstance(topics, list):
        topics = []
        plan["topics"] = topics

    existing = {_topic_key(topic) for topic in topics if isinstance(topic, dict)}
    added: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for row in amendment_rows:
        topic = _candidate_to_topic(row)
        if topic is None:
            continue
        key = _topic_key(topic)
        if key and key in existing:
            skipped.append({"topic": topic["topic"], "reason": "already_planned"})
            continue
        if key:
            existing.add(key)
        topics.append(topic)
        added.append(topic)

    plan["topic_count"] = len([topic for topic in topics if isinstance(topic, dict)])
    plan["status"] = "ready_to_collect_amended" if added else str(plan.get("status") or "ready_to_collect")
    plan["amendment_policy"] = {
        "status": "accepted" if added else "no_new_topics",
        "accepted_by": accepted_by,
        "accepted_at": _now(),
        "reason": reason,
        "source": "argus-demand-plan-amendment-candidates.csv",
        "added_topic_count": len(added),
        "skipped_topic_count": len(skipped),
        "added_topics": [
            {
                "topic": topic["topic"],
                "capability_key": topic["capability_key"],
                "assessment": topic["assessment"],
            }
            for topic in added
        ],
        "skipped_topics": skipped,
    }
    if added and str(amended.get("status") or "") != "processed":
        amended["status"] = "manual_plan_amended"
    else:
        amended["status"] = amended.get("status", "manual_plan_amended")
    amended["next_hermes_action"] = "import_amended_planned_demand"
    return amended


def write_json(payload: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply accepted demand-plan amendment candidates.")
    parser.add_argument("--readiness", type=Path, required=True)
    parser.add_argument("--amendments", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--template-output", type=Path)
    parser.add_argument("--accepted-by", default="operator")
    parser.add_argument("--reason", default="Explicitly accepted validated off-plan audience movement into the Argus demand plan.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    amended = amend_readiness(
        _load_json(args.readiness),
        _read_amendment_rows(args.amendments),
        accepted_by=args.accepted_by,
        reason=args.reason,
    )
    write_json(amended, args.output)
    if args.template_output is not None:
        args.template_output.parent.mkdir(parents=True, exist_ok=True)
        plan = amended.get("demand_collection_plan")
        args.template_output.write_text(
            demand_collection_plan_template_csv(plan if isinstance(plan, dict) else {}),
            encoding="utf-8",
        )
    plan = amended.get("demand_collection_plan") if isinstance(amended.get("demand_collection_plan"), dict) else {}
    policy = plan.get("amendment_policy") if isinstance(plan.get("amendment_policy"), dict) else {}
    return 0 if int(policy.get("added_topic_count") or 0) > 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
