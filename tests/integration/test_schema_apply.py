"""First real validation of schema.sql + seed.sql against a live Postgres.

Relies on the `_schema_applied` session fixture (tests/integration/conftest.py)
to actually run the DDL/DML -- if either file fails to apply, that fixture
raises an AssertionError containing the Postgres error text, which pytest
surfaces as this test's failure (see conftest.py for the exact statement
context). Run via:

    docker compose -f deploy/docker-compose.yml up -d
    CIOS_DATABASE_URL=postgresql://cios_dev:dev_local_only_not_secret@127.0.0.1:5433/cios \
        python3 -m pytest -m integration -q tests/integration/test_schema_apply.py
"""

from __future__ import annotations

import pytest


@pytest.mark.integration
class TestSchemaApply:
    def test_schema_and_seed_apply_without_error(self, pg_conn):
        # Getting a pg_conn at all means the `_schema_applied` fixture ran
        # schema.sql + seed.sql successfully (it would have raised otherwise).
        with pg_conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
            )
            (table_count,) = cur.fetchone()
        assert table_count >= 51, f"expected at least 51 tables, found {table_count}"

    def test_seed_data_present(self, pg_conn):
        with pg_conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM tenants")
            (tenant_count,) = cur.fetchone()
        assert tenant_count > 0, "seed.sql should have inserted at least one tenant"

    def test_rls_enabled_on_tenant_scoped_tables(self, pg_conn):
        with pg_conn.cursor() as cur:
            cur.execute(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                "WHERE relname = 'sources'"
            )
            row_security, force_row_security = cur.fetchone()
        assert row_security is True
        assert force_row_security is True
