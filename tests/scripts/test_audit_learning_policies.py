"""CLI contract for the CI-OS learning policy drift audit."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

from cios.learn.apply import LearningApplyExecutor
from cios.learn.feedback import LearningApplyAction, LearningApplyPlan, ProposalKind
from cios.learn.types import ImprovementPriority


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "audit_learning_policies.py"


def _action() -> LearningApplyAction:
    return LearningApplyAction(
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


def _approved_policy_root(tmp_path: Path) -> Path:
    package_root = tmp_path / "cios"
    LearningApplyExecutor(package_root=package_root).execute(
        LearningApplyPlan(tenant_id=1, actions=[_action()]),
        approved_by="arijit",
    )
    return package_root


def test_audit_learning_policies_cli_passes_clean_package(tmp_path):
    package_root = _approved_policy_root(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--package-root",
            str(package_root),
            "--tenant-id",
            "1",
            "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert payload["policy_count"] == 1
    assert payload["issue_count"] == 0


def test_audit_learning_policies_cli_blocks_drifted_package(tmp_path):
    package_root = _approved_policy_root(tmp_path)
    policy_path = package_root / "config" / "source-coverage-policy.yaml"
    payload = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    payload["policies"][0]["instruction"] = "Changed after approval without re-approval."
    policy_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--package-root",
            str(package_root),
            "--tenant-id",
            "1",
            "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["passed"] is False
    assert payload["drift_count"] == 1
    assert payload["issues"][0]["code"] == "action_id_drift"
