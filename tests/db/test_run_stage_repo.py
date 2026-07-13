from __future__ import annotations

from contextlib import contextmanager

from cios.db.repos.run_stage import PgRunStageRepository


class _FakeCursor:
    def __init__(self, row: dict | None = None) -> None:
        self.row = row or {"id": 123}
        self.sql = ""
        self.params = None
        self.executed: list[tuple[str, object]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, sql: str, params) -> None:
        self.sql = sql
        self.params = params
        self.executed.append((sql, params))

    def fetchone(self) -> dict:
        return self.row


class _FakeConnection:
    def __init__(self, *, row: dict | None = None) -> None:
        self.cursor_obj = _FakeCursor(row=row)
        self.executed: list[tuple] = []

    @contextmanager
    def transaction(self):
        yield self

    def execute(self, *args, **kwargs) -> None:
        self.executed.append((args, kwargs))
        return None

    def cursor(self, **_kwargs) -> _FakeCursor:
        return self.cursor_obj


def test_start_ledger_creates_running_parent() -> None:
    conn = _FakeConnection(row={"id": 321})

    ledger_id = PgRunStageRepository(conn).start_ledger(
        tenant_id=1,
        run_id="daily-algolia-2026-07-11",
        package_name="cios.daily",
        metadata={"trigger": "hermes-cron"},
    )

    assert ledger_id == 321
    assert "INSERT INTO run_stage_ledgers" in conn.cursor_obj.sql
    assert "status, started_at" in conn.cursor_obj.sql
    assert "RETURNING id" in conn.cursor_obj.sql
    assert conn.cursor_obj.params["tenant_id"] == 1
    assert conn.cursor_obj.params["run_id"] == "daily-algolia-2026-07-11"
    assert conn.cursor_obj.params["package_name"] == "cios.daily"
    assert conn.cursor_obj.params["status"] == "running"
    assert conn.cursor_obj.params["metadata"].obj == {"trigger": "hermes-cron"}


def test_save_run_stage_ledger_bulk_inserts_parent_and_ordered_events() -> None:
    conn = _FakeConnection(row={"id": 321})

    ledger_id = PgRunStageRepository(conn).save_run_stage_ledger(
        tenant_id=1,
        run_id="daily-algolia-2026-07-11",
        package_name="cios.daily",
        status="completed",
        stage_ledger=[
            {
                "stage": "source_sweep",
                "status": "completed",
                "started_at": "2026-07-11T22:35:00Z",
                "ended_at": "2026-07-11T22:35:05Z",
                "elapsed_s": 5.1,
                "attempted_sources": 48,
            }
        ],
        metadata={"trigger": "hermes-cron"},
    )

    assert ledger_id == 321
    assert len(conn.cursor_obj.executed) == 2
    parent_sql, parent_params = conn.cursor_obj.executed[0]
    event_sql, event_params = conn.cursor_obj.executed[1]
    assert "INSERT INTO run_stage_ledgers" in parent_sql
    assert parent_params["status"] == "completed"
    assert parent_params["metadata"].obj == {"trigger": "hermes-cron"}
    assert "INSERT INTO run_stage_events" in event_sql
    assert "jsonb_to_recordset" in event_sql
    assert event_params["events"].obj[0]["stage_order"] == 1
    assert event_params["events"].obj[0]["stage"] == "source_sweep"
    assert event_params["events"].obj[0]["metadata"] == {"attempted_sources": 48}


def test_start_stage_upserts_running_stage_event() -> None:
    conn = _FakeConnection(row={"id": 654})

    event_id = PgRunStageRepository(conn).start_stage(
        tenant_id=1,
        ledger_id=321,
        stage_order=2,
        stage="source_sweep",
        metadata={"active_sources": 48},
    )

    assert event_id == 654
    assert "INSERT INTO run_stage_events" in conn.cursor_obj.sql
    assert "ON CONFLICT (tenant_id, ledger_id, stage_order)" in conn.cursor_obj.sql
    assert "status = 'running'" in conn.cursor_obj.sql
    assert conn.cursor_obj.params["tenant_id"] == 1
    assert conn.cursor_obj.params["ledger_id"] == 321
    assert conn.cursor_obj.params["stage_order"] == 2
    assert conn.cursor_obj.params["stage"] == "source_sweep"
    assert conn.cursor_obj.params["metadata"].obj == {"active_sources": 48}


def test_finish_stage_records_terminal_status_elapsed_time_and_error() -> None:
    conn = _FakeConnection()

    PgRunStageRepository(conn).finish_stage(
        tenant_id=1,
        event_id=654,
        status="failed",
        metadata={"attempted_sources": 48},
        error_type="TimeoutError",
        error="source sweep exceeded budget",
    )

    assert "UPDATE run_stage_events" in conn.cursor_obj.sql
    assert "elapsed_s = EXTRACT(EPOCH" in conn.cursor_obj.sql
    assert "metadata = run_stage_events.metadata || %(metadata)s::jsonb" in conn.cursor_obj.sql
    assert conn.cursor_obj.params["tenant_id"] == 1
    assert conn.cursor_obj.params["event_id"] == 654
    assert conn.cursor_obj.params["status"] == "failed"
    assert conn.cursor_obj.params["error_type"] == "TimeoutError"
    assert conn.cursor_obj.params["error"] == "source sweep exceeded budget"
    assert conn.cursor_obj.params["metadata"].obj == {"attempted_sources": 48}


def test_finish_ledger_records_terminal_parent_status() -> None:
    conn = _FakeConnection()

    PgRunStageRepository(conn).finish_ledger(
        tenant_id=1,
        ledger_id=321,
        status="completed",
        metadata={"published": True},
    )

    assert "UPDATE run_stage_ledgers" in conn.cursor_obj.sql
    assert "ended_at = COALESCE" in conn.cursor_obj.sql
    assert "metadata = run_stage_ledgers.metadata || %(metadata)s::jsonb" in conn.cursor_obj.sql
    assert conn.cursor_obj.params["tenant_id"] == 1
    assert conn.cursor_obj.params["ledger_id"] == 321
    assert conn.cursor_obj.params["status"] == "completed"
    assert conn.cursor_obj.params["metadata"].obj == {"published": True}
