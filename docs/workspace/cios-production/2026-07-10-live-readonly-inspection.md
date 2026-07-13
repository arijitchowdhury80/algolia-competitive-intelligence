# 2026-07-10 Live Read-Only Inspection

Status: production wiring inspected, no live changes made.

## What Was Checked

- Host: Chowmes VPS through the Chowmes SSH helper.
- Scope: read-only path, wrapper, venv, and Hermes cron inspection.
- No firewall, service, credential, data, cron, or deployment changes were made.

## Findings

1. The active Hermes cron job is the root-profile job `cios-v2-daily`.
   - Source: `/root/.hermes/cron/jobs.json`.
   - Schedule: `0 9 * * *`.
   - Script: `cios-daily.sh`.
   - Enabled: `true`.
   - Last recorded status: `error`.
   - Last recorded error: `ModuleNotFoundError: No module named 'psycopg'` from `/opt/data/apps/cios/scripts/daily_production_run.py`.

2. The current CI-OS app directory on the VPS is `/root/.hermes/apps/cios`.
   - `/opt/data/apps/cios` was missing during inspection.
   - `/root/.hermes/apps/cios/.venv/bin/python` currently imports `psycopg`, `yaml`, and `httpx` successfully, so the recorded cron error may be stale relative to the current venv state.

3. The live package is stale relative to the local CI-OS build.
   - Missing on live: `/root/.hermes/apps/cios/src/cios/intelligence`.
   - Missing on live: `/root/.hermes/apps/cios/tests/deploy/test_cios_daily_wrapper.py`.
   - Present on live: `/root/.hermes/apps/cios/src/cios/admin`.

4. The live wrapper is the old unsafe wrapper.
   - Path: `/root/.hermes/apps/cios/deploy/cios-daily.sh`.
   - Also present as `/root/.hermes/scripts/cios-daily.sh`.
   - It does not default `CIOS_ENABLE_PRODUCT_MARKET_INTELLIGENCE=1`.
   - It does not clear stale `$APP/out` before the run.
   - It copies public artifacts directly and treats dashboard JSON/brief copies as optional.
   - It does not validate current-run artifacts before touching the public site.

5. Old Argus competitive-research jobs are paused, but still present.
   - Argus profile daily job `19930dfa21e5`: disabled, state `paused`.
   - Argus profile weekly job `03671620cd60`: disabled, state `paused`.
   - Their wrappers still exist under `/opt/data/skills/competitive-research/scripts/`.

## Implication

The live host is not yet running the CI-OS product-market intelligence spine that the local repo now contains. A real Hermes cron acceptance run would be invalid until the production app is synchronized with the local package and the wrapper contract passes on the VPS.

## Required Before Live Acceptance

1. Deploy/synchronize the local CI-OS package to the live app directory.
2. Ensure both wrapper locations point to the safe wrapper contract:
   - `/root/.hermes/apps/cios/deploy/cios-daily.sh`
   - `/root/.hermes/scripts/cios-daily.sh`
3. Run:

   ```bash
   /root/.hermes/apps/cios/.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios
   ```

4. Run the Hermes cron path or a one-shot equivalent through the same script resolution Hermes uses.
5. Verify:
   - product-market chain status is `ran`.
   - current-run cockpit, `brief.html`, dashboard JSON, and competitor briefs are produced.
   - public `ci.chowmes.com` updates only after those artifacts exist.
   - Playwright/click validation passes against the live URL.
