"""Smoke contract for the Hermes-callable learning apply executor."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import yaml


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "execute_learning_apply_plan.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("execute_learning_apply_plan", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_plan(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "tenant_id": 1,
                "actions": [
                    {
                        "tenant_id": 1,
                        "kind": "source_retry_tuning",
                        "package_scope": "ci-os",
                        "target": "source_retry_policy",
                        "operation": "propose_policy_update",
                        "package_path": "config/source-retry-policy.yaml",
                        "summary": "Add bounded retry for HTTP 503 fetch failures.",
                        "instruction": "Tune source retry policy for repeated 503 failures.",
                        "change": {"source": "https://coveo.com/blog", "proposed_fix": "add backoff"},
                        "requires_human_approval": True,
                        "touches_hermes_core": False,
                        "evidence_event_ids": [702],
                        "source_improvement_ids": [402],
                    }
                ],
                "skipped": [],
            }
        ),
        encoding="utf-8",
    )


def test_execute_learning_apply_plan_script_exists_and_imports() -> None:
    module = _load_module()

    assert hasattr(module, "main")
    assert hasattr(module, "execute_learning_apply_plan_payload")


def test_execute_learning_apply_plan_payload_proposal_only(tmp_path) -> None:
    module = _load_module()
    package_root = tmp_path / "cios"
    plan_path = tmp_path / "learning-apply-plan.json"
    _write_plan(plan_path)

    result = module.execute_learning_apply_plan_payload(plan_path, package_root=package_root)

    assert result["applied_count"] == 0
    assert result["proposal_count"] == 1
    assert not (package_root / "config" / "source-retry-policy.yaml").exists()
    assert (package_root / result["proposals"][0]["proposal_path"]).exists()


def test_execute_learning_apply_plan_payload_applies_when_approved(tmp_path) -> None:
    module = _load_module()
    package_root = tmp_path / "cios"
    plan_path = tmp_path / "learning-apply-plan.json"
    _write_plan(plan_path)

    result = module.execute_learning_apply_plan_payload(
        plan_path,
        package_root=package_root,
        approved_by="arijit",
    )

    assert result["applied_count"] == 1
    policy_path = package_root / "config" / "source-retry-policy.yaml"
    policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))["policies"][0]
    assert policy["approved_by"] == "arijit"
    assert policy["target"] == "source_retry_policy"
    assert policy["source_improvement_ids"] == [402]
