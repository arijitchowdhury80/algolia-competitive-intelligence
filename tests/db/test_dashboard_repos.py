from __future__ import annotations

from contextlib import contextmanager
from datetime import date

from cios.db.repos.dashboard import PgMonitoredCompetitorsRepository, PgReportHistoryRepository


class _FakeCursor:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows
        self.sql = ""
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, sql: str, params) -> None:
        self.sql = sql
        self.params = params

    def fetchall(self) -> list[dict]:
        return self.rows


class _FakeConnection:
    def __init__(self, rows: list[dict]) -> None:
        self.cursor_obj = _FakeCursor(rows)

    @contextmanager
    def transaction(self):
        yield self

    def execute(self, *_args, **_kwargs) -> None:
        return None

    def cursor(self, **_kwargs) -> _FakeCursor:
        return self.cursor_obj


def test_report_history_repo_selects_latest_per_report_date_before_limit() -> None:
    conn = _FakeConnection(
        [
            {
                "id": 12,
                "report_date": date(2026, 7, 10),
                "cadence": "daily",
                "title": "today",
                "summary": "summary",
                "status": "rendered",
                "html_path": None,
            }
        ]
    )

    rows = PgReportHistoryRepository(conn).get_recent_reports(tenant_id=1, limit=10)

    sql = conn.cursor_obj.sql
    assert rows[0]["report_date"] == date(2026, 7, 10)
    assert "DISTINCT ON (report_date, cadence)" in sql
    assert "latest_per_period" in sql
    assert "LIMIT %s" in sql


def test_monitored_competitors_repo_returns_active_source_rows_for_gap_planning() -> None:
    conn = _FakeConnection(
        [
            {
                "competitor_id": 7,
                "competitor_name": "Algonomy",
                "domain": "algonomy.com",
                "category": "commerce",
                "status": "active",
                "source_count": 2,
                "active_source_count": 1,
                "failed_source_count": 0,
                "monitored_sources": [
                    {
                        "source_id": 70,
                        "source_family": "docs",
                        "url": "https://algonomy.com/docs/commerce-search",
                        "status": "active",
                    }
                ],
            }
        ]
    )

    rows = PgMonitoredCompetitorsRepository(conn).get_monitored_competitors(tenant_id=1)

    sql = conn.cursor_obj.sql
    assert rows[0]["monitored_sources"][0]["url"] == "https://algonomy.com/docs/commerce-search"
    assert "jsonb_agg" in sql
    assert "AS monitored_sources" in sql
    assert "s.status = 'active'" in sql
