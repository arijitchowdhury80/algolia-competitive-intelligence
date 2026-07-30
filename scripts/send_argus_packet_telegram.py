#!/usr/bin/env python3
"""Force-send a canonical Argus intelligence packet to Telegram.

This is an operator validation tool for the Phase 4 gate. It deliberately
uses the same DeliveryCommander and Postgres repositories as the production
delivery path, so the send produces real delivery ledger rows.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json

from cios.db.repos.delivery import PgBotDeliveryRepository, PgDeliveryAttemptRepository
from cios.db.session import get_dsn, tenant_context
from cios.delivery.commander import DeliveryCommander
from cios.delivery.packet_delivery import build_packet_delivery_request
from cios.delivery.types import Cadence, DeliveryRequest
from cios.intelligence.argus_packet import ArgusIntelligencePacket
from cios.platform.channels.adapter import ChannelAdapter
from cios.platform.channels.adapters.telegram import TelegramAdapter


class SingleTelegramAdapterRegistry:
    def __init__(self, adapter: ChannelAdapter) -> None:
        self._adapter = adapter

    def get_adapter(self, channel: str) -> ChannelAdapter:
        if channel != "telegram":
            raise KeyError(f"no adapter for channel {channel}")
        return self._adapter


def load_packet(packet_path: Path) -> ArgusIntelligencePacket:
    """Load and validate a canonical Argus packet from JSON."""

    return ArgusIntelligencePacket.model_validate_json(packet_path.read_text(encoding="utf-8"))


def build_request_from_packet_file(
    *,
    packet_path: Path,
    cadence: Cadence,
    telegram_chat_id: str,
    dashboard_url: str | None = None,
    report_id: int = 0,
) -> DeliveryRequest:
    """Build a daily or forced-weekly delivery request from a packet file."""

    packet = load_packet(packet_path)
    return build_packet_delivery_request(
        packet,
        cadence=cadence,
        telegram_chat_id=telegram_chat_id,
        dashboard_url=dashboard_url,
        report_id=report_id,
    )


def build_telegram_adapter_from_env(env: dict[str, str]) -> TelegramAdapter:
    """Build a Telegram adapter from either CI-OS or adapter-native env names."""

    token = env.get("TELEGRAM_BOT_TOKEN") or env.get("ARGUS_TELEGRAM_BOT_TOKEN")
    chat_id = env.get("CIOS_TELEGRAM_CHAT_ID") or env.get("ARGUS_TELEGRAM_CHAT_ID")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN or ARGUS_TELEGRAM_BOT_TOKEN is required")
    if not chat_id:
        raise RuntimeError("CIOS_TELEGRAM_CHAT_ID or ARGUS_TELEGRAM_CHAT_ID is required")
    adapter = TelegramAdapter()
    adapter.bot_token = token
    adapter.default_chat_id = chat_id
    return adapter


def _insert_report(conn, request: DeliveryRequest) -> int:
    report = request.report
    with tenant_context(conn, request.tenant_id):
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO reports (tenant_id, cadence, report_date, title, status, summary, metadata)
                VALUES (%s, %s, %s, %s, 'rendered', %s, %s)
                RETURNING id
                """,
                (
                    request.tenant_id,
                    report.cadence.value,
                    date.today(),
                    report.title,
                    report.summary,
                    Json({"packet_id": report.packet_id, "run_id": report.run_id, "forced_validation": True}),
                ),
            )
            return cur.fetchone()["id"]


async def send_packet_file(
    *,
    packet_path: Path,
    cadence: Cadence,
    database_url: str | None = None,
    telegram_chat_id: str | None = None,
    dashboard_url: str | None = None,
    adapter: ChannelAdapter | None = None,
) -> dict[str, Any]:
    """Insert a report row, force-send the packet, and return delivery evidence."""

    chat_id = telegram_chat_id or os.environ.get("CIOS_TELEGRAM_CHAT_ID") or os.environ.get("ARGUS_TELEGRAM_CHAT_ID")
    if not chat_id:
        raise RuntimeError("telegram chat id is required")

    request = build_request_from_packet_file(
        packet_path=packet_path,
        cadence=cadence,
        telegram_chat_id=chat_id,
        dashboard_url=dashboard_url,
    )
    resolved_dsn = database_url or get_dsn()
    with psycopg.connect(resolved_dsn) as conn:
        report_id = _insert_report(conn, request)
        request = request.model_copy(update={"report": request.report.model_copy(update={"report_id": report_id})})
        commander = DeliveryCommander(
            SingleTelegramAdapterRegistry(adapter or build_telegram_adapter_from_env(os.environ)),
            PgBotDeliveryRepository(conn),
            PgDeliveryAttemptRepository(conn),
        )
        outcome = await commander.deliver(request)

    return {
        "delivered": outcome.delivered,
        "delivered_channel": outcome.delivered_channel.value if outcome.delivered_channel else None,
        "report_id": report_id,
        "packet_id": request.report.packet_id,
        "run_id": request.report.run_id,
        "cadence": request.report.cadence.value,
        "bot_deliveries": [
            {"id": row.id, "channel": row.channel.value, "status": row.status.value}
            for row in outcome.bot_deliveries
        ],
        "attempts": [
            {"id": row.id, "channel": row.channel.value, "status": row.status.value}
            for row in outcome.attempts
        ],
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Force-send an Argus packet to Telegram.")
    parser.add_argument("--packet", required=True, type=Path, help="Path to argus-intelligence-packet JSON.")
    parser.add_argument("--cadence", required=True, choices=[Cadence.DAILY.value, Cadence.WEEKLY.value])
    parser.add_argument("--database-url", default=os.environ.get("CIOS_DATABASE_URL"))
    parser.add_argument("--telegram-chat-id", default=os.environ.get("CIOS_TELEGRAM_CHAT_ID"))
    parser.add_argument("--dashboard-url", default=None)
    return parser.parse_args()


async def _amain() -> int:
    args = _parse_args()
    result = await send_packet_file(
        packet_path=args.packet,
        cadence=Cadence(args.cadence),
        database_url=args.database_url,
        telegram_chat_id=args.telegram_chat_id,
        dashboard_url=args.dashboard_url,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["delivered"] else 1


def main() -> int:
    return asyncio.run(_amain())


if __name__ == "__main__":
    raise SystemExit(main())
