"""Smoke contract for the Hermes-callable recommendation challenge command."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from cios.learn.types import ImprovementItem, LearningEvent


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "record_recommendation_challenge.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("record_recommendation_challenge", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeLearningEvents:
    def insert(self, event: LearningEvent) -> LearningEvent:
        return event.model_copy(update={"id": 101})


class FakeImprovementQueue:
    def insert(self, item: ImprovementItem) -> ImprovementItem:
        return item.model_copy(update={"id": 202})


def test_record_recommendation_challenge_script_exists_and_imports() -> None:
    module = _load_module()

    assert hasattr(module, "main")
    assert hasattr(module, "resolve_tenant_id")
    assert hasattr(module, "record_challenge")


def test_record_challenge_returns_machine_readable_ids() -> None:
    module = _load_module()

    payload = module.record_challenge(
        learning_events=FakeLearningEvents(),
        improvement_queue=FakeImprovementQueue(),
        tenant_id=1,
        recommendation_id=7,
        challenge="Why prioritize Constructor when Coveo coverage is degraded?",
        category="coverage",
        run_id="run-2026-07-10",
        scorecard_dimension=None,
    )

    assert payload["learning_event_id"] == 101
    assert payload["improvement_id"] == 202
    assert payload["next_sweep_instruction"]
    assert payload["category"] == "coverage"
    assert payload["recommendation_id"] == 7


def test_record_recommendation_challenge_resolves_tenant_slug() -> None:
    module = _load_module()

    class Conn:
        def execute(self, sql, params):
            assert "FROM tenants" in sql
            assert params == ("algolia",)
            return self

        def fetchone(self):
            return {"id": 42}

    assert module.resolve_tenant_id(Conn(), "algolia") == 42
