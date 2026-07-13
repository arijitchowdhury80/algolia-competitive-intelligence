#!/usr/bin/env python3
"""Refresh Argus product-market intelligence from persisted ledgers.

This is a CI-OS package entrypoint intended for Hermes job execution after
new demand evidence is imported. It does not crawl outward sources and does
not duplicate source ledger rows. It replays existing product, conversation,
and demand ledgers through the Argus synthesis layer, then stores the derived
patterns, recommendations, and run intelligence summary.

Usage:
  .venv/bin/python scripts/refresh_product_market_from_ledger.py \
      --tenant algolia --own-company-name Algolia
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import psycopg
from psycopg.rows import dict_row

from cios.db.repos.product_market import PgProductMarketRepository
from cios.db.session import get_dsn
from cios.intelligence.demand_quality import DemandQualityConfig
from cios.intelligence.runner import run_product_market_ledger_refresh


def load_learning_instructions(path: Path | None) -> list[dict]:
    if path is None:
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    instructions = data.get("instructions") if isinstance(data, dict) else []
    if not isinstance(instructions, list):
        return []
    return [dict(item) for item in instructions if isinstance(item, dict)]


def resolve_tenant_id(conn, tenant_slug: str) -> int:
    row = conn.execute("SELECT id FROM tenants WHERE slug = %s", (tenant_slug,)).fetchone()
    if not row:
        raise ValueError(f"unknown tenant slug: {tenant_slug}")
    return int(row["id"])


def _default_own_company_name(tenant_slug: str) -> str:
    return tenant_slug.replace("-", " ").title()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", required=True, help="Tenant slug to replay, for example algolia")
    parser.add_argument("--own-company-name", help="Tenant company name; defaults from tenant slug")
    parser.add_argument("--days", type=int, default=30, help="Lookback window for replayed ledgers")
    parser.add_argument("--limit", type=int, default=500, help="Maximum rows per ledger plane")
    parser.add_argument("--learning-plan", help="Optional next-sweep learning plan JSON")
    parser.add_argument("--demand-change-floor", type=float, help="Minimum fractional demand lift for rising demand")
    parser.add_argument("--demand-value-floor", type=float, help="Minimum metric value for rising demand")
    args = parser.parse_args(argv)

    own_company_name = args.own_company_name or _default_own_company_name(args.tenant)
    learning_instructions = load_learning_instructions(Path(args.learning_plan)) if args.learning_plan else []
    demand_quality = DemandQualityConfig(
        change_floor=(
            DemandQualityConfig().change_floor
            if args.demand_change_floor is None
            else args.demand_change_floor
        ),
        value_floor=(
            DemandQualityConfig().value_floor
            if args.demand_value_floor is None
            else args.demand_value_floor
        ),
    )
    with psycopg.connect(get_dsn(), autocommit=True, row_factory=dict_row) as conn:
        tenant_id = resolve_tenant_id(conn, args.tenant)
        summary = run_product_market_ledger_refresh(
            tenant_id=tenant_id,
            own_company_name=own_company_name,
            repository=PgProductMarketRepository(conn),
            days=args.days,
            limit=args.limit,
            learning_instructions=learning_instructions,
            demand_quality=demand_quality,
        )

    print(json.dumps(summary.model_dump(mode="json"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
