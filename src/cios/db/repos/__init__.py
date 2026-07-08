"""Postgres implementations of the Protocol repositories declared alongside
each domain module (hunter/lifecycle.py, collect/runner.py,
delivery/commander.py, learn/recorder.py).

Each Pg* class takes a psycopg3 `Connection` (or a dsn to open its own) and
implements its Protocol's exact method signatures -- structural typing only,
no subclassing required. Every method that touches a tenant-scoped table
opens its own transaction and sets `app.tenant_id` via
`cios.db.session.tenant_context` before running the query, so callers never
have to remember to scope the connection themselves.
"""
