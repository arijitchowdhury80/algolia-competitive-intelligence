#!/usr/bin/env python3
"""Record a user challenge to an Argus recommendation.

Hermes can call this command from an agent action or run console without
importing CI-OS internals into Hermes core. The command writes a
learning_events row, queues improvement work when applicable, and prints a
machine-readable JSON summary.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import psycopg
from psycopg.rows import dict_row

from cios.db.repos.learn import PgImprovementQueueRepository, PgLearningEventRepository
from cios.db.session import get_dsn
from cios.learn.recommendation_challenge import RecommendationChallengeCategory, RecommendationChallengeRecorder


def resolve_tenant_id(conn, tenant_slug: str) -> int:
    row = conn.execute("SELECT id FROM tenants WHERE slug = %s", (tenant_slug,)).fetchone()
    if not row:
        raise ValueError(f"unknown tenant slug: {tenant_slug}")
    return int(row["id"])


def record_challenge(
    *,
    learning_events,
    improvement_queue,
    tenant_id: int,
    recommendation_id: int,
    challenge: str,
    category: str,
    run_id: str | None = None,
    scorecard_dimension: str | None = None,
) -> dict:
    result = RecommendationChallengeRecorder(learning_events, improvement_queue).record_challenge(
        tenant_id=tenant_id,
        recommendation_id=recommendation_id,
        run_id=run_id,
        challenge=challenge,
        category=category,
        scorecard_dimension=scorecard_dimension,
    )
    return {
        "tenant_id": tenant_id,
        "recommendation_id": recommendation_id,
        "category": category,
        "learning_event_id": result.event.id,
        "improvement_id": result.improvement.id if result.improvement else None,
        "next_sweep_instruction": result.next_sweep_instruction,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", required=True, help="Tenant slug, for example algolia")
    parser.add_argument("--recommendation-id", required=True, type=int)
    parser.add_argument("--challenge", required=True)
    parser.add_argument(
        "--category",
        required=True,
        choices=[category.value for category in RecommendationChallengeCategory],
    )
    parser.add_argument("--run-id")
    parser.add_argument("--scorecard-dimension")
    args = parser.parse_args(argv)

    with psycopg.connect(get_dsn(), autocommit=True, row_factory=dict_row) as conn:
        tenant_id = resolve_tenant_id(conn, args.tenant)
        payload = record_challenge(
            learning_events=PgLearningEventRepository(conn),
            improvement_queue=PgImprovementQueueRepository(conn),
            tenant_id=tenant_id,
            recommendation_id=args.recommendation_id,
            challenge=args.challenge,
            category=args.category,
            run_id=args.run_id,
            scorecard_dimension=args.scorecard_dimension,
        )

    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
