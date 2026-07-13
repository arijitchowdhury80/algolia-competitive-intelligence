"""Smoke contract for the Hermes-callable product-market runner script."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "run_product_market_intelligence.py"
REFRESH_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "refresh_product_market_from_ledger.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_product_market_intelligence", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_refresh_module():
    spec = importlib.util.spec_from_file_location("refresh_product_market_from_ledger", REFRESH_SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_product_market_runner_script_exists_and_imports() -> None:
    module = _load_module()

    assert hasattr(module, "main")
    assert hasattr(module, "resolve_tenant_id")


def test_product_market_runner_resolves_tenant_slug() -> None:
    module = _load_module()

    class Conn:
        def execute(self, sql, params):
            assert "FROM tenants" in sql
            assert params == ("algolia",)
            return self

        def fetchone(self):
            return {"id": 42}

    assert module.resolve_tenant_id(Conn(), "algolia") == 42


def test_product_market_ledger_refresh_script_exists_and_imports() -> None:
    module = _load_refresh_module()

    assert hasattr(module, "main")
    assert hasattr(module, "resolve_tenant_id")


def test_product_market_ledger_refresh_script_resolves_tenant_slug() -> None:
    module = _load_refresh_module()

    class Conn:
        def execute(self, sql, params):
            assert "FROM tenants" in sql
            assert params == ("algolia",)
            return self

        def fetchone(self):
            return {"id": 42}

    assert module.resolve_tenant_id(Conn(), "algolia") == 42


def test_product_market_ledger_refresh_script_loads_learning_plan_instructions(tmp_path) -> None:
    module = _load_refresh_module()
    plan = tmp_path / "next-sweep-learning-plan.json"
    plan.write_text(
        json.dumps(
            {
                "instructions": [
                    {
                        "kind": "coverage_recheck",
                        "instruction": "Re-audit Coveo before ranking Constructor again.",
                        "source_improvement_ids": [202],
                    }
                ],
                "skipped": [{"id": 303, "reason": "not approved"}],
            }
        ),
        encoding="utf-8",
    )

    instructions = module.load_learning_instructions(plan)

    assert instructions == [
        {
            "kind": "coverage_recheck",
            "instruction": "Re-audit Coveo before ranking Constructor again.",
            "source_improvement_ids": [202],
        }
    ]
