"""Phase 3 export contract for canonical Argus packets."""

from __future__ import annotations

import json

from cios.intelligence.argus_packet_scenarios import build_argus_packet_scenario


def test_packet_export_bundle_preserves_run_identity_across_consumers(tmp_path) -> None:
    from cios.intelligence.argus_packet_export import write_argus_packet_bundle

    packet = build_argus_packet_scenario("actionable_day")

    result = write_argus_packet_bundle(packet, tmp_path)

    packet_json = json.loads(result.packet_path.read_text(encoding="utf-8"))
    latest_json = json.loads(result.latest_path.read_text(encoding="utf-8"))
    dashboard_json = json.loads(result.dashboard_state_path.read_text(encoding="utf-8"))
    public_status_json = json.loads(result.public_status_path.read_text(encoding="utf-8"))
    delivery_plan_json = json.loads(result.delivery_plan_path.read_text(encoding="utf-8"))

    for payload in [packet_json, latest_json, dashboard_json, public_status_json, delivery_plan_json]:
        assert payload["packet_id"] == packet.packet_id
        assert payload["run_id"] == packet.run.run_id

    assert result.run_id == packet.run.run_id
    assert result.packet_id == packet.packet_id
    assert delivery_plan_json["telegram_daily"]["status"] == packet.consumer_state.telegram_daily.status
    assert dashboard_json["intelligence_spine"]["top_insight"] == packet.executive_read.headline
