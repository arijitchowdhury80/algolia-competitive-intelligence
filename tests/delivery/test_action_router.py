"""Tests for ActionRouter: tenant channel preference order, evidence-gate,
material-alert interrupt classification.
"""

from __future__ import annotations

import pytest

from cios.delivery.action_router import ActionRouter
from cios.delivery.types import ActionItem, Cadence, ReportReadyEvent
from cios.platform.channels.types import Channel


class FakeChannelConfig:
    def __init__(self, preference=None, recipients=None, threads=None):
        self._preference = preference or {}
        self._recipients = recipients or {}
        self._threads = threads or {}

    def get_channel_preference(self, tenant_id):
        return self._preference.get(tenant_id, [])

    def get_recipient(self, tenant_id, channel):
        return self._recipients.get((tenant_id, channel))

    def get_thread_id(self, tenant_id, channel):
        return self._threads.get((tenant_id, channel))


class FakeOwners:
    def get_owner(self, tenant_id, priority):
        return "product-marketing" if priority == "high" else "ci-team"


def _action_item(**overrides):
    base = dict(tenant_id=1, recommendation="Update battlecard", evidence_ids=[101], priority="high")
    base.update(overrides)
    return ActionItem(**base)


def test_route_action_item_requires_evidence():
    router = ActionRouter(FakeChannelConfig())
    with pytest.raises(ValueError):
        router.route_action_item(_action_item(evidence_ids=[]))


def test_route_action_item_uses_explicit_owner_over_directory():
    router = ActionRouter(FakeChannelConfig(), owners=FakeOwners())
    plan = router.route_action_item(_action_item(owner="arijit"))
    assert plan.owner == "arijit"


def test_route_action_item_falls_back_to_owner_directory():
    router = ActionRouter(FakeChannelConfig(), owners=FakeOwners())
    plan = router.route_action_item(_action_item(owner=None, priority="high"))
    assert plan.owner == "product-marketing"


def test_default_channel_order_when_tenant_has_no_preference():
    config = FakeChannelConfig(
        recipients={
            (1, Channel.TELEGRAM): "chat123",
            (1, Channel.EMAIL): "a@example.com",
        }
    )
    router = ActionRouter(config)
    plan = router.route_action_item(_action_item())
    assert [t.channel for t in plan.targets] == [Channel.TELEGRAM, Channel.EMAIL]


def test_tenant_preference_overrides_default_order():
    config = FakeChannelConfig(
        preference={1: [Channel.EMAIL, Channel.TELEGRAM]},
        recipients={
            (1, Channel.TELEGRAM): "chat123",
            (1, Channel.EMAIL): "a@example.com",
        },
    )
    router = ActionRouter(config)
    plan = router.route_action_item(_action_item())
    assert [t.channel for t in plan.targets] == [Channel.EMAIL, Channel.TELEGRAM]


def test_channel_with_no_configured_recipient_is_skipped():
    config = FakeChannelConfig(recipients={(1, Channel.TELEGRAM): "chat123"})
    router = ActionRouter(config)
    plan = router.route_action_item(_action_item())
    assert plan.targets == [t for t in plan.targets if t.channel == Channel.TELEGRAM]
    assert len(plan.targets) == 1


def test_report_high_confidence_material_alert_classified_as_interrupt():
    config = FakeChannelConfig(recipients={(1, Channel.TELEGRAM): "chat123"})
    router = ActionRouter(config)
    report = ReportReadyEvent(
        report_id=1, tenant_id=1, cadence=Cadence.AD_HOC, is_material_alert=True, confidence=0.92
    )
    plan = router.route_report(report)
    assert plan.classification == "material_alert"


def test_report_low_confidence_alert_not_classified_as_interrupt():
    config = FakeChannelConfig(recipients={(1, Channel.TELEGRAM): "chat123"})
    router = ActionRouter(config)
    report = ReportReadyEvent(
        report_id=1, tenant_id=1, cadence=Cadence.DAILY, is_material_alert=True, confidence=0.4
    )
    plan = router.route_report(report)
    assert plan.classification == "daily"
