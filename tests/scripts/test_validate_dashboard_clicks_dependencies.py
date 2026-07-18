from __future__ import annotations

import subprocess
import sys
import tomllib
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "validate_dashboard_clicks.py"


def _load_validator_module():
    spec = importlib.util.spec_from_file_location("validate_dashboard_clicks", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_click_validator_declares_playwright_e2e_dependency() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    optional = pyproject["project"]["optional-dependencies"]

    assert "e2e" in optional
    assert any(item.startswith("playwright>=") for item in optional["e2e"])
    assert any("e2e" in item for item in optional["dev"])


def test_click_validator_dependency_message_explains_how_to_bootstrap_e2e(monkeypatch) -> None:
    module = _load_validator_module()
    monkeypatch.setattr(module.importlib.util, "find_spec", lambda name: None if name == "playwright" else object())

    errors = module.dependency_errors()

    message = module._dependency_help(errors)
    assert errors == ["Python package `playwright` is not installed."]
    assert "dashboard click validation dependencies missing" in message
    assert "python -m pip install -e '.[e2e]'" in message
    assert "python -m playwright install chromium" in message
    assert "ModuleNotFoundError" not in message


def test_click_validator_preflight_accepts_tenant_argument_without_import_crash() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--check-dependencies",
            "--tenant",
            "algolia",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode in {0, 2}
    assert "ModuleNotFoundError" not in result.stderr
    assert "unrecognized arguments" not in result.stderr
    if result.returncode == 2:
        assert "dashboard click validation dependencies missing" in result.stderr


def test_click_validator_accepts_not_scored_backend_rubric_contract() -> None:
    module = _load_validator_module()

    module._validate_confidence_rubric_text(
        "Pattern across partners Where the market is heading Argus recommendation "
        "Confidence rubric Not scored No backend recommendation scorecard exists "
        "No tenant-side demand evidence was captured in this run."
    )


def test_click_validator_rejects_old_fake_confidence_rubric_contract() -> None:
    module = _load_validator_module()

    with pytest.raises(AssertionError, match="backend scorecard"):
        module._validate_confidence_rubric_text(
            "Pattern across partners Where the market is heading Argus recommendation "
            "Confidence rubric Quality gate Public-source boundary Materiality separation"
        )


def test_click_validator_builds_run_bound_structured_verdict() -> None:
    module = _load_validator_module()

    verdict = module.build_verdict(
        run_id="cios-20260714T090000Z-1234",
        results=[
            module.CheckResult("structure", "ok"),
            module.CheckResult("viewport_390", "ok"),
        ],
        generated_at="2026-07-14T09:03:00Z",
    )

    assert verdict == {
        "schema_version": 1,
        "gate": "dashboard_click_validation",
        "run_id": "cios-20260714T090000Z-1234",
        "generated_at": "2026-07-14T09:03:00Z",
        "status": "pass",
        "exit_code": 0,
        "checks": {"structure": True, "viewport_390": True},
    }
