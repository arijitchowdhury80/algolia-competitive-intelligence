"""Re-render the cockpit + brief from CURRENT DB state — no fetching, no LLM.

The 15-minute pipeline is for making new intelligence; this script is for
refreshing the SCREEN from what the ledger already knows (~seconds). It runs
the same DashboardStateBuilder the daily runner uses, wired to the same Pg
repos, with coverage/run context carried over from the last published state
JSON (those two are run-time facts; everything else is ledger truth).

Usage (inside the hermes container):
  cd /opt/data/apps/cios && .venv/bin/python scripts/rerender_dashboard.py \
      [--tenant algolia] [--out-dir /opt/data/apps/cios/out]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import psycopg
from psycopg.rows import dict_row

from cios.dashboard.cockpit_renderer import render_brief_page, render_cockpit_html
from cios.db.repos.dashboard import PgReportHistoryRepository, PgSuppressedSignalsRepository
from cios.dashboard.state_builder import DashboardStateBuilder


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "daily_production_run", Path(__file__).resolve().parent / "daily_production_run.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", default="algolia")
    ap.add_argument("--out-dir", default=str(Path(__file__).resolve().parents[1] / "out"))
    args = ap.parse_args()

    runner = _load_runner()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    saved = json.load(open(out_dir / "argus-dashboard.json"))

    conn = psycopg.connect(runner.app_dsn(runner.get_dsn()), autocommit=True, row_factory=dict_row)
    tenant = conn.execute("SELECT id FROM tenants WHERE slug = %s", (args.tenant,)).fetchone()
    if not tenant:
        print(f"unknown tenant {args.tenant}", file=sys.stderr)
        return 2
    tenant_id = tenant["id"]

    builder = DashboardStateBuilder(
        signals=runner.DbMaterialSignals(conn),
        theses=runner.DbTheses(conn),
        coverage=runner.DbCoverage(saved.get("coverage") or {}),
        runs=runner.DbRuns(saved.get("run_health") or saved.get("run") or {}),
        report_history=PgReportHistoryRepository(conn),
        suppressed_signals=PgSuppressedSignalsRepository(conn),
        prescriptions=runner.PgPrescriptionsRepository(conn),
    )
    state = builder.build(tenant_id=tenant_id, cadence="daily")

    cockpit = render_cockpit_html(state)
    (out_dir / "argus-dashboard.html").write_text(cockpit)
    (out_dir / "argus-dashboard.json").write_text(runner.to_json_str(state))

    # brief.html from the newest rendered report's markdown for this tenant.
    row = conn.execute(
        "SELECT metadata, title, report_date FROM reports WHERE tenant_id = %s "
        "ORDER BY report_date DESC, id DESC LIMIT 1",
        (tenant_id,),
    ).fetchone()
    brief_md = ""
    if row:
        meta = row["metadata"] or {}
        if isinstance(meta, str):
            meta = json.loads(meta or "{}")
        brief_md = meta.get("reader_text") or meta.get("markdown") or ""
    if brief_md:
        brief_html = render_brief_page(brief_md, str(row["report_date"]))
        (out_dir / "brief.html").write_text(brief_html)
        print("brief.html written")
    else:
        print("no report markdown found; brief.html not written")

    print(f"re-rendered cockpit {len(cockpit)} bytes from live DB state")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
