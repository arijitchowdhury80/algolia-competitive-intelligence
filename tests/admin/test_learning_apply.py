"""Tests for the admin learning-apply artifact reader."""

from __future__ import annotations

from pathlib import Path

import yaml

from cios.admin.learning_apply import LearningApplyArtifactStore
from cios.learn.apply import LearningApplyExecutor
from cios.learn.feedback import LearningApplyAction, LearningApplyPlan, ProposalKind


def _action(*, tenant_id: int = 1, target: str = "source_retry_policy") -> LearningApplyAction:
    return LearningApplyAction(
        tenant_id=tenant_id,
        kind=ProposalKind.SOURCE_RETRY_TUNING,
        target=target,
        package_path="config/source-retry-policy.yaml",
        summary="Add bounded retry for HTTP 503 fetch failures.",
        instruction="Tune source retry policy for repeated 503 failures.",
        change={"source": "https://coveo.com/blog", "priority": "high"},
        evidence_event_ids=[702],
        source_improvement_ids=[402],
    )


def test_learning_apply_store_reads_proposals_and_approved_policies(tmp_path: Path) -> None:
    package_root = tmp_path / "cios"
    action = _action()
    executor = LearningApplyExecutor(package_root=package_root)
    executor.execute(LearningApplyPlan(tenant_id=1, actions=[action]))
    executor.execute(LearningApplyPlan(tenant_id=1, actions=[action]), approved_by="arijit")

    status = LearningApplyArtifactStore(package_root).status("algolia", tenant_id=1)

    assert status.tenant_slug == "algolia"
    assert status.proposal_count == 1
    assert status.approved_policy_count == 1
    assert status.proposals[0].target == "source_retry_policy"
    assert status.proposals[0].source_improvement_ids == [402]
    assert status.approved_policies[0].approved_by == "arijit"
    assert status.approved_policies[0].evidence_event_ids == [702]
    assert status.policy_audit.passed is True
    assert status.policy_audit.policy_count == 1
    assert status.policy_audit.issue_count == 0


def test_learning_apply_store_filters_wrong_tenant_and_broken_files(tmp_path: Path) -> None:
    package_root = tmp_path / "cios"
    executor = LearningApplyExecutor(package_root=package_root)
    executor.execute(LearningApplyPlan(tenant_id=2, actions=[_action(tenant_id=2, target="other_policy")]))
    proposal_dir = package_root / "docs" / "workspace" / "cios-learning-apply-plan" / "proposals"
    proposal_dir.mkdir(parents=True, exist_ok=True)
    (proposal_dir / "broken.json").write_text("{", encoding="utf-8")

    status = LearningApplyArtifactStore(package_root).status("algolia", tenant_id=1)

    assert status.proposal_count == 0
    assert status.approved_policy_count == 0
    assert status.policy_audit.passed is True
    assert status.policy_audit.policy_count == 0


def test_learning_apply_store_exposes_policy_audit_drift(tmp_path: Path) -> None:
    package_root = tmp_path / "cios"
    action = _action()
    executor = LearningApplyExecutor(package_root=package_root)
    executor.execute(LearningApplyPlan(tenant_id=1, actions=[action]), approved_by="arijit")
    policy_path = package_root / "config" / "source-retry-policy.yaml"
    payload = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    payload["policies"][0]["instruction"] = "Changed after approval without re-approval."
    policy_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    status = LearningApplyArtifactStore(package_root).status("algolia", tenant_id=1)

    assert status.policy_audit.passed is False
    assert status.policy_audit.policy_count == 1
    assert status.policy_audit.drift_count == 1
    assert status.policy_audit.issue_count == 1
    assert status.policy_audit.issues[0].code == "action_id_drift"
    assert "restore the approved policy fields" in status.policy_audit.rollback_plan[0]
