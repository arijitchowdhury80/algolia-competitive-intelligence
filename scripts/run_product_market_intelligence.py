#!/usr/bin/env python3
"""Run one product-market intelligence import/synthesis pass.

This is a CI-OS package entrypoint intended for Hermes cron/job execution.
It does not modify Hermes core. Hermes supplies a JSON payload produced by
Scout, web/conversation collectors, and Looker/GA importers; CI-OS validates,
persists, synthesizes, and prints a machine-readable summary.

Usage:
  .venv/bin/python scripts/run_product_market_intelligence.py \
      --input /path/to/product-market.json

Payload shape:
  {
    "tenant_id": 1,
    "own_company_name": "Algolia",
    "scout_records": [...],
    "conversation_records": [...],
    "looker_rows": [...]
  }
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
from cios.intelligence.runner import (
    ProductMarketRunPayload,
    load_product_market_payload,
    run_product_market_payload,
)


def resolve_tenant_id(conn, tenant_slug: str) -> int:
    row = conn.execute("SELECT id FROM tenants WHERE slug = %s", (tenant_slug,)).fetchone()
    if not row:
        raise ValueError(f"unknown tenant slug: {tenant_slug}")
    return int(row["id"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="JSON payload with Scout, conversation, and Looker/GA rows")
    parser.add_argument("--tenant", help="Optional tenant slug; overrides/sets payload tenant_id from DB")
    parser.add_argument("--own-company-name", help="Optional own company name override")
    parser.add_argument("--demand-change-floor", type=float, help="Override payload demand_quality.change_floor")
    parser.add_argument("--demand-value-floor", type=float, help="Override payload demand_quality.value_floor")
    args = parser.parse_args(argv)

    payload = load_product_market_payload(Path(args.input))

    with psycopg.connect(get_dsn(), autocommit=True, row_factory=dict_row) as conn:
        if args.tenant:
            payload = payload.model_copy(update={"tenant_id": resolve_tenant_id(conn, args.tenant)})
        if args.own_company_name:
            payload = payload.model_copy(update={"own_company_name": args.own_company_name})
        if args.demand_change_floor is not None or args.demand_value_floor is not None:
            payload = payload.model_copy(
                update={
                    "demand_quality": DemandQualityConfig(
                        change_floor=(
                            payload.demand_quality.change_floor
                            if args.demand_change_floor is None
                            else args.demand_change_floor
                        ),
                        value_floor=(
                            payload.demand_quality.value_floor
                            if args.demand_value_floor is None
                            else args.demand_value_floor
                        ),
                    )
                }
            )
        summary = run_product_market_payload(
            ProductMarketRunPayload.model_validate(payload),
            repository=PgProductMarketRepository(conn),
        )

    print(json.dumps(summary.model_dump(mode="json"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
