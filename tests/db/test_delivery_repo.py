"""Static repository contract tests for delivery persistence."""

from __future__ import annotations

from datetime import datetime, timezone

from cios.db.repos.delivery import PgBotDeliveryRepository
from cios.delivery.types import BotDeliveryRecord, BotDeliveryStatus, Cadence
from cios.platform.channels.types import Channel


class _FakeCursor:
    def __init__(self, row):
        self.row = row
        self.sql = ""
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def execute(self, sql, params=None):
        self.sql = sql
        self.params = params

    def fetchone(self):
        return self.row


class _FakeConnection:
    def __init__(self, row):
        self.cursor_obj = _FakeCursor(row)

    def cursor(self, row_factory=None):
        return self.cursor_obj

    def execute(self, sql, params=None):
        self.cursor_obj.execute(sql, params)

    def transaction(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None


def test_bot_delivery_repository_writes_packet_and_run_identity() -> None:
    created_at = datetime(2026, 7, 30, tzinfo=timezone.utc)
    conn = _FakeConnection(
        row={
            "id": 10,
            "tenant_id": 1,
            "cadence": "daily",
            "bot_profile": "argus",
            "channel": "telegram",
            "recipient_redacted": "*****6789",
            "status": "sent",
            "markdown_path": None,
            "html_path": None,
            "dashboard_url": "https://ci.chowmes.com/",
            "report_id": 79,
            "packet_id": "packet-actionable-day",
            "run_id": "run-actionable-day",
            "error": None,
            "created_at": created_at,
        }
    )
    repo = PgBotDeliveryRepository(conn)

    saved = repo.save(
        BotDeliveryRecord(
            tenant_id=1,
            cadence=Cadence.DAILY,
            channel=Channel.TELEGRAM,
            recipient_redacted="*****6789",
            status=BotDeliveryStatus.SENT,
            dashboard_url="https://ci.chowmes.com/",
            report_id=79,
            packet_id="packet-actionable-day",
            run_id="run-actionable-day",
            created_at=created_at,
        )
    )

    assert "packet_id" in conn.cursor_obj.sql
    assert "run_id" in conn.cursor_obj.sql
    assert conn.cursor_obj.params["packet_id"] == "packet-actionable-day"
    assert conn.cursor_obj.params["run_id"] == "run-actionable-day"
    assert saved.packet_id == "packet-actionable-day"
    assert saved.run_id == "run-actionable-day"
