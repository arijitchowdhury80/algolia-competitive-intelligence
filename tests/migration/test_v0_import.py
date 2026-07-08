"""Tests for the V0 -> V2 migration (Gate 2).

No live Postgres, no network. Mapping functions are tested as pure dict-in
dict-out transforms; the IO layer is tested against a small in-memory sqlite
fixture (invented V0-shaped tables, matching the Gate 0 inventory row
counts' *shape*, not exact V0 column names -- those are unknown until this
runs on the VPS) and a fake SqlExecutor that stands in for Postgres.
"""

from __future__ import annotations

import re
import sqlite3

import pytest

from cios.migration.v0_import import (
    ImportReport,
    V0Importer,
    V0SchemaError,
    introspect_columns,
    map_bot_delivery,
    map_report,
    map_semantic_delta,
    map_semantic_fact,
    map_snapshot,
    map_source,
    map_source_health_event,
    normalize_url,
    read_v0_rows,
    resolve_column_map,
)


# ---------------------------------------------------------------------------
# Pure mapping function tests
# ---------------------------------------------------------------------------


def test_normalize_url_lowercases_and_strips_trailing_slash():
    assert normalize_url("HTTPS://Example.com/Blog/") == "https://example.com/blog"


def test_map_source_active_flag_and_normalized_url():
    row = {
        "id": 1,
        "name": "Constructor Blog",
        "url": "https://Constructor.io/Blog/",
        "competitor": "Constructor",
        "source_family": "blog",
        "active": 1,
        "first_seen_at": "2026-01-01",
        "last_seen_at": "2026-07-01",
        "last_checked_at": "2026-07-01",
    }
    mapped = map_source(row, tenant_id=1, competitor_id=42)
    assert mapped["tenant_id"] == 1
    assert mapped["competitor_id"] == 42
    assert mapped["normalized_url"] == "https://constructor.io/blog"
    assert mapped["status"] == "active"
    assert mapped["evidence"] == {"v0_source_id": 1}


def test_map_source_inactive_flag_maps_to_retired():
    row = {"id": 2, "name": "Old page", "url": "https://x.com/a", "competitor": "X", "active": 0}
    mapped = map_source(row, tenant_id=1, competitor_id=1)
    assert mapped["status"] == "retired"


def test_map_source_missing_source_family_falls_back_to_unknown():
    row = {"id": 3, "name": "n", "url": "https://x.com", "competitor": "X"}
    mapped = map_source(row, tenant_id=1, competitor_id=1)
    assert mapped["source_family"] == "unknown"


def test_map_snapshot_carries_v0_id_and_content_preview_in_metadata():
    row = {
        "id": 55,
        "source_id": 1,
        "fetched_at": "2026-07-01T09:00:00Z",
        "content_hash": "abc123",
        "content": "x" * 1000,
    }
    mapped = map_snapshot(row, tenant_id=1, source_id=9)
    assert mapped["source_id"] == 9
    assert mapped["fetch_run_id"] is None
    assert mapped["metadata"]["v0_snapshot_id"] == 55
    assert len(mapped["metadata"]["content_preview"]) == 500


def test_map_semantic_fact_synthesizes_evidence_when_v0_has_none():
    row = {"id": 7, "statement": "Constructor shipped a new ranking model."}
    mapped = map_semantic_fact(row, tenant_id=1, competitor_id=42)
    assert mapped["evidence_ids"] == ["v0:semantic_facts:7"]


def test_map_semantic_fact_preserves_existing_evidence_ids():
    row = {"id": 8, "statement": "s", "evidence_ids": ["url:https://x.com"]}
    mapped = map_semantic_fact(row, tenant_id=1, competitor_id=42)
    assert mapped["evidence_ids"] == ["url:https://x.com"]


def test_map_semantic_delta_forces_draft_when_published_without_evidence():
    row = {"id": 9, "what_changed": "pricing page rewritten", "quality_status": "published"}
    mapped = map_semantic_delta(row, tenant_id=1, competitor_id=42)
    # semantic_delta_published_needs_evidence: never carry 'published' forward
    # without evidence.
    assert mapped["quality_status"] == "draft"
    assert mapped["evidence_ids"] == ["v0:semantic_deltas:9"]


def test_map_semantic_delta_keeps_published_when_evidence_present():
    row = {
        "id": 10,
        "what_changed": "pricing page rewritten",
        "quality_status": "published",
        "evidence_ids": ["url:https://x.com/pricing"],
    }
    mapped = map_semantic_delta(row, tenant_id=1, competitor_id=42)
    assert mapped["quality_status"] == "published"


def test_map_source_health_event_normalizes_unknown_event_type():
    row = {"id": 1, "event_type": "weird_v0_status", "created_at": "2026-07-01T00:00:00Z"}
    mapped = map_source_health_event(row, tenant_id=1, source_id=5)
    assert mapped["event_type"] == "fetch_error"
    assert mapped["metadata"]["v0_event_type"] == "weird_v0_status"


def test_map_source_health_event_keeps_known_event_type():
    row = {"id": 2, "event_type": "timeout", "created_at": "2026-07-01T00:00:00Z"}
    mapped = map_source_health_event(row, tenant_id=1, source_id=5)
    assert mapped["event_type"] == "timeout"
    assert "v0_event_type" not in mapped["metadata"]


def test_map_report_defaults_cadence_to_daily():
    row = {"id": 1, "report_date": "2026-07-01"}
    mapped = map_report(row, tenant_id=1)
    assert mapped["cadence"] == "daily"
    assert mapped["metadata"] == {"v0_report_id": 1}


def test_map_bot_delivery_redacts_recipient_and_normalizes_status():
    row = {
        "id": 1,
        "channel": "telegram",
        "created_at": "2026-07-01T09:00:00Z",
        "recipient": "6789423537",
        "status": "not_a_real_status",
    }
    mapped = map_bot_delivery(row, tenant_id=1)
    assert mapped["recipient_redacted"] == "***3537"
    assert mapped["status"] == "sent"  # unrecognized status falls back safely


# ---------------------------------------------------------------------------
# Column introspection / fail-loudly tests
# ---------------------------------------------------------------------------


@pytest.fixture
def v0_conn():
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE sources (
            id INTEGER PRIMARY KEY,
            name TEXT,
            url TEXT,
            competitor TEXT,
            type TEXT,
            active INTEGER
        );
        CREATE TABLE snapshots (
            id INTEGER PRIMARY KEY,
            source_id INTEGER,
            fetched_at TEXT,
            content_hash TEXT,
            content TEXT
        );
        CREATE TABLE semantic_facts (
            id INTEGER PRIMARY KEY,
            source_id INTEGER,
            statement TEXT,
            confidence REAL
        );
        CREATE TABLE semantic_deltas (
            id INTEGER PRIMARY KEY,
            source_id INTEGER,
            what_changed TEXT,
            quality_status TEXT,
            created_at TEXT
        );
        CREATE TABLE source_health_events (
            id INTEGER PRIMARY KEY,
            source_id INTEGER,
            event_type TEXT,
            created_at TEXT
        );
        CREATE TABLE report_index (
            id INTEGER PRIMARY KEY,
            report_date TEXT,
            title TEXT
        );
        CREATE TABLE bot_deliveries (
            id INTEGER PRIMARY KEY,
            channel TEXT,
            recipient TEXT,
            status TEXT,
            created_at TEXT
        );
        """
    )
    conn.executemany(
        "INSERT INTO sources (id, name, url, competitor, type, active) VALUES (?,?,?,?,?,?)",
        [
            (1, "Constructor Blog", "https://constructor.io/blog", "Constructor", "blog", 1),
            (2, "Coveo Newsroom", "https://coveo.com/news", "Coveo", "news", 1),
        ],
    )
    conn.executemany(
        "INSERT INTO snapshots (id, source_id, fetched_at, content_hash, content) VALUES (?,?,?,?,?)",
        [
            (1, 1, "2026-07-01T09:00:00Z", "hash1", "some content"),
            (2, 2, "2026-07-01T09:05:00Z", "hash2", "other content"),
        ],
    )
    conn.executemany(
        "INSERT INTO semantic_facts (id, source_id, statement, confidence) VALUES (?,?,?,?)",
        [(1, 1, "Constructor uses vector search.", 0.9)],
    )
    conn.executemany(
        "INSERT INTO semantic_deltas (id, source_id, what_changed, quality_status, created_at) VALUES (?,?,?,?,?)",
        [(1, 1, "New pricing page", "published", "2026-07-01T00:00:00Z")],
    )
    conn.executemany(
        "INSERT INTO source_health_events (id, source_id, event_type, created_at) VALUES (?,?,?,?)",
        [(1, 1, "ok", "2026-07-01T00:00:00Z"), (2, 2, "timeout", "2026-07-01T01:00:00Z")],
    )
    conn.executemany(
        "INSERT INTO report_index (id, report_date, title) VALUES (?,?,?)",
        [(1, "2026-07-01", "Daily Brief")],
    )
    conn.executemany(
        "INSERT INTO bot_deliveries (id, channel, recipient, status, created_at) VALUES (?,?,?,?,?)",
        [(1, "telegram", "6789423537", "sent", "2026-07-01T09:00:00Z")],
    )
    conn.commit()
    yield conn
    conn.close()


def test_resolve_column_map_raises_v0_schema_error_when_required_missing():
    with pytest.raises(V0SchemaError) as exc_info:
        resolve_column_map("sources", {"id", "name"})  # missing url, competitor
    message = str(exc_info.value)
    assert "url" in message
    assert "competitor" in message


def test_read_v0_rows_uses_column_aliases(v0_conn):
    rows = read_v0_rows(v0_conn, "sources")
    assert len(rows) == 2
    assert rows[0]["competitor"] == "Constructor"
    assert rows[0]["source_family"] == "blog"  # aliased from 'type'


def test_read_v0_rows_raises_for_missing_table():
    conn = sqlite3.connect(":memory:")
    with pytest.raises(V0SchemaError):
        read_v0_rows(conn, "sources")
    conn.close()


# ---------------------------------------------------------------------------
# Fake Postgres executor (dict-backed) for IO-layer / idempotency tests.
# ---------------------------------------------------------------------------


class FakeExecutor:
    """Minimal in-memory stand-in for a Postgres connection.

    Only understands the small set of SQL shapes v0_import.py generates:
    `SELECT id FROM t WHERE c1 = %s AND c2 = %s ...` and
    `INSERT INTO t (c1, c2, ...) VALUES (%s, %s, ...)`.
    """

    def __init__(self) -> None:
        self.tables: dict[str, list[dict]] = {}
        self._next_id: dict[str, int] = {}

    def seed(self, table: str, rows: list[dict]) -> None:
        self.tables[table] = list(rows)
        self._next_id[table] = max((r["id"] for r in rows), default=0) + 1

    def fetchone(self, sql: str, params: tuple = ()):
        match = re.match(r"SELECT id FROM (\w+) WHERE (.+)", sql.strip())
        table, where = match.group(1), match.group(2)
        cols = re.findall(r"(\w+)\s*=\s*%s", where)
        rows = self.tables.get(table, [])
        for row in rows:
            if all(row.get(col) == val for col, val in zip(cols, params)):
                return {"id": row["id"]}
        return None

    def fetchall(self, sql: str, params: tuple = ()):
        raise NotImplementedError("not used by v0_import.py")

    def execute(self, sql: str, params: tuple = ()):
        match = re.match(r"INSERT INTO (\w+) \(([^)]+)\)", sql.strip())
        table = match.group(1)
        cols = [c.strip() for c in match.group(2).split(",")]
        row = dict(zip(cols, params))
        new_id = self._next_id.get(table, 1)
        row["id"] = new_id
        self.tables.setdefault(table, []).append(row)
        self._next_id[table] = new_id + 1
        return new_id


@pytest.fixture
def fake_executor():
    executor = FakeExecutor()
    executor.seed("tenants", [{"id": 1, "slug": "algolia"}])
    return executor


def test_v0_importer_full_run_maps_all_tables(v0_conn, fake_executor):
    importer = V0Importer(sqlite_path=":memory:", executor=fake_executor, tenant_slug="algolia")
    report = importer.run(conn=v0_conn)

    assert isinstance(report, ImportReport)
    assert report.dry_run is False

    assert report.read_counts["sources"] == 2
    assert report.inserted_counts["sources"] == 2
    assert len(fake_executor.tables["competitors"]) == 2  # Constructor, Coveo
    assert len(fake_executor.tables["sources"]) == 2

    assert report.inserted_counts["snapshots"] == 2
    assert len(fake_executor.tables["source_snapshots"]) == 2

    assert report.inserted_counts["semantic_facts"] == 1
    fact = fake_executor.tables["semantic_facts"][0]
    assert fact["evidence_ids"] == ["v0:semantic_facts:1"]

    assert report.inserted_counts["semantic_deltas"] == 1
    delta = fake_executor.tables["semantic_deltas"][0]
    # published with no V0 evidence array -> forced to draft.
    assert delta["quality_status"] == "draft"

    assert report.inserted_counts["source_health_events"] == 2
    assert report.inserted_counts["report_index"] == 1
    assert report.inserted_counts["bot_deliveries"] == 1

    # tenant scoping: every inserted row carries tenant_id 1.
    for table in ("sources", "source_snapshots", "semantic_facts", "semantic_deltas",
                   "source_health_events", "reports", "bot_deliveries"):
        for row in fake_executor.tables.get(table, []):
            assert row["tenant_id"] == 1


def test_v0_importer_rerun_is_idempotent(v0_conn, fake_executor):
    importer = V0Importer(sqlite_path=":memory:", executor=fake_executor, tenant_slug="algolia")
    importer.run(conn=v0_conn)

    counts_after_first_run = {t: len(rows) for t, rows in fake_executor.tables.items()}

    second_report = importer.run(conn=v0_conn)

    # nothing new inserted on re-run.
    assert second_report.inserted_counts["sources"] == 0
    assert second_report.inserted_counts["snapshots"] == 0
    assert second_report.inserted_counts["semantic_facts"] == 0
    assert second_report.inserted_counts["semantic_deltas"] == 0
    assert second_report.inserted_counts["source_health_events"] == 0
    assert second_report.inserted_counts["report_index"] == 0
    assert second_report.inserted_counts["bot_deliveries"] == 0

    counts_after_second_run = {t: len(rows) for t, rows in fake_executor.tables.items()}
    assert counts_after_first_run == counts_after_second_run


def test_v0_importer_dry_run_reads_but_does_not_write(v0_conn, fake_executor):
    importer = V0Importer(
        sqlite_path=":memory:", executor=fake_executor, tenant_slug="algolia", dry_run=True
    )
    report = importer.run(conn=v0_conn)

    assert report.dry_run is True
    assert report.read_counts["sources"] == 2
    assert report.inserted_counts["sources"] == 2  # counted as "would insert"
    # but no actual rows landed in the fake Postgres tables.
    assert "competitors" not in fake_executor.tables
    assert "sources" not in fake_executor.tables
    assert "source_snapshots" not in fake_executor.tables


def test_v0_importer_missing_tenant_raises():
    executor = FakeExecutor()  # no tenants seeded
    conn = sqlite3.connect(":memory:")
    conn.executescript("CREATE TABLE sources (id INTEGER PRIMARY KEY, name TEXT, url TEXT, competitor TEXT);")
    importer = V0Importer(sqlite_path=":memory:", executor=executor, tenant_slug="algolia")
    with pytest.raises(V0SchemaError, match="Tenant slug"):
        importer.run(conn=conn)
    conn.close()
