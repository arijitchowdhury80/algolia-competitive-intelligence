"""Smoke contract for recording accepted Argus recommendations as learning."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from cios.learn.types import ImprovementItem, ImprovementStatus, LearningEvent, LearningEventType


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "record_recommendation_acceptance.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("record_recommendation_acceptance", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeLearningEvents:
    def insert(self, event: LearningEvent) -> LearningEvent:
        assert event.event_type == LearningEventType.USER_FEEDBACK
        assert "accepted recommendation 7" in event.lesson
        return event.model_copy(update={"id": 111})


class FakeImprovementQueue:
    def insert(self, item: ImprovementItem) -> ImprovementItem:
        assert item.status == ImprovementStatus.APPROVED
        assert item.priority.value == "high"
        assert "priority" in (item.proposed_fix or "").lower()
        return item.model_copy(update={"id": 222})


def test_record_recommendation_acceptance_script_exists_and_imports() -> None:
    module = _load_module()

    assert hasattr(module, "main")
    assert hasattr(module, "record_acceptance")
    assert hasattr(module, "resolve_tenant_id")


def test_record_acceptance_returns_approved_learning_item() -> None:
    module = _load_module()

    payload = module.record_acceptance(
        learning_events=FakeLearningEvents(),
        improvement_queue=FakeImprovementQueue(),
        tenant_id=1,
        recommendation_id=7,
        action="Turn Agent Studio into an evidence-backed market narrative.",
        rationale="Accurate, non-obvious, and directly usable by Product Marketing.",
        accepted_by="arijit",
        run_id="cios-run",
        named_team="Product Marketing",
    )

    assert payload["learning_event_id"] == 111
    assert payload["improvement_id"] == 222
    assert payload["improvement_status"] == "approved"
    assert payload["next_sweep_instruction"]
    assert payload["named_team"] == "Product Marketing"
