"""Postgres connection/session management for CI-OS (psycopg3).

Keep this thin: no ORM, no connection pool abstraction beyond what psycopg3
already gives us. Every tenant-scoped query MUST run inside a transaction
that has done `SET LOCAL app.tenant_id = <id>` first -- schema.sql's RLS
policies read that GUC (`current_setting('app.tenant_id', true)`), and
`SET LOCAL` scopes the setting to the current transaction so it can never
leak across connections pulled from a pool or reused across requests.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg import Connection


class MissingDatabaseUrlError(RuntimeError):
    """Raised when CIOS_DATABASE_URL is not set."""


def get_dsn() -> str:
    """Read the Postgres DSN from CIOS_DATABASE_URL.

    Raises MissingDatabaseUrlError with a clear message if unset -- we never
    guess at a default connection string (would risk silently hitting the
    wrong database).
    """
    dsn = os.environ.get("CIOS_DATABASE_URL")
    if not dsn:
        raise MissingDatabaseUrlError(
            "CIOS_DATABASE_URL is not set. Export it, e.g. "
            "CIOS_DATABASE_URL=postgresql://cios_app:<password>@127.0.0.1:5433/cios"
        )
    return dsn


@contextmanager
def get_connection(dsn: str | None = None) -> Iterator[Connection]:
    """Open a psycopg3 connection as a context manager.

    Uses `dsn` if given, otherwise reads CIOS_DATABASE_URL via get_dsn().
    Callers are responsible for transaction boundaries (see `transaction`
    and `tenant_context` below) -- this just owns connection open/close.
    """
    resolved_dsn = dsn if dsn is not None else get_dsn()
    conn = psycopg.connect(resolved_dsn)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def transaction(conn: Connection) -> Iterator[Connection]:
    """Transaction context manager: commit on success, rollback on exception.

    psycopg3 connections already support `with conn.transaction():` as a
    savepoint-aware transaction block; we just re-export that behavior under
    a name that matches the rest of this module's vocabulary.
    """
    with conn.transaction():
        yield conn


@contextmanager
def tenant_context(conn: Connection, tenant_id: int) -> Iterator[Connection]:
    """Run `SET LOCAL app.tenant_id = <tenant_id>` for the current transaction.

    Must be used inside an open transaction (it opens one via `transaction()`
    if the connection isn't already in one) so the setting is transaction-
    scoped per the RLS contract documented in schema.sql:

        RLS contract: every tenant-scoped table has RLS ENABLED + FORCED
        with a policy USING (tenant_id = current_setting('app.tenant_id')::bigint).

    `SET LOCAL` (not bare `SET`) ensures the GUC resets at transaction end,
    so a pooled/reused connection can never leak one tenant's context into
    another tenant's query.
    """
    # Postgres does not allow bind parameters in `SET LOCAL <name> = <value>`
    # position, so a naive `SET LOCAL app.tenant_id = %s` is a SYNTAX ERROR
    # (parameters are only allowed in DML/query positions) -- discovered by
    # running this against a live Postgres for the first time. `set_config`
    # is a regular function call and DOES accept a bind parameter for its
    # value argument, so it is used here instead; the third argument `true`
    # requests session-local (i.e. transaction-scoped, matching `SET LOCAL`)
    # semantics per Postgres docs.
    with conn.transaction():
        conn.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),))
        yield conn
