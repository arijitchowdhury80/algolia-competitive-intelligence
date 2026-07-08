"""Tests for the V0 -> V2 migration (Gate 2).

No live Postgres, no network. Mapping functions are tested as pure dict-in
dict-out transforms; the IO layer is tested against a small in-memory sqlite
fixture that mirrors the REAL production `ci.sqlite` schema (verified
2026-07-08: 43 sources, 351 snapshots, 13 semantic_facts, 86 semantic_deltas,
351 source_health_events, 12 report_index, 12 bot_deliveries) -- column
names, not just row-count shape. A separate read-only integration test runs
the importer's dry-run against the real file at /tmp/v0-ci.sqlite when it is
present on disk (never checked into the repo), skipping gracefully when it
is not.
"""

from __future__ import annotations

import os
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

REAL_V0_SQLITE_PATH = "/tmp/v0-ci.sqlite"


# ---------------------------------------------------------------------------
# Pure mapping function tests
# ---------------------------------------------------------------------------


def test_normalize_url_lowercases_and_strips_trailing_slash():
    assert normalize_url("HTTPS://Example.com/Blog/") == "https://example.com/blog"


def test_map_source_active_flag_and_normalized_url():
    row = {
        "id": 1,
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
    row = {"id": 2, "url": "https://x.com/a", "competitor": "X", "active": 0}
    mapped = map_source(row, tenant_id=1, competitor_id=1)
    assert mapped["status"] == "retired"


def test_map_source_missing_source_family_falls_back_to_unknown():
    row = {"id": 3, "url": "https://x.com", "competitor": "X"}
    mapped = map_source(row, tenant_id=1, competitor_id=1)
    assert mapped["source_family"] == "unknown"


def test_map_source_derives_title_when_no_name_column():
    # Real prod sources has no `name` column at all.
    row = {"id": 4, "url": "https://x.com", "competitor": "Coveo", "source_family": "blog"}
    mapped = map_source(row, tenant_id=1, competitor_id=1)
    assert mapped["title"] == "Coveo blog"


def test_map_snapshot_carries_v0_id_and_content_preview_in_metadata():
    row = {
        "id": 55,
        "source_url": "https://constructor.io/blog",
        "fetched_at": "2026-07-01T09:00:00Z",
        "content_hash": "abc123",
        "content": "x" * 1000,
        "status": "ok",
        "http_status": 200,
    }
    mapped = map_snapshot(row, tenant_id=1, source_id=9)
    assert mapped["source_id"] == 9
    assert mapped["fetch_run_id"] is None
    assert mapped["metadata"]["v0_snapshot_id"] == 55
    assert mapped["metadata"]["status"] == "ok"
    assert mapped["metadata"]["http_status"] == 200
    assert len(mapped["metadata"]["content_preview"]) == 500


def test_map_semantic_fact_uses_evidence_text_as_statement():
    row = {
        "id": 7,
        "evidence_text": "Constructor shipped a new ranking model.",
        "evidence_url": "https://constructor.io/blog/ranking",
    }
    mapped = map_semantic_fact(row, tenant_id=1, competitor_id=42)
    assert mapped["statement"] == "Constructor shipped a new ranking model."
    assert mapped["evidence_ids"] == ["https://constructor.io/blog/ranking"]


def test_map_semantic_fact_falls_back_to_fact_json_when_evidence_text_blank():
    row = {
        "id": 8,
        "evidence_text": "",
        "fact_json": '{"strategic_claim": "New enterprise tier launched"}',
    }
    mapped = map_semantic_fact(row, tenant_id=1, competitor_id=42)
    assert mapped["statement"] == "New enterprise tier launched"


def test_map_semantic_fact_synthesizes_evidence_when_v0_has_none():
    row = {"id": 9, "evidence_text": "s"}
    mapped = map_semantic_fact(row, tenant_id=1, competitor_id=42)
    assert mapped["evidence_ids"] == ["v0:semantic_facts:9"]


def test_map_semantic_delta_maps_real_columns_and_folds_owner_into_action():
    row = {
        "id": 9,
        "what_changed": "pricing page rewritten",
        "why_it_matters": "new tier introduced",
        "implication": "monitor pricing narrative",
        "recommended_action": "Flag to AE team.",
        "action_owner": "Competitive Intelligence",
        "quality_status": "published",
        "evidence_urls": '["https://x.com/pricing"]',
    }
    mapped = map_semantic_delta(row, tenant_id=1, competitor_id=42)
    assert mapped["what_changed"] == "pricing page rewritten"
    assert mapped["why_it_matters"] == "new tier introduced"
    assert mapped["implication"] == "monitor pricing narrative"
    assert mapped["recommended_action"] == "[Owner: Competitive Intelligence] Flag to AE team."
    assert mapped["evidence_ids"] == ["https://x.com/pricing"]
    assert mapped["quality_status"] == "published"


def test_map_semantic_delta_forces_draft_when_published_without_evidence():
    row = {"id": 10, "what_changed": "pricing page rewritten", "quality_status": "published"}
    mapped = map_semantic_delta(row, tenant_id=1, competitor_id=42)
    # semantic_delta_published_needs_evidence: never carry 'published' forward
    # without evidence.
    assert mapped["quality_status"] == "draft"
    assert mapped["evidence_ids"] == ["v0:semantic_deltas:10"]


def test_map_semantic_delta_handles_malformed_evidence_urls_json():
    row = {"id": 11, "what_changed": "x", "evidence_urls": "not valid json"}
    mapped = map_semantic_delta(row, tenant_id=1, competitor_id=42)
    assert mapped["evidence_ids"] == ["v0:semantic_deltas:11"]


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


def test_map_source_health_event_preserves_extra_fields_in_metadata():
    row = {
        "id": 3,
        "event_type": "ok",
        "created_at": "2026-07-01T00:00:00Z",
        "failure_streak": 0,
        "collector": "direct_http",
        "duration_ms": 241,
    }
    mapped = map_source_health_event(row, tenant_id=1, source_id=5)
    assert mapped["metadata"]["failure_streak"] == 0
    assert mapped["metadata"]["collector"] == "direct_http"
    assert mapped["metadata"]["duration_ms"] == 241


def test_map_report_defaults_cadence_to_daily_and_maps_generated_to_rendered():
    row = {"id": 1, "report_date": "2026-07-01", "status": "generated"}
    mapped = map_report(row, tenant_id=1)
    assert mapped["cadence"] == "daily"
    assert mapped["status"] == "rendered"
    assert mapped["metadata"]["v0_report_id"] == 1


def test_map_report_synthesizes_title_when_missing():
    row = {"id": 2, "report_date": "2026-07-01", "cadence": "weekly"}
    mapped = map_report(row, tenant_id=1)
    assert mapped["title"] == "Weekly report 2026-07-01"


def test_map_bot_delivery_redacts_recipient_and_normalizes_queued_status():
    row = {
        "id": 1,
        "channel": "telegram",
        "created_at": "2026-07-01T09:00:00Z",
        "recipient": "6789423537",
        "status": "queued_for_telegram",
        "delivered_at": "2026-07-01T09:00:23",
    }
    mapped = map_bot_delivery(row, tenant_id=1, report_id=7)
    assert mapped["recipient_redacted"] == "***3537"
    # delivered_at present -> trust it over the "queued_" label.
    assert mapped["status"] == "delivered"
    assert mapped["report_id"] == 7


def test_map_bot_delivery_queued_without_delivered_at_stays_queued():
    row = {
        "id": 2,
        "channel": "telegram",
        "created_at": "2026-07-01T09:00:00Z",
        "status": "queued_for_telegram",
    }
    mapped = map_bot_delivery(row, tenant_id=1, report_id=None)
    assert mapped["status"] == "queued"


def test_map_bot_delivery_unrecognized_status_falls_back_safely():
    row = {
        "id": 3,
        "channel": "telegram",
        "created_at": "2026-07-01T09:00:00Z",
        "status": "not_a_real_status",
    }
    mapped = map_bot_delivery(row, tenant_id=1, report_id=None)
    assert mapped["status"] == "sent"


# ---------------------------------------------------------------------------
# Column introspection / fail-loudly tests
# ---------------------------------------------------------------------------


@pytest.fixture
def v0_conn():
    """In-memory sqlite mirroring the REAL prod ci.sqlite schema (verified
    2026-07-08). Includes one snapshot/health-event whose source_url matches
    a known source, and one orphan row per child table whose source_url
    matches nothing in `sources` (to exercise the skip-and-count path)."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE sources (
            id INTEGER PRIMARY KEY,
            competitor TEXT,
            tier INTEGER,
            url TEXT,
            source_type TEXT,
            signal_type TEXT,
            cadence TEXT,
            priority INTEGER,
            enabled INTEGER,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT,
            collector TEXT,
            fallback_collectors TEXT,
            expected_content_markers TEXT,
            requires_js INTEGER,
            gated INTEGER,
            criticality TEXT
        );
        CREATE TABLE snapshots (
            id INTEGER PRIMARY KEY,
            source_url TEXT,
            fetched_at TEXT,
            status TEXT,
            http_status INTEGER,
            content_hash TEXT,
            content_text TEXT,
            error TEXT,
            collector TEXT,
            duration_ms INTEGER,
            quality_score REAL
        );
        CREATE TABLE semantic_facts (
            id INTEGER PRIMARY KEY,
            source_url TEXT,
            competitor TEXT,
            source_type TEXT,
            detected_date TEXT,
            fact_type TEXT,
            fact_json TEXT,
            evidence_text TEXT,
            evidence_url TEXT,
            confidence REAL,
            created_at TEXT
        );
        CREATE TABLE semantic_deltas (
            id INTEGER PRIMARY KEY,
            source_url TEXT,
            competitor TEXT,
            source_type TEXT,
            detected_date TEXT,
            delta_type TEXT,
            before_json TEXT,
            after_json TEXT,
            delta_summary TEXT,
            materiality_score REAL,
            materiality_reason TEXT,
            algolia_implication TEXT,
            action_owner TEXT,
            recommended_action TEXT,
            evidence_urls TEXT,
            quality_status TEXT,
            created_at TEXT
        );
        CREATE TABLE source_health_events (
            id INTEGER PRIMARY KEY,
            source_url TEXT,
            status TEXT,
            failure_reason TEXT,
            http_status INTEGER,
            last_success_at TEXT,
            last_failure_at TEXT,
            failure_streak INTEGER,
            replacement_recommendation TEXT,
            created_at TEXT,
            collector TEXT,
            duration_ms INTEGER,
            quality_score REAL,
            recommended_collector TEXT
        );
        CREATE TABLE report_index (
            id INTEGER PRIMARY KEY,
            cadence TEXT,
            date_start TEXT,
            date_end TEXT,
            markdown_path TEXT,
            html_path TEXT,
            pdf_path TEXT,
            quality_score REAL,
            top_signal_ids TEXT,
            top_action_owners TEXT,
            source_health_summary TEXT,
            status TEXT,
            created_at TEXT
        );
        CREATE TABLE bot_deliveries (
            id INTEGER PRIMARY KEY,
            report_id INTEGER,
            bot_profile TEXT,
            channel TEXT,
            recipient TEXT,
            status TEXT,
            delivered_at TEXT,
            error TEXT,
            created_at TEXT,
            cadence TEXT,
            message_kind TEXT,
            markdown_path TEXT,
            html_path TEXT,
            dashboard_url TEXT,
            artifact_paths TEXT,
            delivery_metadata TEXT,
            updated_at TEXT
        );
        """
    )
    conn.executemany(
        "INSERT INTO sources (id, competitor, url, source_type, enabled) VALUES (?,?,?,?,?)",
        [
            (1, "Constructor", "https://constructor.io/blog", "blog", 1),
            (2, "Coveo", "https://coveo.com/news", "news", 1),
        ],
    )
    conn.executemany(
        "INSERT INTO snapshots (id, source_url, fetched_at, content_hash, content_text, status) VALUES (?,?,?,?,?,?)",
        [
            (1, "https://constructor.io/blog", "2026-07-01T09:00:00Z", "hash1", "some content", "ok"),
            (2, "https://coveo.com/news", "2026-07-01T09:05:00Z", "hash2", "other content", "ok"),
            # orphan: no source with this url.
            (3, "https://unknown-vendor.example.com/blog", "2026-07-01T09:10:00Z", "hash3", "x", "ok"),
        ],
    )
    conn.executemany(
        "INSERT INTO semantic_facts (id, source_url, competitor, evidence_text, evidence_url, confidence) VALUES (?,?,?,?,?,?)",
        [(1, "https://constructor.io/blog", "Constructor", "Constructor uses vector search.", "https://constructor.io/blog", 0.9)],
    )
    conn.executemany(
        "INSERT INTO semantic_deltas (id, source_url, competitor, delta_summary, quality_status, action_owner, evidence_urls, created_at) VALUES (?,?,?,?,?,?,?,?)",
        [(1, "https://constructor.io/blog", "Constructor", "New pricing page", "published", "AE Team", '["https://constructor.io/pricing"]', "2026-07-01T00:00:00Z")],
    )
    conn.executemany(
        "INSERT INTO source_health_events (id, source_url, status, created_at) VALUES (?,?,?,?)",
        [
            (1, "https://constructor.io/blog", "ok", "2026-07-01T00:00:00Z"),
            (2, "https://coveo.com/news", "timeout", "2026-07-01T01:00:00Z"),
        ],
    )
    conn.executemany(
        "INSERT INTO report_index (id, cadence, date_start, status) VALUES (?,?,?,?)",
        [(1, "daily", "2026-07-01", "generated")],
    )
    conn.executemany(
        "INSERT INTO bot_deliveries (id, report_id, channel, recipient, status, created_at) VALUES (?,?,?,?,?,?)",
        [(1, 1, "telegram", "6789423537", "queued_for_telegram", "2026-07-01T09:00:00Z")],
    )
    conn.commit()
    yield conn
    conn.close()


def test_resolve_column_map_raises_v0_schema_error_when_required_missing():
    with pytest.raises(V0SchemaError) as exc_info:
        resolve_column_map("sources", {"id"})  # missing url, competitor
    message = str(exc_info.value)
    assert "url" in message
    assert "competitor" in message


def test_read_v0_rows_uses_column_aliases(v0_conn):
    rows = read_v0_rows(v0_conn, "sources")
    assert len(rows) == 2
    assert rows[0]["competitor"] == "Constructor"
    assert rows[0]["source_family"] == "blog"  # aliased from 'source_type'


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

    assert report.read_counts["snapshots"] == 3
    assert report.inserted_counts["snapshots"] == 2
    assert report.skip_reasons["snapshots"]["unknown_source_url"] == 1
    assert len(fake_executor.tables["source_snapshots"]) == 2

    assert report.inserted_counts["semantic_facts"] == 1
    fact = fake_executor.tables["semantic_facts"][0]
    assert fact["statement"] == "Constructor uses vector search."
    assert fact["evidence_ids"] == ["https://constructor.io/blog"]

    assert report.inserted_counts["semantic_deltas"] == 1
    delta = fake_executor.tables["semantic_deltas"][0]
    assert delta["what_changed"] == "New pricing page"
    assert delta["recommended_action"] == "[Owner: AE Team] "
    # published WITH evidence -> stays published.
    assert delta["quality_status"] == "published"

    assert report.inserted_counts["source_health_events"] == 2
    assert report.inserted_counts["report_index"] == 1
    assert fake_executor.tables["reports"][0]["status"] == "rendered"
    assert report.inserted_counts["bot_deliveries"] == 1
    delivery = fake_executor.tables["bot_deliveries"][0]
    assert delivery["report_id"] == fake_executor.tables["reports"][0]["id"]

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
    conn.executescript("CREATE TABLE sources (id INTEGER PRIMARY KEY, url TEXT, competitor TEXT);")
    importer = V0Importer(sqlite_path=":memory:", executor=executor, tenant_slug="algolia")
    with pytest.raises(V0SchemaError, match="Tenant slug"):
        importer.run(conn=conn)
    conn.close()


# ---------------------------------------------------------------------------
# Real-file integration test: read-only dry run against the actual prod
# ci.sqlite copy. Skips gracefully when the file isn't present (it's never
# checked into the repo -- pulled ad hoc from the VPS for verification).
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not os.path.exists(REAL_V0_SQLITE_PATH),
    reason=f"real V0 sqlite not present at {REAL_V0_SQLITE_PATH}",
)
def test_v0_importer_dry_run_against_real_prod_sqlite():
    executor = FakeExecutor()
    executor.seed("tenants", [{"id": 1, "slug": "algolia"}])
    importer = V0Importer(
        sqlite_path=REAL_V0_SQLITE_PATH,
        executor=executor,
        tenant_slug="algolia",
        dry_run=True,
    )
    conn = sqlite3.connect(REAL_V0_SQLITE_PATH)
    try:
        report = importer.run(conn=conn)
    finally:
        conn.close()

    assert report.read_counts["sources"] == 43
    assert report.read_counts["snapshots"] == 351
    assert report.read_counts["semantic_facts"] == 13
    assert report.read_counts["semantic_deltas"] == 86
    assert report.read_counts["source_health_events"] == 351
    assert report.read_counts["report_index"] == 12
    assert report.read_counts["bot_deliveries"] == 12
