"""Tests for DeliveryCommander: true-state bot_deliveries recording,
bounded retries, and channel fallback order.
"""

from __future__ import annotations

import pytest

from cios.delivery.commander import DeliveryCommander
from cios.delivery.types import (
    BotDeliveryStatus,
    Cadence,
    DeliveryAttemptStatus,
    DeliveryRequest,
    RecipientTarget,
    ReportReadyEvent,
    RoutingPlan,
)
from cios.platform.channels.adapter import ChannelAdapter, NotSupported
from cios.platform.channels.types import Channel, DeliveryResult


class FakeAdapter(ChannelAdapter):
    """Configurable fake adapter: fails N times then succeeds, or always fails."""

    def __init__(self, channel: Channel, fail_times: int = 0, always_fail: bool = False, raises: bool = False):
        self.channel_name = channel.value
        self._channel = channel
        self._fail_times = fail_times
        self._always_fail = always_fail
        self._raises = raises
        self.send_calls = 0

    async def receive(self, raw_event):  # pragma: no cover - unused in these tests
        raise NotSupported("not used")

    async def send(self, response):
        self.send_calls += 1
        if self._raises:
            raise RuntimeError("adapter blew up")
        if self._always_fail or self.send_calls <= self._fail_times:
            return DeliveryResult(success=False, channel=self._channel, error=f"simulated failure {self.send_calls}")
        return DeliveryResult(success=True, channel=self._channel, provider_message_id=f"msg-{self.send_calls}")

    def verify_signature(self, raw_event):  # pragma: no cover - unused
        raise NotSupported("not used")

    def map_identity(self, raw_event):  # pragma: no cover - unused
        raise NotSupported("not used")

    def supports(self, capability):
        return True


class FakeRegistry:
    def __init__(self, adapters: dict[str, ChannelAdapter]):
        self._adapters = adapters

    def get_adapter(self, channel: str) -> ChannelAdapter:
        return self._adapters[channel]


class FakeRepo:
    def __init__(self):
        self.saved = []
        self._next_id = 1

    def save(self, record):
        saved = record.model_copy(update={"id": self._next_id})
        self._next_id += 1
        self.saved.append(saved)
        return saved


def _request(targets, max_attempts=3, cadence=Cadence.DAILY, is_material_alert=False, confidence=None):
    report = ReportReadyEvent(
        report_id=42,
        tenant_id=1,
        cadence=cadence,
        title="Daily Brief",
        markdown_body="Coveo shipped a **feature**.",
        dashboard_url="https://dash.example.com",
        is_material_alert=is_material_alert,
        confidence=confidence,
    )
    plan = RoutingPlan(tenant_id=1, targets=targets)
    return DeliveryRequest(tenant_id=1, report=report, plan=plan, max_attempts_per_channel=max_attempts)


@pytest.mark.asyncio
async def test_successful_send_records_sent_status_not_assumed():
    telegram = FakeAdapter(Channel.TELEGRAM, fail_times=0)
    registry = FakeRegistry({"telegram": telegram})
    bot_deliveries, attempts = FakeRepo(), FakeRepo()
    commander = DeliveryCommander(registry, bot_deliveries, attempts)

    request = _request([RecipientTarget(channel=Channel.TELEGRAM, recipient_user_id="chat123")])
    outcome = await commander.deliver(request)

    assert outcome.delivered is True
    assert outcome.delivered_channel == Channel.TELEGRAM
    final = [r for r in bot_deliveries.saved if r.status != BotDeliveryStatus.SENDING][-1]
    assert final.status == BotDeliveryStatus.SENT
    assert final.error is None


@pytest.mark.asyncio
async def test_adapter_failure_records_failed_bot_delivery_not_sent():
    """Gate 6 true-state fix: an adapter failure must never be recorded as sent."""
    telegram = FakeAdapter(Channel.TELEGRAM, always_fail=True)
    registry = FakeRegistry({"telegram": telegram})
    bot_deliveries, attempts = FakeRepo(), FakeRepo()
    commander = DeliveryCommander(registry, bot_deliveries, attempts)

    request = _request([RecipientTarget(channel=Channel.TELEGRAM, recipient_user_id="chat123")], max_attempts=2)
    outcome = await commander.deliver(request)

    assert outcome.delivered is False
    final = [r for r in bot_deliveries.saved if r.status != BotDeliveryStatus.SENDING][-1]
    assert final.status == BotDeliveryStatus.FAILED
    assert "simulated failure" in final.error
    assert all(a.status == DeliveryAttemptStatus.FAILED for a in attempts.saved)


@pytest.mark.asyncio
async def test_bounded_retries_stop_at_max_attempts():
    telegram = FakeAdapter(Channel.TELEGRAM, always_fail=True)
    registry = FakeRegistry({"telegram": telegram})
    commander = DeliveryCommander(registry, FakeRepo(), FakeRepo())

    request = _request([RecipientTarget(channel=Channel.TELEGRAM, recipient_user_id="chat123")], max_attempts=3)
    await commander.deliver(request)

    assert telegram.send_calls == 3


@pytest.mark.asyncio
async def test_retry_then_success_within_budget_is_recorded_sent():
    telegram = FakeAdapter(Channel.TELEGRAM, fail_times=2)
    registry = FakeRegistry({"telegram": telegram})
    bot_deliveries, attempts = FakeRepo(), FakeRepo()
    commander = DeliveryCommander(registry, bot_deliveries, attempts)

    request = _request([RecipientTarget(channel=Channel.TELEGRAM, recipient_user_id="chat123")], max_attempts=3)
    outcome = await commander.deliver(request)

    assert outcome.delivered is True
    assert telegram.send_calls == 3
    failed_attempts = [a for a in attempts.saved if a.status == DeliveryAttemptStatus.FAILED]
    sent_attempts = [a for a in attempts.saved if a.status == DeliveryAttemptStatus.SENT]
    assert len(failed_attempts) == 2
    assert len(sent_attempts) == 1


@pytest.mark.asyncio
async def test_falls_through_to_next_channel_when_first_channel_exhausts_retries():
    telegram = FakeAdapter(Channel.TELEGRAM, always_fail=True)
    email = FakeAdapter(Channel.EMAIL, fail_times=0)
    registry = FakeRegistry({"telegram": telegram, "email": email})
    bot_deliveries, attempts = FakeRepo(), FakeRepo()
    commander = DeliveryCommander(registry, bot_deliveries, attempts)

    request = _request(
        [
            RecipientTarget(channel=Channel.TELEGRAM, recipient_user_id="chat123"),
            RecipientTarget(channel=Channel.EMAIL, recipient_user_id="a@example.com"),
        ],
        max_attempts=2,
    )
    outcome = await commander.deliver(request)

    assert outcome.delivered is True
    assert outcome.delivered_channel == Channel.EMAIL
    assert telegram.send_calls == 2
    assert email.send_calls == 1


@pytest.mark.asyncio
async def test_adapter_exception_is_captured_not_raised_and_recorded_failed():
    telegram = FakeAdapter(Channel.TELEGRAM, raises=True)
    registry = FakeRegistry({"telegram": telegram})
    bot_deliveries, attempts = FakeRepo(), FakeRepo()
    commander = DeliveryCommander(registry, bot_deliveries, attempts)

    request = _request([RecipientTarget(channel=Channel.TELEGRAM, recipient_user_id="chat123")], max_attempts=1)
    outcome = await commander.deliver(request)

    assert outcome.delivered is False
    final = [r for r in bot_deliveries.saved if r.status != BotDeliveryStatus.SENDING][-1]
    assert final.status == BotDeliveryStatus.FAILED
    assert "adapter blew up" in final.error


@pytest.mark.asyncio
async def test_unregistered_channel_records_failed_bot_delivery():
    registry = FakeRegistry({})
    bot_deliveries, attempts = FakeRepo(), FakeRepo()
    commander = DeliveryCommander(registry, bot_deliveries, attempts)

    request = _request([RecipientTarget(channel=Channel.TELEGRAM, recipient_user_id="chat123")])
    outcome = await commander.deliver(request)

    assert outcome.delivered is False
    final = bot_deliveries.saved[-1]
    assert final.status == BotDeliveryStatus.FAILED
    assert "no adapter registered" in final.error


def test_recipient_redaction_masks_all_but_last_four_chars():
    from cios.delivery.types import redact_recipient

    assert redact_recipient("1234567890") == "******7890"
    assert redact_recipient("abc") == "***"
