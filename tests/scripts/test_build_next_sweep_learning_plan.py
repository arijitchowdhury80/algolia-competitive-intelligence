"""Smoke contract for the Hermes-callable next-sweep learning plan command."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from cios.learn.apply import LearningApplyExecutor
from cios.learn.feedback import LearningApplyAction, LearningApplyPlan, ProposalKind
from cios.learn.types import ImprovementItem, ImprovementPriority, ImprovementStatus


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "build_next_sweep_learning_plan.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("build_next_sweep_learning_plan", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_next_sweep_learning_plan_script_exists_and_imports() -> None:
    module = _load_module()

    assert hasattr(module, "main")
    assert hasattr(module, "resolve_tenant_id")
    assert hasattr(module, "build_learning_plan_payload")


def test_build_learning_plan_payload_is_machine_readable_and_traceable() -> None:
    module = _load_module()
    item = ImprovementItem(
        id=202,
        tenant_id=1,
        source="argus_recommendation:7",
        problem="User challenged recommendation 7; coverage may be incomplete.",
        proposed_fix="Re-evaluate recommendation 7 against source coverage in the next sweep.",
        priority=ImprovementPriority.CRITICAL,
        status=ImprovementStatus.APPROVED,
    )

    payload = module.build_learning_plan_payload(
        tenant_id=1,
        items=[item],
        evidence_by_item={202: [101]},
    )

    assert payload["tenant_id"] == 1
    assert len(payload["instructions"]) == 1
    assert payload["instructions"][0]["source_improvement_ids"] == [202]
    assert payload["instructions"][0]["evidence_event_ids"] == [101]
    assert "source coverage" in payload["instructions"][0]["instruction"]
    assert payload["skipped"] == []


def test_build_next_sweep_learning_plan_resolves_tenant_slug() -> None:
    module = _load_module()

    class Conn:
        def execute(self, sql, params):
            assert "FROM tenants" in sql
            assert params == ("algolia",)
            return self

        def fetchone(self):
            return {"id": 42}

    assert module.resolve_tenant_id(Conn(), "algolia") == 42


def test_load_policy_instructions_reads_approved_package_policies(tmp_path) -> None:
    module = _load_module()
    package_root = tmp_path / "cios"
    action = LearningApplyAction(
        tenant_id=1,
        kind=ProposalKind.SOURCE_RETRY_TUNING,
        target="source_retry_policy",
        package_path="config/source-retry-policy.yaml",
        summary="Add bounded retry for HTTP 503 fetch failures.",
        instruction="Tune source retry policy for repeated 503 failures.",
        change={"source": "https://coveo.com/blog", "priority": "high"},
        evidence_event_ids=[702],
        source_improvement_ids=[402],
    )
    LearningApplyExecutor(package_root=package_root).execute(
        LearningApplyPlan(tenant_id=1, actions=[action]),
        approved_by="arijit",
    )

    instructions = module.load_policy_instructions(package_root, tenant_id=1)

    assert instructions == [
        {
            "tenant_id": 1,
            "kind": "source_retry_tuning",
            "priority": "high",
            "summary": "Add bounded retry for HTTP 503 fetch failures.",
            "instruction": "Tune source retry policy for repeated 503 failures.",
            "status": "ready_for_next_sweep",
            "change": {"source": "https://coveo.com/blog", "priority": "high"},
            "evidence_event_ids": [702],
            "source_improvement_ids": [402],
            "policy_action_id": instructions[0]["policy_action_id"],
            "policy_target": "source_retry_policy",
            "policy_package_path": "config/source-retry-policy.yaml",
            "policy_approved_by": "arijit",
            "policy_source": "ci_os_package_policy",
        }
    ]
    assert len(instructions[0]["policy_action_id"]) == 16


def test_build_learning_plan_payload_merges_policy_instructions_without_duplicates() -> None:
    module = _load_module()
    item = ImprovementItem(
        id=402,
        tenant_id=1,
        source="argus_recommendation:8",
        problem="retry policy missed repeated 503 failures",
        proposed_fix="Add bounded retry for HTTP 503 fetch failures.",
        priority=ImprovementPriority.HIGH,
        status=ImprovementStatus.APPROVED,
    )
    policy_instruction = {
        "tenant_id": 1,
        "kind": "source_retry_tuning",
        "priority": "high",
        "summary": "Add bounded retry for HTTP 503 fetch failures.",
        "instruction": "Add bounded retry for HTTP 503 fetch failures.",
        "status": "ready_for_next_sweep",
        "change": {"source": "https://coveo.com/blog", "priority": "high"},
        "evidence_event_ids": [702],
        "source_improvement_ids": [402],
    }

    payload = module.build_learning_plan_payload(
        tenant_id=1,
        items=[item],
        evidence_by_item={402: [702]},
        policy_instructions=[policy_instruction],
    )

    assert len(payload["instructions"]) == 1
    assert payload["instructions"][0]["source_improvement_ids"] == [402]
    assert payload["instructions"][0]["evidence_event_ids"] == [702]
    assert payload["metadata"]["approved_policy_count"] == 1
    assert payload["metadata"]["policy_instruction_count"] == 0
    assert payload["metadata"]["duplicate_policy_instruction_count"] == 1
    assert payload["metadata"]["policy_sources"] == [
        {
            "action_id": None,
            "target": None,
            "package_path": None,
            "approved_by": None,
            "kind": "source_retry_tuning",
            "summary": "Add bounded retry for HTTP 503 fetch failures.",
            "status": "duplicate_existing_instruction",
            "evidence_event_ids": [702],
            "source_improvement_ids": [402],
        }
    ]


def test_build_learning_plan_payload_reports_package_policy_impact() -> None:
    module = _load_module()
    policy_instruction = {
        "tenant_id": 1,
        "kind": "coverage_recheck",
        "priority": "critical",
        "summary": "Re-audit Coveo before ranking Constructor.",
        "instruction": "Run a coverage recheck for Coveo product and conversation sources.",
        "status": "ready_for_next_sweep",
        "change": {"company": "Coveo", "priority": "critical"},
        "evidence_event_ids": [701],
        "source_improvement_ids": [401],
        "policy_action_id": "abc123def4567890",
        "policy_target": "source_coverage_policy",
        "policy_package_path": "config/source-coverage-policy.yaml",
        "policy_approved_by": "arijit",
        "policy_source": "ci_os_package_policy",
    }

    payload = module.build_learning_plan_payload(
        tenant_id=1,
        items=[],
        evidence_by_item={},
        policy_instructions=[policy_instruction],
    )

    assert len(payload["instructions"]) == 1
    assert payload["metadata"] == {
        "db_instruction_count": 0,
        "approved_policy_count": 1,
        "policy_instruction_count": 1,
        "duplicate_policy_instruction_count": 0,
        "skipped_policy_instruction_count": 0,
        "policy_sources": [
            {
                "action_id": "abc123def4567890",
                "target": "source_coverage_policy",
                "package_path": "config/source-coverage-policy.yaml",
                "approved_by": "arijit",
                "kind": "coverage_recheck",
                "summary": "Re-audit Coveo before ranking Constructor.",
                "status": "loaded",
                "evidence_event_ids": [701],
                "source_improvement_ids": [401],
            }
        ],
    }
