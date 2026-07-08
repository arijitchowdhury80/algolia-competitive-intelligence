"""Postgres implementations of the dashboard/state_builder.py Protocols that
back the "Report history", "Suppressed Signals", and role-lens "plays"
panels of Arijit's original dashboard layout.

All three are straight reads off tables that already exist for other
purposes (`reports`, `suppressed_diagnostics`, `action_items`) -- no schema
changes needed.
"""

from __future__ import annotations

from psycopg import Connection
from psycopg.rows import dict_row

from cios.db.session import tenant_context


class PgReportHistoryRepository:
    """Implements dashboard.state_builder.ReportHistoryRepository against
    `reports`."""

    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def get_recent_reports(self, tenant_id: int, limit: int = 10) -> list[dict]:
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT id, report_date, cadence, title, summary, status, html_path
                    FROM reports
                    WHERE tenant_id = %s
                    ORDER BY report_date DESC, id DESC
                    LIMIT %s
                    """,
                    (tenant_id, limit),
                )
                return [dict(r) for r in cur.fetchall()]


def _action_item_to_prescription_row(row: dict) -> dict:
    """Reverses cios.brief... prescription_to_action_item's fold (see
    scripts/daily_production_run.py) back into the shape
    dashboard.state_builder.PrescriptionsRepository needs.

    action_items has no dedicated title/play/expected_effect columns --
    prescription_to_action_item folded `f"{title}: {steps joined by '; '}"`
    into `recommendation` on write, so this splits on the first ": " to
    recover them. A prescription with no play steps was written as just its
    bare title (no ": "), which round-trips to title=recommendation,
    play=[]. `expected_effect` has no column at all and is genuinely lost on
    write, not just unread here -- it renders as absent, never fabricated.
    """
    recommendation = row.get("recommendation") or ""
    if ": " in recommendation:
        title, steps = recommendation.split(": ", 1)
        play = [step.strip() for step in steps.split("; ") if step.strip()]
    else:
        title, play = recommendation, []
    return {
        "title": title,
        "team": row.get("owner") or "",
        "play": play,
        "urgency_window": row.get("priority") or row.get("due_window") or "this_month",
        "expected_effect": None,
        "evidence_urls": list(row.get("evidence_ids") or []),
    }


# Priority/due_window ordering for the lens plays list -- most urgent first,
# same three-value vocabulary as cios.prescribe.types.UrgencyWindow.
_URGENCY_SORT_ORDER = {"act_now": 0, "this_week": 1, "this_month": 2}


class PgPrescriptionsRepository:
    """Implements dashboard.state_builder.PrescriptionsRepository against
    `action_items` -- the table the daily/weekly run already persists
    prescribed plays to (prescription_to_action_item + insert_action_item in
    scripts/daily_production_run.py). Scoped to today's action items so the
    lenses show this cycle's plays, not every open action item ever
    recorded."""

    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def get_current_prescriptions(self, tenant_id: int) -> list[dict]:
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT owner, recommendation, evidence_ids, priority, due_window, created_at
                    FROM action_items
                    WHERE tenant_id = %s AND created_at::date = CURRENT_DATE
                    ORDER BY created_at DESC
                    """,
                    (tenant_id,),
                )
                rows = [dict(r) for r in cur.fetchall()]
        rows.sort(key=lambda r: _URGENCY_SORT_ORDER.get(r.get("priority"), 99))
        return [_action_item_to_prescription_row(r) for r in rows]


class PgSuppressedSignalsRepository:
    """Implements dashboard.state_builder.SuppressedSignalsRepository
    against `suppressed_diagnostics`."""

    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def get_recent_suppressed(self, tenant_id: int, limit: int = 10) -> list[dict]:
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT id, reason, finding_ids, suppressed_at, notes
                    FROM suppressed_diagnostics
                    WHERE tenant_id = %s
                    ORDER BY suppressed_at DESC
                    LIMIT %s
                    """,
                    (tenant_id, limit),
                )
                return [dict(r) for r in cur.fetchall()]
