#!/usr/bin/env python3
"""Evaluate controlled-pilot monitoring health for a released CI-OS package."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int_value(value: Any, default: int = 0) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _ratio(failed: int, active: int) -> float:
    if active <= 0:
        return 0.0
    return round(failed / active, 4)


def _blocker(requirement: str, actual: str, next_step: str) -> dict[str, str]:
    return {"requirement": requirement, "actual": actual, "next_step": next_step}


def _plane(public_status: Mapping[str, Any], name: str) -> dict[str, Any]:
    return _dict_value(_dict_value(public_status.get("planes")).get(name))


def _demand_plan_coverage(public_status: Mapping[str, Any], demand: Mapping[str, Any]) -> tuple[int, int, int]:
    plan = _dict_value(demand.get("demand_collection_plan"))
    if not plan:
        plan = _dict_value(public_status.get("demand_collection_plan"))
    coverage = _dict_value(plan.get("coverage"))
    covered = _int_value(coverage.get("covered_topic_count"))
    planned = _int_value(coverage.get("planned_topic_count"), _int_value(plan.get("topic_count")))
    missing = _int_value(coverage.get("missing_topic_count"))
    if not covered and planned and not missing:
        summary = str(demand.get("summary") or "")
        match = re.search(r"covers\s+(\d+)\s+of\s+(\d+)", summary, flags=re.IGNORECASE)
        if match:
            covered = _int_value(match.group(1))
            planned = _int_value(match.group(2), planned)
            missing = max(planned - covered, 0)
    return (covered, planned, missing)


def evaluate_pilot_monitoring(
    *,
    public_status: dict[str, Any],
    launch_readiness: dict[str, Any],
    release_id: str,
    package_commit: str,
    max_failed_source_ratio: float,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Return a controlled-pilot monitoring verdict from live release artifacts."""

    source_coverage = _dict_value(public_status.get("source_coverage"))
    active_sources = _int_value(source_coverage.get("active_source_count"))
    checked_sources = _int_value(source_coverage.get("checked_source_count"))
    failed_sources = _int_value(source_coverage.get("failed_source_count"))
    failed_source_ratio = _ratio(failed_sources, active_sources)
    run = _dict_value(public_status.get("product_market_run"))
    demand = _plane(public_status, "audience_demand")
    product = _plane(public_status, "product_reality")
    covered_topics, planned_topics, missing_topics = _demand_plan_coverage(public_status, demand)
    demand_signal_count = _int_value(
        _dict_value(demand.get("counts")).get("demand_signal_count"),
        _int_value(run.get("demand_signal_count")),
    )
    recommendation_count = _int_value(run.get("recommendation_count"))
    pattern_count = _int_value(run.get("pattern_count"))
    next_monitoring_action_count = len(public_status.get("next_monitoring_actions") or [])
    product_event_count = _int_value(_dict_value(product.get("counts")).get("product_event_count"))

    publication_current = (
        public_status.get("publish_status") == "published"
        and public_status.get("public_dashboard_updated") is True
        and public_status.get("status") in {"published", "limited_by_evidence"}
    )
    checks = {
        "publication_current": publication_current,
        "launch_readiness_passed": launch_readiness.get("status") == "pass",
        "source_coverage_complete": active_sources > 0 and checked_sources >= active_sources,
        "source_failure_ratio_ok": failed_source_ratio <= max_failed_source_ratio,
        "audience_demand_present": demand_signal_count > 0 and not bool(demand.get("blocks_action")),
        "product_reality_present": product_event_count > 0 and not bool(product.get("blocks_action")),
        "decision_activity_present": recommendation_count > 0 or pattern_count > 0 or next_monitoring_action_count > 0,
    }

    blockers: list[dict[str, str]] = []
    if not checks["publication_current"]:
        blockers.append(
            _blocker(
                "publication_current",
                f"publish_status={public_status.get('publish_status')} dashboard_updated={public_status.get('public_dashboard_updated')}",
                "Publish a current dashboard release before admitting pilot monitoring.",
            )
        )
    if not checks["launch_readiness_passed"]:
        blockers.append(
            _blocker(
                "launch_readiness_passed",
                f"launch_readiness.status={launch_readiness.get('status')}",
                "Rerun the CI-OS E2E launch readiness gate and preserve the passing artifact.",
            )
        )
    if not checks["source_coverage_complete"]:
        blockers.append(
            _blocker(
                "source_coverage_complete",
                f"active={active_sources} checked={checked_sources}",
                "Run the daily wrapper until all active sources are checked or explicitly removed from scope.",
            )
        )
    if not checks["source_failure_ratio_ok"]:
        blockers.append(
            _blocker(
                "source_failure_ratio_ok",
                f"failed_source_ratio={failed_source_ratio:.4f} max_failed_source_ratio={max_failed_source_ratio:.4f}",
                "Repair failed sources or reduce pilot scope before release monitoring starts.",
            )
        )
    if not checks["audience_demand_present"]:
        blockers.append(
            _blocker(
                "audience_demand_present",
                f"demand_signal_count={demand_signal_count} blocks_action={bool(demand.get('blocks_action'))}",
                "Refresh the demand plane from Looker or GA4 before release monitoring starts.",
            )
        )
    if not checks["product_reality_present"]:
        blockers.append(
            _blocker(
                "product_reality_present",
                f"product_event_count={product_event_count} blocks_action={bool(product.get('blocks_action'))}",
                "Refresh Scout-backed product evidence before release monitoring starts.",
            )
        )
    if not checks["decision_activity_present"]:
        blockers.append(
            _blocker(
                "decision_activity_present",
                (
                    f"recommendation_count={recommendation_count} pattern_count={pattern_count} "
                    f"next_monitoring_action_count={next_monitoring_action_count}"
                ),
                "Run Argus synthesis until the pilot has a recommendation, pattern, or next monitoring action.",
            )
        )

    monitoring_debt: list[str] = []
    if public_status.get("status") == "limited_by_evidence":
        monitoring_debt.append("public status is limited_by_evidence")
    if missing_topics:
        monitoring_debt.append(f"demand plan missing {missing_topics} of {planned_topics} planned topics")
    if failed_sources:
        monitoring_debt.append(f"{failed_sources} active sources failed this run")
    product_failed = _int_value(_dict_value(product.get("counts")).get("product_surface_failed_count"))
    if product_failed:
        monitoring_debt.append(f"{product_failed} product-surface captures failed")
    if recommendation_count <= 0:
        monitoring_debt.append("no current recommendation in public run status")

    status = "pass" if not blockers else "fail"
    return {
        "gate": "cios_controlled_pilot_monitoring",
        "generated_at": generated_at or _now(),
        "tenant_slug": public_status.get("tenant_slug"),
        "release_id": release_id,
        "package_commit": package_commit,
        "status": status,
        "exit_code": 0 if status == "pass" else 2,
        "summary": "CI-OS controlled pilot monitoring is ready."
        if status == "pass"
        else "CI-OS controlled pilot monitoring is not ready.",
        "checks": checks,
        "blockers": blockers,
        "monitoring": {
            "publication": {
                "public_status": public_status.get("status"),
                "publish_status": public_status.get("publish_status"),
                "public_dashboard_updated": public_status.get("public_dashboard_updated"),
                "generated_at": public_status.get("generated_at"),
            },
            "source_coverage": {
                "active_source_count": active_sources,
                "checked_source_count": checked_sources,
                "failed_source_count": failed_sources,
                "failed_source_ratio": failed_source_ratio,
                "max_failed_source_ratio": max_failed_source_ratio,
            },
            "audience_demand": {
                "status": demand.get("status"),
                "demand_signal_count": demand_signal_count,
                "planned_topic_coverage": f"{covered_topics}/{planned_topics}" if planned_topics else "0/0",
                "missing_topic_count": missing_topics,
            },
            "product_reality": {
                "status": product.get("status"),
                "product_event_count": product_event_count,
                "product_surface_failed_count": product_failed,
            },
            "recommendations": {
                "recommendation_count": recommendation_count,
                "pattern_count": pattern_count,
                "next_monitoring_action_count": next_monitoring_action_count,
            },
        },
        "monitoring_debt": monitoring_debt,
        "next_hermes_action": public_status.get("next_hermes_action"),
    }


def write_payload(payload: Mapping[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(f"{json.dumps(payload, indent=2, sort_keys=True)}\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check CI-OS controlled pilot monitoring readiness.")
    parser.add_argument("--public-status", type=Path, required=True)
    parser.add_argument("--launch-readiness", type=Path, required=True)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--package-commit", required=True)
    parser.add_argument("--max-failed-source-ratio", type=float, default=0.10)
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = evaluate_pilot_monitoring(
        public_status=_load_json(args.public_status),
        launch_readiness=_load_json(args.launch_readiness),
        release_id=args.release_id,
        package_commit=args.package_commit,
        max_failed_source_ratio=args.max_failed_source_ratio,
    )
    if args.output:
        write_payload(payload, args.output)
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return int(payload["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
