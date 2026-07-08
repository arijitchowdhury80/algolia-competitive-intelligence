"""Smoke tests for scripts/daily_production_run.py. No network, no live DB."""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from cios.brain.brief import compose_daily_brief
from cios.brain.types import Signal
from cios.prescribe.types import Effort, Grounding, Prescription, Team, UrgencyWindow

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


def test_llm_budget_raised_to_35(daily_run):
    assert daily_run.LLM_BUDGET == 35


def _prescription(
    title: str = "Counter-position the price cut",
    urgency: UrgencyWindow = UrgencyWindow.ACT_NOW,
    team: Team = Team.MARKETING,
) -> Prescription:
    return Prescription(
        tenant_id=1,
        title=title,
        play=["Brief the field by EOD", "Publish a comparison one-pager"],
        team=team,
        urgency_window=urgency,
        grounding=Grounding(
            signal_evidence_urls=["https://rival.com/pricing"],
            evidence_urls=["https://rival.com/pricing"],
        ),
        expected_effect="Neutralizes the price objection before it spreads.",
        effort=Effort.M,
        materiality_score=0.8,
    )


class _StubPrescriptionEngine:
    """No-live-LLM stand-in for cios.prescribe.engine.PrescriptionEngine,
    matching its async .prescribe(...) signature."""

    def __init__(self, prescriptions: list[Prescription]) -> None:
        self._prescriptions = prescriptions

    async def prescribe(self, tenant_id, signals, connections=None, theses=None, brand_position=None):
        return self._prescriptions


# -- "YOUR PLAYS" brief section (via a fake/stub PrescriptionEngine) --------


@pytest.mark.asyncio
async def test_stub_prescription_engine_feeds_your_plays_section():
    stub = _StubPrescriptionEngine([_prescription()])
    prescriptions = await stub.prescribe(tenant_id=1, signals=[])
    from datetime import date as _date

    md = compose_daily_brief([], "Acme Corp", _date(2026, 7, 8), prescriptions=prescriptions)
    assert "## YOUR PLAYS" in md
    assert "Counter-position the price cut" in md
    assert "Brief the field by EOD" in md


# -- brief.py prescription rendering (unit test the render function) -------


def test_format_your_plays_renders_title_steps_team_urgency(daily_run):
    from cios.brain.brief import _format_your_plays

    lines = _format_your_plays([_prescription()])
    text = "\n".join(lines)
    assert "## YOUR PLAYS" in text
    assert "Counter-position the price cut" in text
    assert "Marketing" in text
    assert "act now" in text
    assert "Brief the field by EOD" in text
    assert "Expected effect: Neutralizes the price objection before it spreads." in text


def test_format_your_plays_sorts_act_now_first(daily_run):
    from cios.brain.brief import _format_your_plays

    later = _prescription(title="This-month play", urgency=UrgencyWindow.THIS_MONTH)
    now_play = _prescription(title="Act-now play", urgency=UrgencyWindow.ACT_NOW)
    text = "\n".join(_format_your_plays([later, now_play]))
    assert text.index("Act-now play") < text.index("This-month play")


def test_format_your_plays_empty_when_no_prescriptions(daily_run):
    from cios.brain.brief import _format_your_plays

    assert _format_your_plays([]) == []
    assert _format_your_plays(None) == []


# -- action_items mapping from a Prescription -------------------------------


def test_prescription_to_action_item_maps_evidence_and_team(daily_run):
    p = _prescription()
    row = daily_run.prescription_to_action_item(p, report_id=99)
    assert row["tenant_id"] == 1
    assert row["owner"] == "Marketing"
    assert "Counter-position the price cut" in row["recommendation"]
    assert "Brief the field by EOD" in row["recommendation"]
    assert row["evidence_ids"] == ["https://rival.com/pricing"]
    assert row["priority"] == "act_now"
    assert row["due_window"] == "act_now"
    assert row["report_id"] == 99
    # action_items schema CHECK: evidence_ids must be non-empty.
    assert len(row["evidence_ids"]) > 0


def test_prescription_to_action_item_no_report_id_is_none(daily_run):
    row = daily_run.prescription_to_action_item(_prescription())
    assert row["report_id"] is None
