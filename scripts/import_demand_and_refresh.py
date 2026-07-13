#!/usr/bin/env python3
"""Import GA / Looker demand evidence and refresh Argus from persisted ledgers.

This is the operator fast lane for the inward demand plane. It does not crawl
outward competitor sources and it does not implement a second synthesis path.
It reuses the CI-OS package layers:

1. Copy provided exports into the tenant demand drop folder.
2. Normalize queued exports with DemandImportStore.prepare().
3. Optionally run refresh_product_market_from_ledger.py.
4. Optionally rerender dashboard artifacts from current DB state.

Usage:
  .venv/bin/python scripts/import_demand_and_refresh.py \
      --tenant algolia --input /path/to/looker.csv

  .venv/bin/python scripts/import_demand_and_refresh.py \
      --tenant algolia --queued
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import psycopg
from psycopg.rows import dict_row

from cios.admin.demand_imports import DemandImportLedgerPersister, DemandImportStore
from cios.admin.types import DemandImportCreate
from cios.dashboard.artifacts import publish_dashboard_artifacts
from cios.db.repos.product_market import PgProductMarketRepository
from cios.db.session import get_dsn


def _script_dir() -> Path:
    return Path(__file__).resolve().parent


def _default_app_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def _copy_inputs(
    store: DemandImportStore,
    tenant: str,
    inputs: list[Path],
    *,
    demand_plan: dict[str, Any] | None = None,
) -> list[str]:
    copied: list[str] = []
    for source in inputs:
        content = source.read_text(encoding="utf-8")
        uploaded = store.upload(
            tenant,
            DemandImportCreate(filename=source.name, content=content),
            demand_plan=demand_plan,
        )
        copied.append(uploaded.path)
    return copied


def _load_json_file(path: Path) -> dict[str, Any] | None:
    if not path.exists() or path.stat().st_size == 0:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _extract_demand_collection_plan(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None

    direct = payload.get("demand_collection_plan")
    if isinstance(direct, dict) and isinstance(direct.get("topics"), list):
        return direct

    planes = payload.get("planes")
    if isinstance(planes, dict):
        demand_plane = planes.get("audience_demand")
        if isinstance(demand_plane, dict):
            details = demand_plane.get("details")
            if isinstance(details, dict):
                plan = details.get("demand_collection_plan")
                if isinstance(plan, dict) and isinstance(plan.get("topics"), list):
                    return plan

    if isinstance(payload.get("topics"), list):
        return payload
    return None


def _demand_plan_candidates(
    *,
    tenant: str,
    app_dir: Path,
    work_root: Path,
    out_dir: Path,
    explicit_path: Path | None,
) -> list[Path]:
    candidates: list[Path] = []
    if explicit_path is not None:
        candidates.append(explicit_path)
    candidates.extend(
        [
            out_dir / "argus-demand-readiness.json",
            out_dir / "argus-data-plane-manifest.json",
            app_dir / "out" / "argus-demand-readiness.json",
            app_dir / "out" / "argus-data-plane-manifest.json",
            work_root / tenant / "argus-demand-readiness.json",
            work_root / tenant / "argus-data-plane-manifest.json",
            app_dir / "data" / "looker" / tenant / "argus-demand-plan.json",
        ]
    )
    deduped: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _load_current_demand_plan(
    *,
    tenant: str,
    app_dir: Path,
    work_root: Path,
    out_dir: Path,
    explicit_path: Path | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    candidates = _demand_plan_candidates(
        tenant=tenant,
        app_dir=app_dir,
        work_root=work_root,
        out_dir=out_dir,
        explicit_path=explicit_path,
    )
    for path in candidates:
        payload = _load_json_file(path)
        plan = _extract_demand_collection_plan(payload)
        if plan is not None:
            topics = plan.get("topics") if isinstance(plan.get("topics"), list) else []
            return plan, {
                "status": "loaded",
                "source_path": str(path),
                "topic_count": len(topics),
            }
    return None, {
        "status": "not_found",
        "candidate_paths": [str(path) for path in candidates],
        "topic_count": 0,
    }


def _provided_demand_plan_summary(plan: dict[str, Any]) -> dict[str, Any]:
    topics = plan.get("topics") if isinstance(plan.get("topics"), list) else []
    return {
        "status": "provided",
        "source_path": None,
        "topic_count": len(topics),
    }


def _run_command(cmd: list[str], *, cwd: Path) -> dict[str, Any]:
    completed = subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "command": cmd,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def _parse_json_stdout(stdout: str) -> dict[str, Any] | None:
    text = stdout.strip()
    if not text:
        return None
    candidates = [text, *[line.strip() for line in reversed(text.splitlines()) if line.strip()]]
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _write_json_payload(payload: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(f"{json.dumps(payload, indent=2, sort_keys=True)}\n", encoding="utf-8")


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


def _argus_read_from_refresh(refresh_result: dict[str, Any]) -> dict[str, Any] | None:
    if int(refresh_result.get("returncode", 1)) != 0:
        return None
    parsed = _parse_json_stdout(str(refresh_result.get("stdout") or ""))
    if not parsed:
        return None
    brief = parsed.get("intelligence_brief") if isinstance(parsed.get("intelligence_brief"), dict) else {}
    demand_read = brief.get("demand_read") if isinstance(brief.get("demand_read"), dict) else {}
    demand_recommendation_trace = (
        brief.get("demand_recommendation_trace")
        if isinstance(brief.get("demand_recommendation_trace"), dict)
        else {}
    )
    conversion = (
        brief.get("conversion_diagnostics")
        if isinstance(brief.get("conversion_diagnostics"), dict)
        else parsed.get("conversion_diagnostics")
    )
    if not isinstance(conversion, dict):
        conversion = {}
    return {
        "verdict": parsed.get("verdict"),
        "top_insight": brief.get("top_insight"),
        "primary_action": brief.get("primary_action"),
        "demand_summary": demand_read.get("summary"),
        "conversion_summary": conversion.get("summary"),
        "demand_recommendation_trace": demand_recommendation_trace,
        "counts": {
            "product_events": int(parsed.get("product_event_count") or 0),
            "conversation_themes": int(parsed.get("conversation_theme_count") or 0),
            "demand_signals": int(parsed.get("demand_signal_count") or 0),
            "patterns": int(parsed.get("pattern_count") or 0),
            "recommendations": int(parsed.get("recommendation_count") or 0),
        },
    }


def _demand_intake_payload(
    *,
    summary: dict[str, Any],
    mode: str,
    summary_path: Path,
) -> dict[str, Any]:
    demand_import = {
        "tenant": summary.get("tenant"),
        "copied_inputs": summary.get("copied_inputs") or [],
        "prepare": summary.get("prepare") or {},
    }
    for key in ("demand_ledger", "argus_read"):
        if key in summary:
            demand_import[key] = summary[key]
    return {
        "status": "demand_imported_and_argus_refreshed",
        "command_status": "ok",
        "exit_code": 0,
        "mode": mode,
        "next_hermes_action": "continue_product_market_synthesis",
        "summary_path": str(summary_path),
        "demand_import": demand_import,
    }


def _write_demand_intake_history(*, payload: dict[str, Any], path: Path) -> dict[str, str]:
    _write_json_payload(payload, path)
    return {
        "status": "written",
        "path": str(path),
        "run_output_dir": str(path.parent),
    }


def _refresh_post_rerender_artifacts(
    *,
    tenant: str,
    app_dir: Path,
    work_root: Path,
    out_dir: Path,
    python: str,
    demand_intake_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Refresh the Hermes/Argus sidecars that make a rerender operational.

    The demand fast lane is not just "rerender HTML." Once demand changes,
    Hermes needs the same public operating artifacts the daily wrapper creates:
    demand readiness, evidence queue, operator handoff, and dashboard JSON/HTML
    with those artifacts attached before any publish step copies files public.
    """

    dashboard = out_dir / "argus-dashboard.json"
    html = out_dir / "argus-dashboard.html"
    demand_readiness = out_dir / "argus-demand-readiness.json"
    demand_plan_template = out_dir / "argus-demand-plan-template.csv"
    demand_intake = out_dir / "argus-demand-intake.json"
    evidence_queue = out_dir / "argus-evidence-work-queue.json"
    product_muscle_queue = out_dir / "argus-product-muscle-work-queue.json"
    handoff = out_dir / "argus-operator-handoff.json"
    data_plane_manifest = out_dir / "argus-data-plane-manifest.json"
    results: dict[str, Any] = {}

    if demand_intake_payload is not None:
        _write_json_payload(demand_intake_payload, demand_intake)
        results["demand_intake"] = {"status": "written", "path": str(demand_intake)}

    commands: list[tuple[str, list[str]]] = [
        (
            "demand_readiness",
            [
                python,
                str(_script_dir() / "export_argus_demand_readiness.py"),
                "--tenant",
                tenant,
                "--app-dir",
                str(app_dir),
                "--work-root",
                str(work_root),
                "--dashboard",
                str(dashboard),
                "--output",
                str(demand_readiness),
            ],
        ),
        (
            "demand_plan_template",
            [
                python,
                str(_script_dir() / "export_argus_demand_plan_template.py"),
                "--readiness",
                str(demand_readiness),
                "--output",
                str(demand_plan_template),
            ],
        ),
        (
            "attach_demand_readiness",
            [
                python,
                str(_script_dir() / "attach_post_run_summaries.py"),
                "--dashboard",
                str(dashboard),
                "--demand-readiness",
                str(demand_readiness),
            ],
        ),
        (
            "evidence_work_queue",
            [
                python,
                str(_script_dir() / "export_argus_evidence_work_queue.py"),
                "--tenant",
                tenant,
                "--output",
                str(evidence_queue),
            ],
        ),
        (
            "product_muscle_work_queue",
            [
                python,
                str(_script_dir() / "export_argus_product_muscle_work_queue.py"),
                "--tenant",
                tenant,
                "--work-root",
                str(work_root),
                "--demand-readiness",
                str(demand_readiness),
                "--output",
                str(product_muscle_queue),
            ],
        ),
        (
            "operator_handoff",
            [
                python,
                str(_script_dir() / "build_argus_operator_handoff.py"),
                "--tenant",
                tenant,
                "--work-queue",
                str(evidence_queue),
                "--product-muscle-queue",
                str(product_muscle_queue),
                "--demand-readiness",
                str(demand_readiness),
                "--demand-plan-template",
                str(demand_plan_template),
                "--dashboard",
                str(dashboard),
                "--output",
                str(handoff),
            ],
        ),
        (
            "attach_operator_handoff",
            [
                python,
                str(_script_dir() / "attach_operator_handoff_to_dashboard.py"),
                "--dashboard",
                str(dashboard),
                "--handoff",
                str(handoff),
                "--html",
                str(html),
            ],
        ),
        (
            "data_plane_manifest",
            [
                python,
                str(_script_dir() / "export_argus_data_plane_manifest.py"),
                "--tenant",
                tenant,
                "--dashboard",
                str(dashboard),
                "--demand-readiness",
                str(demand_readiness),
                "--demand-plan-template",
                str(demand_plan_template),
                "--demand-intake",
                str(demand_intake),
                "--evidence-work-queue",
                str(evidence_queue),
                "--product-muscle-work-queue",
                str(product_muscle_queue),
                "--operator-handoff",
                str(handoff),
                "--output",
                str(data_plane_manifest),
            ],
        ),
    ]

    for name, cmd in commands:
        result = _run_command(cmd, cwd=app_dir)
        results[name] = result
        if result["returncode"] != 0:
            results["failed_step"] = name
            return results
    return results


def _resolve_tenant_id(tenant: str) -> int:
    with psycopg.connect(get_dsn(), autocommit=True, row_factory=dict_row) as conn:
        row = conn.execute("SELECT id FROM tenants WHERE slug = %s", (tenant,)).fetchone()
    if not row:
        raise ValueError(f"unknown tenant slug: {tenant}")
    return int(row["id"])


def _persist_prepared_demand(
    *,
    tenant_id: int,
    prepared,
    demand_import_ledger_persister=None,
) -> dict[str, Any]:
    if demand_import_ledger_persister is not None:
        persister = demand_import_ledger_persister
        result = (
            persister.persist(tenant_id=tenant_id, prepared=prepared)
            if hasattr(persister, "persist")
            else persister(tenant_id=tenant_id, prepared=prepared)
        )
    else:
        with psycopg.connect(get_dsn(), autocommit=True) as conn:
            result = DemandImportLedgerPersister(
                repository=PgProductMarketRepository(conn),
            ).persist(tenant_id=tenant_id, prepared=prepared)
    if hasattr(result, "model_dump"):
        return result.model_dump(mode="json")
    return dict(result)


def _archive_consumed_demand(
    *,
    store: DemandImportStore,
    tenant: str,
    prepared,
    summary: dict[str, Any],
) -> bool:
    demand_ledger = summary.get("demand_ledger")
    if not isinstance(demand_ledger, dict) or demand_ledger.get("status") != "persisted":
        return True
    try:
        summary["archive"] = store.archive_prepared(tenant, prepared)
    except Exception as exc:  # noqa: BLE001 - keep operator failure structured.
        summary["status"] = "archive_failed"
        summary["archive"] = {"status": "error", "error": f"{exc.__class__.__name__}: {exc}"}
        return False
    return True


def import_demand_exports(
    *,
    tenant: str,
    tenant_id: int | None = None,
    inputs: list[Path],
    app_dir: Path,
    work_root: Path,
    prepare_only: bool = False,
    persist_demand: bool = True,
    demand_import_ledger_persister=None,
    refresh: bool = True,
    rerender: bool = True,
    own_company_name: str | None = None,
    days: int = 30,
    limit: int = 500,
    out_dir: Path | None = None,
    publish: bool = False,
    public_dir: Path | None = None,
    python_bin: str | None = None,
    demand_plan: dict[str, Any] | None = None,
    demand_plan_path: Path | None = None,
    require_ready: bool = False,
    demand_change_floor: float | None = None,
    demand_value_floor: float | None = None,
) -> dict[str, Any]:
    store = DemandImportStore(app_dir=app_dir, work_root=work_root)
    python = python_bin or sys.executable
    run_out_dir = out_dir or (app_dir / "out")
    if demand_plan is not None:
        demand_plan_summary = _provided_demand_plan_summary(demand_plan)
    else:
        demand_plan, demand_plan_summary = _load_current_demand_plan(
            tenant=tenant,
            app_dir=app_dir,
            work_root=work_root,
            out_dir=run_out_dir,
            explicit_path=demand_plan_path,
        )
    copied_inputs = _copy_inputs(store, tenant, inputs, demand_plan=demand_plan)
    prepared = store.prepare(tenant, demand_plan=demand_plan)
    summary: dict[str, Any] = {
        "status": "prepared",
        "tenant": tenant,
        "demand_plan": demand_plan_summary,
        "copied_inputs": copied_inputs,
        "prepare": prepared.model_dump(mode="json"),
    }

    if require_ready and prepared.ready_count == 0:
        summary["status"] = "no_ready_demand"
        summary["error"] = "No ready GA / Looker demand exports were found in the tenant demand drop folder."
        return summary

    if prepare_only:
        return summary

    if persist_demand:
        resolved_tenant_id = tenant_id if tenant_id is not None else _resolve_tenant_id(tenant)
        try:
            summary["demand_ledger"] = _persist_prepared_demand(
                tenant_id=resolved_tenant_id,
                prepared=prepared,
                demand_import_ledger_persister=demand_import_ledger_persister,
            )
        except Exception as exc:  # noqa: BLE001 - operator CLI should return structured failure.
            summary["status"] = "demand_persist_failed"
            summary["demand_ledger"] = {"status": "error", "error": f"{exc.__class__.__name__}: {exc}"}
            return summary

    if refresh:
        refresh_cmd = [
            python,
            str(_script_dir() / "refresh_product_market_from_ledger.py"),
            "--tenant",
            tenant,
            "--days",
            str(days),
            "--limit",
            str(limit),
        ]
        if own_company_name:
            refresh_cmd.extend(["--own-company-name", own_company_name])
        if demand_change_floor is not None:
            refresh_cmd.extend(["--demand-change-floor", str(demand_change_floor)])
        if demand_value_floor is not None:
            refresh_cmd.extend(["--demand-value-floor", str(demand_value_floor)])
        summary["refresh"] = _run_command(refresh_cmd, cwd=app_dir)
        if summary["refresh"]["returncode"] != 0:
            summary["status"] = "refresh_failed"
            return summary
        argus_read = _argus_read_from_refresh(summary["refresh"])
        if argus_read:
            summary["argus_read"] = argus_read

    if rerender:
        rerender_cmd = [
            python,
            str(_script_dir() / "rerender_dashboard.py"),
            "--tenant",
            tenant,
            "--out-dir",
            str(run_out_dir),
        ]
        summary["rerender"] = _run_command(rerender_cmd, cwd=app_dir)
        if summary["rerender"]["returncode"] != 0:
            summary["status"] = "rerender_failed"
            return summary
        if not _archive_consumed_demand(store=store, tenant=tenant, prepared=prepared, summary=summary):
            return summary
        demand_intake_path = run_out_dir / "argus-demand-intake.json"
        demand_intake_mode = "manual_upload" if summary.get("copied_inputs") else "queued_manual_export"
        demand_intake_history_path = _demand_intake_history_path(work_root=work_root, tenant=tenant)
        demand_intake_payload = _demand_intake_payload(
            summary=summary,
            mode=demand_intake_mode,
            summary_path=demand_intake_history_path,
        )
        summary["post_rerender_artifacts"] = _refresh_post_rerender_artifacts(
            tenant=tenant,
            app_dir=app_dir,
            work_root=work_root,
            out_dir=run_out_dir,
            python=python,
            demand_intake_payload=demand_intake_payload,
        )
        failed_step = summary["post_rerender_artifacts"].get("failed_step")
        if failed_step:
            summary["status"] = "artifact_refresh_failed"
            return summary
        summary["demand_intake_history"] = _write_demand_intake_history(
            payload=demand_intake_payload,
            path=demand_intake_history_path,
        )

    if publish:
        if public_dir is None:
            summary["status"] = "publish_failed"
            summary["publish"] = {"status": "error", "error": "--public-dir is required when publish=True"}
            return summary
        try:
            summary["publish"] = publish_dashboard_artifacts(out_dir=run_out_dir, public_dir=public_dir)
        except Exception as exc:  # noqa: BLE001 - operator CLI must return a structured failure.
            summary["status"] = "publish_failed"
            summary["publish"] = {"status": "error", "error": f"{exc.__class__.__name__}: {exc}"}
            return summary
        if "archive" not in summary and not _archive_consumed_demand(
            store=store,
            tenant=tenant,
            prepared=prepared,
            summary=summary,
        ):
            return summary
        summary["status"] = "published"
        return summary

    if "archive" not in summary and not _archive_consumed_demand(
        store=store,
        tenant=tenant,
        prepared=prepared,
        summary=summary,
    ):
        return summary
    summary["status"] = "refreshed"
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import GA / Looker demand evidence and refresh Argus.")
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--input", action="append", help="CSV, JSON, or JSONL GA / Looker export.")
    parser.add_argument(
        "--queued",
        action="store_true",
        help="Process GA / Looker exports already queued in the tenant demand drop folder.",
    )
    parser.add_argument("--app-dir", type=Path, default=_default_app_dir())
    parser.add_argument("--work-root", type=Path, default=Path("/tmp/cios-product-market"))
    parser.add_argument("--tenant-id", type=int, help="Optional tenant id for demand-ledger persistence.")
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--publish", action="store_true", help="Publish rerendered artifacts into --public-dir.")
    parser.add_argument("--public-dir", type=Path, help="Public dashboard directory. Required with --publish.")
    parser.add_argument(
        "--demand-plan",
        type=Path,
        help="Optional Argus demand plan, readiness, or data-plane manifest JSON to match imports against.",
    )
    parser.add_argument("--own-company-name")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--demand-change-floor", type=float, help="Minimum fractional demand lift for rising demand")
    parser.add_argument("--demand-value-floor", type=float, help="Minimum metric value for rising demand")
    parser.add_argument("--python-bin")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--skip-ledger-persist", action="store_true")
    parser.add_argument("--skip-refresh", action="store_true")
    parser.add_argument("--skip-rerender", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    raw_inputs = args.input or []
    if not raw_inputs and not args.queued:
        parser.error("--input is required unless --queued is set")

    inputs = [Path(value).expanduser() for value in raw_inputs]
    for input_path in inputs:
        if not input_path.is_file():
            raise FileNotFoundError(f"demand input not found: {input_path}")

    summary = import_demand_exports(
        tenant=args.tenant,
        tenant_id=args.tenant_id,
        inputs=inputs,
        app_dir=args.app_dir.expanduser(),
        work_root=args.work_root.expanduser(),
        prepare_only=args.prepare_only,
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
        demand_plan_path=args.demand_plan.expanduser() if args.demand_plan else None,
        require_ready=args.queued and not raw_inputs,
        demand_change_floor=args.demand_change_floor,
        demand_value_floor=args.demand_value_floor,
    )
    text = json.dumps(summary, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if summary["status"] in {"prepared", "refreshed", "published"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
