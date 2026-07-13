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
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import psycopg
from psycopg.rows import dict_row

from cios.db.session import tenant_context
from cios.dashboard.cockpit_renderer import (
    attach_competitor_brief_hrefs,
    render_brief_page_from_state,
    render_cockpit_html,
    render_competitor_brief_page_from_state,
)
from cios.dashboard.publisher import publish_to_file
from cios.db.repos.dashboard import (
    PgMonitoredCompetitorsRepository,
    PgReportHistoryRepository,
    PgSourceHealthRepository,
    PgSuppressedSignalsRepository,
)
from cios.db.repos.product_market import PgProductMarketRepository
from cios.dashboard.state_builder import DashboardStateBuilder


POST_RUN_PRODUCT_MARKET_KEYS = (
    "post_run_product_muscle_gap_discovery",
    "post_run_product_surface_promotion",
    "post_run_next_sweep_status",
    "demand_readiness",
)


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "daily_production_run", Path(__file__).resolve().parent / "daily_production_run.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_dashboard_artifacts(state, *, tenant_slug: str, html_path: Path, report_date: str) -> dict:
    stamped_state = attach_competitor_brief_hrefs(state, tenant_slug=tenant_slug, report_date=report_date)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(render_cockpit_html(stamped_state), encoding="utf-8")

    full_brief_path = html_path.parent / "brief.html"
    full_brief_path.write_text(render_brief_page_from_state(stamped_state, report_date), encoding="utf-8")

    competitor_paths: list[Path] = []
    seen_competitors: set[int] = set()
    brief_targets: list[tuple[int, str]] = [
        (competitor.competitor_id, competitor.brief_href)
        for competitor in stamped_state.monitored_competitors
        if competitor.brief_href
    ] or [
        (card.competitor_id, card.brief_href)
        for card in stamped_state.competitor_cards
        if card.brief_href
    ]
    for competitor_id, brief_href in brief_targets:
        if competitor_id in seen_competitors:
            continue
        seen_competitors.add(competitor_id)
        competitor_path = html_path.parent / brief_href.removeprefix("./")
        competitor_path.parent.mkdir(parents=True, exist_ok=True)
        competitor_path.write_text(
            render_competitor_brief_page_from_state(
                stamped_state,
                competitor_id=competitor_id,
                report_date=report_date,
            ),
            encoding="utf-8",
        )
        competitor_paths.append(competitor_path)

    json_path = html_path.with_suffix(".json")
    publish_to_file(stamped_state, json_path)
    return {
        "cockpit": html_path,
        "full_brief": full_brief_path,
        "json": json_path,
        "competitor_briefs": competitor_paths,
    }


def run_dict_from_saved_dashboard(
    saved: dict[str, Any],
    *,
    latest_product_market_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run = dict(saved.get("run_health") or saved.get("run") or {})
    product_market_run = saved.get("product_market_run")
    if not isinstance(product_market_run, dict):
        if isinstance(latest_product_market_summary, dict):
            run["product_market_summary"] = latest_product_market_summary
        return run

    status = str(product_market_run.get("status") or "").strip()
    if not status or status == "not_recorded":
        return run

    try:
        scout_artifact_count = int(product_market_run.get("scout_artifact_count") or 0)
    except (TypeError, ValueError):
        scout_artifact_count = 0

    intelligence_brief = product_market_run.get("intelligence_brief")
    if not isinstance(intelligence_brief, dict):
        intelligence_brief = {}
    conversion_diagnostics = product_market_run.get("conversion_diagnostics")
    if not isinstance(conversion_diagnostics, dict):
        conversion_diagnostics = {}

    run["product_market_summary"] = {
        "status": status,
        "next_sweep_plan_path": product_market_run.get("next_sweep_plan_path"),
        "product_surface_plan_summary": {
            "target_count": int(product_market_run.get("target_count") or 0),
            "target_company_count": int(product_market_run.get("target_company_count") or 0),
            "target_companies": list(product_market_run.get("target_companies") or []),
            "surface_family_counts": dict(product_market_run.get("surface_family_counts") or {}),
            "learning_prioritized_count": int(product_market_run.get("learning_prioritized_count") or 0),
            "prioritized_targets": list(product_market_run.get("prioritized_targets") or []),
        },
        "product_muscle_gap_plan": dict(product_market_run.get("product_muscle_gap_plan") or {}),
        "post_run_product_muscle_gap_discovery": dict(
            product_market_run.get("post_run_product_muscle_gap_discovery") or {}
        ),
        "post_run_product_surface_promotion": dict(
            product_market_run.get("post_run_product_surface_promotion") or {}
        ),
        "post_run_next_sweep_status": product_market_run.get("post_run_next_sweep_status"),
        "runner_summary": {
            "verdict": product_market_run.get("runner_verdict"),
            "learning_instruction_count": int(product_market_run.get("learning_instruction_count") or 0),
            "learning_instruction_improvement_ids": list(product_market_run.get("consumed_learning_ids") or []),
            "intelligence_brief": dict(intelligence_brief),
            "conversion_diagnostics": dict(conversion_diagnostics),
        },
        "looker_discovered_count": int(product_market_run.get("looker_discovered_count") or 0),
        "looker_ready_count": int(product_market_run.get("looker_ready_count") or 0),
        "looker_error_count": int(product_market_run.get("looker_error_count") or 0),
        "looker_normalized_row_count": int(product_market_run.get("looker_normalized_row_count") or 0),
        "looker_skipped_row_count": int(product_market_run.get("looker_skipped_row_count") or 0),
        "looker_archived_count": int(product_market_run.get("looker_archived_count") or 0),
        "looker_manifest_path": product_market_run.get("looker_manifest_path"),
        "demand_readiness": dict(product_market_run.get("demand_readiness") or {}),
        "scout_paths": [f"rerender-preserved-scout-artifact-{idx}" for idx in range(scout_artifact_count)],
        "errors": list(product_market_run.get("errors") or []),
    }
    if isinstance(latest_product_market_summary, dict):
        run["product_market_summary"] = _merge_post_run_product_market_trace(
            latest_product_market_summary,
            run.get("product_market_summary"),
        )
    return run


def _merge_post_run_product_market_trace(
    latest_summary: dict[str, Any],
    saved_summary: Any,
) -> dict[str, Any]:
    """Keep final report metadata while preserving post-run sidecar evidence.

    The daily wrapper writes the report before executing post-run product
    muscle discovery and candidate promotion. Those sidecar results are then
    attached to the saved dashboard JSON. Rerender should prefer the latest
    report's Argus read, but it must not erase the post-run operational trace.
    """

    merged = dict(latest_summary)
    if not isinstance(saved_summary, dict):
        return merged
    for key in POST_RUN_PRODUCT_MARKET_KEYS:
        if merged.get(key) in (None, "", [], {}):
            saved_value = saved_summary.get(key)
            if saved_value not in (None, "", [], {}):
                merged[key] = saved_value
    return merged


def latest_product_market_summary_from_reports(conn, tenant_id: int) -> dict[str, Any] | None:
    with tenant_context(conn, tenant_id):
        row = conn.execute(
            """
            SELECT metadata->'product_market_summary' AS product_market_summary
            FROM reports
            WHERE tenant_id = %s
              AND metadata ? 'product_market_summary'
            ORDER BY id DESC
            LIMIT 1
            """,
            (tenant_id,),
        ).fetchone()
    if not row:
        return None
    summary = row["product_market_summary"] if isinstance(row, dict) else row[0]
    return summary if isinstance(summary, dict) else None


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
    latest_summary = latest_product_market_summary_from_reports(conn, tenant_id)
    run = run_dict_from_saved_dashboard(saved, latest_product_market_summary=latest_summary)

    builder = DashboardStateBuilder(
        signals=runner.DbMaterialSignals(conn),
        theses=runner.DbTheses(conn),
        coverage=runner.DbCoverage(saved.get("coverage") or {}),
        runs=runner.DbRuns(run),
        report_history=PgReportHistoryRepository(conn),
        suppressed_signals=PgSuppressedSignalsRepository(conn),
        prescriptions=runner.PgPrescriptionsRepository(conn),
        monitored_competitors=PgMonitoredCompetitorsRepository(conn),
        source_health=PgSourceHealthRepository(conn),
        product_market=PgProductMarketRepository(conn),
    )
    state = builder.build(tenant_id=tenant_id, cadence="daily")

    from datetime import date as _date
    report_date = (
        state.report_history[0].report_date.isoformat()
        if state.report_history
        else _date.today().isoformat()
    )
    paths = _write_dashboard_artifacts(
        state,
        tenant_slug=args.tenant,
        html_path=out_dir / "argus-dashboard.html",
        report_date=report_date,
    )

    print(f"brief.html written (state-first)")
    print(f"competitor briefs written: {len(paths['competitor_briefs'])}")
    print(f"re-rendered cockpit {paths['cockpit'].stat().st_size} bytes from live DB state")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
