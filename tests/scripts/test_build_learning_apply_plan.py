"""Smoke contract for the Hermes-callable learning apply plan command."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "build_learning_apply_plan.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("build_learning_apply_plan", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_learning_apply_plan_script_exists_and_imports() -> None:
    module = _load_module()

    assert hasattr(module, "main")
    assert hasattr(module, "build_apply_plan_payload")


def test_build_apply_plan_payload_from_next_sweep_plan_file(tmp_path) -> None:
    module = _load_module()
    next_sweep = tmp_path / "next-sweep-learning-plan.json"
    next_sweep.write_text(
        json.dumps(
            {
                "tenant_id": 1,
                "instructions": [
                    {
                        "tenant_id": 1,
                        "kind": "coverage_recheck",
                        "priority": "critical",
                        "summary": "Re-audit Coveo before ranking Constructor.",
                        "instruction": "Run a coverage recheck for Coveo product and conversation sources.",
                        "status": "ready_for_next_sweep",
                        "change": {"company": "Coveo"},
                        "evidence_event_ids": [701],
                        "source_improvement_ids": [401],
                    }
                ],
                "skipped": [],
            }
        ),
        encoding="utf-8",
    )

    payload = module.build_apply_plan_payload(next_sweep, tenant_id=1)

    assert payload["tenant_id"] == 1
    assert len(payload["actions"]) == 1
    action = payload["actions"][0]
    assert action["package_scope"] == "ci-os"
    assert action["target"] == "source_coverage_policy"
    assert action["package_path"] == "config/source-coverage-policy.yaml"
    assert action["requires_human_approval"] is True
    assert action["touches_hermes_core"] is False
    assert action["evidence_event_ids"] == [701]
    assert action["source_improvement_ids"] == [401]
    assert payload["skipped"] == []


def test_build_apply_plan_payload_rejects_tenant_mismatch(tmp_path) -> None:
    module = _load_module()
    next_sweep = tmp_path / "next-sweep-learning-plan.json"
    next_sweep.write_text(
        json.dumps(
            {
                "tenant_id": 2,
                "instructions": [
                    {
                        "tenant_id": 2,
                        "kind": "scoring_review",
                        "priority": "high",
                        "summary": "Raise action threshold.",
                        "instruction": "Raise the action threshold for weak scorecards.",
                        "status": "ready_for_next_sweep",
                        "evidence_event_ids": [801],
                        "source_improvement_ids": [501],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    try:
        module.build_apply_plan_payload(next_sweep, tenant_id=1)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "tenant_id" in str(exc)
