# CI-OS database

Postgres 16, database `cios`. Multi-tenant with Row Level Security. This is the
product memory: reports, dashboard, delivery, and content planning all render
from these tables, not from scraped prose.

## Files

- `schema.sql` — v1 baseline DDL for every table, plus RLS policies and the
  `cios_app` application role. Apply once on a fresh database.
- `seed.sql` — 3 tenants (algolia, spryker, amplitude), the global permission
  catalog, 10 roles per tenant with grants, and the Algolia owner user with a
  Telegram identity. Idempotent.
- `../../../tests/db/test_schema.sql` — plain-SQL smoke tests (PASS/FAIL lines).

## Bring it up locally

```bash
cp deploy/.env.example deploy/.env          # fill POSTGRES_USER / POSTGRES_PASSWORD
docker compose -f deploy/docker-compose.yml up -d
# wait for healthcheck, then apply schema + seed as the superuser:
export CIOS_DATABASE_URL="postgresql://<POSTGRES_USER>:<POSTGRES_PASSWORD>@127.0.0.1:5433/cios"
psql "$CIOS_DATABASE_URL" -v ON_ERROR_STOP=1 -f src/cios/db/schema.sql
psql "$CIOS_DATABASE_URL" -v ON_ERROR_STOP=1 -f src/cios/db/seed.sql
psql "$CIOS_DATABASE_URL" -f tests/db/test_schema.sql   # expect all PASS
```

Set a password for the app role once (kept out of git / env only):

```bash
psql "$CIOS_DATABASE_URL" -c "ALTER ROLE cios_app LOGIN PASSWORD '<app-password>';"
```

The application connects as `cios_app` using its own `CIOS_DATABASE_URL`
(the env-spec variable). `cios_app` is `NOBYPASSRLS`, so it can never read
across tenants regardless of application bugs.

## On the VPS (Hermes / chowmes)

Same steps. Deploy per Gate 0 D1/D4:

- The `cios-postgres` compose service runs on the host, bound to
  `127.0.0.1:5433` (never exposed publicly).
- Code is deployed to `/opt/data/apps/cios/`; workers connect over the
  localhost port.
- This container has an independent lifecycle from PRISM's stopped
  `postgres:16` container and from Umami's `postgres:15`. Do not share them.

## How tenant context works (RLS)

Every tenant-scoped table has RLS **enabled and forced** with the policy:

```sql
USING (tenant_id = current_setting('app.tenant_id')::bigint)
```

The application MUST set the tenant on each connection/transaction before any
query:

```sql
SET app.tenant_id = '42';          -- session scope
-- or, preferred, per transaction:
SET LOCAL app.tenant_id = '42';
```

With no `app.tenant_id` set, the policy compares against NULL and returns zero
rows (fail-closed). Superusers bypass RLS and are used only for schema and seed.
Global tables (`tenants`, `permissions`) are not tenant-scoped and have no RLS.

This enforces the spec invariant "no channel request may access data before
identity resolution and ACL evaluation" at the database layer, not just in app
code.

## Migration policy

- `schema.sql` is the **v1 baseline**: the single source of truth for a fresh
  install. Apply it once.
- From **v2 onward**, all schema changes go through **Alembic** migrations under
  `src/cios/db/` (per Gate 0 D4 layout). Do not hand-edit `schema.sql` for
  changes once v2 begins; write a migration and, if desired, regenerate the
  baseline from a fresh migrate. Alembic's version table lives in the same
  database.
- Evidence and other invariants are enforced by CHECK constraints and RLS here.
  A few invariants are necessarily application-level (noted inline in
  `schema.sql`); those are owned by the platform module, not the schema.
