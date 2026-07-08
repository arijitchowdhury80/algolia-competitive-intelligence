"""Regression test for the reader_text persistence gap: scripts/daily_production_run.py
called insert_report() at the daily brief call site without a `metadata` dict, so
reports.metadata never carried the full reader_text -- only a 200-char `summary`
truncation was ever persisted. rerender_dashboard.py's later read of
`reports.metadata.reader_text` therefore always came up empty.

insert_report() itself already accepted an optional `metadata` dict; this test
locks in that passing `metadata={"reader_text": ...}` actually reaches the SQL
call as a Json-wrapped parameter, using a fake psycopg-shaped connection so no
real Postgres is required.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from psycopg.types.json import Json

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_daily_production_run():
    spec = importlib.util.spec_from_file_location(
        "daily_production_run_under_test", REPO_ROOT / "scripts" / "daily_production_run.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def runner():
    return _load_daily_production_run()


class _FakeCursor:
    def __init__(self) -> None:
        self.last_call = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params):
        self.last_call = (sql, params)

    def fetchone(self):
        return {"id": 42}


class _FakeConn:
    def __init__(self) -> None:
        self.cursor_obj = _FakeCursor()
        self.executed_set_local = []

    def transaction(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, *args, **kwargs):
        # tenant_context's `SET LOCAL app.tenant_id = ...`
        self.executed_set_local.append(sql)

    def cursor(self, row_factory=None):
        return self.cursor_obj


def test_insert_report_persists_reader_text_metadata(runner) -> None:
    conn = _FakeConn()
    reader_text = "# Your competitive picture\n\nFull brief body text here."

    report_id = runner.insert_report(
        conn, tenant_id=7, cadence="daily", title="Argus daily brief - algolia",
        summary=reader_text[:200], metadata={"reader_text": reader_text},
    )

    assert report_id == 42
    sql, params = conn.cursor_obj.last_call
    assert "INSERT INTO reports" in sql
    # metadata is the last bind param, wrapped in psycopg's Json adapter.
    metadata_param = params[-1]
    assert isinstance(metadata_param, Json)
    assert metadata_param.obj == {"reader_text": reader_text}


def test_insert_report_defaults_metadata_to_empty_dict(runner) -> None:
    conn = _FakeConn()
    runner.insert_report(conn, tenant_id=7, cadence="daily", title="t", summary="s")
    _, params = conn.cursor_obj.last_call
    metadata_param = params[-1]
    assert isinstance(metadata_param, Json)
    assert metadata_param.obj == {}
