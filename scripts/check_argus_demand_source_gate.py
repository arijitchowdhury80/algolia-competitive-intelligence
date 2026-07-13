#!/usr/bin/env python3
"""Hermes gate for Argus inward-demand source readiness.

The readiness exporter explains the state. This gate turns that state into an
exit code Hermes cron, admin actions, and launch checks can enforce.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR.parents[0] / "src"))

from export_argus_demand_readiness import build_demand_readiness_payload
from cios.admin.demand_sources import demand_source_ids


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


def build_readiness(
    *,
    tenant_slug: str,
    app_dir: Path,
    work_root: Path,
    env: dict[str, str] | None = None,
    dashboard: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return build_demand_readiness_payload(
        tenant_slug=tenant_slug,
        app_dir=app_dir,
        work_root=work_root,
        env=env,
        dashboard=dashboard,
    )


def evaluate_gate(
    readiness: dict[str, Any],
    *,
    require_current_demand: bool = False,
) -> dict[str, Any]:
    readiness_status = str(readiness.get("status") or "unknown")
    manual_import = readiness.get("manual_import") if isinstance(readiness.get("manual_import"), dict) else {}
    ga4_connector = readiness.get("ga4_connector") if isinstance(readiness.get("ga4_connector"), dict) else {}
    demand_plane = readiness.get("demand_plane") if isinstance(readiness.get("demand_plane"), dict) else {}
    source_contract = (
        readiness.get("demand_source_contract")
        if isinstance(readiness.get("demand_source_contract"), dict)
        else {}
    )
    demand_plan = (
        source_contract.get("demand_plan")
        if isinstance(source_contract.get("demand_plan"), dict)
        else {}
    )

    processed_rows = _int_value(demand_plane.get("looker_normalized_row_count")) + _int_value(
        demand_plane.get("demand_signal_count")
    )
    current_demand_processed = readiness_status == "processed" and processed_rows > 0
    manual_export_ready = _int_value(manual_import.get("ready_preview_count")) > 0
    manual_export_bad = _int_value(manual_import.get("error_preview_count")) > 0
    ga4_ready = bool(ga4_connector.get("ready"))
    source_ready = current_demand_processed or manual_export_ready or ga4_ready

    if require_current_demand:
        passed = current_demand_processed
        reason = (
            "Current demand evidence is already processed."
            if passed
            else "Current demand evidence has not been processed yet."
        )
    else:
        passed = source_ready and not manual_export_bad
        reason = (
            "A usable demand source is ready for Hermes."
            if passed
            else "No usable demand source is ready for Hermes."
        )
    exit_code = 0 if passed else (3 if manual_export_bad else 2)

    return {
        "gate": "argus_demand_source",
        "status": "pass" if passed else "fail",
        "exit_code": exit_code,
        "reason": reason,
        "tenant_slug": readiness.get("tenant_slug"),
        "readiness_status": readiness_status,
        "next_hermes_action": readiness.get("next_hermes_action"),
        "require_current_demand": require_current_demand,
        "checks": {
            "source_ready": source_ready,
            "current_demand_processed": current_demand_processed,
            "manual_export_ready": manual_export_ready,
            "manual_export_bad": manual_export_bad,
            "ga4_ready": ga4_ready,
            "processed_row_count": processed_rows,
        },
        "readiness_summary": {
            "summary": readiness.get("summary"),
            "manual_drop_folder": manual_import.get("drop_folder"),
            "manual_inbox_file_count": _int_value(manual_import.get("inbox_file_count")),
            "manual_ready_preview_count": _int_value(manual_import.get("ready_preview_count")),
            "manual_error_preview_count": _int_value(manual_import.get("error_preview_count")),
            "ga4_enabled": bool(ga4_connector.get("enabled")),
            "ga4_ready": ga4_ready,
            "ga4_missing_required": list(ga4_connector.get("missing_required") or []),
            "ga4_setup_required": list(ga4_connector.get("setup_required") or []),
            "demand_source_contract_status": source_contract.get("status"),
            "ready_demand_source_count": _int_value(source_contract.get("ready_source_count")),
            "demand_source_ids": demand_source_ids(source_contract),
            "demand_plan_status": demand_plan.get("status"),
            "demand_plan_topic_count": _int_value(demand_plan.get("topic_count")),
            "demand_plan_top_topics": list(demand_plan.get("top_topics") or [])[:5],
        },
        "safety": {
            "secret_values_included": False,
            "credentials_reported_as_booleans_only": True,
        },
    }


def write_payload(payload: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(f"{json.dumps(payload, indent=2, sort_keys=True)}\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check whether Argus has a usable inward-demand source.")
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--app-dir", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--work-root", type=Path, default=Path("/tmp/cios-product-market"))
    parser.add_argument("--dashboard", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--require-current-demand",
        action="store_true",
        help="Fail unless demand has already been processed into the current dashboard state.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    readiness = build_readiness(
        tenant_slug=args.tenant,
        app_dir=args.app_dir.expanduser(),
        work_root=args.work_root.expanduser(),
        dashboard=_load_json(_dashboard_path(args.dashboard, app_dir=args.app_dir.expanduser())),
    )
    gate = evaluate_gate(
        readiness,
        require_current_demand=bool(args.require_current_demand),
    )
    if args.output:
        write_payload(gate, args.output)
    else:
        print(json.dumps(gate, indent=2, sort_keys=True))
    return int(gate["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
