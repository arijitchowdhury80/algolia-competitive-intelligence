"""Postgres repository for durable CI-OS run-stage ledgers."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Json

from cios.db.repos.collect import _postgres_safe
from cios.db.session import tenant_context


def _stage_event_rows(stage_ledger: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(stage_ledger, start=1):
        if not isinstance(raw, dict):
            continue
        rows.append(
            {
                "stage_order": index,
                "stage": _postgres_safe(str(raw.get("stage") or "")),
                "status": _postgres_safe(str(raw.get("status") or "")),
                "started_at": raw.get("started_at"),
                "ended_at": raw.get("ended_at"),
                "elapsed_s": raw.get("elapsed_s"),
                "error_type": _postgres_safe(raw.get("error_type")),
                "error": _postgres_safe(raw.get("error")),
                "metadata": _postgres_safe(
                    {
                        key: value
                        for key, value in raw.items()
                        if key
                        not in {
                            "stage",
                            "status",
                            "started_at",
                            "ended_at",
                            "elapsed_s",
                            "error_type",
                            "error",
                        }
                    }
                ),
            }
        )
    return rows


class PgRunStageRepository:
    """Persistence boundary for live and completed Hermes-invoked CI-OS runs."""

    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def start_ledger(
        self,
        *,
        tenant_id: int,
        run_id: str,
        package_name: str,
        metadata: dict[str, Any] | None = None,
        started_at: datetime | None = None,
    ) -> int:
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO run_stage_ledgers (
                        tenant_id, run_id, package_name, status, started_at,
                        metadata
                    ) VALUES (
                        %(tenant_id)s, %(run_id)s, %(package_name)s,
                        %(status)s, COALESCE(%(started_at)s, now()),
                        %(metadata)s
                    )
                    RETURNING id
                    """,
                    {
                        "tenant_id": tenant_id,
                        "run_id": _postgres_safe(run_id),
                        "package_name": _postgres_safe(package_name),
                        "status": "running",
                        "started_at": started_at,
                        "metadata": Json(_postgres_safe(metadata or {})),
                    },
                )
                row = cur.fetchone()
        assert row is not None
        return int(row["id"])

    def save_run_stage_ledger(
        self,
        *,
        tenant_id: int,
        run_id: str,
        package_name: str,
        status: str,
        stage_ledger: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Persist an already-completed ordered stage ledger in one call."""

        events = _stage_event_rows(stage_ledger)
        started_at = events[0].get("started_at") if events else None
        ended_at = events[-1].get("ended_at") if events else None
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO run_stage_ledgers (
                        tenant_id, run_id, package_name, status, started_at,
                        ended_at, metadata
                    ) VALUES (
                        %(tenant_id)s, %(run_id)s, %(package_name)s, %(status)s,
                        %(started_at)s, %(ended_at)s, %(metadata)s
                    )
                    RETURNING id
                    """,
                    {
                        "tenant_id": tenant_id,
                        "run_id": _postgres_safe(run_id),
                        "package_name": _postgres_safe(package_name),
                        "status": _postgres_safe(status),
                        "started_at": started_at,
                        "ended_at": ended_at,
                        "metadata": Json(_postgres_safe(metadata or {})),
                    },
                )
                row = cur.fetchone()
                assert row is not None
                ledger_id = int(row["id"])
                if events:
                    cur.execute(
                        """
                        INSERT INTO run_stage_events (
                            tenant_id, ledger_id, stage_order, stage, status,
                            started_at, ended_at, elapsed_s, error_type, error,
                            metadata
                        )
                        SELECT
                            %(tenant_id)s,
                            %(ledger_id)s,
                            event.stage_order,
                            event.stage,
                            event.status,
                            NULLIF(event.started_at, '')::timestamptz,
                            NULLIF(event.ended_at, '')::timestamptz,
                            event.elapsed_s,
                            event.error_type,
                            event.error,
                            COALESCE(event.metadata, '{}'::jsonb)
                        FROM jsonb_to_recordset(%(events)s::jsonb) AS event(
                            stage_order integer,
                            stage text,
                            status text,
                            started_at text,
                            ended_at text,
                            elapsed_s numeric,
                            error_type text,
                            error text,
                            metadata jsonb
                        )
                        """,
                        {
                            "tenant_id": tenant_id,
                            "ledger_id": ledger_id,
                            "events": Json(_postgres_safe(events)),
                        },
                    )
        return ledger_id

    def start_stage(
        self,
        *,
        tenant_id: int,
        ledger_id: int,
        stage_order: int,
        stage: str,
        metadata: dict[str, Any] | None = None,
        started_at: datetime | None = None,
    ) -> int:
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO run_stage_events (
                        tenant_id, ledger_id, stage_order, stage, status,
                        started_at, metadata
                    ) VALUES (
                        %(tenant_id)s, %(ledger_id)s, %(stage_order)s,
                        %(stage)s, 'running',
                        COALESCE(%(started_at)s, now()), %(metadata)s
                    )
                    ON CONFLICT (tenant_id, ledger_id, stage_order)
                    DO UPDATE SET
                        stage = EXCLUDED.stage,
                        status = 'running',
                        started_at = COALESCE(EXCLUDED.started_at, run_stage_events.started_at, now()),
                        ended_at = NULL,
                        elapsed_s = NULL,
                        error_type = NULL,
                        error = NULL,
                        metadata = run_stage_events.metadata || EXCLUDED.metadata
                    RETURNING id
                    """,
                    {
                        "tenant_id": tenant_id,
                        "ledger_id": ledger_id,
                        "stage_order": stage_order,
                        "stage": _postgres_safe(stage),
                        "started_at": started_at,
                        "metadata": Json(_postgres_safe(metadata or {})),
                    },
                )
                row = cur.fetchone()
        assert row is not None
        return int(row["id"])

    def finish_stage(
        self,
        *,
        tenant_id: int,
        event_id: int,
        status: str,
        metadata: dict[str, Any] | None = None,
        ended_at: datetime | None = None,
        error_type: str | None = None,
        error: str | None = None,
    ) -> None:
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    UPDATE run_stage_events
                    SET
                        status = %(status)s,
                        ended_at = COALESCE(%(ended_at)s, now()),
                        elapsed_s = EXTRACT(EPOCH FROM (COALESCE(%(ended_at)s, now()) - started_at)),
                        error_type = %(error_type)s,
                        error = %(error)s,
                        metadata = run_stage_events.metadata || %(metadata)s::jsonb
                    WHERE tenant_id = %(tenant_id)s
                      AND id = %(event_id)s
                    """,
                    {
                        "tenant_id": tenant_id,
                        "event_id": event_id,
                        "status": _postgres_safe(status),
                        "ended_at": ended_at,
                        "error_type": _postgres_safe(error_type),
                        "error": _postgres_safe(error),
                        "metadata": Json(_postgres_safe(metadata or {})),
                    },
                )

    def finish_ledger(
        self,
        *,
        tenant_id: int,
        ledger_id: int,
        status: str,
        metadata: dict[str, Any] | None = None,
        ended_at: datetime | None = None,
    ) -> None:
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    UPDATE run_stage_ledgers
                    SET
                        status = %(status)s,
                        ended_at = COALESCE(%(ended_at)s, now()),
                        metadata = run_stage_ledgers.metadata || %(metadata)s::jsonb
                    WHERE tenant_id = %(tenant_id)s
                      AND id = %(ledger_id)s
                    """,
                    {
                        "tenant_id": tenant_id,
                        "ledger_id": ledger_id,
                        "status": _postgres_safe(status),
                        "ended_at": ended_at,
                        "metadata": Json(_postgres_safe(metadata or {})),
                    },
                )
