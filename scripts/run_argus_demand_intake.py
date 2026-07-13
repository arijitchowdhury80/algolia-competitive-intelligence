#!/usr/bin/env python3
"""Run the Hermes-facing inward-demand intake loop for Argus.

This is the package-level coordinator Hermes can call before an Argus replay:

1. Inspect demand readiness.
2. If a manual GA / Looker export is queued, process the queued file.
3. If GA4 is ready, export GA4 into the same queue and process it.
4. If no usable source exists, return a structured blocked result.

The script does not modify Hermes core. It orchestrates CI-OS package commands
and writes a machine-readable result so Hermes can decide the next action.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cios.admin.demand_imports import Ga4DemandExportControl

from export_argus_demand_readiness import build_demand_readiness_payload
from import_demand_and_refresh import import_demand_exports


SUCCESSFUL_IMPORT_STATUSES = {"prepared", "refreshed", "published"}


def _default_app_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _demand_intake_history_path(*, work_root: Path, tenant: str) -> Path:
    run_root = work_root / tenant / "demand-intake-runs"
    stamp = _stamp()
    candidate = run_root / stamp / "demand-intake-summary.json"
    if not candidate.exists():
        return candidate
    index = 2
    while True:
        candidate = run_root / f"{stamp}-{index}" / "demand-intake-summary.json"
        if not candidate.exists():
            return candidate
        index += 1


def _write_json_payload(payload: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json_payload(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists() or path.stat().st_size == 0:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _as_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return dict(value)
    return dict(value)


def _blocked_result(*, tenant: str, readiness: dict[str, Any], exit_code: int) -> dict[str, Any]:
    return {
        "status": str(readiness.get("status") or "blocked"),
        "exit_code": exit_code,
        "tenant": tenant,
        "mode": "blocked",
        "next_hermes_action": readiness.get("next_hermes_action"),
        "readiness": readiness,
        "ga4_export": None,
        "demand_import": None,
    }


def _import_ready_demand(
    *,
    tenant: str,
    tenant_id: int | None,
    app_dir: Path,
    work_root: Path,
    persist_demand: bool,
    refresh: bool,
    rerender: bool,
    own_company_name: str | None,
    days: int,
    limit: int,
    out_dir: Path | None,
    publish: bool,
    public_dir: Path | None,
    python_bin: str | None,
    demand_plan: dict[str, Any] | None,
    demand_change_floor: float | None,
    demand_value_floor: float | None,
    importer: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    return importer(
        tenant=tenant,
        tenant_id=tenant_id,
        inputs=[],
        app_dir=app_dir,
        work_root=work_root,
        prepare_only=False,
        persist_demand=persist_demand,
        refresh=refresh,
        rerender=rerender,
        own_company_name=own_company_name,
        days=days,
        limit=limit,
        out_dir=out_dir,
        publish=publish,
        public_dir=public_dir,
        python_bin=python_bin,
        demand_plan=demand_plan,
        require_ready=True,
        demand_change_floor=demand_change_floor,
        demand_value_floor=demand_value_floor,
    )


def run_demand_intake(
    *,
    tenant: str,
    app_dir: Path,
    work_root: Path,
    tenant_id: int | None = None,
    persist_demand: bool = True,
    refresh: bool = True,
    rerender: bool = True,
    own_company_name: str | None = None,
    days: int = 30,
    limit: int = 500,
    out_dir: Path | None = None,
    publish: bool = False,
    public_dir: Path | None = None,
    python_bin: str | None = None,
    dashboard: dict[str, Any] | None = None,
    demand_change_floor: float | None = None,
    demand_value_floor: float | None = None,
    readiness_builder: Callable[..., dict[str, Any]] = build_demand_readiness_payload,
    ga4_control: Any | None = None,
    importer: Callable[..., dict[str, Any]] = import_demand_exports,
) -> dict[str, Any]:
    readiness = readiness_builder(
        tenant_slug=tenant,
        app_dir=app_dir,
        work_root=work_root,
        dashboard=dashboard,
    )
    readiness_status = str(readiness.get("status") or "unknown")

    if readiness_status == "processed":
        return {
            "status": "demand_already_processed",
            "exit_code": 0,
            "tenant": tenant,
            "mode": "already_processed",
            "next_hermes_action": readiness.get("next_hermes_action"),
            "readiness": readiness,
            "ga4_export": None,
            "demand_import": None,
        }

    if readiness_status == "blocked_bad_manual_export":
        return _blocked_result(tenant=tenant, readiness=readiness, exit_code=3)

    if readiness_status not in {"queued_manual_exports", "ready_to_export_ga4"}:
        return _blocked_result(tenant=tenant, readiness=readiness, exit_code=2)

    demand_plan = (
        readiness.get("demand_collection_plan")
        if isinstance(readiness.get("demand_collection_plan"), dict)
        else None
    )
    mode = "queued_manual_export"
    ga4_export: dict[str, Any] | None = None
    if readiness_status == "ready_to_export_ga4":
        mode = "ga4_export"
        control = ga4_control or Ga4DemandExportControl(app_dir=app_dir)
        try:
            ga4_export = _as_dict(control.run(tenant, demand_plan=demand_plan))
        except Exception as exc:  # noqa: BLE001 - operator script must return structured failure.
            return {
                "status": "ga4_export_failed",
                "exit_code": 1,
                "tenant": tenant,
                "mode": mode,
                "next_hermes_action": "repair_ga4_export",
                "readiness": readiness,
                "ga4_export": {"status": "error", "error": f"{exc.__class__.__name__}: {exc}"},
                "demand_import": None,
            }

    demand_import = _import_ready_demand(
        tenant=tenant,
        tenant_id=tenant_id,
        app_dir=app_dir,
        work_root=work_root,
        persist_demand=persist_demand,
        refresh=refresh,
        rerender=rerender,
        own_company_name=own_company_name,
        days=days,
        limit=limit,
        out_dir=out_dir,
        publish=publish,
        public_dir=public_dir,
        python_bin=python_bin,
        demand_plan=demand_plan,
        demand_change_floor=demand_change_floor,
        demand_value_floor=demand_value_floor,
        importer=importer,
    )
    if str(demand_import.get("status") or "") not in SUCCESSFUL_IMPORT_STATUSES:
        return {
            "status": "demand_import_failed",
            "exit_code": 1,
            "tenant": tenant,
            "mode": mode,
            "next_hermes_action": "repair_queued_demand_export",
            "readiness": readiness,
            "ga4_export": ga4_export,
            "demand_import": demand_import,
        }

    return {
        "status": (
            "ga4_exported_demand_imported_and_argus_refreshed"
            if ga4_export is not None
            else "demand_imported_and_argus_refreshed"
        ),
        "exit_code": 0,
        "tenant": tenant,
        "mode": mode,
        "next_hermes_action": "continue_product_market_synthesis",
        "readiness": readiness,
        "ga4_export": ga4_export,
        "demand_import": demand_import,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Argus inward-demand intake and replay.")
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--app-dir", type=Path, default=_default_app_dir())
    parser.add_argument("--work-root", type=Path, default=Path("/tmp/cios-product-market"))
    parser.add_argument("--tenant-id", type=int, help="Optional tenant id for demand-ledger persistence.")
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--public-dir", type=Path)
    parser.add_argument("--dashboard", type=Path)
    parser.add_argument("--own-company-name")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--demand-change-floor", type=float, help="Minimum fractional demand lift for rising demand")
    parser.add_argument("--demand-value-floor", type=float, help="Minimum metric value for rising demand")
    parser.add_argument("--python-bin")
    parser.add_argument("--skip-ledger-persist", action="store_true")
    parser.add_argument("--skip-refresh", action="store_true")
    parser.add_argument("--skip-rerender", action="store_true")
    parser.add_argument(
        "--record-history",
        action="store_true",
        help="Also write a durable demand-intake history summary under --work-root.",
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_demand_intake(
        tenant=args.tenant,
        tenant_id=args.tenant_id,
        app_dir=args.app_dir.expanduser(),
        work_root=args.work_root.expanduser(),
        persist_demand=not args.skip_ledger_persist,
        refresh=not args.skip_refresh,
        rerender=not args.skip_rerender,
        own_company_name=args.own_company_name,
        days=args.days,
        limit=args.limit,
        out_dir=args.out_dir.expanduser() if args.out_dir else None,
        publish=args.publish,
        public_dir=args.public_dir.expanduser() if args.public_dir else None,
        python_bin=args.python_bin,
        dashboard=_load_json_payload(args.dashboard.expanduser() if args.dashboard else None),
        demand_change_floor=args.demand_change_floor,
        demand_value_floor=args.demand_value_floor,
    )
    payload = dict(result)
    if args.record_history:
        history_path = _demand_intake_history_path(work_root=args.work_root.expanduser(), tenant=args.tenant)
        payload["generated_at"] = payload.get("generated_at") or _now()
        payload["summary_path"] = str(history_path)
        payload["run_output_dir"] = str(history_path.parent)
        _write_json_payload(payload, history_path)

    text = json.dumps(payload, indent=2, sort_keys=True)
    if args.output:
        _write_json_payload(payload, args.output)
    print(text)
    return int(payload["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
