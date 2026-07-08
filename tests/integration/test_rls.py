"""RLS bleed check: a row inserted under tenant A's context must not be
visible to a plain SELECT run under tenant B's context.

schema.sql's tenant_isolation policy (`CREATE POLICY` loop, DO $$ block near
the bottom) is applied uniformly to every tenant-scoped table via
`current_setting('app.tenant_id', true)`. This test exercises two
representative tables (`sources`, `competitors`) rather than all 51 --
the policy is generated identically for every table in the loop, so these
two are a fair proxy.
"""

from __future__ import annotations

import uuid

import pytest

from cios.db.session import tenant_context

pytestmark = pytest.mark.integration


@pytest.fixture()
def two_tenants(pg_conn):
    unique = uuid.uuid4().hex
    with pg_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO tenants (name, slug) VALUES (%s, %s) RETURNING id",
            (f"RLS Tenant A {unique}", f"rls-tenant-a-{unique}"),
        )
        (tenant_a,) = cur.fetchone()
        cur.execute(
            "INSERT INTO tenants (name, slug) VALUES (%s, %s) RETURNING id",
            (f"RLS Tenant B {unique}", f"rls-tenant-b-{unique}"),
        )
        (tenant_b,) = cur.fetchone()
    pg_conn.commit()
    return tenant_a, tenant_b


class TestRowLevelSecurity:
    def test_tenant_a_competitor_not_visible_under_tenant_b_context(self, app_conn, two_tenants):
        tenant_a, tenant_b = two_tenants

        with tenant_context(app_conn, tenant_a):
            app_conn.execute(
                "INSERT INTO competitors (tenant_id, name) VALUES (%s, %s)",
                (tenant_a, "Only Tenant A Can See This"),
            )

        with tenant_context(app_conn, tenant_b):
            rows = app_conn.execute(
                "SELECT * FROM competitors WHERE name = %s", ("Only Tenant A Can See This",)
            ).fetchall()
        assert rows == [], "tenant B must not see tenant A's competitor row (RLS bleed)"

        with tenant_context(app_conn, tenant_a):
            rows = app_conn.execute(
                "SELECT * FROM competitors WHERE name = %s", ("Only Tenant A Can See This",)
            ).fetchall()
        assert len(rows) == 1, "tenant A should still see its own row"

    def test_tenant_a_source_not_visible_under_tenant_b_context(self, app_conn, two_tenants):
        tenant_a, tenant_b = two_tenants

        with tenant_context(app_conn, tenant_a):
            competitor_id = app_conn.execute(
                "INSERT INTO competitors (tenant_id, name) VALUES (%s, %s) RETURNING id",
                (tenant_a, "Acme for RLS Source Test"),
            ).fetchone()[0]
            app_conn.execute(
                "INSERT INTO sources (tenant_id, competitor_id, source_family, url, normalized_url) "
                "VALUES (%s, %s, %s, %s, %s)",
                (tenant_a, competitor_id, "blog", "https://acme.example/rls", "https://acme.example/rls"),
            )

        with tenant_context(app_conn, tenant_b):
            rows = app_conn.execute(
                "SELECT * FROM sources WHERE normalized_url = %s", ("https://acme.example/rls",)
            ).fetchall()
        assert rows == [], "tenant B must not see tenant A's source row (RLS bleed)"

    def test_no_tenant_context_set_returns_zero_rows_fail_closed(self, app_conn, two_tenants):
        """current_setting('app.tenant_id', true) is NULL when unset -> the
        policy's tenant_id = NULL comparison is NULL -> zero rows. Confirms
        the fail-closed behavior documented in schema.sql's RLS contract."""
        tenant_a, _ = two_tenants
        with tenant_context(app_conn, tenant_a):
            app_conn.execute(
                "INSERT INTO competitors (tenant_id, name) VALUES (%s, %s)",
                (tenant_a, "Fail Closed Check"),
            )

        with app_conn.transaction():
            rows = app_conn.execute(
                "SELECT * FROM competitors WHERE name = %s", ("Fail Closed Check",)
            ).fetchall()
        assert rows == [], "with no app.tenant_id set, RLS must fail closed (zero rows)"
