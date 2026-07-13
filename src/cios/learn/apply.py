"""Safe execution of Argus learning apply plans inside the CI-OS package.

This module is the first durable learning-apply layer. It does not touch
Hermes core and it does not silently mutate package behavior. Without explicit
human approval it writes review proposals only. With approval, it records an
idempotent policy entry under the CI-OS package config path named by the
learning apply action.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field

from cios.learn.feedback import LearningApplyAction, LearningApplyPlan
from cios.learn.types import ImprovementPriority


class LearningApplyProposalResult(BaseModel):
    """One review artifact written for an apply-plan action."""

    action_id: str
    target: str
    package_path: str
    proposal_path: str
    status: str


class LearningApplyExecutionResult(BaseModel):
    """Result of executing a learning apply plan in safe package scope."""

    tenant_id: int
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    applied_count: int = 0
    proposal_count: int = 0
    applied: list[dict[str, Any]] = Field(default_factory=list)
    proposals: list[LearningApplyProposalResult] = Field(default_factory=list)
    skipped: list[dict[str, Any]] = Field(default_factory=list)


class LearningPolicyAuditRecord(BaseModel):
    """One approved policy entry checked for drift."""

    package_path: str
    action_id: str
    expected_action_id: Optional[str] = None
    target: str = ""
    tenant_id: Optional[int] = None
    approved_by: Optional[str] = None
    status: str


class LearningPolicyAuditIssue(BaseModel):
    """One policy audit failure with operator rollback guidance."""

    code: str
    package_path: str
    action_id: Optional[str] = None
    expected_action_id: Optional[str] = None
    target: Optional[str] = None
    message: str
    rollback_hint: str


class LearningPolicyAuditResult(BaseModel):
    """Read-only drift audit for approved CI-OS learning policies."""

    package_root: str
    tenant_id: Optional[int] = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    passed: bool = True
    policy_count: int = 0
    ok_count: int = 0
    drift_count: int = 0
    invalid_count: int = 0
    issue_count: int = 0
    policies: list[LearningPolicyAuditRecord] = Field(default_factory=list)
    issues: list[LearningPolicyAuditIssue] = Field(default_factory=list)
    rollback_plan: list[str] = Field(default_factory=list)


class LearningApplyExecutor:
    """Turn `LearningApplyPlan` actions into reviewable CI-OS package work.

    The executor has one mutation path: approved config-policy records under
    `config/*.yaml` inside the supplied package root. Everything else remains
    proposal-only so a human can review the implication before code, prompt, or
    doctrine changes are made.
    """

    def __init__(
        self,
        *,
        package_root: Path,
        proposal_dir: str = "docs/workspace/cios-learning-apply-plan/proposals",
    ) -> None:
        self.package_root = package_root
        self.proposal_dir = proposal_dir

    def execute(
        self,
        plan: LearningApplyPlan,
        *,
        approved_by: Optional[str] = None,
    ) -> LearningApplyExecutionResult:
        result = LearningApplyExecutionResult(tenant_id=plan.tenant_id)

        for action in plan.actions:
            action_id = self._action_id(action)
            proposal = self._write_proposal(action, action_id, approved_by=approved_by)
            result.proposals.append(proposal)
            result.proposal_count += 1

            if not approved_by:
                continue
            if not self._is_config_policy_target(action):
                result.skipped.append(
                    {
                        "source_improvement_ids": list(action.source_improvement_ids),
                        "reason": "manual review targets are proposal-only",
                    }
                )
                continue

            applied = self._upsert_policy(action, action_id, approved_by=approved_by)
            result.applied.append(applied)
            result.applied_count += 1

        return result

    def _write_proposal(
        self,
        action: LearningApplyAction,
        action_id: str,
        *,
        approved_by: Optional[str],
    ) -> LearningApplyProposalResult:
        status = "approved_policy_written" if approved_by and self._is_config_policy_target(action) else "pending_human_approval"
        rel_path = f"{self.proposal_dir.rstrip('/')}/{action_id}-{action.target}.json"
        out_path = self._resolve_package_path(rel_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "action_id": action_id,
            "status": status,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "approved_by": approved_by,
            "action": action.model_dump(mode="json"),
        }
        out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return LearningApplyProposalResult(
            action_id=action_id,
            target=action.target,
            package_path=action.package_path,
            proposal_path=rel_path,
            status=status,
        )

    def _upsert_policy(
        self,
        action: LearningApplyAction,
        action_id: str,
        *,
        approved_by: str,
    ) -> dict[str, Any]:
        policy_path = self._resolve_package_path(action.package_path)
        policy_path.parent.mkdir(parents=True, exist_ok=True)
        existing: dict[str, Any] = {}
        if policy_path.exists():
            loaded = yaml.safe_load(policy_path.read_text(encoding="utf-8")) or {}
            if isinstance(loaded, dict):
                existing = loaded
        policies = existing.get("policies") or []
        if not isinstance(policies, list):
            policies = []

        policy = {
            "action_id": action_id,
            "status": "approved",
            "approved_by": approved_by,
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "tenant_id": action.tenant_id,
            "kind": action.kind.value,
            "target": action.target,
            "summary": action.summary,
            "instruction": action.instruction,
            "change": action.change,
            "evidence_event_ids": list(action.evidence_event_ids),
            "source_improvement_ids": list(action.source_improvement_ids),
        }
        retained = [item for item in policies if not isinstance(item, dict) or item.get("action_id") != action_id]
        retained.append(policy)
        payload = {
            "schema_version": 1,
            "generated_by": "cios.learn.apply.LearningApplyExecutor",
            "policies": retained,
        }
        policy_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
        return {
            "action_id": action_id,
            "target": action.target,
            "package_path": action.package_path,
            "status": "approved",
        }

    def _is_config_policy_target(self, action: LearningApplyAction) -> bool:
        return action.package_path.startswith("config/") and action.package_path.endswith((".yaml", ".yml"))

    def _resolve_package_path(self, rel_path: str) -> Path:
        path = Path(rel_path)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("learning apply paths must stay inside the CI-OS package")
        resolved_root = self.package_root.resolve()
        resolved = (resolved_root / path).resolve()
        try:
            resolved.relative_to(resolved_root)
        except ValueError as exc:
            raise ValueError("learning apply paths must stay inside the CI-OS package") from exc
        return resolved

    def _action_id(self, action: LearningApplyAction) -> str:
        return learning_apply_action_id(action)


def learning_apply_action_id(action: LearningApplyAction) -> str:
    stable = {
        "tenant_id": action.tenant_id,
        "kind": action.kind.value,
        "target": action.target,
        "package_path": action.package_path,
        "summary": action.summary,
        "instruction": action.instruction,
        "change": action.change,
        "evidence_event_ids": list(action.evidence_event_ids),
        "source_improvement_ids": list(action.source_improvement_ids),
    }
    raw = json.dumps(stable, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def audit_learning_policies(package_root: Path, *, tenant_id: int | None = None) -> LearningPolicyAuditResult:
    """Audit approved package policies before a production Hermes run.

    Approved policy `action_id` values are stable hashes of the fields that
    define the corresponding `LearningApplyAction`. If a policy is edited after
    approval without going back through explicit approval, this audit detects
    the mismatch and returns operator rollback guidance. It is read-only.
    """

    package_root = Path(package_root)
    result = LearningPolicyAuditResult(package_root=str(package_root), tenant_id=tenant_id)
    config_dir = package_root / "config"
    if not config_dir.exists():
        return result

    for policy_path in sorted(config_dir.glob("*policy.y*ml")):
        rel_path = _relative_to_package(policy_path, package_root)
        try:
            loaded = yaml.safe_load(policy_path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            _add_policy_issue(
                result,
                LearningPolicyAuditIssue(
                    code="invalid_policy_file",
                    package_path=rel_path,
                    message=f"policy file could not be parsed: {exc}",
                    rollback_hint=f"Restore {rel_path} from the last known good package version before production cutover.",
                ),
                invalid=True,
            )
            continue
        if not isinstance(loaded, dict):
            _add_policy_issue(
                result,
                LearningPolicyAuditIssue(
                    code="invalid_policy_file",
                    package_path=rel_path,
                    message="policy file must be a YAML object",
                    rollback_hint=f"Restore {rel_path} from the last known good package version before production cutover.",
                ),
                invalid=True,
            )
            continue

        policies = loaded.get("policies") or []
        if not isinstance(policies, list):
            _add_policy_issue(
                result,
                LearningPolicyAuditIssue(
                    code="invalid_policy_file",
                    package_path=rel_path,
                    message="policy file policies field must be a list",
                    rollback_hint=f"Restore {rel_path} from the last known good package version before production cutover.",
                ),
                invalid=True,
            )
            continue

        for policy in policies:
            if not isinstance(policy, dict) or policy.get("status") != "approved":
                continue
            policy_tenant_id = _optional_int(policy.get("tenant_id"))
            if tenant_id is not None and policy_tenant_id != tenant_id:
                continue
            _audit_one_policy(result, policy, rel_path)

    result.issue_count = len(result.issues)
    result.passed = result.issue_count == 0
    return result


def _audit_one_policy(result: LearningPolicyAuditResult, policy: dict[str, Any], rel_path: str) -> None:
    action_id = str(policy.get("action_id") or "")
    target = str(policy.get("target") or "")
    approved_by = policy.get("approved_by")
    tenant_id = _optional_int(policy.get("tenant_id"))
    result.policy_count += 1

    try:
        action = _policy_to_action(policy, rel_path)
        expected_action_id = learning_apply_action_id(action)
    except Exception as exc:  # noqa: BLE001
        result.policies.append(
            LearningPolicyAuditRecord(
                package_path=rel_path,
                action_id=action_id,
                target=target,
                tenant_id=tenant_id,
                approved_by=approved_by,
                status="invalid",
            )
        )
        _add_policy_issue(
            result,
            LearningPolicyAuditIssue(
                code="invalid_policy",
                package_path=rel_path,
                action_id=action_id or None,
                target=target or None,
                message=f"approved policy cannot be reconstructed as a safe action: {exc}",
                rollback_hint=(
                    f"Policy entry {action_id or target or 'unknown'} in {rel_path} is invalid; "
                    "revert this policy entry to the last approved version or remove it before production cutover."
                ),
            ),
            invalid=True,
        )
        return

    status = "ok" if action_id == expected_action_id else "drifted"
    result.policies.append(
        LearningPolicyAuditRecord(
            package_path=rel_path,
            action_id=action_id,
            expected_action_id=expected_action_id,
            target=target,
            tenant_id=tenant_id,
            approved_by=approved_by,
            status=status,
        )
    )
    if status == "ok":
        result.ok_count += 1
        return

    _add_policy_issue(
        result,
        LearningPolicyAuditIssue(
            code="action_id_drift",
            package_path=rel_path,
            action_id=action_id or None,
            expected_action_id=expected_action_id,
            target=target or None,
            message="approved policy fields no longer match the approved action_id",
            rollback_hint=(
                f"Policy {action_id or target or 'unknown'} in {rel_path} drifted after approval; "
                "restore the approved policy fields or re-run the learning apply plan with explicit approval."
            ),
        ),
        drift=True,
    )


def _policy_to_action(policy: dict[str, Any], package_path: str) -> LearningApplyAction:
    return LearningApplyAction(
        tenant_id=int(policy.get("tenant_id")),
        kind=str(policy.get("kind") or "other"),
        target=str(policy.get("target") or ""),
        package_path=package_path,
        summary=str(policy.get("summary") or ""),
        instruction=str(policy.get("instruction") or ""),
        change=policy.get("change") if isinstance(policy.get("change"), dict) else {},
        evidence_event_ids=_int_list(policy.get("evidence_event_ids")),
        source_improvement_ids=_int_list(policy.get("source_improvement_ids")),
    )


def _add_policy_issue(
    result: LearningPolicyAuditResult,
    issue: LearningPolicyAuditIssue,
    *,
    drift: bool = False,
    invalid: bool = False,
) -> None:
    result.issues.append(issue)
    result.rollback_plan.append(issue.rollback_hint)
    if drift:
        result.drift_count += 1
    if invalid:
        result.invalid_count += 1


def load_approved_policy_instructions(package_root: Path, *, tenant_id: int) -> list[dict[str, Any]]:
    """Load approved CI-OS package policies as next-sweep instructions.

    This is the bridge that makes a reviewed learning apply durable. It reads
    only package-local `config/*policy.yaml` files and returns the same
    instruction shape the product-market runner already understands.
    """

    config_dir = package_root / "config"
    if not config_dir.exists():
        return []

    instructions: list[dict[str, Any]] = []
    for policy_path in sorted(config_dir.glob("*policy.y*ml")):
        loaded = yaml.safe_load(policy_path.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            continue
        policies = loaded.get("policies") or []
        if not isinstance(policies, list):
            continue
        for policy in policies:
            if not isinstance(policy, dict):
                continue
            if policy.get("status") != "approved":
                continue
            if int(policy.get("tenant_id") or -1) != tenant_id:
                continue
            change = policy.get("change") if isinstance(policy.get("change"), dict) else {}
            priority = _policy_priority(change)
            instructions.append(
                {
                    "tenant_id": tenant_id,
                    "kind": str(policy.get("kind") or "other"),
                    "priority": priority.value,
                    "summary": str(policy.get("summary") or "").strip(),
                    "instruction": str(policy.get("instruction") or policy.get("summary") or "").strip(),
                    "status": "ready_for_next_sweep",
                    "change": change,
                    "evidence_event_ids": list(policy.get("evidence_event_ids") or []),
                    "source_improvement_ids": list(policy.get("source_improvement_ids") or []),
                    "policy_action_id": str(policy.get("action_id") or ""),
                    "policy_target": str(policy.get("target") or ""),
                    "policy_package_path": _relative_to_package(policy_path, package_root),
                    "policy_approved_by": policy.get("approved_by"),
                    "policy_source": "ci_os_package_policy",
                }
            )
    instructions.sort(
        key=lambda instruction: (
            _priority_order(ImprovementPriority(instruction["priority"])),
            instruction["source_improvement_ids"][0] if instruction["source_improvement_ids"] else 10**12,
        )
    )
    return instructions


def _policy_priority(change: dict[str, Any]) -> ImprovementPriority:
    raw = str(change.get("priority") or ImprovementPriority.MEDIUM.value).lower()
    try:
        return ImprovementPriority(raw)
    except ValueError:
        return ImprovementPriority.MEDIUM


def _priority_order(priority: ImprovementPriority) -> int:
    return {
        ImprovementPriority.CRITICAL: 0,
        ImprovementPriority.HIGH: 1,
        ImprovementPriority.MEDIUM: 2,
        ImprovementPriority.LOW: 3,
    }.get(priority, 99)


def _relative_to_package(path: Path, package_root: Path) -> str:
    try:
        return str(path.relative_to(package_root))
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


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
