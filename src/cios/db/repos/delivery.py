"""Postgres implementations of delivery/commander.py's repository Protocols."""

from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row

from cios.db.session import tenant_context
from cios.delivery.types import (
    BotDeliveryRecord,
    BotDeliveryStatus,
    Cadence,
    DeliveryAttemptRecord,
    DeliveryAttemptStatus,
)
from cios.platform.channels.types import Channel

_BOT_DELIVERY_COLUMNS = (
    "id, tenant_id, cadence, bot_profile, channel, recipient_redacted, status, "
    "markdown_path, html_path, dashboard_url, report_id, packet_id, run_id, error, created_at"
)
_DELIVERY_ATTEMPT_COLUMNS = (
    "id, tenant_id, user_id, channel, status, delivery_ref, error, created_at"
)


def _row_to_bot_delivery(row: dict[str, Any]) -> BotDeliveryRecord:
    return BotDeliveryRecord(
        id=row["id"],
        tenant_id=row["tenant_id"],
        cadence=Cadence(row["cadence"]),
        bot_profile=row["bot_profile"],
        channel=Channel(row["channel"]),
        recipient_redacted=row["recipient_redacted"],
        status=BotDeliveryStatus(row["status"]),
        markdown_path=row["markdown_path"],
        html_path=row["html_path"],
        dashboard_url=row["dashboard_url"],
        report_id=row["report_id"],
        packet_id=row["packet_id"],
        run_id=row["run_id"],
        error=row["error"],
        created_at=row["created_at"],
    )


def _row_to_delivery_attempt(row: dict[str, Any]) -> DeliveryAttemptRecord:
    return DeliveryAttemptRecord(
        id=row["id"],
        tenant_id=row["tenant_id"],
        user_id=row["user_id"],
        channel=Channel(row["channel"]),
        status=DeliveryAttemptStatus(row["status"]),
        delivery_ref=row["delivery_ref"],
        error=row["error"],
        created_at=row["created_at"],
    )


class PgBotDeliveryRepository:
    """Implements delivery.commander.BotDeliveryRepository against `bot_deliveries`.

    `report_id` in schema.sql has an FK to `reports(id)` -- a row cannot be
    saved unless that report already exists. Callers integrating this repo
    into a real pipeline must persist the `reports` row first.
    """

    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def save(self, record: BotDeliveryRecord) -> BotDeliveryRecord:
        with tenant_context(self._conn, record.tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                if record.id is None:
                    cur.execute(
                        f"""
                        INSERT INTO bot_deliveries (
                            tenant_id, cadence, bot_profile, channel, recipient_redacted,
                            status, markdown_path, html_path, dashboard_url, report_id, packet_id, run_id,
                            error, created_at
                        ) VALUES (%(tenant_id)s, %(cadence)s, %(bot_profile)s, %(channel)s, %(recipient_redacted)s,
                                  %(status)s, %(markdown_path)s, %(html_path)s, %(dashboard_url)s, %(report_id)s,
                                  %(packet_id)s, %(run_id)s, %(error)s, %(created_at)s)
                        RETURNING {_BOT_DELIVERY_COLUMNS}
                        """,
                        _bot_delivery_params(record),
                    )
                else:
                    cur.execute(
                        f"""
                        UPDATE bot_deliveries SET
                            status = %(status)s,
                            error = %(error)s,
                            markdown_path = %(markdown_path)s,
                            html_path = %(html_path)s,
                            dashboard_url = %(dashboard_url)s,
                            packet_id = %(packet_id)s,
                            run_id = %(run_id)s
                        WHERE id = %(id)s AND tenant_id = %(tenant_id)s
                        RETURNING {_BOT_DELIVERY_COLUMNS}
                        """,
                        {**_bot_delivery_params(record), "id": record.id},
                    )
                row = cur.fetchone()
        assert row is not None
        return _row_to_bot_delivery(row)


def _bot_delivery_params(record: BotDeliveryRecord) -> dict[str, Any]:
    return {
        "tenant_id": record.tenant_id,
        "cadence": record.cadence.value,
        "bot_profile": record.bot_profile,
        "channel": record.channel.value,
        "recipient_redacted": record.recipient_redacted,
        "status": record.status.value,
        "markdown_path": record.markdown_path,
        "html_path": record.html_path,
        "dashboard_url": record.dashboard_url,
        "report_id": record.report_id,
        "packet_id": record.packet_id,
        "run_id": record.run_id,
        "error": record.error,
        "created_at": record.created_at,
    }


class PgDeliveryAttemptRepository:
    """Implements delivery.commander.DeliveryAttemptRepository against `delivery_attempts`."""

    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def save(self, record: DeliveryAttemptRecord) -> DeliveryAttemptRecord:
        with tenant_context(self._conn, record.tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    f"""
                    INSERT INTO delivery_attempts (
                        tenant_id, user_id, channel, status, delivery_ref, error, created_at
                    ) VALUES (%(tenant_id)s, %(user_id)s, %(channel)s, %(status)s, %(delivery_ref)s,
                              %(error)s, %(created_at)s)
                    RETURNING {_DELIVERY_ATTEMPT_COLUMNS}
                    """,
                    {
                        "tenant_id": record.tenant_id,
                        "user_id": record.user_id,
                        "channel": record.channel.value,
                        "status": record.status.value,
                        "delivery_ref": record.delivery_ref,
                        "error": record.error,
                        "created_at": record.created_at,
                    },
                )
                row = cur.fetchone()
        assert row is not None
        return _row_to_delivery_attempt(row)
