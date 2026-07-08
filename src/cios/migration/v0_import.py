"""One-time V0 (`ci.sqlite`) -> V2 (Postgres, `cios` database) migration.

Per docs/planning/CI-OS-gate0-implementation-plan.md §1 (V0 inventory) and §3
(reuse decision: "ci.sqlite data ... MIGRATE into Postgres as Algolia-tenant
history"). V0 keeps running untouched until the Gate 6 cutover; this script
only reads it.

Mapping table (V0 table -> V2 table, key decisions):

    V0 table              V2 table(s)              Key decision
    --------------------  -----------------------  ------------------------------------------------
    sources               competitors + sources    One `competitors` row derived per distinct V0
                                                     `competitor` value; `sources` rows link to it.
                                                     `source_family` falls back to "unknown" if V0
                                                     never recorded a type.
    snapshots              source_snapshots         `fetch_run_id` left NULL -- V0 has no fetch-run
                                                     concept, and the column is nullable in V2.
                                                     V0 row id + a content preview are kept in
                                                     `metadata` for provenance and dedup.
    semantic_facts         semantic_facts           V2 requires non-empty `evidence_ids`
                                                     (semantic_fact_needs_evidence); V0 rows with no
                                                     evidence array get a synthetic
                                                     "v0:semantic_facts:<id>" evidence id so the
                                                     CHECK constraint holds without inventing claims.
    semantic_deltas        semantic_deltas          Same evidence fallback. `quality_status` is
                                                     forced back to 'draft' unless the V0 row already
                                                     carries non-empty evidence, to respect
                                                     semantic_delta_published_needs_evidence.
    source_health_events   source_health_events     `event_type` is normalized to the V2 CHECK enum;
                                                     unrecognized V0 event types map to 'fetch_error'
                                                     (fail-safe, never silently dropped).
    report_index            reports                 `cadence` defaults to 'daily' when V0 has no
                                                     cadence column (V0 only ever produced daily
                                                     briefs per the Gate 0 inventory).
    bot_deliveries          bot_deliveries           `recipient` is redacted (last 4 chars kept) to
                                                     match the `recipient_redacted` column contract.

    NOT migrated: `synthesis_runs` (no V2 equivalent table -- a synthesis run
    is process telemetry, not evidence, and Gate 4's synthesizer will emit its
    own quality_reviews); `signals`, `action_items` (both 0 rows in every V0
    history per the Gate 0 inventory -- the promotion pipeline never
    populated them, so there is nothing to migrate).

Design:
  * Mapping functions (`map_*`) are pure: dict in, dict out, no IO. This is
    what tests/migration/test_v0_import.py exercises directly.
  * `V0Importer` is the IO layer: reads sqlite via the stdlib, and writes via
    an injected `SqlExecutor` (never a concrete Postgres driver import here
    so tests never need a live database).
  * Idempotent: every insert goes through `_insert_if_absent`, which checks a
    natural-key WHERE clause before inserting (V0's own history has no
    unique constraints to lean on in V2, so the generic guard is uniform
    across tables rather than relying on schema-specific ON CONFLICT
    targets).
  * Dry-run mode (`dry_run=True`) reads and maps everything but issues no
    writes; it reports row counts per table so an operator can sanity-check
    before committing.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional, Protocol

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class V0SchemaError(RuntimeError):
    """A V0 sqlite table is missing a column this migration needs.

    Raised instead of guessing -- the exact V0 column names are unknown until
    this runs against the real VPS `ci.sqlite` (3 duplicate copies to
    reconcile, per Gate 0 §1), so silent fallback would risk mis-mapping
    evidence.
    """


# ---------------------------------------------------------------------------
# Column resolution: V0 schemas are introspected, never assumed.
# ---------------------------------------------------------------------------

# logical field -> accepted V0 column name aliases, in preference order.
REQUIRED_COLUMNS: dict[str, dict[str, tuple[str, ...]]] = {
    "sources": {
        "id": ("id",),
        "name": ("name", "source_name", "title"),
        "url": ("url", "source_url"),
        "competitor": ("competitor", "competitor_name"),
    },
    "snapshots": {
        "id": ("id",),
        "source_id": ("source_id",),
        "fetched_at": ("fetched_at", "captured_at", "created_at"),
        "content_hash": ("content_hash", "hash"),
    },
    "semantic_facts": {
        "id": ("id",),
        "source_id": ("source_id", "competitor_source_id"),
        "statement": ("statement", "fact", "text"),
    },
    "semantic_deltas": {
        "id": ("id",),
        "source_id": ("source_id", "competitor_source_id"),
        "what_changed": ("what_changed", "summary", "delta"),
    },
    "source_health_events": {
        "id": ("id",),
        "source_id": ("source_id",),
        "event_type": ("event_type", "status", "type"),
        "created_at": ("created_at", "occurred_at", "timestamp"),
    },
    "report_index": {
        "id": ("id",),
        "report_date": ("report_date", "date"),
    },
    "bot_deliveries": {
        "id": ("id",),
        "channel": ("channel",),
        "created_at": ("created_at", "sent_at", "queued_at"),
    },
}

# optional columns read opportunistically -- absence never raises.
OPTIONAL_COLUMNS: dict[str, dict[str, tuple[str, ...]]] = {
    "sources": {
        "source_family": ("type", "source_type", "source_family"),
        "active": ("active", "is_active"),
        "first_seen_at": ("first_seen_at", "created_at"),
        "last_seen_at": ("last_seen_at",),
        "last_checked_at": ("last_checked_at",),
    },
    "snapshots": {
        "content": ("content", "text", "body"),
        "title": ("title",),
    },
    "semantic_facts": {
        "fact_type": ("fact_type", "type"),
        "confidence": ("confidence",),
        "first_seen_at": ("first_seen_at", "created_at"),
        "last_seen_at": ("last_seen_at",),
        "evidence_ids": ("evidence_ids",),
    },
    "semantic_deltas": {
        "delta_type": ("delta_type", "type"),
        "materiality_score": ("materiality_score", "materiality"),
        "why_it_matters": ("why_it_matters",),
        "implication": ("implication",),
        "recommended_action": ("recommended_action",),
        "confidence": ("confidence",),
        "created_at": ("created_at",),
        "quality_status": ("quality_status", "status"),
        "evidence_ids": ("evidence_ids",),
    },
    "source_health_events": {
        "http_status": ("http_status",),
        "detail": ("detail", "message", "error"),
    },
    "report_index": {
        "cadence": ("cadence",),
        "title": ("title",),
        "status": ("status",),
        "markdown_path": ("markdown_path", "path"),
        "html_path": ("html_path",),
        "summary": ("summary",),
    },
    "bot_deliveries": {
        "cadence": ("cadence",),
        "bot_profile": ("bot_profile", "profile"),
        "recipient": ("recipient", "chat_id", "recipient_id"),
        "status": ("status",),
        "error": ("error",),
    },
}

_ALLOWED_HEALTH_EVENT_TYPES = {
    "ok",
    "fetch_error",
    "http_error",
    "timeout",
    "empty",
    "recovered",
    "retired",
}
_ALLOWED_DELIVERY_STATUSES = {"queued", "sending", "sent", "delivered", "failed"}


def introspect_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    """Return the set of actual column names in a V0 sqlite table."""
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    return cols


def resolve_column_map(table: str, available: set[str]) -> dict[str, str]:
    """Resolve logical field names to actual V0 column names for `table`.

    Raises V0SchemaError listing every missing required field (with the
    aliases tried) rather than guessing at a single one -- one clear failure
    beats N silent mis-mappings.
    """
    required = REQUIRED_COLUMNS.get(table, {})
    optional = OPTIONAL_COLUMNS.get(table, {})
    resolved: dict[str, str] = {}
    missing: list[str] = []

    for logical, aliases in required.items():
        found = next((a for a in aliases if a in available), None)
        if found is None:
            missing.append(f"{logical} (tried: {', '.join(aliases)})")
        else:
            resolved[logical] = found

    if missing:
        raise V0SchemaError(
            f"V0 table '{table}' is missing required column(s) for migration: "
            + "; ".join(missing)
            + f". Actual columns present: {sorted(available)}"
        )

    for logical, aliases in optional.items():
        found = next((a for a in aliases if a in available), None)
        if found is not None:
            resolved[logical] = found

    return resolved


def read_v0_rows(conn: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    """Read every row of a V0 table as {logical_field: value} dicts.

    Raises V0SchemaError up front (via resolve_column_map) if the table is
    missing a column this migration depends on.
    """
    available = introspect_columns(conn, table)
    if not available:
        raise V0SchemaError(f"V0 table '{table}' does not exist in this sqlite file.")
    column_map = resolve_column_map(table, available)

    select_cols = ", ".join(column_map.values())
    cursor = conn.execute(f"SELECT {select_cols} FROM {table}")
    logical_names = list(column_map.keys())
    rows = []
    for raw_row in cursor.fetchall():
        rows.append(dict(zip(logical_names, raw_row)))
    return rows


# ---------------------------------------------------------------------------
# Pure mapping functions: V0 logical row dict -> V2 target row dict.
# No IO. Fully unit-testable.
# ---------------------------------------------------------------------------


def normalize_url(url: str) -> str:
    normalized = url.strip().lower()
    if normalized.endswith("/") and len(normalized) > len("https://"):
        normalized = normalized.rstrip("/")
    return normalized


def _is_truthy(value: Any) -> bool:
    return value in (1, True, "1", "true", "True")


def map_competitor(row: dict[str, Any], tenant_id: int) -> dict[str, Any]:
    """sources.competitor -> a competitors row (one per distinct name)."""
    return {
        "tenant_id": tenant_id,
        "name": row["competitor"],
        "domain": None,
        "category": None,
        "status": "active",
    }


def map_source(row: dict[str, Any], tenant_id: int, competitor_id: int) -> dict[str, Any]:
    return {
        "tenant_id": tenant_id,
        "competitor_id": competitor_id,
        "source_family": row.get("source_family") or "unknown",
        "url": row["url"],
        "normalized_url": normalize_url(row["url"]),
        "title": row.get("name"),
        "status": "active" if _is_truthy(row.get("active", 1)) else "retired",
        "first_seen_at": row.get("first_seen_at"),
        "last_seen_at": row.get("last_seen_at"),
        "last_checked_at": row.get("last_checked_at"),
        "evidence": {"v0_source_id": row["id"]},
    }


def map_snapshot(row: dict[str, Any], tenant_id: int, source_id: int) -> dict[str, Any]:
    content = row.get("content") or ""
    return {
        "tenant_id": tenant_id,
        "source_id": source_id,
        "fetch_run_id": None,
        "captured_at": row["fetched_at"],
        "content_hash": row.get("content_hash"),
        "title": row.get("title"),
        "text_path": None,
        "raw_path": None,
        "metadata": {
            "v0_snapshot_id": row["id"],
            "content_preview": content[:500],
        },
    }


def map_semantic_fact(
    row: dict[str, Any], tenant_id: int, competitor_id: int
) -> dict[str, Any]:
    evidence_ids = row.get("evidence_ids") or [f"v0:semantic_facts:{row['id']}"]
    return {
        "tenant_id": tenant_id,
        "competitor_id": competitor_id,
        "fact_type": row.get("fact_type"),
        "statement": row["statement"],
        "evidence_ids": evidence_ids,
        "confidence": row.get("confidence"),
        "first_seen_at": row.get("first_seen_at"),
        "last_seen_at": row.get("last_seen_at"),
    }


def map_semantic_delta(
    row: dict[str, Any], tenant_id: int, competitor_id: int
) -> dict[str, Any]:
    evidence_ids = row.get("evidence_ids") or []
    requested_status = row.get("quality_status") or "draft"
    # semantic_delta_published_needs_evidence: never carry a 'published'
    # status forward without evidence -- fall back to 'draft' instead of
    # violating the constraint or inventing evidence.
    quality_status = requested_status if evidence_ids or requested_status != "published" else "draft"
    if not evidence_ids:
        evidence_ids = [f"v0:semantic_deltas:{row['id']}"]
    return {
        "tenant_id": tenant_id,
        "competitor_id": competitor_id,
        "delta_type": row.get("delta_type"),
        "materiality_score": row.get("materiality_score"),
        "what_changed": row["what_changed"],
        "why_it_matters": row.get("why_it_matters"),
        "implication": row.get("implication"),
        "recommended_action": row.get("recommended_action"),
        "evidence_ids": evidence_ids,
        "quality_status": quality_status,
        "confidence": row.get("confidence"),
        "created_at": row.get("created_at"),
    }


def map_source_health_event(
    row: dict[str, Any], tenant_id: int, source_id: int
) -> dict[str, Any]:
    event_type = row.get("event_type") or "fetch_error"
    if event_type not in _ALLOWED_HEALTH_EVENT_TYPES:
        # unknown V0 status: never drop the event, fail safe to fetch_error
        # and keep the original value for audit in metadata.
        original = event_type
        event_type = "fetch_error"
    else:
        original = None
    metadata = {"v0_event_id": row["id"]}
    if original is not None:
        metadata["v0_event_type"] = original
    return {
        "tenant_id": tenant_id,
        "source_id": source_id,
        "fetch_run_id": None,
        "event_type": event_type,
        "http_status": row.get("http_status"),
        "detail": row.get("detail"),
        "metadata": metadata,
        "created_at": row["created_at"],
    }


def map_report(row: dict[str, Any], tenant_id: int) -> dict[str, Any]:
    return {
        "tenant_id": tenant_id,
        "cadence": row.get("cadence") or "daily",
        "report_date": row["report_date"],
        "title": row.get("title"),
        "status": row.get("status") or "delivered",
        "markdown_path": row.get("markdown_path"),
        "html_path": row.get("html_path"),
        "json_path": None,
        "summary": row.get("summary"),
        "metadata": {"v0_report_id": row["id"]},
    }


def map_bot_delivery(row: dict[str, Any], tenant_id: int) -> dict[str, Any]:
    recipient = row.get("recipient")
    recipient_redacted = f"***{str(recipient)[-4:]}" if recipient else None
    status = row.get("status") or "sent"
    if status not in _ALLOWED_DELIVERY_STATUSES:
        status = "sent"
    return {
        "tenant_id": tenant_id,
        "cadence": row.get("cadence") or "daily",
        "bot_profile": row.get("bot_profile"),
        "channel": row["channel"],
        "recipient_redacted": recipient_redacted,
        "status": status,
        "markdown_path": None,
        "html_path": None,
        "dashboard_url": None,
        "report_id": None,
        "error": row.get("error"),
        "created_at": row["created_at"],
    }


# ---------------------------------------------------------------------------
# IO layer
# ---------------------------------------------------------------------------


class SqlExecutor(Protocol):
    """Injected IO boundary -- no concrete Postgres driver import here.

    Placeholders are '%s' (psycopg-style); a sqlite-backed fake used in
    tests can translate if needed.
    """

    def fetchone(self, sql: str, params: tuple = ()) -> Optional[dict[str, Any]]: ...

    def fetchall(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]: ...

    def execute(self, sql: str, params: tuple = ()) -> Optional[int]:
        """Execute a write; return the new row id if the caller needs it."""
        ...


@dataclass
class ImportReport:
    dry_run: bool
    read_counts: dict[str, int] = field(default_factory=dict)
    inserted_counts: dict[str, int] = field(default_factory=dict)
    skipped_counts: dict[str, int] = field(default_factory=dict)


def _insert_if_absent(
    executor: SqlExecutor,
    table: str,
    row: dict[str, Any],
    natural_key: dict[str, Any],
    dry_run: bool,
) -> bool:
    """Insert `row` into `table` unless a row matching `natural_key` exists.

    Returns True if a row was (or would be, in dry-run) inserted.
    V0's own history has no reusable unique constraints in the V2 schema for
    most of these tables, so a uniform WHERE-NOT-EXISTS guard is used instead
    of relying on per-table ON CONFLICT targets -- this is what makes re-runs
    idempotent regardless of table.
    """
    where_clause = " AND ".join(f"{col} = %s" for col in natural_key)
    existing = executor.fetchone(
        f"SELECT id FROM {table} WHERE {where_clause}", tuple(natural_key.values())
    )
    if existing is not None:
        return False
    if dry_run:
        return True

    columns = list(row.keys())
    placeholders = ", ".join(["%s"] * len(columns))
    col_list = ", ".join(columns)
    executor.execute(
        f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})",
        tuple(row[c] for c in columns),
    )
    return True


class V0Importer:
    """Reads a V0 `ci.sqlite` file and imports its history into V2 Postgres,
    scoped to a single tenant (Algolia, by default -- Gate 2 target)."""

    def __init__(
        self,
        sqlite_path: str,
        executor: SqlExecutor,
        tenant_slug: str = "algolia",
        dry_run: bool = False,
    ) -> None:
        self.sqlite_path = sqlite_path
        self.executor = executor
        self.tenant_slug = tenant_slug
        self.dry_run = dry_run

    def _get_tenant_id(self) -> int:
        row = self.executor.fetchone(
            "SELECT id FROM tenants WHERE slug = %s", (self.tenant_slug,)
        )
        if row is None:
            raise V0SchemaError(
                f"Tenant slug '{self.tenant_slug}' not found in V2 Postgres. "
                "Run db/seed.sql first (Gate 1)."
            )
        return row["id"]

    def _get_or_create_competitor(self, tenant_id: int, name: str) -> Optional[int]:
        existing = self.executor.fetchone(
            "SELECT id FROM competitors WHERE tenant_id = %s AND name = %s",
            (tenant_id, name),
        )
        if existing is not None:
            return existing["id"]
        if self.dry_run:
            return None
        return self.executor.execute(
            "INSERT INTO competitors (tenant_id, name, domain, category, status) "
            "VALUES (%s, %s, %s, %s, %s)",
            (tenant_id, name, None, None, "active"),
        )

    def _get_or_create_source(
        self, tenant_id: int, mapped: dict[str, Any]
    ) -> Optional[int]:
        existing = self.executor.fetchone(
            "SELECT id FROM sources WHERE tenant_id = %s AND normalized_url = %s",
            (tenant_id, mapped["normalized_url"]),
        )
        if existing is not None:
            return existing["id"]
        if self.dry_run:
            return None
        columns = list(mapped.keys())
        placeholders = ", ".join(["%s"] * len(columns))
        return self.executor.execute(
            f"INSERT INTO sources ({', '.join(columns)}) VALUES ({placeholders})",
            tuple(mapped[c] for c in columns),
        )

    def run(self, conn: Optional[sqlite3.Connection] = None) -> ImportReport:
        report = ImportReport(dry_run=self.dry_run)
        owns_conn = conn is None
        if conn is None:
            conn = sqlite3.connect(self.sqlite_path)

        try:
            tenant_id = self._get_tenant_id()

            # -- competitors + sources ------------------------------------
            source_rows = read_v0_rows(conn, "sources")
            report.read_counts["sources"] = len(source_rows)
            competitor_ids: dict[str, Optional[int]] = {}
            source_id_map: dict[Any, Optional[int]] = {}
            inserted_sources = 0
            skipped_sources = 0

            for row in source_rows:
                competitor_name = row["competitor"]
                if competitor_name not in competitor_ids:
                    competitor_ids[competitor_name] = self._get_or_create_competitor(
                        tenant_id, competitor_name
                    )
                competitor_id = competitor_ids[competitor_name]
                mapped = map_source(row, tenant_id, competitor_id)
                before = self.executor.fetchone(
                    "SELECT id FROM sources WHERE tenant_id = %s AND normalized_url = %s",
                    (tenant_id, mapped["normalized_url"]),
                )
                new_id = self._get_or_create_source(tenant_id, mapped)
                source_id_map[row["id"]] = new_id
                if before is None:
                    inserted_sources += 1
                else:
                    skipped_sources += 1

            report.inserted_counts["sources"] = inserted_sources
            report.skipped_counts["sources"] = skipped_sources

            # -- snapshots -------------------------------------------------
            self._import_child_table(
                conn,
                v0_table="snapshots",
                v2_table="source_snapshots",
                report=report,
                map_row=lambda row: map_snapshot(
                    row, tenant_id, source_id_map.get(row["source_id"])
                ),
                natural_key=lambda mapped, row: {
                    "source_id": mapped["source_id"],
                    "content_hash": mapped["content_hash"],
                },
                requires_parent="source_id",
                parent_map=source_id_map,
            )

            # -- semantic facts (linked via source -> competitor) ----------
            self._import_child_table(
                conn,
                v0_table="semantic_facts",
                v2_table="semantic_facts",
                report=report,
                map_row=lambda row: map_semantic_fact(
                    row,
                    tenant_id,
                    competitor_ids.get(self._competitor_for_source(row, source_rows)),
                ),
                natural_key=lambda mapped, row: {
                    "competitor_id": mapped["competitor_id"],
                    "statement": mapped["statement"],
                },
                requires_parent="source_id",
                parent_map=source_id_map,
            )

            # -- semantic deltas --------------------------------------------
            self._import_child_table(
                conn,
                v0_table="semantic_deltas",
                v2_table="semantic_deltas",
                report=report,
                map_row=lambda row: map_semantic_delta(
                    row,
                    tenant_id,
                    competitor_ids.get(self._competitor_for_source(row, source_rows)),
                ),
                natural_key=lambda mapped, row: {
                    "competitor_id": mapped["competitor_id"],
                    "what_changed": mapped["what_changed"],
                },
                requires_parent="source_id",
                parent_map=source_id_map,
            )

            # -- source health events ---------------------------------------
            self._import_child_table(
                conn,
                v0_table="source_health_events",
                v2_table="source_health_events",
                report=report,
                map_row=lambda row: map_source_health_event(
                    row, tenant_id, source_id_map.get(row["source_id"])
                ),
                natural_key=lambda mapped, row: {
                    "source_id": mapped["source_id"],
                    "created_at": mapped["created_at"],
                    "event_type": mapped["event_type"],
                },
                requires_parent="source_id",
                parent_map=source_id_map,
            )

            # -- reports (from report_index) ---------------------------------
            self._import_flat_table(
                conn,
                v0_table="report_index",
                v2_table="reports",
                report=report,
                map_row=lambda row: map_report(row, tenant_id),
                natural_key=lambda mapped: {
                    "tenant_id": mapped["tenant_id"],
                    "cadence": mapped["cadence"],
                    "report_date": mapped["report_date"],
                },
            )

            # -- bot deliveries ------------------------------------------------
            self._import_flat_table(
                conn,
                v0_table="bot_deliveries",
                v2_table="bot_deliveries",
                report=report,
                map_row=lambda row: map_bot_delivery(row, tenant_id),
                natural_key=lambda mapped: {
                    "tenant_id": mapped["tenant_id"],
                    "channel": mapped["channel"],
                    "created_at": mapped["created_at"],
                },
            )

        finally:
            if owns_conn:
                conn.close()

        return report

    @staticmethod
    def _competitor_for_source(row: dict[str, Any], source_rows: list[dict[str, Any]]) -> Any:
        source_id = row.get("source_id")
        for source_row in source_rows:
            if source_row["id"] == source_id:
                return source_row["competitor"]
        return None

    def _import_child_table(
        self,
        conn: sqlite3.Connection,
        *,
        v0_table: str,
        v2_table: str,
        report: ImportReport,
        map_row: Callable[[dict[str, Any]], dict[str, Any]],
        natural_key: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
        requires_parent: str,
        parent_map: dict[Any, Optional[int]],
    ) -> None:
        rows = read_v0_rows(conn, v0_table)
        report.read_counts[v0_table] = len(rows)
        inserted = 0
        skipped = 0
        for row in rows:
            parent_v0_id = row.get(requires_parent)
            if parent_v0_id not in parent_map or (
                parent_map.get(parent_v0_id) is None and not self.dry_run
            ):
                # orphaned row (parent missing/blocked) -- never silently
                # invent a parent; skip and count it.
                skipped += 1
                continue
            mapped = map_row(row)
            inserted_flag = _insert_if_absent(
                self.executor, v2_table, mapped, natural_key(mapped, row), self.dry_run
            )
            if inserted_flag:
                inserted += 1
            else:
                skipped += 1
        report.inserted_counts[v0_table] = inserted
        report.skipped_counts[v0_table] = skipped

    def _import_flat_table(
        self,
        conn: sqlite3.Connection,
        *,
        v0_table: str,
        v2_table: str,
        report: ImportReport,
        map_row: Callable[[dict[str, Any]], dict[str, Any]],
        natural_key: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> None:
        rows = read_v0_rows(conn, v0_table)
        report.read_counts[v0_table] = len(rows)
        inserted = 0
        skipped = 0
        for row in rows:
            mapped = map_row(row)
            inserted_flag = _insert_if_absent(
                self.executor, v2_table, mapped, natural_key(mapped), self.dry_run
            )
            if inserted_flag:
                inserted += 1
            else:
                skipped += 1
        report.inserted_counts[v0_table] = inserted
        report.skipped_counts[v0_table] = skipped
