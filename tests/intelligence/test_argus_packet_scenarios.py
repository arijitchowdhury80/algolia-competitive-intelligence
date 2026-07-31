"""Phase 2 scenario harness tests for the Argus Intelligence Packet.

These fixtures make the intelligence spine testable before more UI, runtime,
or Telegram work resumes. Consumers must be able to render these packets without
inventing recommendations, blockers, confidence, or weekly patterns.
"""

from __future__ import annotations

from importlib import import_module

import pytest


def _scenario_module():
    try:
        return import_module("cios.intelligence.argus_packet_scenarios")
    except ModuleNotFoundError as exc:
        pytest.fail(f"Missing Phase 2 scenario harness module: {exc}")


def _packet(name: str):
    scenarios = _scenario_module()
    return scenarios.build_argus_packet_scenario(name)


def test_phase2_declares_all_required_intelligence_scenarios() -> None:
    scenarios = _scenario_module()

    assert scenarios.list_argus_packet_scenarios() == [
        "actionable_day",
        "quiet_verified_day",
        "degraded_day",
        "contradiction_day",
        "stale_evidence_day",
        "missing_demand_day",
        "weekly_trend_day",
        "noisy_duplicate_day",
    ]


def test_actionable_day_promotes_only_evidence_backed_action() -> None:
    packet = _packet("actionable_day")

    assert packet.status == "actionable"
    assert packet.recommendations
    recommendation = packet.recommendations[0]
    assert recommendation.owner == "PMM"
    assert recommendation.movement_ref_ids == [packet.market_movements[0].movement_id]
    assert set(recommendation.proof_ref_ids) <= {node.node_id for node in packet.proof_graph.nodes}
    assert "audience_demand" in {plane.plane for plane in packet.evidence_planes if plane.status == "present"}
    assert packet.attention_state.now == [packet.market_movements[0].movement_id]


def test_quiet_day_is_verified_quiet_not_missing_collection() -> None:
    packet = _packet("quiet_verified_day")

    assert packet.status == "quiet_verified"
    assert packet.recommendations == []
    assert packet.blocked_actions == []
    assert packet.source_health.checked == packet.source_health.active
    assert packet.source_health.failed == 0
    assert packet.executive_read.decision_posture == "quiet"
    assert packet.attention_state.quiet
    assert "missing" not in {plane.status for plane in packet.evidence_planes}


def test_degraded_day_surfaces_failures_without_faking_actionability() -> None:
    packet = _packet("degraded_day")

    assert packet.status == "degraded"
    assert packet.recommendations == []
    assert packet.source_health.failed > 0
    assert packet.quality.known_failures
    assert packet.next_monitoring_actions
    assert packet.executive_read.decision_posture in {"investigate", "wait_for_proof"}


def test_contradiction_day_blocks_action_and_preserves_conflict() -> None:
    packet = _packet("contradiction_day")

    assert packet.status == "watch"
    assert packet.contradictions
    assert packet.blocked_actions
    assert packet.recommendations == []
    assert packet.market_movements[0].contradiction_ref_ids == [packet.contradictions[0].contradiction_id]
    assert packet.executive_read.decision_posture == "wait_for_proof"


def test_stale_evidence_day_cannot_publish_as_current() -> None:
    packet = _packet("stale_evidence_day")

    assert packet.status == "stale"
    assert packet.quality.freshness_status == "stale"
    assert packet.source_health.stale > 0
    assert packet.recommendations == []
    assert packet.consumer_state.public_status is not None
    assert packet.consumer_state.public_status.status == "stale"


def test_missing_demand_day_blocks_recommendation_until_audience_demand_exists() -> None:
    packet = _packet("missing_demand_day")

    assert packet.status == "watch"
    assert packet.recommendations == []
    demand_plane = next(plane for plane in packet.evidence_planes if plane.plane == "audience_demand")
    assert demand_plane.status == "missing"
    assert packet.blocked_actions
    assert "Audience Demand" in packet.blocked_actions[0].blocked_reason
    assert packet.next_monitoring_actions[0].evidence_needed == ["fresh Audience Demand export"]


def test_weekly_trend_day_forms_pattern_over_time() -> None:
    packet = _packet("weekly_trend_day")

    assert packet.cadence == "weekly"
    assert packet.time_window.grain == "weekly"
    assert packet.time_window.comparison_start_at is not None
    assert packet.market_movements[0].direction in {"rising", "steady"}
    assert packet.market_movements[0].velocity in {"medium", "high"}
    assert "across the week" in packet.executive_read.plain_read
    assert "today" not in packet.executive_read.headline.lower()


def test_noisy_duplicate_day_suppresses_duplicate_noise() -> None:
    packet = _packet("noisy_duplicate_day")

    assert packet.status == "watch"
    assert packet.recommendations == []
    conversation_plane = next(plane for plane in packet.evidence_planes if plane.plane == "market_conversation")
    assert conversation_plane.coverage["raw_signal_count"] > conversation_plane.signal_count
    assert conversation_plane.coverage["duplicates_suppressed"] > 0
    assert packet.executive_read.decision_posture == "watch"


def test_scenarios_do_not_depend_on_consumer_side_story_synthesis() -> None:
    for scenario_name in _scenario_module().list_argus_packet_scenarios():
        packet = _packet(scenario_name)

        assert packet.executive_read.plain_read
        assert packet.evidence_planes
        assert packet.proof_graph.nodes or packet.status == "quiet_verified"
        assert packet.lineage.upstream_objects == ["phase2_fixture"]
        for _, consumer in packet.consumer_state.items():
            assert consumer.run_id == packet.run.run_id
            assert consumer.packet_id == packet.packet_id


def test_existing_consumers_can_render_every_scenario_without_story_drift() -> None:
    dashboard = import_module("cios.dashboard.packet_consumers")
    telegram = import_module("cios.delivery.packet_telegram_format")

    for scenario_name in _scenario_module().list_argus_packet_scenarios():
        packet = _packet(scenario_name)

        state = dashboard.build_dashboard_state_from_packet(packet)
        latest = dashboard.build_latest_json_from_packet(packet)
        daily_text = telegram.render_daily_packet_brief_html(packet)
        weekly_text = telegram.render_weekly_packet_brief_html(packet)

        assert state.run_health.run_id == packet.run.run_id
        assert state.intelligence_spine.verdict == packet.status
        assert state.intelligence_spine.top_insight == packet.executive_read.headline
        assert latest["packet_id"] == packet.packet_id
        assert latest["run_id"] == packet.run.run_id
        assert latest["status"] == packet.status
        if packet.status in {"watch", "degraded", "stale"} and not packet.recommendations:
            assert "Argus read:" in daily_text
        else:
            assert packet.executive_read.plain_read in daily_text
        if packet.cadence == "weekly" and packet.time_window.grain == "weekly":
            assert packet.executive_read.plain_read in weekly_text
        else:
            assert "Weekly synthesis unavailable" in weekly_text
