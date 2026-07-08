# CI-OS — SESSION.md

Updated: 2026-07-08 ~06:30 ET (session close persist) (Claude Fable 5, caveman mode, overnight multi-agent build)

## Status
V2 DEPLOYED LIVE (parallel run) on the VPS: real Telegram baseline brief delivered to Arijit's chat (quality passed), cron 09:15 UTC daily, real V0 history migrated. Arijit's product doctrine recorded (docs/planning/CI-OS-product-doctrine-2026-07-08.md) and briefs rebuilt to it. Previously: Brain live-certified (5/5 criteria) AND the 3-tenant Gate 7 rehearsal FULLY PASSED (~03:00 ET) after a 6-iteration fix loop. 18 commits, 259 offline + 16 integration tests. Delivery hard-gated on quality; evidence article-level; quotes verified verbatim; revise loop in. V0 untouched, cron intact.

## Resume action (do first, in order)
0. Phase 1 CORE DONE: Hermes cron job `cios-v2-daily` (09:15 ET, no-agent, script /root/.hermes/scripts/cios-daily.sh, container venv at /opt/data/apps/cios) drives the pipeline; duplicate system cron removed. TZ: VPS+container = ET (V0 09:00 ET, V2 09:15 ET). Verify tomorrow's Hermes-fired run. Phase 1b next: webhook deliver_only delivery route, shim-as-provider check, email target.
1. Arijit eyeballs the 09:00 ET Telegram brief (chat 6789423537) — V0 hotfix live proof. Report quality.
2. Show Arijit the dashboard preview: python3 scripts/render_dashboard_preview.py docs/planning/gate7-rehearsal-runs/dashboard-state.v2.1.daily.json (renderer DONE, 1037df6; history/suppressed panels = flagged data gaps).
3. Run the V0 sqlite migration against the REAL ci.sqlite on the VPS (3 duplicate copies to reconcile).
4. V0 cutover ONLY after Arijit's explicit yes (Mandate Boundary). Rehearsal harness rerun: shim on :8663 + docker Postgres + schema/seed + cios_app password (see memory).

## Where we stopped (exact)
Gate 7 rehearsal FULL PASS committed (`2bb0673`); persist ran right after. Nothing in flight. Report: docs/planning/gate7-rehearsal-runs/2026-07-08-run.md (bottom line now computed, not hardcoded).

## Decisions locked (2026-07-07/08)
- All prior locks (multi-tenant day 1; tiered models; telegram→email→dashboard; brain-before-breadth; V0 lives until parity cutover).
- VPS Claude provider: Anthropic API key (from Arijit's Mac keychain after his /login) at VPS `~/.cios-anthropic.key` + appended to `/root/.hermes/.env`. Verified live. Key never printed/committed.
- Arijit standing orders (in memory, permanent): status reports = plain-English DONE/NOW/PENDING table with % + traffic lights, unprompted at every stage; /persist at every logical stage; no gate jargon at him.
- Eval agents: sonnet minimum (haiku failed to report twice).
- Competitor sets: proceeding on goal-spec §4 defaults; Arijit redline still open.

## Remaining work
- Live brain cert verdict (item 1) → then adversarial panel already built in (verify_panel.py ran within cert).
- Dashboard; Gate 7 E2E; V0 cutover (Arijit gate).
- Real-ci.sqlite migration run on VPS (script synthetic-tested only; 3 duplicate sqlite copies to reconcile).
- Backlog: RSS + Scout fetchers; WhatsApp/Apple adapters; VPS 0.0.0.0:4719 port audit.

## Reference files
- `docs/planning/CI-OS-Fable-build-goal-spec.md` — THE spec. `docs/planning/CI-OS-gate0-implementation-plan.md` — build plan + budgets.
- Code: `src/cios/{platform,hunter,collect,execspeech,brain,learn,delivery,db,migration}/`. Tests mirror in `tests/`.
- V0 reference copy (from prod): `docs/workspace/v0-reference/ci_core.py`.
- Integration tests: `pytest -m integration` with `deploy/docker-compose.yml` Postgres (env in `deploy/.env`, gitignored).
- Vault: `Projects/CI-OS/index.md` + `tasks.md` + `log.md`. Memory: `ci-os-v2-build-2026-07-08`.

## What has NOT been done
- V0 hotfix NOT live-verified (9AM brief unseen) — the production system's proof is still pending.
- Migration NOT run against real ci.sqlite (synthetic fixture only).
- Dashboard renderer DONE (1037df6); report-history + suppressed-signals panels omitted pending truthful data sources.
- Cutover: not proposed; V0 prod untouched beyond the 2026-07-07 hotfix; cron intact.
- Exec-speech lane not exercised in rehearsal (module built + unit-tested only); coverage honestly marked incomplete in runs.

## Files written this session
- CI-OS repo: 19 commits `349f25e..1037df6` (src/cios/* + tests/* + deploy/* + pyproject/pytest.ini + .gitignore).
- VPS: `~/.cios-anthropic.key` (chowmesadmin), `ANTHROPIC_API_KEY` line in `/root/.hermes/.env`.
- Vault: `Projects/CI-OS/index.md` (compiled truth updated), `log.md` + `tasks.md` (new), `wiki/log.md` + `hot.md`, `Projects/AI-OS/My-Projects.md`.
- Memory: `ci-os-v2-build-2026-07-08`, `build-status-report-format`, `haiku-eval-agents-unreliable`, `session_pointer`, `MEMORY.md`.
