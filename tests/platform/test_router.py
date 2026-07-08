from __future__ import annotations

import yaml
import pytest

from cios.platform.models.router import ModelRouter

BASE_CONFIG = {
    "tiers": {
        "default": {"provider": "google", "model_id": "gemini-flash-lite"},
        "standard": {"provider": "google", "model_id": "gemini-flash"},
        "high": {"provider": "anthropic-cli", "model_id": "sonnet"},
        "judgment": {"provider": "anthropic-cli", "model_id": "opus"},
    },
    "tenant_overrides": {
        "acme": {
            "high": {"provider": "google", "model_id": "gemini-pro-high"},
        }
    },
    "escalation_rules": {
        "needs_long_context": "standard",
        "needs_json_mode": "standard",
        "needs_vision": "high",
        "needs_tool_use": "high",
    },
}


@pytest.fixture
def router(tmp_path):
    config_path = tmp_path / "model-routing.yaml"
    config_path.write_text(yaml.safe_dump(BASE_CONFIG))
    return ModelRouter(config_path=config_path)


def test_select_model_defaults_to_lowest_tier(router):
    selection = router.select_model(task_profile="daily_brief", capability_needs=[])
    assert selection.tier == "default"
    assert selection.provider == "google"
    assert selection.model_id == "gemini-flash-lite"
    assert selection.escalated is False
    assert selection.escalation_reason is None


def test_select_model_escalates_only_when_needed(router):
    selection = router.select_model(
        task_profile="synth", capability_needs=["needs_long_context"]
    )
    assert selection.tier == "standard"
    assert selection.escalated is True
    assert selection.escalation_reason is not None
    assert "needs_long_context" in selection.escalation_reason


def test_select_model_picks_highest_required_tier_across_needs(router):
    selection = router.select_model(
        task_profile="vision_task",
        capability_needs=["needs_json_mode", "needs_vision"],
    )
    assert selection.tier == "high"
    assert selection.provider == "anthropic-cli"
    assert selection.model_id == "sonnet"
    assert selection.escalated is True


def test_tenant_override_changes_provider_and_model(router):
    default_selection = router.select_model(
        task_profile="vision_task", capability_needs=["needs_vision"]
    )
    assert default_selection.provider == "anthropic-cli"
    assert default_selection.model_id == "sonnet"

    tenant_selection = router.select_model(
        task_profile="vision_task",
        capability_needs=["needs_vision"],
        tenant_id="acme",
    )
    assert tenant_selection.provider == "google"
    assert tenant_selection.model_id == "gemini-pro-high"
    assert tenant_selection.tier == "high"


def test_record_run_returns_expected_fields(router):
    selection = router.select_model(task_profile="daily_brief", capability_needs=[])
    record = router.record_run(
        selection=selection,
        task_profile="daily_brief",
        tenant_id="acme",
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        latency_ms=123.4,
        cost_cents=0.5,
        success=True,
    )
    assert record.run_id
    assert record.tenant_id == "acme"
    assert record.task_profile == "daily_brief"
    assert record.tier == "default"
    assert record.provider == "google"
    assert record.model_id == "gemini-flash-lite"
    assert record.total_tokens == 15
    assert record.success is True
    assert record.escalated is False
    assert record.started_at is not None
    assert record.finished_at is not None
