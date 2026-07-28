#!/usr/bin/env python3
"""Record human acceptance of an Argus recommendation as approved learning.

This is the positive counterpart to `record_recommendation_challenge.py`.
Acceptance is not a free pass to mutate code or Hermes behavior. It records a
traceable learning event and an already-approved CI-OS package learning item,
so the existing next-sweep/apply-plan gates can prove the learning effect.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import psycopg
from psycopg.rows import dict_row

from cios.db.repos.learn import PgImprovementQueueRepository, PgLearningEventRepository
from cios.db.session import get_dsn
from cios.learn.recorder import ImprovementQueueRepository, LearningEventRepository
from cios.learn.types import (
    ImprovementItem,
    ImprovementPriority,
    ImprovementStatus,
    LearningEvent,
    LearningEventType,
)


def resolve_tenant_id(conn, tenant_slug: str) -> int:
    row = conn.execute("SELECT id FROM tenants WHERE slug = %s", (tenant_slug,)).fetchone()
    if not row:
        raise ValueError(f"unknown tenant slug: {tenant_slug}")
    return int(row["id"])


def _clean(value: str, field: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field} is required")
    return cleaned


def record_acceptance(
    *,
    learning_events: LearningEventRepository,
    improvement_queue: ImprovementQueueRepository,
    tenant_id: int,
    recommendation_id: int,
    action: str,
    rationale: str,
    accepted_by: str,
    run_id: str | None = None,
    named_team: str | None = None,
) -> dict[str, Any]:
    if recommendation_id <= 0:
        raise ValueError("recommendation acceptance requires recommendation_id")
    action = _clean(action, "action")
    rationale = _clean(rationale, "rationale")
    accepted_by = _clean(accepted_by, "accepted_by")
    team = _clean(named_team or "Product Marketing", "named_team")

    lesson = (
        f"{accepted_by} accepted recommendation {recommendation_id} for {team}; "
        f"action: {action}; rationale: {rationale}"
    )
    proposed_change = (
        "In the next sweep, keep product proof plus rising audience demand as an action-grade priority when it "
        "reveals a narrative gap; preserve the recommendation unless newer evidence contradicts it or confidence "
        f"limits worsen. Accepted action: {action}"
    )
    event = learning_events.insert(
        LearningEvent(
            tenant_id=tenant_id,
            run_id=run_id,
            event_type=LearningEventType.USER_FEEDBACK,
            lesson=lesson,
            proposed_change=proposed_change,
        )
    )
    improvement = improvement_queue.insert(
        ImprovementItem(
            tenant_id=tenant_id,
            source=f"argus_recommendation_acceptance:{recommendation_id}",
            problem=lesson,
            proposed_fix=proposed_change,
            priority=ImprovementPriority.HIGH,
            status=ImprovementStatus.APPROVED,
        )
    )
    return {
        "tenant_id": tenant_id,
        "recommendation_id": recommendation_id,
        "accepted_by": accepted_by,
        "named_team": team,
        "learning_event_id": event.id,
        "improvement_id": improvement.id,
        "improvement_status": improvement.status.value,
        "next_sweep_instruction": proposed_change,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", required=True, help="Tenant slug, for example algolia")
    parser.add_argument("--recommendation-id", required=True, type=int)
    parser.add_argument("--action", required=True)
    parser.add_argument("--rationale", required=True)
    parser.add_argument("--accepted-by", required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--named-team", default="Product Marketing")
    args = parser.parse_args(argv)

    with psycopg.connect(get_dsn(), autocommit=True, row_factory=dict_row) as conn:
        tenant_id = resolve_tenant_id(conn, args.tenant)
        payload = record_acceptance(
            learning_events=PgLearningEventRepository(conn),
            improvement_queue=PgImprovementQueueRepository(conn),
            tenant_id=tenant_id,
            recommendation_id=args.recommendation_id,
            action=args.action,
            rationale=args.rationale,
            accepted_by=args.accepted_by,
            run_id=args.run_id,
            named_team=args.named_team,
        )

    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
