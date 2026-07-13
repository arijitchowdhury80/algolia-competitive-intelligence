"""Tests for safely turning Argus learning apply plans into package work."""

from __future__ import annotations

import json

import yaml

from cios.learn.apply import LearningApplyExecutor
from cios.learn.feedback import LearningApplyAction, LearningApplyPlan, ProposalKind
from cios.learn.types import ImprovementPriority


def _plan(*actions: LearningApplyAction) -> LearningApplyPlan:
    return LearningApplyPlan(tenant_id=1, actions=list(actions), skipped=[])


def _action(**overrides) -> LearningApplyAction:
    defaults = dict(
        tenant_id=1,
        kind=ProposalKind.COVERAGE_RECHECK,
        target="source_coverage_policy",
        package_path="config/source-coverage-policy.yaml",
        summary="Re-audit Coveo before ranking Constructor.",
        instruction="Run a coverage recheck for Coveo product and conversation sources.",
        change={"company": "Coveo", "priority": ImprovementPriority.CRITICAL.value},
        evidence_event_ids=[701],
        source_improvement_ids=[401],
    )
    defaults.update(overrides)
    return LearningApplyAction(**defaults)


def test_executor_without_approval_writes_review_proposals_without_mutating_config(tmp_path):
    package_root = tmp_path / "cios"
    executor = LearningApplyExecutor(package_root=package_root)

    result = executor.execute(_plan(_action()))

    assert result.applied_count == 0
    assert result.proposal_count == 1
    assert result.skipped == []
    assert not (package_root / "config" / "source-coverage-policy.yaml").exists()
    proposal_path = package_root / result.proposals[0].proposal_path
    assert proposal_path.exists()
    payload = json.loads(proposal_path.read_text(encoding="utf-8"))
    assert payload["status"] == "pending_human_approval"
    assert payload["action"]["package_scope"] == "ci-os"
    assert payload["action"]["touches_hermes_core"] is False
    assert payload["action"]["evidence_event_ids"] == [701]
    assert payload["action"]["source_improvement_ids"] == [401]


def test_executor_with_approval_writes_idempotent_config_policy(tmp_path):
    package_root = tmp_path / "cios"
    executor = LearningApplyExecutor(package_root=package_root)
    plan = _plan(_action())

    first = executor.execute(plan, approved_by="arijit")
    second = executor.execute(plan, approved_by="arijit")

    assert first.applied_count == 1
    assert second.applied_count == 1
    policy_path = package_root / "config" / "source-coverage-policy.yaml"
    data = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert len(data["policies"]) == 1
    policy = data["policies"][0]
    assert policy["status"] == "approved"
    assert policy["approved_by"] == "arijit"
    assert policy["target"] == "source_coverage_policy"
    assert policy["evidence_event_ids"] == [701]
    assert policy["source_improvement_ids"] == [401]
    assert policy["change"] == {"company": "Coveo", "priority": "critical"}


def test_executor_does_not_mutate_manual_review_targets_even_when_approved(tmp_path):
    package_root = tmp_path / "cios"
    executor = LearningApplyExecutor(package_root=package_root)
    action = _action(
        kind=ProposalKind.OTHER,
        target="manual_learning_review",
        package_path="docs/workspace/argus-learning-apply-review.md",
        summary="Needs a human read.",
        instruction="Review this learning manually.",
    )

    result = executor.execute(_plan(action), approved_by="arijit")

    assert result.applied_count == 0
    assert result.proposal_count == 1
    assert result.skipped == [
        {
            "source_improvement_ids": [401],
            "reason": "manual review targets are proposal-only",
        }
    ]
    assert not (package_root / "docs" / "workspace" / "argus-learning-apply-review.md").exists()
