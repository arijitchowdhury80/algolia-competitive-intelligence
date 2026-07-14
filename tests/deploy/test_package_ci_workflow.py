from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "ci-os-package.yml"


def test_package_ci_workflow_targets_dedicated_package_branch() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "pull_request:" in text
    assert "push:" in text
    assert "ci-os-package-main" in text
    assert "actions/checkout@v7" in text
    assert "actions/setup-python@v6" in text


def test_package_ci_workflow_runs_static_default_and_real_postgres_layers() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "pyright --project pyright-phase2.json" in text
    assert "python3 -m pytest -q" in text
    assert "postgres:16-alpine" in text
    assert "CIOS_ALLOW_SCHEMA_RESET_FOR_TESTS: \"1\"" in text
    assert "postgresql://cios_dev:ci_test_only@127.0.0.1:5432/cios" in text
    assert "python3 -m pytest -m integration -q" in text
