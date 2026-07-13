"""Tests for approved learning policy drift and rollback audits."""

from __future__ import annotations

import yaml

from cios.learn.apply import LearningApplyExecutor, audit_learning_policies
from cios.learn.feedback import LearningApplyAction, LearningApplyPlan, ProposalKind
from cios.learn.types import ImprovementPriority


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


def _approved_policy_root(tmp_path):
    package_root = tmp_path / "cios"
    LearningApplyExecutor(package_root=package_root).execute(
        LearningApplyPlan(tenant_id=1, actions=[_action()]),
        approved_by="arijit",
    )
    return package_root


def test_audit_learning_policies_passes_clean_approved_policy(tmp_path):
    package_root = _approved_policy_root(tmp_path)

    result = audit_learning_policies(package_root, tenant_id=1)

    assert result.passed is True
    assert result.policy_count == 1
    assert result.ok_count == 1
    assert result.issue_count == 0
    assert result.rollback_plan == []
    assert result.policies[0].status == "ok"
    assert result.policies[0].target == "source_coverage_policy"
    assert result.policies[0].package_path == "config/source-coverage-policy.yaml"


def test_audit_learning_policies_detects_policy_drift_after_approval(tmp_path):
    package_root = _approved_policy_root(tmp_path)
    policy_path = package_root / "config" / "source-coverage-policy.yaml"
    payload = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    payload["policies"][0]["summary"] = "Changed after approval without re-approval."
    policy_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    result = audit_learning_policies(package_root, tenant_id=1)

    assert result.passed is False
    assert result.policy_count == 1
    assert result.drift_count == 1
    assert result.issue_count == 1
    issue = result.issues[0]
    assert issue.code == "action_id_drift"
    assert issue.package_path == "config/source-coverage-policy.yaml"
    assert issue.action_id != issue.expected_action_id
    assert "restore the approved policy fields" in issue.rollback_hint
    assert result.rollback_plan == [issue.rollback_hint]


def test_audit_learning_policies_detects_invalid_policy_with_rollback_hint(tmp_path):
    package_root = _approved_policy_root(tmp_path)
    policy_path = package_root / "config" / "source-coverage-policy.yaml"
    payload = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    del payload["policies"][0]["evidence_event_ids"]
    policy_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    result = audit_learning_policies(package_root, tenant_id=1)

    assert result.passed is False
    assert result.invalid_count == 1
    assert result.issues[0].code == "invalid_policy"
    assert "revert this policy entry" in result.issues[0].rollback_hint
