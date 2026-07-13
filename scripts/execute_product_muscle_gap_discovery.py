#!/usr/bin/env python3
"""Validate product-muscle gap candidates and store accepted product surfaces."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cios.collect.fetcher import HttpContentFetcher, ProbeFetcherAdapter  # noqa: E402
from cios.db.repos.product_surfaces import PgProductSurfaceRepository  # noqa: E402
from cios.db.session import get_connection  # noqa: E402
from cios.hunter.validator import SourceValidator  # noqa: E402
from cios.intelligence.product_muscle_gap_discovery import execute_product_muscle_gap_discovery  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402


def _load_gap_plan(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    if "missing_companies" in data or "feature_unknown_collection_targets" in data:
        return data
    product_market_run = data.get("product_market_run")
    if isinstance(product_market_run, dict) and isinstance(product_market_run.get("product_muscle_gap_plan"), dict):
        return dict(product_market_run["product_muscle_gap_plan"])
    product_market_summary = data.get("product_market_summary")
    if isinstance(product_market_summary, dict) and isinstance(
        product_market_summary.get("product_muscle_gap_plan"), dict
    ):
        return dict(product_market_summary["product_muscle_gap_plan"])
    raise ValueError(f"{path} does not contain product_muscle_gap_plan")


def _resolve_tenant_id(conn: Any, *, tenant_id: int | None, tenant_slug: str | None) -> int:
    if tenant_id is not None:
        return tenant_id
    slug = str(tenant_slug or "").strip()
    if not slug:
        raise ValueError("Either --tenant or --tenant-id is required")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id FROM tenants WHERE slug = %s", (slug,))
        row = cur.fetchone()
    if not row:
        raise ValueError(f"tenant slug not found: {slug}")
    return int(row["id"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    tenant_group = parser.add_mutually_exclusive_group(required=True)
    tenant_group.add_argument("--tenant", dest="tenant_slug", help="Tenant slug, e.g. algolia.")
    tenant_group.add_argument("--tenant-id", type=int)
    parser.add_argument("--gap-plan", required=True, help="Gap-plan JSON or dashboard JSON containing product_muscle_gap_plan.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--fetch-timeout-seconds", type=float, default=8.0)
    parser.add_argument("--fetch-retries", type=int, default=0)
    args = parser.parse_args(argv)

    gap_plan = _load_gap_plan(Path(args.gap_plan))
    with get_connection() as conn:
        tenant_id = _resolve_tenant_id(conn, tenant_id=args.tenant_id, tenant_slug=args.tenant_slug)
        product_surface_repo = PgProductSurfaceRepository(conn)

        class _ExistingLookup:
            def exists(self, tenant_id: int, normalized_url: str) -> bool:
                return product_surface_repo.get_by_normalized_url(tenant_id, normalized_url) is not None

        validator = SourceValidator(
            fetcher=ProbeFetcherAdapter(HttpContentFetcher(timeout=args.fetch_timeout_seconds, retries=args.fetch_retries)),
            existing_sources=_ExistingLookup(),
        )
        summary = execute_product_muscle_gap_discovery(
            tenant_id=tenant_id,
            gap_plan=gap_plan,
            validator=validator,
            product_surfaces=product_surface_repo,
        )
        conn.commit()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
