# cios-claude-shim

Thin localhost HTTP wrapper around the `claude` CLI, per Gate-0 decision D3
(`docs/planning/CI-OS-gate0-implementation-plan.md`). Runs ON THE VPS HOST
(not in a container) so container code can call `claude -p` via HTTP
without the container needing direct CLI/auth access.

## Security — read this first

**MUST bind 127.0.0.1 only. NEVER bind 0.0.0.0 or expose this port publicly.**
The shim has no auth of its own — it trusts anything that can reach
127.0.0.1:8663. It must never be reachable off-host.

## Environment

- `CLAUDE_CODE_OAUTH_TOKEN` — the Claude Code OAuth token backing the CLI's
  logged-in session (shared Max subscription). NOT an API key. Set in the
  systemd unit's `EnvironmentFile`, never committed to this repo.

## Install (systemd)

```bash
sudo useradd --system --no-create-home cios-shim   # if not already present
sudo cp deploy/claude-shim/cios-claude-shim.service /etc/systemd/system/
sudo cp deploy/claude-shim/shim.py /opt/cios/claude-shim/shim.py
sudo cp deploy/.env /etc/cios-claude-shim.env   # contains CLAUDE_CODE_OAUTH_TOKEN
sudo systemctl daemon-reload
sudo systemctl enable --now cios-claude-shim
sudo systemctl status cios-claude-shim
```

## Verify

```bash
curl -s http://127.0.0.1:8663/health
```

Should never succeed from any host other than the VPS itself — confirm with
`sudo ss -tlnp | grep 8663` and check the bind address is `127.0.0.1`, not
`0.0.0.0` or `*`.

## Behavior notes

- `/generate` retries live entirely on the CALLER side
  (`src/cios/platform/models/providers/claude_cli.py`), not in the shim —
  the shim makes one `claude -p` attempt per request.
- Auth failures (CLI reports "not logged in" or similar in stdout/stderr)
  return HTTP 503 with a clear error body, not a generic 500, so callers can
  distinguish "needs re-auth" from "transient failure."
- `/health` caches its result for 5 minutes in-memory to avoid spamming the
  CLI on every poll.
