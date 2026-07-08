"""Fixtures for the CI-OS Postgres integration suite.

How to run:

    docker compose -f deploy/docker-compose.yml up -d
    # wait for the healthcheck, then:
    CIOS_DATABASE_URL=postgresql://cios_dev:dev_local_only_not_secret@127.0.0.1:5433/cios \
        python3 -m pytest -m integration -q
    docker compose -f deploy/docker-compose.yml down -v

CIOS_DATABASE_URL must point at a SUPERUSER role (the postgres image's
POSTGRES_USER) -- schema.sql's DDL (CREATE ROLE, ENABLE/FORCE ROW LEVEL
SECURITY, GRANT) requires superuser privileges. Tests that exercise the
Pg*Repository classes connect as the unprivileged, RLS-bound `cios_app` role
instead (see the `app_conn` fixture), which is what production code paths
use.
"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest

from cios.db.session import get_dsn

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_SQL = REPO_ROOT / "src" / "cios" / "db" / "schema.sql"
SEED_SQL = REPO_ROOT / "src" / "cios" / "db" / "seed.sql"

# Dev-only password for the RLS-bound app role, matching deploy/.env's
# throwaway POSTGRES_PASSWORD convention. Never a real secret.
CIOS_APP_PASSWORD = "cios_app_dev_local_only_not_secret"


def _require_dsn() -> str:
    try:
        return get_dsn()
    except Exception as exc:  # noqa: BLE001 -- surface a clear skip reason
        pytest.skip(f"CIOS_DATABASE_URL not set or invalid: {exc}")


@pytest.fixture(scope="session")
def superuser_dsn() -> str:
    return _require_dsn()


@pytest.fixture(scope="session")
def _schema_applied(superuser_dsn: str) -> str:
    """Reset the public schema and apply schema.sql + seed.sql once per test
    session, then set a known password on cios_app so tests can connect as
    the RLS-bound app role. Returns the superuser dsn for convenience."""
    with psycopg.connect(superuser_dsn, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")

        schema_sql = SCHEMA_SQL.read_text()
        try:
            conn.execute(schema_sql)
        except Exception as exc:
            raise AssertionError(
                f"schema.sql failed to apply.\nPostgres error: {exc}\n"
                f"Full schema.sql is at {SCHEMA_SQL}"
            ) from exc

        seed_sql = SEED_SQL.read_text()
        try:
            conn.execute(seed_sql)
        except Exception as exc:
            raise AssertionError(
                f"seed.sql failed to apply.\nPostgres error: {exc}\n"
                f"Full seed.sql is at {SEED_SQL}"
            ) from exc

        conn.execute(f"ALTER ROLE cios_app WITH PASSWORD '{CIOS_APP_PASSWORD}'")
    return superuser_dsn


@pytest.fixture()
def pg_conn(_schema_applied: str):
    """Superuser connection -- bypasses RLS. Use for setup/assertions that
    need to see rows across tenants (e.g. counting rows a policy hides)."""
    with psycopg.connect(_schema_applied) as conn:
        yield conn


def _app_dsn(superuser_dsn: str) -> str:
    """Swap the superuser dsn's user/password for cios_app's, keeping host/
    port/dbname. Avoids hardcoding connection details separately from
    whatever CIOS_DATABASE_URL the caller provided."""
    info = psycopg.conninfo.conninfo_to_dict(superuser_dsn)
    info["user"] = "cios_app"
    info["password"] = CIOS_APP_PASSWORD
    return psycopg.conninfo.make_conninfo(**info)


@pytest.fixture()
def app_conn(_schema_applied: str):
    """Connection as the unprivileged, RLS-bound `cios_app` role -- the role
    every Pg*Repository is meant to run as in production."""
    dsn = _app_dsn(_schema_applied)
    with psycopg.connect(dsn) as conn:
        yield conn


@pytest.fixture()
def app_dsn(_schema_applied: str) -> str:
    return _app_dsn(_schema_applied)
