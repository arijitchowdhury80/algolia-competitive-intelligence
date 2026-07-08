"""One-time V0 (`ci.sqlite`) -> V2 (Postgres, `cios` database) migration.

Per docs/planning/CI-OS-gate0-implementation-plan.md §1 (V0 inventory) and §3
(reuse decision: "ci.sqlite data ... MIGRATE into Postgres as Algolia-tenant
history"). V0 keeps running untouched until the Gate 6 cutover; this script
only reads it.

Column names below are verified against the REAL production `ci.sqlite`
(copy pulled 2026-07-08, 43 sources / 351 snapshots / 13 semantic_facts / 86
semantic_deltas / 351 source_health_events / 12 report_index / 12
bot_deliveries / 0 signals / 0 action_items / 12 synthesis_runs). V0 has no
`source_id` foreign keys on snapshots, semantic_facts, semantic_deltas, or
source_health_events -- every one of those tables carries a `source_url`
column instead, and joins back to `sources` by URL.

Mapping table (V0 table -> V2 table, key decisions):

    V0 table              V2 table(s)              Key decision
    --------------------  -----------------------  ------------------------------------------------
    sources               competitors + sources    One `competitors` row derived per distinct V0
                                                     `competitor` value; `sources` rows link to it.
                                                     `source_family` <- `source_type`. V0 has no
                                                     `name` column; title is derived from
                                                     competitor + source_type.
    snapshots              source_snapshots         Joined to `sources` by normalize_url(source_url)
                                                     (raw-url fallback for edge cases). Rows whose
                                                     source_url matches no known source are skipped
                                                     and counted, never crash. `fetch_run_id` left
                                                     NULL -- V0 has no fetch-run concept.
    semantic_facts         semantic_facts           competitor_id resolved directly from the V0
                                                     `competitor` column (present on this table in
                                                     the real schema -- no join through sources
                                                     needed for that FK). `statement` is derived
                                                     from `evidence_text`, falling back to
                                                     `fact_json`'s `strategic_claim`/`title` when
                                                     evidence_text is blank. V2 requires non-empty
                                                     `evidence_ids` (semantic_fact_needs_evidence);
                                                     `evidence_url` becomes the sole evidence id, or
                                                     a synthetic "v0:semantic_facts:<id>" id when
                                                     absent, so the CHECK constraint holds without
                                                     inventing claims. Still validated against the
                                                     source_url map (§ source_url is the join key)
                                                     and skipped if the source_url is unknown.
    semantic_deltas         semantic_deltas         competitor_id likewise resolved directly from
                                                     the V0 `competitor` column. `delta_summary` ->
                                                     `what_changed`, `materiality_reason` ->
                                                     `why_it_matters`, `algolia_implication` ->
                                                     `implication`. `evidence_urls` (a JSON text
                                                     list in V0) is parsed defensively into
                                                     `evidence_ids`; parse failures or an empty list
                                                     fall back to a synthetic evidence id. V2's
                                                     `semantic_deltas` table has no owner/metadata
                                                     column, so `action_owner` (when present) is
                                                     folded into `recommended_action` as an
                                                     "[Owner: ...]" prefix rather than silently
                                                     dropped. `quality_status` is still forced back
                                                     to 'draft' unless the row carries evidence, to
                                                     respect semantic_delta_published_needs_evidence.
    source_health_events   source_health_events     Joined to `sources` by source_url (same as
                                                     snapshots); `status` is normalized to the V2
                                                     CHECK enum via `event_type` -- unrecognized V0
                                                     statuses map to 'fetch_error' (fail-safe, never
                                                     silently dropped) with the original value kept
                                                     in `metadata.v0_event_type`. `failure_reason` ->
                                                     `detail`; failure_streak / last_success_at /
                                                     last_failure_at / collector / duration_ms /
                                                     quality_score / recommended_collector /
                                                     replacement_recommendation all preserved in
                                                     `metadata` (V2 has no column for them).
    report_index            reports                 `date_start` -> `report_date`. `status`
                                                     'generated' -> 'rendered' (V2 CHECK only allows
                                                     draft/rendered/delivered); unrecognized statuses
                                                     fall back to 'draft'. V0 has no `title` column;
                                                     one is synthesized from cadence + report_date.
                                                     `pdf_path`, `date_end`, `quality_score`,
                                                     `top_signal_ids`, `top_action_owners`,
                                                     `source_health_summary` all preserved in
                                                     `metadata` (no matching V2 columns). The V0 id
                                                     -> V2 id mapping built here is reused by
                                                     bot_deliveries to resolve `report_id`.
    bot_deliveries          bot_deliveries           `report_id` resolved via the report_index id
                                                     map (nullable in V2 -- unresolved links keep
                                                     `report_id = NULL` rather than skipping the
                                                     delivery). `recipient` is redacted (last 4
                                                     chars kept) to match the `recipient_redacted`
                                                     column contract. V0 status strings (e.g.
                                                     "queued_for_telegram") are normalized to the V2
                                                     CHECK enum by keyword + `delivered_at`
                                                     presence, never guessed blindly to 'sent'.
                                                     `artifact_paths` / `delivery_metadata` have no
                                                     home in V2's bot_deliveries schema (no metadata
                                                     column) and are intentionally dropped --
                                                     markdown_path/html_path/dashboard_url already
                                                     cover the addressable artifacts.

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
  * Rows referencing an unknown `source_url` are never dropped silently --
    they are counted in `ImportReport.skipped_counts` and itemized (with
    reason) in `ImportReport.skip_reasons`.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class V0SchemaError(RuntimeError):
    """A V0 sqlite table is missing a column this migration needs.

    Raised instead of guessing -- silent fallback would risk mis-mapping
    evidence.
    """


# ---------------------------------------------------------------------------
# Column resolution: V0 schemas are introspected, never assumed.
# ---------------------------------------------------------------------------

# logical field -> accepted V0 column name aliases, in preference order.
REQUIRED_COLUMNS: dict[str, dict[str, tuple[str, ...]]] = {
    "sources": {
        "id": ("id",),
        # Real prod ci.sqlite (2026-07-08) has NO name column at all; name is
        # derived downstream from competitor + source_type when absent.
        "url": ("url", "source_url"),
        "competitor": ("competitor", "competitor_name"),
    },
    "snapshots": {
        "id": ("id",),
        # Real prod schema keys snapshots by source_url, not source_id.
        "source_url": ("source_url", "url"),
        "fetched_at": ("fetched_at", "captured_at", "created_at"),
    },
    "semantic_facts": {
        "id": ("id",),
        "source_url": ("source_url",),
        "competitor": ("competitor",),
    },
    "semantic_deltas": {
        "id": ("id",),
        "source_url": ("source_url",),
        "competitor": ("competitor",),
        "what_changed": ("delta_summary", "what_changed", "summary"),
    },
    "source_health_events": {
        "id": ("id",),
        "source_url": ("source_url",),
        "event_type": ("status", "event_type", "type"),
        "created_at": ("created_at", "occurred_at", "timestamp"),
    },
    "report_index": {
        "id": ("id",),
        "report_date": ("date_start", "report_date", "date"),
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
        "name": ("name", "source_name", "title"),
        "source_family": ("type", "source_type", "source_family"),
        "active": ("active", "is_active", "enabled"),
        "first_seen_at": ("first_seen_at", "created_at"),
        "last_seen_at": ("last_seen_at", "updated_at"),
        "last_checked_at": ("last_checked_at", "updated_at"),
    },
    "snapshots": {
        "content": ("content", "content_text", "text", "body"),
        "title": ("title",),
        "content_hash": ("content_hash", "hash"),
        "status": ("status",),
        "http_status": ("http_status",),
        "error": ("error",),
        "collector": ("collector",),
        "duration_ms": ("duration_ms",),
        "quality_score": ("quality_score",),
    },
    "semantic_facts": {
        "fact_type": ("fact_type", "type"),
        "fact_json": ("fact_json",),
        "evidence_text": ("evidence_text",),
        "evidence_url": ("evidence_url",),
        "confidence": ("confidence",),
        "first_seen_at": ("detected_date", "first_seen_at", "created_at"),
        "last_seen_at": ("created_at", "last_seen_at"),
        "evidence_ids": ("evidence_ids",),
    },
    "semantic_deltas": {
        "delta_type": ("delta_type", "type"),
        "materiality_score": ("materiality_score", "materiality"),
        "why_it_matters": ("materiality_reason", "why_it_matters"),
        "implication": ("algolia_implication", "implication"),
        "recommended_action": ("recommended_action",),
        "action_owner": ("action_owner", "owner"),
        "confidence": ("confidence",),
        "created_at": ("created_at",),
        "quality_status": ("quality_status", "status"),
        "evidence_urls": ("evidence_urls", "evidence_ids"),
    },
    "source_health_events": {
        "http_status": ("http_status",),
        "detail": ("failure_reason", "detail", "message", "error"),
        "failure_streak": ("failure_streak",),
        "last_success_at": ("last_success_at",),
        "last_failure_at": ("last_failure_at",),
        "collector": ("collector",),
        "duration_ms": ("duration_ms",),
        "quality_score": ("quality_score",),
        "recommended_collector": ("recommended_collector",),
        "replacement_recommendation": ("replacement_recommendation",),
    },
    "report_index": {
        "cadence": ("cadence",),
        "title": ("title",),
        "status": ("status",),
        "markdown_path": ("markdown_path", "path"),
        "html_path": ("html_path",),
        "pdf_path": ("pdf_path",),
        "date_end": ("date_end",),
        "quality_score": ("quality_score",),
        "top_signal_ids": ("top_signal_ids",),
        "top_action_owners": ("top_action_owners",),
        "source_health_summary": ("source_health_summary",),
        "summary": ("summary",),
    },
    "bot_deliveries": {
        "report_id": ("report_id",),
        "cadence": ("cadence",),
        "bot_profile": ("bot_profile", "profile"),
        "recipient": ("recipient", "chat_id", "recipient_id"),
        "status": ("status",),
        "error": ("error",),
        "markdown_path": ("markdown_path",),
        "html_path": ("html_path",),
        "dashboard_url": ("dashboard_url",),
        "delivered_at": ("delivered_at", "sent_at"),
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
_ALLOWED_DELIVERY_STATUSES = {"queued", "sending", "sent", "delivered", "failed", "blocked"}
_ALLOWED_REPORT_STATUSES = {"draft", "rendered", "delivered"}
_ALLOWED_REPORT_CADENCES = {"daily", "weekly", "ad_hoc"}
_ALLOWED_DELIVERY_CADENCES = {"daily", "weekly", "ad_hoc", "alert"}


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

    select_cols = ", ".join(f'"{col}"' for col in column_map.values())
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


def _parse_json_list(raw: Any) -> list[str]:
    """Defensively parse a V0 JSON-text list column (e.g. evidence_urls).

    Never raises: malformed/blank/non-list JSON all collapse to an empty
    list, letting the caller apply its own evidence fallback.
    """
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(item) for item in raw]
    if not isinstance(raw, str) or not raw.strip():
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if isinstance(parsed, list):
        return [str(item) for item in parsed]
    return []


def _parse_json_object(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


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
        # Prod V0 sources have no name column: derive a stable human title.
        "title": row.get("name") or f"{row.get('competitor', '')} {row.get('source_family') or 'source'}".strip(),
        "status": "active" if _is_truthy(row.get("active", 1)) else "retired",
        "first_seen_at": row.get("first_seen_at"),
        "last_seen_at": row.get("last_seen_at"),
        "last_checked_at": row.get("last_checked_at"),
        "evidence": {"v0_source_id": row["id"]},
    }


def map_snapshot(row: dict[str, Any], tenant_id: int, source_id: int) -> dict[str, Any]:
    content = row.get("content") or ""
    metadata = {
        "v0_snapshot_id": row["id"],
        "content_preview": content[:500],
    }
    for key in ("status", "http_status", "error", "collector", "duration_ms", "quality_score"):
        if row.get(key) is not None:
            metadata[key] = row[key]
    return {
        "tenant_id": tenant_id,
        "source_id": source_id,
        "fetch_run_id": None,
        "captured_at": row["fetched_at"],
        "content_hash": row.get("content_hash"),
        "title": row.get("title"),
        "text_path": None,
        "raw_path": None,
        "metadata": metadata,
    }


def map_semantic_fact(
    row: dict[str, Any], tenant_id: int, competitor_id: int
) -> dict[str, Any]:
    statement = (row.get("evidence_text") or "").strip()
    if not statement:
        fact_json = _parse_json_object(row.get("fact_json"))
        for key in ("strategic_claim", "title", "topic"):
            candidate = fact_json.get(key)
            if candidate:
                statement = str(candidate)
                break
    if not statement:
        statement = f"[V0 semantic_facts id={row['id']}: no statement text recorded]"

    evidence_ids = row.get("evidence_ids")
    if not evidence_ids:
        evidence_url = row.get("evidence_url")
        evidence_ids = [evidence_url] if evidence_url else [f"v0:semantic_facts:{row['id']}"]

    return {
        "tenant_id": tenant_id,
        "competitor_id": competitor_id,
        "fact_type": row.get("fact_type"),
        "statement": statement,
        "evidence_ids": evidence_ids,
        "confidence": row.get("confidence"),
        "first_seen_at": row.get("first_seen_at"),
        "last_seen_at": row.get("last_seen_at"),
    }


def map_semantic_delta(
    row: dict[str, Any], tenant_id: int, competitor_id: int
) -> dict[str, Any]:
    evidence_ids = row.get("evidence_urls")
    if isinstance(evidence_ids, str):
        evidence_ids = _parse_json_list(evidence_ids)
    evidence_ids = list(evidence_ids or [])

    requested_status = row.get("quality_status") or "draft"
    # semantic_delta_published_needs_evidence: never carry a 'published'
    # status forward without evidence -- fall back to 'draft' instead of
    # violating the constraint or inventing evidence.
    quality_status = requested_status if evidence_ids or requested_status != "published" else "draft"
    if not evidence_ids:
        evidence_ids = [f"v0:semantic_deltas:{row['id']}"]

    recommended_action = row.get("recommended_action")
    action_owner = row.get("action_owner")
    if action_owner:
        # V2 semantic_deltas has no owner/metadata column -- fold the owner
        # into recommended_action rather than silently dropping it.
        prefix = f"[Owner: {action_owner}] "
        recommended_action = prefix + (recommended_action or "")

    return {
        "tenant_id": tenant_id,
        "competitor_id": competitor_id,
        "delta_type": row.get("delta_type"),
        "materiality_score": row.get("materiality_score"),
        "what_changed": row["what_changed"],
        "why_it_matters": row.get("why_it_matters"),
        "implication": row.get("implication"),
        "recommended_action": recommended_action,
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
    metadata: dict[str, Any] = {"v0_event_id": row["id"]}
    if original is not None:
        metadata["v0_event_type"] = original
    for key in (
        "failure_streak",
        "last_success_at",
        "last_failure_at",
        "collector",
        "duration_ms",
        "quality_score",
        "recommended_collector",
        "replacement_recommendation",
    ):
        if row.get(key) is not None:
            metadata[key] = row[key]
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
    cadence = row.get("cadence") or "daily"
    if cadence not in _ALLOWED_REPORT_CADENCES:
        cadence = "ad_hoc"

    status = row.get("status") or "draft"
    if status == "generated":
        status = "rendered"
    elif status not in _ALLOWED_REPORT_STATUSES:
        status = "draft"

    title = row.get("title") or f"{cadence.title()} report {row['report_date']}"

    metadata: dict[str, Any] = {"v0_report_id": row["id"]}
    for key in (
        "pdf_path",
        "date_end",
        "quality_score",
        "top_signal_ids",
        "top_action_owners",
        "source_health_summary",
    ):
        if row.get(key) is not None:
            metadata[key] = row[key]

    return {
        "tenant_id": tenant_id,
        "cadence": cadence,
        "report_date": row["report_date"],
        "title": title,
        "status": status,
        "markdown_path": row.get("markdown_path"),
        "html_path": row.get("html_path"),
        "json_path": None,
        "summary": row.get("summary"),
        "metadata": metadata,
    }


def _normalize_delivery_status(raw_status: Optional[str], delivered_at: Optional[str]) -> str:
    status = (raw_status or "").lower()
    if "fail" in status or "error" in status:
        return "failed"
    if "block" in status:
        return "blocked"
    if "delivered" in status:
        return "delivered"
    if "sending" in status:
        return "sending"
    if "queued" in status:
        # queued_for_* style V0 statuses: trust an explicit delivered_at over
        # the label, since the queue name doesn't reflect final delivery.
        return "delivered" if delivered_at else "queued"
    if "sent" in status:
        return "sent"
    if status in _ALLOWED_DELIVERY_STATUSES:
        return status
    return "delivered" if delivered_at else "sent"


def map_bot_delivery(row: dict[str, Any], tenant_id: int, report_id: Optional[int]) -> dict[str, Any]:
    recipient = row.get("recipient")
    recipient_redacted = f"***{str(recipient)[-4:]}" if recipient else None
    cadence = row.get("cadence") or "daily"
    if cadence not in _ALLOWED_DELIVERY_CADENCES:
        cadence = "ad_hoc"
    status = _normalize_delivery_status(row.get("status"), row.get("delivered_at"))
    return {
        "tenant_id": tenant_id,
        "cadence": cadence,
        "bot_profile": row.get("bot_profile"),
        "channel": row["channel"],
        "recipient_redacted": recipient_redacted,
        "status": status,
        "markdown_path": row.get("markdown_path"),
        "html_path": row.get("html_path"),
        "dashboard_url": row.get("dashboard_url"),
        "report_id": report_id,
        "error": row.get("error") or None,
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
    skip_reasons: dict[str, dict[str, int]] = field(default_factory=dict)

    def _record_skip(self, table: str, reason: str) -> None:
        self.skipped_counts[table] = self.skipped_counts.get(table, 0) + 1
        reasons = self.skip_reasons.setdefault(table, {})
        reasons[reason] = reasons.get(reason, 0) + 1


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
            # source_url is the join key for every downstream table -- build
            # both a normalized-url map (primary) and a raw-url map
            # (fallback) so odd casing/trailing-slash V0 data still resolves.
            normalized_url_map: dict[str, Optional[int]] = {}
            raw_url_map: dict[str, Optional[int]] = {}
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
                normalized_url_map[mapped["normalized_url"]] = new_id
                raw_url_map[row["url"]] = new_id
                if before is None:
                    inserted_sources += 1
                else:
                    skipped_sources += 1

            report.inserted_counts["sources"] = inserted_sources
            report.skipped_counts["sources"] = skipped_sources

            def resolve_source_id(url: Optional[str]) -> tuple[bool, Optional[int]]:
                if not url:
                    return False, None
                normalized = normalize_url(url)
                if normalized in normalized_url_map:
                    return True, normalized_url_map[normalized]
                if url in raw_url_map:
                    return True, raw_url_map[url]
                return False, None

            # -- snapshots ---------------------------------------------------
            self._import_by_source_url(
                conn,
                v0_table="snapshots",
                v2_table="source_snapshots",
                report=report,
                resolve_source_id=resolve_source_id,
                map_row=lambda row, source_id: map_snapshot(row, tenant_id, source_id),
                natural_key=lambda mapped: {
                    "source_id": mapped["source_id"],
                    "content_hash": mapped["content_hash"],
                },
            )

            # -- semantic facts (competitor resolved directly from row) -----
            self._import_by_source_url(
                conn,
                v0_table="semantic_facts",
                v2_table="semantic_facts",
                report=report,
                resolve_source_id=resolve_source_id,
                map_row=lambda row, _source_id: map_semantic_fact(
                    row, tenant_id, competitor_ids.get(row["competitor"])
                ),
                natural_key=lambda mapped: {
                    "competitor_id": mapped["competitor_id"],
                    "statement": mapped["statement"],
                },
            )

            # -- semantic deltas ----------------------------------------------
            self._import_by_source_url(
                conn,
                v0_table="semantic_deltas",
                v2_table="semantic_deltas",
                report=report,
                resolve_source_id=resolve_source_id,
                map_row=lambda row, _source_id: map_semantic_delta(
                    row, tenant_id, competitor_ids.get(row["competitor"])
                ),
                natural_key=lambda mapped: {
                    "competitor_id": mapped["competitor_id"],
                    "what_changed": mapped["what_changed"],
                },
            )

            # -- source health events ------------------------------------------
            self._import_by_source_url(
                conn,
                v0_table="source_health_events",
                v2_table="source_health_events",
                report=report,
                resolve_source_id=resolve_source_id,
                map_row=lambda row, source_id: map_source_health_event(row, tenant_id, source_id),
                natural_key=lambda mapped: {
                    "source_id": mapped["source_id"],
                    "created_at": mapped["created_at"],
                    "event_type": mapped["event_type"],
                },
            )

            # -- reports (from report_index) ---------------------------------
            report_id_map = self._import_flat_table(
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
                map_row=lambda row: map_bot_delivery(
                    row, tenant_id, report_id_map.get(row.get("report_id"))
                ),
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

    def _import_by_source_url(
        self,
        conn: sqlite3.Connection,
        *,
        v0_table: str,
        v2_table: str,
        report: ImportReport,
        resolve_source_id: Callable[[Optional[str]], tuple[bool, Optional[int]]],
        map_row: Callable[[dict[str, Any], Optional[int]], dict[str, Any]],
        natural_key: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> None:
        """Import a V0 table keyed by `source_url`, joining to `sources` by URL.

        Rows whose source_url matches no known source are never inserted and
        never crash the run -- they're counted as skipped with a reason.
        """
        rows = read_v0_rows(conn, v0_table)
        report.read_counts[v0_table] = len(rows)
        inserted = 0
        skipped = 0
        for row in rows:
            found, source_id = resolve_source_id(row.get("source_url"))
            if not found:
                skipped += 1
                report._record_skip(v0_table, "unknown_source_url")
                continue
            if source_id is None and not self.dry_run:
                # Source lookup resolved but returned no id outside dry-run --
                # treat as a data integrity gap, never invent a parent.
                skipped += 1
                report._record_skip(v0_table, "source_not_persisted")
                continue
            mapped = map_row(row, source_id)
            inserted_flag = _insert_if_absent(
                self.executor, v2_table, mapped, natural_key(mapped), self.dry_run
            )
            if inserted_flag:
                inserted += 1
            else:
                skipped += 1
                report._record_skip(v0_table, "already_present")
        report.inserted_counts[v0_table] = inserted
        report.skipped_counts.setdefault(v0_table, 0)
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
    ) -> dict[Any, Optional[int]]:
        rows = read_v0_rows(conn, v0_table)
        report.read_counts[v0_table] = len(rows)
        inserted = 0
        skipped = 0
        id_map: dict[Any, Optional[int]] = {}
        for row in rows:
            mapped = map_row(row)
            key = natural_key(mapped)
            existing = self.executor.fetchone(
                f"SELECT id FROM {v2_table} WHERE "
                + " AND ".join(f"{col} = %s" for col in key),
                tuple(key.values()),
            )
            if existing is not None:
                id_map[row["id"]] = existing["id"]
                skipped += 1
                continue
            if self.dry_run:
                id_map[row["id"]] = None
                inserted += 1
                continue
            columns = list(mapped.keys())
            placeholders = ", ".join(["%s"] * len(columns))
            new_id = self.executor.execute(
                f"INSERT INTO {v2_table} ({', '.join(columns)}) VALUES ({placeholders})",
                tuple(mapped[c] for c in columns),
            )
            id_map[row["id"]] = new_id
            inserted += 1
        report.inserted_counts[v0_table] = inserted
        report.skipped_counts[v0_table] = skipped
        return id_map
