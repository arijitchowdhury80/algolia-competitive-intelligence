"""Packet-backed Telegram delivery contract tests."""

from __future__ import annotations

import pytest

from cios.delivery.commander import DeliveryCommander
from cios.delivery.types import BotDeliveryStatus, Cadence, DeliveryAttemptStatus
from cios.intelligence.argus_packet_scenarios import build_argus_packet_scenario
from cios.platform.channels.adapter import ChannelAdapter, NotSupported
from cios.platform.channels.types import Channel, DeliveryResult


class RecordingTelegramAdapter(ChannelAdapter):
    channel_name = "telegram"

    def __init__(self) -> None:
        self.sent = []

    async def receive(self, raw_event):  # pragma: no cover
        raise NotSupported("not used")

    async def send(self, response):
        self.sent.append(response)
        return DeliveryResult(success=True, channel=Channel.TELEGRAM, provider_message_id="tg-1")

    def verify_signature(self, raw_event):  # pragma: no cover
        raise NotSupported("not used")

    def map_identity(self, raw_event):  # pragma: no cover
        raise NotSupported("not used")

    def supports(self, capability):
        return True


class FakeRegistry:
    def __init__(self, adapter):
        self.adapter = adapter

    def get_adapter(self, channel: str):
        assert channel == "telegram"
        return self.adapter


class FakeRepo:
    def __init__(self):
        self.saved = []
        self._next_id = 1

    def save(self, record):
        saved = record.model_copy(update={"id": self._next_id})
        self._next_id += 1
        self.saved.append(saved)
        return saved


def test_daily_packet_delivery_request_uses_packet_identity_and_body() -> None:
    from cios.delivery.packet_delivery import build_packet_delivery_request

    packet = build_argus_packet_scenario("actionable_day")

    request = build_packet_delivery_request(
        packet,
        cadence=Cadence.DAILY,
        telegram_chat_id="123456789",
        dashboard_url="https://ci.chowmes.com/",
        report_id=77,
    )

    assert request.report.packet_id == packet.packet_id
    assert request.report.run_id == packet.run.run_id
    assert request.report.cadence == Cadence.DAILY
    assert request.report.markdown_body is not None
    assert packet.run.run_id in request.report.markdown_body
    assert packet.recommendations[0].action in request.report.markdown_body
    assert request.plan.targets[0].channel == Channel.TELEGRAM


def test_weekly_packet_delivery_request_uses_weekly_pattern_body() -> None:
    from cios.delivery.packet_delivery import build_packet_delivery_request

    packet = build_argus_packet_scenario("weekly_trend_day")

    request = build_packet_delivery_request(
        packet,
        cadence=Cadence.WEEKLY,
        telegram_chat_id="123456789",
        dashboard_url="https://ci.chowmes.com/",
        report_id=78,
    )

    assert request.report.cadence == Cadence.WEEKLY
    assert "Weekly window:" in request.report.markdown_body
    assert "today's competitive brief" not in request.report.markdown_body.lower()


@pytest.mark.asyncio
async def test_delivering_packet_brief_records_true_sent_status_with_packet_identity() -> None:
    from cios.delivery.packet_delivery import build_packet_delivery_request

    packet = build_argus_packet_scenario("actionable_day")
    adapter = RecordingTelegramAdapter()
    bot_deliveries = FakeRepo()
    attempts = FakeRepo()
    commander = DeliveryCommander(FakeRegistry(adapter), bot_deliveries, attempts)

    request = build_packet_delivery_request(
        packet,
        cadence=Cadence.DAILY,
        telegram_chat_id="123456789",
        dashboard_url="https://ci.chowmes.com/",
        report_id=79,
    )
    outcome = await commander.deliver(request)

    final = [record for record in bot_deliveries.saved if record.status != BotDeliveryStatus.SENDING][-1]
    assert outcome.delivered is True
    assert final.status == BotDeliveryStatus.SENT
    assert final.packet_id == packet.packet_id
    assert final.run_id == packet.run.run_id
    assert attempts.saved[-1].status == DeliveryAttemptStatus.SENT
    assert packet.executive_read.plain_read in adapter.sent[0].html_text
