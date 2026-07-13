#!/usr/bin/env python3
"""Export the Hermes-facing Argus evidence work queue artifact.

This command is part of the CI-OS package. Hermes can run it after the daily
pipeline/rerender to persist the current operator evidence gaps as a
machine-readable artifact without depending on the local-admin HTTP surface.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import psycopg

from cios.admin.evidence_work_queue import build_argus_evidence_work_queue
from cios.admin.repository import PgAdminRepository
from cios.admin.types import ArgusRunStatus, EvidenceLedgerState
from cios.db.session import get_dsn


def resolve_tenant_id(conn, tenant_slug: str) -> int:
    row = conn.execute("SELECT id FROM tenants WHERE slug = %s", (tenant_slug,)).fetchone()
    if not row:
        raise ValueError(f"unknown tenant slug: {tenant_slug}")
    if isinstance(row, dict):
        return int(row["id"])
    return int(row[0])


def build_evidence_work_queue_payload(
    *,
    tenant_slug: str,
    tenant_id: int,
    run_status: ArgusRunStatus,
    evidence_ledger: EvidenceLedgerState,
    generated_at: str | None = None,
) -> dict:
    items = build_argus_evidence_work_queue(
        tenant_slug=tenant_slug,
        run_status=run_status,
        evidence_ledger=evidence_ledger,
    )
    return {
        "tenant_slug": tenant_slug,
        "tenant_id": tenant_id,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "work_item_count": len(items),
        "blocking_count": sum(1 for item in items if item.severity == "blocks_action"),
        "limiting_count": sum(1 for item in items if item.severity != "blocks_action"),
        "items": [item.model_dump(mode="json") for item in items],
    }


def write_payload(payload: dict, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(f"{json.dumps(payload, indent=2, sort_keys=True)}\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", required=True, help="Tenant slug, for example algolia")
    parser.add_argument("--output", help="Optional JSON artifact path. Prints to stdout when omitted.")
    args = parser.parse_args(argv)

    with psycopg.connect(get_dsn(), autocommit=True) as conn:
        tenant_id = resolve_tenant_id(conn, args.tenant)
        repo = PgAdminRepository(conn)
        payload = build_evidence_work_queue_payload(
            tenant_slug=args.tenant,
            tenant_id=tenant_id,
            run_status=ArgusRunStatus.model_validate(repo.latest_run_status(args.tenant)),
            evidence_ledger=EvidenceLedgerState.model_validate(repo.evidence_ledger(args.tenant)),
        )

    if args.output:
        write_payload(payload, Path(args.output))
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
