"""Postgres implementations of collect/runner.py's repository Protocols.

Mapping notes (fields on the pydantic models that don't have a 1:1 schema
column get folded into the closest jsonb column -- documented per repo so
the lossy spots are visible, not hidden):

  * Snapshot.text has no `source_snapshots.text_path` file on disk in this
    build (no object storage wired yet) -- the raw text is stored inline in
    `metadata->>'_text'` instead of being dropped, and `text_path`/`raw_path`
    stay NULL. Swap this for real file-backed storage when that lands.
  * ExtractedFact has no tenant_id of its own (collect/types.py -- it's an
    intermediate value object) -- PgFactRepository takes tenant_id at
    construction time. ExtractedFact.fact_json/evidence_text/evidence_url
    have no dedicated semantic_facts columns, so they're packed into
    `evidence_ids` as a single evidence object (satisfies the
    semantic_fact_needs_evidence non-empty-array CHECK and keeps the data).
  * Delta has no tenant_id either -- PgDeltaRepository takes tenant_id at
    construction time. Delta.metadata has no semantic_deltas column and is
    dropped (documented, not silently lost -- flag if this data matters).
"""

from __future__ import annotations

from typing import Any, Optional

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Json

from cios.collect.types import Delta, ExtractedFact, FetchRunResult, Snapshot
from cios.db.session import tenant_context

_SNAPSHOT_COLUMNS = (
    "id, tenant_id, source_id, fetch_run_id, captured_at, content_hash, title, "
    "text_path, raw_path, metadata"
)
_FETCH_RUN_COLUMNS = (
    "id, tenant_id, started_at, finished_at, status, source_count, snapshot_count, "
    "finding_count, errors"
)


def _postgres_safe(value: Any) -> Any:
    """Remove characters PostgreSQL text/jsonb cannot store.

    HTML extraction occasionally surfaces embedded NUL bytes from binary-ish
    page payloads. Postgres rejects those in both text and JSON strings, so
    sanitize at the persistence boundary.
    """
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, list):
        return [_postgres_safe(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_postgres_safe(item) for item in value)
    if isinstance(value, dict):
        return {_postgres_safe(k): _postgres_safe(v) for k, v in value.items()}
    return value


def _safe_fact_evidence_ids(fact: ExtractedFact) -> list[dict[str, Any]]:
    return _postgres_safe([
        {
            "url": fact.evidence_url,
            "text": fact.evidence_text,
            "fact_json": fact.fact_json,
        }
    ])


def _row_to_snapshot(row: dict[str, Any]) -> Snapshot:
    metadata = dict(row["metadata"] or {})
    text = metadata.pop("_text", "")
    return Snapshot(
        id=row["id"],
        tenant_id=row["tenant_id"],
        source_id=row["source_id"],
        fetch_run_id=row["fetch_run_id"],
        captured_at=row["captured_at"],
        content_hash=row["content_hash"],
        title=row["title"],
        text=text,
        metadata=metadata,
    )


def _row_to_fetch_run(row: dict[str, Any]) -> FetchRunResult:
    return FetchRunResult(
        id=row["id"],
        tenant_id=row["tenant_id"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        status=row["status"],
        source_count=row["source_count"] or 0,
        snapshot_count=row["snapshot_count"] or 0,
        finding_count=row["finding_count"] or 0,
        errors=list(row["errors"] or []),
    )


class PgSnapshotRepository:
    """Implements collect.runner.SnapshotRepository against `source_snapshots`."""

    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def latest(self, tenant_id: int, source_id: int) -> Optional[Snapshot]:
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    f"""
                    SELECT {_SNAPSHOT_COLUMNS} FROM source_snapshots
                    WHERE tenant_id = %s AND source_id = %s
                    ORDER BY captured_at DESC LIMIT 1
                    """,
                    (tenant_id, source_id),
                )
                row = cur.fetchone()
        return _row_to_snapshot(row) if row else None

    def save(self, snapshot: Snapshot) -> Snapshot:
        metadata = dict(snapshot.metadata)
        metadata["_text"] = snapshot.text
        metadata = _postgres_safe(metadata)
        with tenant_context(self._conn, snapshot.tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    f"""
                    INSERT INTO source_snapshots (
                        tenant_id, source_id, fetch_run_id, captured_at, content_hash,
                        title, text_path, raw_path, metadata
                    ) VALUES (
                        %(tenant_id)s, %(source_id)s, %(fetch_run_id)s, %(captured_at)s, %(content_hash)s,
                        %(title)s, NULL, NULL, %(metadata)s
                    )
                    RETURNING {_SNAPSHOT_COLUMNS}
                    """,
                    {
                        "tenant_id": snapshot.tenant_id,
                        "source_id": snapshot.source_id,
                        "fetch_run_id": snapshot.fetch_run_id,
                        "captured_at": snapshot.captured_at,
                        "content_hash": snapshot.content_hash,
                        "title": _postgres_safe(snapshot.title),
                        "metadata": Json(metadata),
                    },
                )
                row = cur.fetchone()
        assert row is not None
        return _row_to_snapshot(row)


class PgFactRepository:
    """Implements collect.runner.FactRepository against `semantic_facts`.

    ExtractedFact carries no tenant_id (it's a pre-persistence value object
    in collect/types.py) so the tenant is fixed at construction time.
    """

    def __init__(self, conn: Connection, tenant_id: int) -> None:
        self._conn = conn
        self._tenant_id = tenant_id

    def save(self, fact: ExtractedFact) -> ExtractedFact:
        evidence_ids = _safe_fact_evidence_ids(fact)
        with tenant_context(self._conn, self._tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO semantic_facts (
                        tenant_id, competitor_id, fact_type, statement, evidence_ids, confidence
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        self._tenant_id,
                        fact.competitor_id,
                        _postgres_safe(fact.fact_type),
                        _postgres_safe(fact.statement),
                        Json(evidence_ids),
                        fact.confidence,
                    ),
                )
                row = cur.fetchone()
        assert row is not None
        return fact.model_copy(update={"id": row["id"]})


class PgDeltaRepository:
    """Implements collect.runner.DeltaRepository against `semantic_deltas`.

    Delta carries no tenant_id either -- fixed at construction time, same
    reasoning as PgFactRepository.
    """

    def __init__(self, conn: Connection, tenant_id: int) -> None:
        self._conn = conn
        self._tenant_id = tenant_id

    def save(self, delta: Delta) -> Delta:
        with tenant_context(self._conn, self._tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO semantic_deltas (
                        tenant_id, competitor_id, delta_type, materiality_score, what_changed,
                        why_it_matters, implication, recommended_action, evidence_ids,
                        quality_status, confidence
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        self._tenant_id,
                        delta.competitor_id,
                        _postgres_safe(delta.delta_type),
                        delta.materiality_score,
                        _postgres_safe(delta.what_changed),
                        _postgres_safe(delta.why_it_matters),
                        _postgres_safe(delta.implication),
                        _postgres_safe(delta.recommended_action),
                        Json(_postgres_safe(delta.evidence_urls)),
                        _postgres_safe(delta.quality_status),
                        delta.confidence,
                    ),
                )
                row = cur.fetchone()
        assert row is not None
        return delta.model_copy(update={"id": row["id"]})


class PgFetchRunRepository:
    """Implements collect.runner.FetchRunRepository against `intel_fetch_runs`."""

    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def start(self, tenant_id: int) -> FetchRunResult:
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    f"""
                    INSERT INTO intel_fetch_runs (tenant_id, status)
                    VALUES (%s, 'running')
                    RETURNING {_FETCH_RUN_COLUMNS}
                    """,
                    (tenant_id,),
                )
                row = cur.fetchone()
        assert row is not None
        return _row_to_fetch_run(row)

    def finish(self, run: FetchRunResult) -> FetchRunResult:
        with tenant_context(self._conn, run.tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    f"""
                    UPDATE intel_fetch_runs SET
                        finished_at = %(finished_at)s,
                        status = %(status)s,
                        source_count = %(source_count)s,
                        snapshot_count = %(snapshot_count)s,
                        finding_count = %(finding_count)s,
                        errors = %(errors)s
                    WHERE id = %(id)s AND tenant_id = %(tenant_id)s
                    RETURNING {_FETCH_RUN_COLUMNS}
                    """,
                    {
                        "finished_at": run.finished_at,
                        "status": run.status,
                        "source_count": run.source_count,
                        "snapshot_count": run.snapshot_count,
                        "finding_count": run.finding_count,
                        "errors": Json(run.errors),
                        "id": run.id,
                        "tenant_id": run.tenant_id,
                    },
                )
                row = cur.fetchone()
        assert row is not None
        return _row_to_fetch_run(row)
