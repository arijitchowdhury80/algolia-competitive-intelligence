"""Postgres implementation of hunter/lifecycle.py's SourceRepository Protocol."""

from __future__ import annotations

from typing import Any, Optional

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Json

from cios.db.session import tenant_context
from cios.hunter.types import Source, SourceStatus

_COLUMNS = (
    "id, tenant_id, competitor_id, source_family, url, normalized_url, title, "
    "status, first_seen_at, last_seen_at, last_checked_at, missing_streak_days, "
    "retired_at, evidence"
)


def _row_to_source(row: dict[str, Any]) -> Source:
    return Source(
        id=row["id"],
        tenant_id=row["tenant_id"],
        competitor_id=row["competitor_id"],
        source_family=row["source_family"],
        url=row["url"],
        normalized_url=row["normalized_url"],
        title=row["title"],
        status=SourceStatus(row["status"]),
        first_seen_at=row["first_seen_at"],
        last_seen_at=row["last_seen_at"],
        last_checked_at=row["last_checked_at"],
        missing_streak_days=row["missing_streak_days"],
        retired_at=row["retired_at"],
        evidence=row["evidence"] or {},
    )


class PgSourceRepository:
    """Implements hunter.lifecycle.SourceRepository against the `sources` table."""

    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def get_by_normalized_url(self, tenant_id: int, normalized_url: str) -> Optional[Source]:
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    f"SELECT {_COLUMNS} FROM sources WHERE tenant_id = %s AND normalized_url = %s",
                    (tenant_id, normalized_url),
                )
                row = cur.fetchone()
        return _row_to_source(row) if row else None

    def upsert(self, source: Source) -> Source:
        with tenant_context(self._conn, source.tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    f"""
                    INSERT INTO sources (
                        tenant_id, competitor_id, source_family, url, normalized_url,
                        title, status, first_seen_at, last_seen_at, last_checked_at,
                        missing_streak_days, retired_at, evidence
                    ) VALUES (
                        %(tenant_id)s, %(competitor_id)s, %(source_family)s, %(url)s, %(normalized_url)s,
                        %(title)s, %(status)s, %(first_seen_at)s, %(last_seen_at)s, %(last_checked_at)s,
                        %(missing_streak_days)s, %(retired_at)s, %(evidence)s
                    )
                    ON CONFLICT (tenant_id, normalized_url) DO UPDATE SET
                        competitor_id = EXCLUDED.competitor_id,
                        source_family = EXCLUDED.source_family,
                        url = EXCLUDED.url,
                        title = EXCLUDED.title,
                        status = EXCLUDED.status,
                        last_seen_at = EXCLUDED.last_seen_at,
                        last_checked_at = EXCLUDED.last_checked_at,
                        missing_streak_days = EXCLUDED.missing_streak_days,
                        retired_at = EXCLUDED.retired_at,
                        evidence = EXCLUDED.evidence
                    RETURNING {_COLUMNS}
                    """,
                    {
                        "tenant_id": source.tenant_id,
                        "competitor_id": source.competitor_id,
                        "source_family": source.source_family,
                        "url": source.url,
                        "normalized_url": source.normalized_url,
                        "title": source.title,
                        "status": source.status.value,
                        "first_seen_at": source.first_seen_at,
                        "last_seen_at": source.last_seen_at,
                        "last_checked_at": source.last_checked_at,
                        "missing_streak_days": source.missing_streak_days,
                        "retired_at": source.retired_at,
                        "evidence": Json(source.evidence),
                    },
                )
                row = cur.fetchone()
        assert row is not None
        return _row_to_source(row)
