"""Postgres implementations of the dashboard/state_builder.py Protocols that
back the "Report history", "Suppressed Signals", role-lens "plays",
monitored competitor registry, and source-health panels of Arijit's original
dashboard layout.

These are straight reads off tables that already exist for other purposes
(`reports`, `suppressed_diagnostics`, `action_items`, `competitors`,
`sources`, `source_health_events`, `semantic_deltas`) -- no schema changes
needed.
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
                    WITH latest_per_period AS (
                        SELECT DISTINCT ON (report_date, cadence)
                               id, report_date, cadence, title, summary, status, html_path
                        FROM reports
                        WHERE tenant_id = %s
                        ORDER BY report_date DESC, cadence, id DESC
                    )
                    SELECT id, report_date, cadence, title, summary, status, html_path
                    FROM latest_per_period
                    ORDER BY report_date DESC, cadence
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


class PgMonitoredCompetitorsRepository:
    """Implements dashboard.state_builder.MonitoredCompetitorsRepository.

    This is the full active competitor registry, not the material-signal
    barometer. A competitor with zero published deltas still appears here if
    it is active and has monitored sources.
    """

    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def get_monitored_competitors(self, tenant_id: int) -> list[dict]:
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    WITH latest_health AS (
                        SELECT DISTINCT ON (h.source_id)
                               h.source_id, h.event_type, h.created_at
                        FROM source_health_events h
                        WHERE h.tenant_id = %s
                        ORDER BY h.source_id, h.created_at DESC
                    ),
                    material_counts AS (
                        SELECT competitor_id,
                               COUNT(*) AS material_signal_count,
                               MAX(created_at) AS last_material_signal_at
                        FROM semantic_deltas
                        WHERE tenant_id = %s
                          AND quality_status = 'published'
                          AND created_at >= now() - interval '14 days'
                        GROUP BY competitor_id
                    ),
                    latest_delta AS (
                        SELECT DISTINCT ON (competitor_id)
                               competitor_id, what_changed AS latest_movement_summary
                        FROM semantic_deltas
                        WHERE tenant_id = %s
                          AND quality_status = 'published'
                          AND created_at >= now() - interval '14 days'
                        ORDER BY competitor_id, created_at DESC, id DESC
                    )
                    SELECT c.id AS competitor_id,
                           c.name AS competitor_name,
                           c.domain,
                           c.category,
                           c.status,
                           COUNT(s.id)::int AS source_count,
                           COUNT(s.id) FILTER (WHERE s.status = 'active')::int AS active_source_count,
                           COUNT(s.id) FILTER (
                               WHERE latest_health.event_type IN ('fetch_error','http_error','timeout','empty')
                           )::int AS failed_source_count,
                           MAX(COALESCE(latest_health.created_at, s.last_checked_at)) AS last_checked_at,
                           COALESCE(
                               MAX(COALESCE(latest_health.created_at, s.last_checked_at))::date = CURRENT_DATE,
                               false
                           ) AS checked_today,
                           COALESCE(material_counts.material_signal_count, 0)::int AS material_signal_count,
                           material_counts.last_material_signal_at,
                           latest_delta.latest_movement_summary,
                           COALESCE(
                               jsonb_agg(
                                   jsonb_build_object(
                                       'source_id', s.id,
                                       'source_family', s.source_family,
                                       'url', s.url,
                                       'normalized_url', s.normalized_url,
                                       'status', s.status,
                                       'last_checked_at', s.last_checked_at
                                   )
                                   ORDER BY s.source_family ASC, s.id ASC
                               ) FILTER (WHERE s.id IS NOT NULL AND s.status = 'active'),
                               '[]'::jsonb
                           ) AS monitored_sources
                    FROM competitors c
                    LEFT JOIN sources s
                      ON s.tenant_id = c.tenant_id
                     AND s.competitor_id = c.id
                     AND s.status <> 'retired'
                    LEFT JOIN latest_health ON latest_health.source_id = s.id
                    LEFT JOIN material_counts ON material_counts.competitor_id = c.id
                    LEFT JOIN latest_delta ON latest_delta.competitor_id = c.id
                    WHERE c.tenant_id = %s
                      AND c.status = 'active'
                    GROUP BY c.id, c.name, c.domain, c.category, c.status,
                             material_counts.material_signal_count,
                             material_counts.last_material_signal_at,
                             latest_delta.latest_movement_summary
                    ORDER BY c.priority ASC, c.name ASC
                    """,
                    (tenant_id, tenant_id, tenant_id, tenant_id),
                )
                return [dict(r) for r in cur.fetchall()]


class PgSourceHealthRepository:
    """Implements dashboard.state_builder.SourceHealthRepository against
    source_health_events + sources."""

    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def get_source_health(self, tenant_id: int) -> list[dict]:
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    WITH latest_health AS (
                        SELECT DISTINCT ON (h.source_id)
                               h.source_id,
                               h.event_type AS latest_event_type,
                               h.http_status,
                               h.detail,
                               h.created_at AS checked_at
                        FROM source_health_events h
                        WHERE h.tenant_id = %s
                        ORDER BY h.source_id, h.created_at DESC
                    )
                    SELECT s.id AS source_id,
                           s.competitor_id,
                           c.name AS competitor_name,
                           s.source_family,
                           s.url,
                           s.status,
                           latest_health.latest_event_type,
                           latest_health.http_status,
                           latest_health.detail,
                           COALESCE(latest_health.checked_at, s.last_checked_at) AS checked_at
                    FROM sources s
                    JOIN competitors c ON c.id = s.competitor_id AND c.tenant_id = s.tenant_id
                    LEFT JOIN latest_health ON latest_health.source_id = s.id
                    WHERE s.tenant_id = %s
                      AND c.status = 'active'
                      AND s.status <> 'retired'
                    ORDER BY
                      CASE
                        WHEN latest_health.latest_event_type IN ('fetch_error','http_error','timeout','empty') THEN 0
                        WHEN latest_health.latest_event_type IS NULL THEN 1
                        ELSE 2
                      END,
                      c.priority ASC,
                      c.name ASC,
                      s.source_family ASC,
                      s.id ASC
                    """,
                    (tenant_id, tenant_id),
                )
                return [dict(r) for r in cur.fetchall()]
