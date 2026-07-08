"""Postgres implementations of the dashboard/state_builder.py Protocols that
back the "Report history" and "Suppressed Signals" panels of Arijit's
original dashboard layout.

Both are straight reads off tables that already exist for other purposes
(`reports`, `suppressed_diagnostics`) -- no schema changes needed.
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
