"""Tests for GatedDeliveryCommander: a failed quality verdict must never
ship (Gate 7 rehearsal blocker fix, manifesto Phase 6).
"""

from __future__ import annotations

import pytest

from cios.delivery.gated_commander import GatedDeliveryCommander
from cios.delivery.types import (
    BotDeliveryStatus,
    Cadence,
    DeliveryRequest,
    RecipientTarget,
    ReportReadyEvent,
    RoutingPlan,
)
from cios.learn.types import QualityReview, QualityReviewStatus
from cios.platform.channels.adapter import ChannelAdapter, NotSupported
from cios.platform.channels.types import Channel, DeliveryResult


class FakeAdapter(ChannelAdapter):
    def __init__(self, channel: Channel) -> None:
        self.channel_name = channel.value
        self._channel = channel
        self.send_calls = 0

    async def receive(self, raw_event):  # pragma: no cover - unused
        raise NotSupported("not used")

    async def send(self, response):
        self.send_calls += 1
        return DeliveryResult(success=True, channel=self._channel, provider_message_id="msg-1")

    def verify_signature(self, raw_event):  # pragma: no cover - unused
        raise NotSupported("not used")

    def map_identity(self, raw_event):  # pragma: no cover - unused
        raise NotSupported("not used")

    def supports(self, capability):
        return True


class FakeRegistry:
    def __init__(self, adapters):
        self._adapters = adapters

    def get_adapter(self, channel: str):
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


class FakeRecorder:
    def __init__(self):
        self.calls = []

    def record_quality_verdict(self, tenant_id, review):
        self.calls.append((tenant_id, review))
        return None


def _request(targets):
    report = ReportReadyEvent(
        report_id=42,
        tenant_id=1,
        cadence=Cadence.DAILY,
        title="Daily Brief",
        markdown_body="Coveo shipped a **feature**.",
        dashboard_url="https://dash.example.com",
    )
    plan = RoutingPlan(tenant_id=1, targets=targets)
    return DeliveryRequest(tenant_id=1, report=report, plan=plan)


@pytest.mark.asyncio
async def test_failed_verdict_blocks_delivery_with_zero_sends_and_learning_event():
    telegram = FakeAdapter(Channel.TELEGRAM)
    registry = FakeRegistry({"telegram": telegram})
    bot_deliveries, attempts, recorder = FakeRepo(), FakeRepo(), FakeRecorder()
    commander = GatedDeliveryCommander(registry, bot_deliveries, attempts, recorder)

    verdict = QualityReview(
        tenant_id=1,
        run_id="run-1",
        review_type="pre-delivery",
        status=QualityReviewStatus.FAILED,
        required_fixes=[{"fix": "claim missing a live-format source URL"}],
    )
    request = _request([RecipientTarget(channel=Channel.TELEGRAM, recipient_user_id="chat123")])

    outcome = await commander.deliver(request, verdict)

    assert outcome.delivered is False
    assert telegram.send_calls == 0
    assert len(attempts.saved) == 0
    assert len(bot_deliveries.saved) == 1
    blocked = bot_deliveries.saved[0]
    assert blocked.status == BotDeliveryStatus.BLOCKED
    assert "claim missing a live-format source URL" in blocked.error

    assert len(recorder.calls) == 1
    recorded_tenant, recorded_review = recorder.calls[0]
    assert recorded_tenant == 1
    assert recorded_review is verdict


@pytest.mark.asyncio
async def test_pending_verdict_also_blocks_delivery():
    telegram = FakeAdapter(Channel.TELEGRAM)
    registry = FakeRegistry({"telegram": telegram})
    bot_deliveries, attempts, recorder = FakeRepo(), FakeRepo(), FakeRecorder()
    commander = GatedDeliveryCommander(registry, bot_deliveries, attempts, recorder)

    verdict = QualityReview(tenant_id=1, run_id="run-1", status=QualityReviewStatus.PENDING)
    request = _request([RecipientTarget(channel=Channel.TELEGRAM, recipient_user_id="chat123")])

    outcome = await commander.deliver(request, verdict)

    assert outcome.delivered is False
    assert telegram.send_calls == 0
    assert bot_deliveries.saved[0].status == BotDeliveryStatus.BLOCKED
    assert len(recorder.calls) == 1


@pytest.mark.asyncio
async def test_passed_verdict_delivers_as_before():
    telegram = FakeAdapter(Channel.TELEGRAM)
    registry = FakeRegistry({"telegram": telegram})
    bot_deliveries, attempts, recorder = FakeRepo(), FakeRepo(), FakeRecorder()
    commander = GatedDeliveryCommander(registry, bot_deliveries, attempts, recorder)

    verdict = QualityReview(tenant_id=1, run_id="run-1", status=QualityReviewStatus.PASSED)
    request = _request([RecipientTarget(channel=Channel.TELEGRAM, recipient_user_id="chat123")])

    outcome = await commander.deliver(request, verdict)

    assert outcome.delivered is True
    assert telegram.send_calls == 1
    assert recorder.calls == []
    final = [r for r in bot_deliveries.saved if r.status != BotDeliveryStatus.SENDING][-1]
    assert final.status == BotDeliveryStatus.SENT


def test_deliver_requires_quality_verdict_argument():
    """Absence of a verdict cannot silently deliver: the type enforces it by
    making quality_verdict a required positional argument with no default,
    so a call built without one raises TypeError before anything runs."""
    telegram = FakeAdapter(Channel.TELEGRAM)
    registry = FakeRegistry({"telegram": telegram})
    commander = GatedDeliveryCommander(registry, FakeRepo(), FakeRepo(), FakeRecorder())
    request = _request([RecipientTarget(channel=Channel.TELEGRAM, recipient_user_id="chat123")])

    with pytest.raises(TypeError):
        commander.deliver(request)  # missing required quality_verdict
