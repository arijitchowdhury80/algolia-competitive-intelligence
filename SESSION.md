# CI-OS — SESSION.md

Updated: 2026-07-08 ~17:00 ET (BRIEF PAGE EDITORIAL REDESIGN — Arijit rejected v1 as data dump; v2 SHIPPED + screenshot-verified live) (Claude Fable 5, caveman mode)

## Brief page v2 (after Arijit's rejection of the first pass)
First pass passed structural checks (curl greps) but read as a wall: paragraph-length headlines, 18-play dump, 6 duplicate theses, no design. LESSON: visible-surface verification = SCREENSHOT the rendered page, curl greps are not looking. v2 shipped + screenshot-verified on live ci.chowmes.com/brief.html:
- Dark editorial masthead; distilled headlines (word-cap + dangling-stopword trim); body never repeats headline.
- Your Plays: top 5 by urgency, steps behind disclosure, "+N more on cockpit".
- Living Theses: 7 → 3 on live page — transitive paraphrase clustering (threshold 0.4, match="any") in _build_theses; measured on real production texts (same-hypothesis 0.35–0.53, distinct ≤0.35).
- OPEN root cause (task #28): thesis writer mints paraphrase rows daily instead of updating the standing thesis; render dedup = labeled stopgap.

## P0 punch list (Arijit 15:50 ET) — CLOSED, live-verified
All 4 items shipped and verified by curling the live page (not code-level claims):
1. Brief cards deduped + capped 5 + ranked — brief.html is now composed state-first from the deduped DashboardState (`render_brief_page_from_state`) in BOTH daily runner and rerender script. Live page showed 5 unique stories with "seen in N sources" merge badges (6/3/2/2).
2. Card-vs-thesis contract enforced visually + in copy: signal cards ("What changed now... Read daily, act") vs Living Theses section ("Standing strategic hypotheses... Read weekly, orient"), distinct visual weight, theses reachable because cards capped.
3. Luxury Editorial brief always published — blue template can never reach the URL again. TRUE root cause found: VPS `/root/.hermes/scripts/cios-daily.sh` NEVER copied brief.html to the public root, so the stale blue file survived every deploy. Patched (backup cios-daily.sh.bak-20260708) — now copies brief.html + v2/brief.html every run.
4. Back-nav "← Argus Cockpit" link on brief page (shared `_brief_page_shell`).
BONUS root-cause (class fix): dedup missed LLM paraphrases — `token_set_similarity` is now max(Jaccard, containment) and state_builder clusters on what_changed-only (why_it_matters diluted similarity to ~0.3). Regression tests added from the real live texts. 505 offline tests pass. Commits: 5053214 + follow-up dedup fix. Deployed to BOTH VPS copies (~/cios + /root/.hermes/apps/cios).
NEXT: tomorrow 09:00 ET fully-automatic run — verify Telegram brief + cockpit + brief.html all refresh; Arijit's verdict drives the queue.

## Status
V2 DEPLOYED LIVE (parallel run) on the VPS: real Telegram baseline brief delivered to Arijit's chat (quality passed), cron 09:15 UTC daily, real V0 history migrated. Arijit's product doctrine recorded (docs/planning/CI-OS-product-doctrine-2026-07-08.md) and briefs rebuilt to it. Previously: Brain live-certified (5/5 criteria) AND the 3-tenant Gate 7 rehearsal FULLY PASSED (~03:00 ET) after a 6-iteration fix loop. 18 commits, 259 offline + 16 integration tests. Delivery hard-gated on quality; evidence article-level; quotes verified verbatim; revise loop in. V0 untouched, cron intact.

## Resume action (do first, in order)
-5. SESSION CLOSED ~15:30 ET. Shipped last: selection-sync (barometer click filters lenses), ranked clickable plays + focus-first, cache-busting, render_brief_page (Luxury Editorial brief — CONTENT populates when the 09:00 run persists reader_text). Fast screen refresh (no pipeline): inside container `cd /opt/data/apps/cios && .venv/bin/python scripts/rerender_dashboard.py --tenant algolia` then cp out/*.html to the dashboard public root. FIRST ACTION NEXT SESSION: Arijit's P0 punch list in vault Projects/CI-OS/tasks.md (brief page dedup VISIBLE on live page, card-vs-thesis contract + cap, editorial brief template wired unconditionally, back-nav) — THEN verify the 09:00 ET cycle end-to-end, then Arijit's verdict drives the queue (content engine #23, multi-channel #24, Phase 1b, exec-speech lane, all-competitor synthesis, hero polish).
-4. DAY CLOSED with full loop live; plays visible in lenses on live page; scores/source-dedup are state-time — verify on tomorrow's 09:00 ET run. Fast re-render: render_cockpit_html from out/argus-dashboard.json inside container, cp to dashboard public root (~30s).
-3. COCKPIT: Arijit's real design = docs/mockups/ci-os-dashboard-app-mockup.html (+ design checkpoint doc). LIVE at ci.chowmes.com via cockpit_renderer.py. cockpit-fidelity agent was fixing 5 gaps at persist (per-competitor barometer rows, editorial hero cap, base64 assets, lens plays from action_items, brief.html link). On resume: check agent output / disk (src/cios/dashboard/_cockpit_assets.py exists), pytest, commit, ship BOTH VPS locations (~/cios + /root/.hermes/apps/cios via tar), smoke-regen (CIOS_DELIVER_TENANT=__smoke__ sh /opt/data/scripts/cios-daily.sh in container), screenshot ci.chowmes.com vs mockup side-by-side for Arijit.
-2. FIRST BRIEF DELIVERED 12:07 ET (3 signals + YOUR PLAYS; spryker correctly blocked). Defects fixed live: Argus_CI_bot is THE bot (argus profile env — never the default token); Hermes gateway loads cron at startup ONLY (restart after CLI job create; `cron status` reads the file = false green). Next auto-run 07-09 09:00 ET.
-1. CUTOVER IS DONE (Arijit's order): V0 paused (resume ids 19930dfa21e5/03671620cd60 for rollback), V2 owns 09:00 ET via Hermes cron, ci.chowmes.com root = V2 render (backup .v0-backup-20260708), auto-publish wired. Verify the 09:00 ET run: Telegram brief + dashboard refresh + hermes cron output log. Then: wire ownbrand/horizon/prescribe/collateral modules into daily_production_run + cadence flow.
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
