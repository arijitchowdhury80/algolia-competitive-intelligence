"""Admin read model for CI-OS learning apply artifacts."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml

from cios.admin.types import (
    LearningApplyPolicyAdminRecord,
    LearningApplyProposalAdminRecord,
    LearningApplyStatus,
    LearningPolicyAuditStatus,
)
from cios.learn.apply import LearningApplyExecutionResult, LearningApplyExecutor, audit_learning_policies
from cios.learn.feedback import LearningApplyPlan


class LearningApplyArtifactStore:
    """Reads package-local learning apply proposals and approved policies.

    The executor writes these artifacts inside the CI-OS package. The admin app
    only reads them so operators can see what Argus is proposing and what has
    already been approved into future sweep policy.
    """

    def __init__(self, package_root: Path | None = None) -> None:
        self.package_root = package_root or _default_package_root()

    def status(self, tenant_slug: str, *, tenant_id: int) -> LearningApplyStatus:
        proposals = self._proposals(tenant_id)
        policies = self._approved_policies(tenant_id)
        return LearningApplyStatus(
            tenant_slug=tenant_slug,
            tenant_id=tenant_id,
            proposal_dir=str(self._proposal_dir()),
            config_dir=str(self.package_root / "config"),
            proposal_count=len(proposals),
            approved_policy_count=len(policies),
            proposals=proposals,
            approved_policies=policies,
            policy_audit=self._policy_audit(tenant_id),
        )

    def execute_plan(
        self,
        tenant_slug: str,
        *,
        tenant_id: int,
        plan_path: Path,
        approved_by: str | None = None,
    ) -> LearningApplyExecutionResult:
        plan_path = Path(plan_path)
        if not plan_path.exists():
            raise FileNotFoundError(f"learning apply plan not found: {plan_path}")
        try:
            payload = json.loads(plan_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"learning apply plan is not valid JSON: {plan_path}") from exc
        if not isinstance(payload, dict):
            raise ValueError("learning apply plan must be a JSON object")
        plan = LearningApplyPlan.model_validate(payload)
        if plan.tenant_id != tenant_id:
            raise ValueError(
                f"learning apply plan tenant mismatch: expected {tenant_id}, found {plan.tenant_id}"
            )
        return LearningApplyExecutor(package_root=self.package_root).execute(plan, approved_by=approved_by)

    def _proposal_dir(self) -> Path:
        return self.package_root / "docs" / "workspace" / "cios-learning-apply-plan" / "proposals"

    def _policy_audit(self, tenant_id: int) -> LearningPolicyAuditStatus:
        result = audit_learning_policies(self.package_root, tenant_id=tenant_id)
        return LearningPolicyAuditStatus.model_validate(result.model_dump(mode="json"))

    def _proposals(self, tenant_id: int) -> list[LearningApplyProposalAdminRecord]:
        rows: list[LearningApplyProposalAdminRecord] = []
        proposal_dir = self._proposal_dir()
        if not proposal_dir.exists():
            return rows
        for path in sorted(proposal_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            action = payload.get("action")
            if not isinstance(action, dict):
                continue
            if int(action.get("tenant_id") or -1) != tenant_id:
                continue
            rows.append(
                LearningApplyProposalAdminRecord(
                    action_id=str(payload.get("action_id") or ""),
                    status=str(payload.get("status") or "unknown"),
                    target=str(action.get("target") or ""),
                    package_path=str(action.get("package_path") or ""),
                    proposal_path=str(_relative(path, self.package_root)),
                    summary=str(action.get("summary") or ""),
                    approved_by=payload.get("approved_by"),
                    evidence_event_ids=_int_list(action.get("evidence_event_ids")),
                    source_improvement_ids=_int_list(action.get("source_improvement_ids")),
                )
            )
        return rows

    def _approved_policies(self, tenant_id: int) -> list[LearningApplyPolicyAdminRecord]:
        rows: list[LearningApplyPolicyAdminRecord] = []
        config_dir = self.package_root / "config"
        if not config_dir.exists():
            return rows
        for path in sorted(config_dir.glob("*policy.y*ml")):
            try:
                payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except (OSError, yaml.YAMLError):
                continue
            if not isinstance(payload, dict):
                continue
            policies = payload.get("policies") or []
            if not isinstance(policies, list):
                continue
            for policy in policies:
                if not isinstance(policy, dict):
                    continue
                if policy.get("status") != "approved":
                    continue
                if int(policy.get("tenant_id") or -1) != tenant_id:
                    continue
                rows.append(
                    LearningApplyPolicyAdminRecord(
                        action_id=str(policy.get("action_id") or ""),
                        status=str(policy.get("status") or "approved"),
                        target=str(policy.get("target") or ""),
                        package_path=str(_relative(path, self.package_root)),
                        summary=str(policy.get("summary") or ""),
                        approved_by=policy.get("approved_by"),
                        evidence_event_ids=_int_list(policy.get("evidence_event_ids")),
                        source_improvement_ids=_int_list(policy.get("source_improvement_ids")),
                    )
                )
        return rows


def _default_package_root() -> Path:
    configured = os.environ.get("CIOS_APP_DIR")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[3]


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _int_list(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    out: list[int] = []
    for item in value:
        try:
            out.append(int(item))
        except (TypeError, ValueError):
            continue
    return out
