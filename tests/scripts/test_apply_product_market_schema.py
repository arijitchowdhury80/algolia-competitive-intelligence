"""Tests for the product-market schema applicator used by the Hermes wrapper."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "apply_product_market_schema.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("apply_product_market_schema", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_apply_product_market_schema_executes_idempotent_product_market_ddl(monkeypatch):
    module = _load_module()
    executed = []

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def execute(self, sql):
            executed.append(sql)

    monkeypatch.setattr(module.psycopg, "connect", lambda _url: FakeConnection())

    rc = module.main(["--database-url", "postgresql://example"])

    assert rc == 0
    assert len(executed) == 1
    sql = executed[0]
    assert "CREATE TABLE IF NOT EXISTS product_surfaces" in sql
    assert "CREATE TABLE IF NOT EXISTS product_market_run_intelligence" in sql
    assert "'product_surfaces'" in sql
    assert "DROP POLICY IF EXISTS tenant_isolation ON %I" in sql
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON %I TO cios_app" in sql
