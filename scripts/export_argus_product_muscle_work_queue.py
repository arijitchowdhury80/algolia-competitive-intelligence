#!/usr/bin/env python3
"""Export the Hermes-facing Argus product-muscle work queue artifact."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import psycopg

from cios.admin.feature_comparison import build_feature_comparison_state
from cios.admin.product_muscle_work_queue import build_product_muscle_work_queue
from cios.admin.product_surface_execution_trace import ProductSurfaceExecutionTraceStore
from cios.admin.repository import PgAdminRepository
from cios.admin.types import EvidenceLedgerState, FeatureComparisonState, RegistryState
from cios.db.session import get_dsn


def resolve_tenant_id(conn, tenant_slug: str) -> int:
    row = conn.execute("SELECT id FROM tenants WHERE slug = %s", (tenant_slug,)).fetchone()
    if not row:
        raise ValueError(f"unknown tenant slug: {tenant_slug}")
    if isinstance(row, dict):
        return int(row["id"])
    return int(row[0])


def build_product_muscle_work_queue_payload(
    *,
    tenant_slug: str,
    tenant_id: int,
    registry: RegistryState,
    feature_comparison: FeatureComparisonState,
    evidence_ledger: EvidenceLedgerState,
    product_surface_execution_trace: dict[tuple[str, str], dict] | None = None,
    generated_at: str | None = None,
) -> dict:
    items = build_product_muscle_work_queue(
        tenant_slug=tenant_slug,
        registry=registry,
        feature_comparison=feature_comparison,
        evidence_ledger=evidence_ledger,
        product_surface_execution_trace=product_surface_execution_trace,
    )
    return {
        "tenant_slug": tenant_slug,
        "tenant_id": tenant_id,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "work_item_count": len(items),
        "blocking_count": sum(1 for item in items if item.severity == "blocks_feature_matrix"),
        "limiting_count": sum(1 for item in items if item.severity != "blocks_feature_matrix"),
        "items": [item.model_dump(mode="json") for item in items],
    }


def write_payload(payload: dict, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(f"{json.dumps(payload, indent=2, sort_keys=True)}\n", encoding="utf-8")


def planned_capabilities_from_demand_readiness(payload: Mapping[str, Any] | None) -> list[str]:
    if not isinstance(payload, Mapping):
        return []
    plan = payload.get("demand_collection_plan")
    if not isinstance(plan, Mapping):
        return []
    topics = plan.get("topics")
    if not isinstance(topics, list):
        return []
    capabilities: list[str] = []
    seen: set[str] = set()
    for topic in topics:
        if not isinstance(topic, Mapping):
            continue
        label = _first_text(
            topic.get("topic"),
            topic.get("capability_text"),
            topic.get("capability"),
            topic.get("capability_key"),
        )
        if not label:
            continue
        key = " ".join(label.lower().split())
        if key in seen:
            continue
        seen.add(key)
        capabilities.append(label)
    return capabilities


def _feature_comparison_state(
    repo: PgAdminRepository,
    tenant_slug: str,
    registry: RegistryState,
    *,
    demand_readiness: Mapping[str, Any] | None = None,
) -> FeatureComparisonState:
    return build_feature_comparison_state(
        registry=registry,
        feature_matrix=repo.feature_matrix(tenant_slug),
        planned_capabilities=planned_capabilities_from_demand_readiness(demand_readiness),
        own_company_name=tenant_slug.replace("-", " ").title(),
    )


def _load_json_object(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object at {path}")
    return payload


def _first_text(*values: Any) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return " ".join(text.split())
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", required=True, help="Tenant slug, for example algolia")
    parser.add_argument("--output", help="Optional JSON artifact path. Prints to stdout when omitted.")
    parser.add_argument("--work-root", help="Product-market work root containing latest product-surface artifacts.")
    parser.add_argument("--demand-readiness", help="argus-demand-readiness.json with the active Argus demand plan.")
    args = parser.parse_args(argv)
    demand_readiness = _load_json_object(args.demand_readiness)

    with psycopg.connect(get_dsn(), autocommit=True) as conn:
        tenant_id = resolve_tenant_id(conn, args.tenant)
        repo = PgAdminRepository(conn)
        registry = RegistryState.model_validate(repo.registry(args.tenant))
        surface_trace = ProductSurfaceExecutionTraceStore(
            work_root=Path(args.work_root) if args.work_root else None,
        ).status(args.tenant)
        payload = build_product_muscle_work_queue_payload(
            tenant_slug=args.tenant,
            tenant_id=tenant_id,
            registry=registry,
            feature_comparison=_feature_comparison_state(
                repo,
                args.tenant,
                registry,
                demand_readiness=demand_readiness,
            ),
            evidence_ledger=EvidenceLedgerState.model_validate(repo.evidence_ledger(args.tenant)),
            product_surface_execution_trace=surface_trace,
        )

    if args.output:
        write_payload(payload, Path(args.output))
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
