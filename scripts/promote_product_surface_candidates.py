#!/usr/bin/env python3
"""Promote validated product-surface candidates into active monitoring."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cios.db.repos.product_surfaces import PgProductSurfaceRepository  # noqa: E402
from cios.db.session import get_connection  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402


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
    parser.add_argument("--discovery-source", default="product_muscle_gap_plan")
    parser.add_argument("--promoted-by", default="hermes")
    parser.add_argument("--company-name")
    parser.add_argument("--company-id", type=int)
    parser.add_argument("--surface-family")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    with get_connection() as conn:
        tenant_id = _resolve_tenant_id(conn, tenant_id=args.tenant_id, tenant_slug=args.tenant_slug)
        promoted = PgProductSurfaceRepository(conn).promote_validated_candidates(
            tenant_id=tenant_id,
            discovery_source=args.discovery_source,
            promoted_by=args.promoted_by,
            company_name=args.company_name,
            company_id=args.company_id,
            surface_family=args.surface_family,
            limit=args.limit,
        )
        conn.commit()

    payload = {
        "status": "completed",
        "promoted_count": len(promoted),
        "promoted_surfaces": [target.model_dump(mode="json") for target in promoted],
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
