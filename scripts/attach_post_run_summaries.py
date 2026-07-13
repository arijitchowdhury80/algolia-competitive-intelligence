#!/usr/bin/env python3
"""Attach post-run product muscle loop summaries to a dashboard JSON artifact.

The daily runner renders the dashboard before the wrapper performs post-run
gap discovery and validated-candidate promotion. This script makes those
post-run actions visible to the same run state before the public publish step.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


def _load_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists() or path.stat().st_size == 0:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _count_from(summary: dict[str, Any], *keys: str) -> int:
    for key in keys:
        try:
            value = int(summary.get(key) or 0)
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            return value
    return 0


def _next_sweep_status(
    gap_summary: dict[str, Any],
    promotion_summary: dict[str, Any],
) -> str:
    if not gap_summary and not promotion_summary:
        return "No post-run product muscle loop summaries were recorded."

    stored = _count_from(gap_summary, "stored_candidate_count")
    candidates_seen = _count_from(gap_summary, "candidate_url_count")
    duplicate_surfaces = _count_from(
        gap_summary,
        "duplicate_product_surface_count",
        "duplicate_source_count",
    )
    new_candidate_rejections = _count_from(gap_summary, "new_candidate_rejected_count")
    promoted = _count_from(promotion_summary, "promoted_count")
    parts: list[str] = []
    if stored:
        parts.append(f"queued {stored} candidate product surfaces")
    if promoted:
        parts.append(f"activated {promoted} validated sources")

    if parts:
        return f"Hermes {' and '.join(parts)} for the next sweep."

    if candidates_seen and duplicate_surfaces == candidates_seen:
        return (
            f"Hermes rechecked {duplicate_surfaces} already-monitored product surfaces; "
            "no new sweepable sources were added for the next sweep."
        )

    if candidates_seen and duplicate_surfaces:
        return (
            f"Hermes reviewed {candidates_seen} product-surface checks: "
            f"{duplicate_surfaces} were already monitored and "
            f"{new_candidate_rejections} were rejected; no new sweepable sources were added."
        )

    if candidates_seen:
        return (
            f"Hermes found {candidates_seen} candidate product surfaces, but none were new "
            "sweepable surfaces for the next sweep."
        )

    gap_status = str(gap_summary.get("status") or "not recorded").strip()
    promotion_status = str(promotion_summary.get("status") or "not recorded").strip()
    return f"Hermes recorded post-run loop status: gap discovery {gap_status}; promotion {promotion_status}."


def attach_post_run_summaries(
    dashboard: dict[str, Any],
    *,
    gap_summary: dict[str, Any],
    promotion_summary: dict[str, Any],
    demand_readiness: dict[str, Any] | None = None,
) -> dict[str, Any]:
    updated = dict(dashboard)
    run = updated.get("product_market_run")
    if not isinstance(run, dict):
        run = {}
    else:
        run = dict(run)
    run["post_run_product_muscle_gap_discovery"] = dict(gap_summary)
    run["post_run_product_surface_promotion"] = dict(promotion_summary)
    run["post_run_next_sweep_status"] = _next_sweep_status(gap_summary, promotion_summary)
    if demand_readiness:
        run["demand_readiness"] = dict(demand_readiness)
    updated["product_market_run"] = run
    return updated


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")
    tmp.replace(path)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Attach post-run summaries to argus-dashboard.json.")
    parser.add_argument("--dashboard", required=True, type=Path, help="Dashboard JSON artifact to update.")
    parser.add_argument(
        "--gap-summary",
        type=Path,
        default=None,
        help="Product muscle gap discovery summary JSON.",
    )
    parser.add_argument(
        "--candidate-promotion-summary",
        type=Path,
        default=None,
        help="Product surface candidate promotion summary JSON.",
    )
    parser.add_argument(
        "--demand-readiness",
        type=Path,
        default=None,
        help="Argus inward-demand readiness summary JSON.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional output path. Defaults to updating --dashboard in place.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    dashboard = _load_json(args.dashboard)
    updated = attach_post_run_summaries(
        dashboard,
        gap_summary=_load_json(args.gap_summary),
        promotion_summary=_load_json(args.candidate_promotion_summary),
        demand_readiness=_load_json(args.demand_readiness),
    )
    out_path = args.output or args.dashboard
    _write_json_atomic(out_path, updated)
    print(f"attached post-run summaries to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
