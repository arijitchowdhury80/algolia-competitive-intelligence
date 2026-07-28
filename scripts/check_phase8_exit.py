#!/usr/bin/env python3
"""Evaluate whether the CI-OS controlled Algolia pilot can exit Phase 8."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int_value(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _blocker(requirement: str, actual: str, next_step: str) -> dict[str, str]:
    return {"requirement": requirement, "actual": actual, "next_step": next_step}


def _current_recommendation_ids(public_status: Mapping[str, Any]) -> set[int]:
    ids: set[int] = set()
    for item in public_status.get("current_recommendations") or []:
        if not isinstance(item, dict):
            continue
        recommendation_id = _int_value(item.get("recommendation_id"))
        if recommendation_id > 0:
            ids.add(recommendation_id)
    return ids


def evaluate_phase8_exit(
    *,
    pilot_monitoring: dict[str, Any],
    launch_readiness: dict[str, Any],
    public_status: dict[str, Any],
    disposition: dict[str, Any],
    release_id: str,
    package_commit: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Return the Phase 8 exit verdict from monitored release artifacts."""

    monitoring_recommendations = _dict_value(_dict_value(pilot_monitoring.get("monitoring")).get("recommendations"))
    recommendation_count = _int_value(
        _dict_value(public_status.get("product_market_run")).get("recommendation_count"),
        _int_value(monitoring_recommendations.get("recommendation_count")),
    )
    disposition_rec = _dict_value(disposition.get("recommendation"))
    disposition_details = _dict_value(disposition.get("disposition"))
    disposition_recommendation_id = _int_value(disposition_rec.get("recommendation_id"))
    public_recommendation_ids = _current_recommendation_ids(public_status)
    decision = _clean(disposition.get("decision")).lower()

    checks = {
        "release_identity_matches": pilot_monitoring.get("release_id") == release_id
        and pilot_monitoring.get("package_commit") == package_commit,
        "launch_readiness_passed": launch_readiness.get("status") == "pass",
        "pilot_monitoring_passed": pilot_monitoring.get("status") == "pass",
        "public_recommendation_present": recommendation_count > 0 and bool(public_recommendation_ids),
        "named_team_disposition_final": disposition.get("phase8_exit_evidence") is True
        and decision in {"used", "rejected", "amended"}
        and bool(_clean(disposition_details.get("named_team")))
        and bool(_clean(disposition_details.get("decided_by")))
        and bool(_clean(disposition_details.get("use_case")))
        and bool(_clean(disposition_details.get("reason"))),
        "current_recommendation_matches_disposition": disposition_recommendation_id in public_recommendation_ids,
    }

    blockers: list[dict[str, str]] = []
    if not checks["release_identity_matches"]:
        blockers.append(
            _blocker(
                "release_identity_matches",
                (
                    f"monitor.release_id={pilot_monitoring.get('release_id')} "
                    f"monitor.package_commit={pilot_monitoring.get('package_commit')}"
                ),
                "Rerun pilot monitoring for the deployed Phase 8 release before exit.",
            )
        )
    if not checks["launch_readiness_passed"]:
        blockers.append(
            _blocker(
                "launch_readiness_passed",
                f"launch_readiness.status={launch_readiness.get('status')}",
                "Rerun launch readiness and preserve the passing artifact.",
            )
        )
    if not checks["pilot_monitoring_passed"]:
        blockers.append(
            _blocker(
                "pilot_monitoring_passed",
                f"pilot_monitoring.status={pilot_monitoring.get('status')}",
                "Rerun controlled-pilot monitoring and repair blockers.",
            )
        )
    if not checks["public_recommendation_present"]:
        blockers.append(
            _blocker(
                "public_recommendation_present",
                f"recommendation_count={recommendation_count} current_recommendation_ids={sorted(public_recommendation_ids)}",
                "Expose a current named-owner recommendation in the public run status.",
            )
        )
    if not checks["named_team_disposition_final"]:
        blockers.append(
            _blocker(
                "named_team_disposition_final",
                (
                    f"decision={decision} phase8_exit_evidence={disposition.get('phase8_exit_evidence')} "
                    f"named_team={disposition_details.get('named_team')} use_case_present={bool(_clean(disposition_details.get('use_case')))}"
                ),
                "Record a final named-team use, rejection, or amendment with concrete use case and reason.",
            )
        )
    if not checks["current_recommendation_matches_disposition"]:
        blockers.append(
            _blocker(
                "current_recommendation_matches_disposition",
                f"disposition_recommendation_id={disposition_recommendation_id} current_ids={sorted(public_recommendation_ids)}",
                "Record disposition against the current public recommendation.",
            )
        )

    status = "pass" if not blockers else "fail"
    return {
        "gate": "cios_phase8_exit",
        "generated_at": generated_at or _now(),
        "release_id": release_id,
        "package_commit": package_commit,
        "status": status,
        "exit_code": 0 if status == "pass" else 2,
        "summary": "CI-OS Phase 8 exit gate passed."
        if status == "pass"
        else "CI-OS Phase 8 exit gate is not complete.",
        "phase8_exit_evidence": status == "pass",
        "checks": checks,
        "blockers": blockers,
        "decision": {
            "decision": decision,
            "recommendation_id": disposition_recommendation_id,
            "named_team": disposition_details.get("named_team"),
            "decided_by": disposition_details.get("decided_by"),
            "use_case": disposition_details.get("use_case"),
            "reason": disposition_details.get("reason"),
        },
        "monitoring": {
            "public_recommendation_count": recommendation_count,
            "current_recommendation_ids": sorted(public_recommendation_ids),
            "pilot_monitoring_status": pilot_monitoring.get("status"),
            "launch_readiness_status": launch_readiness.get("status"),
        },
    }


def write_payload(payload: Mapping[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(f"{json.dumps(payload, indent=2, sort_keys=True)}\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check the CI-OS Phase 8 controlled-pilot exit gate.")
    parser.add_argument("--pilot-monitoring", required=True, type=Path)
    parser.add_argument("--launch-readiness", required=True, type=Path)
    parser.add_argument("--public-status", required=True, type=Path)
    parser.add_argument("--disposition", required=True, type=Path)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--package-commit", required=True)
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = evaluate_phase8_exit(
        pilot_monitoring=_load_json(args.pilot_monitoring),
        launch_readiness=_load_json(args.launch_readiness),
        public_status=_load_json(args.public_status),
        disposition=_load_json(args.disposition),
        release_id=args.release_id,
        package_commit=args.package_commit,
    )
    if args.output:
        write_payload(payload, args.output)
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return int(payload["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
