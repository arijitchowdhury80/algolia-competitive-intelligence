"""Smoke tests for scripts/daily_production_run.py. No network, no live DB."""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "daily_production_run.py"
CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "tenants-sources.yaml"


def _load_module():
    spec = importlib.util.spec_from_file_location("daily_production_run", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def daily_run():
    return _load_module()


def test_config_loads_expected_shape():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    # own_brand is a separate section (src/cios/ownbrand) keyed by tenant,
    # not one of daily_production_run's competitor source lists.
    tenant_plans = {k: v for k, v in data.items() if k != "own_brand"}

    assert set(tenant_plans.keys()) == {"algolia", "spryker", "amplitude"}
    for slug, sources in tenant_plans.items():
        assert len(sources) <= 6
        for source in sources:
            assert set(source.keys()) == {"name", "domain", "url", "family"}

    assert set(data["own_brand"].keys()) == {"algolia", "spryker", "amplitude"}


def test_build_daily_message_starts_with_marker(daily_run):
    message = daily_run.build_daily_message("some brief body")
    assert message.startswith("ARGUS — Daily Competitive Brief")
    assert "some brief body" in message


def test_is_weekly_due_true_on_sunday(daily_run):
    # 2026-07-12 is a Sunday.
    sunday = datetime(2026, 7, 12, 9, 0, tzinfo=timezone.utc)
    assert daily_run.is_weekly_due(sunday) is True


def test_is_weekly_due_false_on_non_sunday(daily_run):
    # 2026-07-13 is a Monday.
    monday = datetime(2026, 7, 13, 9, 0, tzinfo=timezone.utc)
    assert daily_run.is_weekly_due(monday) is False


def test_is_monthly_due_true_on_first_monday(daily_run):
    # 2026-08-03 is the first Monday of August 2026.
    first_monday = datetime(2026, 8, 3, 9, 0, tzinfo=timezone.utc)
    assert daily_run.is_monthly_due(first_monday) is True


def test_is_monthly_due_false_on_other_monday(daily_run):
    # 2026-08-10 is a Monday but not the first Monday of the month.
    other_monday = datetime(2026, 8, 10, 9, 0, tzinfo=timezone.utc)
    assert daily_run.is_monthly_due(other_monday) is False


def test_select_adapter_for_tenant_capturing_for_non_delivered(daily_run):
    telegram_env = {"TELEGRAM_BOT_TOKEN": "tok", "CIOS_TELEGRAM_CHAT_ID": "chat"}
    adapter = daily_run.select_adapter_for_tenant("spryker", "algolia", telegram_env)
    assert isinstance(adapter, daily_run.CapturingTelegramAdapter)


def test_select_adapter_for_tenant_real_for_delivered(daily_run):
    telegram_env = {"TELEGRAM_BOT_TOKEN": "tok-123", "CIOS_TELEGRAM_CHAT_ID": "chat-456"}
    adapter = daily_run.select_adapter_for_tenant("algolia", "algolia", telegram_env)
    assert isinstance(adapter, daily_run.TelegramAdapter)
    assert not isinstance(adapter, daily_run.CapturingTelegramAdapter)
    assert adapter.bot_token == "tok-123"
    assert adapter.default_chat_id == "chat-456"
