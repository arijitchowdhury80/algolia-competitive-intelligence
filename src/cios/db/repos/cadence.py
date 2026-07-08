"""Postgres implementations of brain/cadence.py's ledger Protocols.

Schema-gap workaround (see docs/planning, and daily_production_run.py's
top-level comment for the full rationale): there is no dedicated table for
weekly synthesis results. PgWeeklyResultLedger stores each week's
WeeklySynthesisResult as JSON inside `reports.metadata` on the `reports` row
created for that weekly report (cadence='weekly'), keyed as:

    {"weekly_synthesis": {"<competitor_id>": {...WeeklySynthesisResult...}}}

and reconstructs it later by scanning `reports` for the tenant/cadence/date
window and pulling the competitor's entry back out of metadata.

Second gap: `semantic_deltas` has no owner/team_to_involve/signal_type
columns preserved 1:1 with the brain's Signal pydantic model. See the inline
comment in PgDailySignalLedger.signals_for_week below for the documented
default used until that column exists.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row

from cios.brain.types import Signal, WeeklySynthesisResult
from cios.db.session import tenant_context


class PgDailySignalLedger:
    """Implements brain.cadence.DailySignalLedger against `semantic_deltas`."""

    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def signals_for_week(self, tenant_id: int, competitor_id: int, week_start: date) -> list[Signal]:
        week_end = week_start + timedelta(days=7)
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT id, competitor_id, delta_type, materiality_score, what_changed,
                           why_it_matters, implication, recommended_action, evidence_ids,
                           confidence, created_at
                    FROM semantic_deltas
                    WHERE tenant_id = %s AND competitor_id = %s AND quality_status = 'published'
                      AND created_at >= %s AND created_at < %s
                    ORDER BY created_at ASC
                    """,
                    (tenant_id, competitor_id, week_start, week_end),
                )
                rows = cur.fetchall()

        signals: list[Signal] = []
        for row in rows:
            signals.append(
                Signal(
                    competitor_id=row["competitor_id"],
                    # semantic_deltas does not persist owner/team_to_involve;
                    # generic default used until that column exists (known gap)
                    signal_type=row["delta_type"] or "signal",
                    headline=row["what_changed"] or "",
                    what_changed=row["what_changed"] or "",
                    why_it_matters=row["why_it_matters"],
                    implication=row["implication"],
                    recommended_action=row["recommended_action"] or "",
                    owner="PMM",
                    team_to_involve="Product",
                    materiality_score=float(row["materiality_score"] or 0.0),
                    confidence=float(row["confidence"]) if row["confidence"] is not None else None,
                    evidence_urls=list(row["evidence_ids"] or []),
                )
            )
        return signals


class PgWeeklyResultLedger:
    """Implements brain.cadence.WeeklyResultLedger against `reports.metadata`.

    No table stores weekly synthesis results (schema-gap workaround, see
    module docstring): each weekly report row's metadata jsonb carries the
    per-competitor WeeklySynthesisResult under key "weekly_synthesis".
    """

    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def weeklies_for_month(
        self, tenant_id: int, competitor_id: int, month_start: date
    ) -> list[WeeklySynthesisResult]:
        if month_start.month == 12:
            next_month_start = date(month_start.year + 1, 1, 1)
        else:
            next_month_start = date(month_start.year, month_start.month + 1, 1)

        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT metadata FROM reports
                    WHERE tenant_id = %s AND cadence = 'weekly'
                      AND report_date >= %s AND report_date < %s
                    ORDER BY report_date ASC
                    """,
                    (tenant_id, month_start, next_month_start),
                )
                rows = cur.fetchall()

        results: list[WeeklySynthesisResult] = []
        for row in rows:
            metadata: dict[str, Any] = row["metadata"] or {}
            entry = (metadata.get("weekly_synthesis") or {}).get(str(competitor_id))
            if entry:
                results.append(WeeklySynthesisResult.model_validate(entry))
        return results
