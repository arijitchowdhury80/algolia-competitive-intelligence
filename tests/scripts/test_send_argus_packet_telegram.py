"""Tests for forced Argus packet Telegram delivery script."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from cios.delivery.types import Cadence
from cios.intelligence.argus_packet_scenarios import build_argus_packet_scenario

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "send_argus_packet_telegram.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("send_argus_packet_telegram", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_load_packet_from_json_preserves_packet_identity(tmp_path) -> None:
    script = _load_module()
    packet = build_argus_packet_scenario("actionable_day")
    packet_path = tmp_path / "packet.json"
    packet_path.write_text(packet.model_dump_json(), encoding="utf-8")

    loaded = script.load_packet(packet_path)

    assert loaded.packet_id == packet.packet_id
    assert loaded.run.run_id == packet.run.run_id


def test_build_forced_weekly_request_does_not_require_calendar_sunday(tmp_path) -> None:
    script = _load_module()
    packet = build_argus_packet_scenario("weekly_trend_day")
    packet_path = tmp_path / "packet.json"
    packet_path.write_text(json.dumps(packet.model_dump(mode="json")), encoding="utf-8")

    request = script.build_request_from_packet_file(
        packet_path=packet_path,
        cadence=Cadence.WEEKLY,
        telegram_chat_id="123456789",
        dashboard_url="https://ci.chowmes.com/",
        report_id=88,
    )

    assert request.report.packet_id == packet.packet_id
    assert request.report.run_id == packet.run.run_id
    assert request.report.cadence == Cadence.WEEKLY
    assert "Weekly window:" in request.report.markdown_body
