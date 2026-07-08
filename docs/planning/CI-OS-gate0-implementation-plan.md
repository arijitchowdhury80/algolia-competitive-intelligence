# CI-OS Gate 0 — Implementation Plan, V0 Inventory, and Reuse Decision

Date: 2026-07-07
Status: Gate 0 deliverable (per `CI-OS-Fable-build-goal-spec.md` §5)
Inputs: live VPS inventory (read directly), planning-packet deep extraction, spec §3 locked decisions

---

## 1. V0 inventory (verified on the live VPS, 2026-07-07 evening)

### Runtime
- Host: Ubuntu, python3 3.12.3, Docker 29.6.1, 71G disk free, 7.8G RAM (5.8G available), node v22.23.1.
- Caddy at `/home/chowmesadmin/lab-judge/Caddyfile` serves: ci.chowmes.com → 127.0.0.1:8662 (CI dashboard, live HTTP 200), plus scout/prism/prism2/scratchpad/umami/judge sites.
- Hermes container (`hermes`): python 3.13.5 (venv `/opt/hermes/.venv`), node present.
- Claude Code CLI **already installed on host** (`/usr/bin/claude`, v2.1.195) but **auth expired** ("Not logged in", creds file dated 2026-07-01). Needs `CLAUDE_CODE_OAUTH_TOKEN` minted by Arijit (`claude setup-token`) — the only human step.
- Security flag (out of scope, log it): a python3 process listens on 0.0.0.0:4719 — identify and localhost-bind it later.

### V0 CI system (two layers)
1. **Skill monolith** (the running daily/weekly): container path `/opt/data/knowledge/obsidian/MyOS/Projects/Competitive Intelligence/skills/competitive-research/` — `ci_core.py` (171KB, hotfixed 2026-07-07, backup `.bak-20260707`), `daily-research-run.py`, `weekly-review.py`, Hermes cron (daily 09:00 ET, weekly Sun 09:00 ET) → Telegram 6789423537.
2. **Structured repo** (partially built, newer thinking): container path `/opt/data/apps/algolia-competitive-intelligence` — `packages/ci-core/` (engine + source registry + tests + report renderers), `workers/` (daily/weekly/dashboard runners), `apps/dashboard/` (static seed), `docs/`. README: "CI Collector Router v1 is live on Chowmes."

### V0 database (`ci.sqlite`, 3 duplicate copies — reconcile at migration)
10 tables. Key row counts: sources 43, snapshots 351, semantic_facts 13, semantic_deltas 86, synthesis_runs 12, report_index 12, bot_deliveries 12, source_health_events 351, **signals 0, action_items 0** (all history — the promotion pipeline never populated them; hotfix addresses the promotion path, first live rows expected next 09:00 run).

### V0 collection shape
`raw/<date>-v2-collection.json`: `{date, db_path, sources_loaded, direct:{snapshots, signals, errors, signal_ids, semantic_facts, semantic_deltas}, monitors:{}, search:{}, errors:[]}` — monitors/search inert (`--skip-search --skip-monitors`, parallel-cli unauthenticated).

### Postgres
None running. PRISM's postgres:16-alpine container exists but stopped. Umami runs its own postgres:15.

---

## 2. Architecture decisions (Gate 0)

### D1. Database: dedicated Postgres 16 container, `cios` database
- Spec demands `CIOS_DATABASE_URL`, multi-tenant isolation, and 40+ interrelated tables — beyond healthy SQLite use.
- New docker-compose service (`cios-postgres`, postgres:16-alpine, localhost-only port), NOT shared with PRISM's stopped container (independent lifecycles; PRISM is another product).
- Tenant isolation: `tenant_id NOT NULL` on every tenant-scoped table + Postgres **RLS policies** per tenant, enforced at the connection level (SET app.tenant_id). Application-layer checks are not sufficient alone.
- V0's `ci.sqlite` stays untouched (V0 keeps running until Gate 6 cutover); a one-time migration script imports sources/snapshots/deltas history into the Algolia tenant at Gate 2.

### D2. Schema reconciliation (the deep-read caught these; fix at Gate 1/2 DDL time)
1. **Add `tenant_id` to every table** the data-model spec left unscoped: sources, source_scan_runs, source_observations, source_candidates, competitor_scan_rollups, intel_fetch_runs, source_snapshots, raw_findings, all semantic/claims/thesis/content tables, quality_reviews, false_negative_audits, learning_events, improvement_queue, action_items, bot_deliveries, dashboard_state, suppressed_diagnostics, content_recommendations, weekly_content_plan. (Spec contradiction: channels doc says "every table tenant_id", data-model doc omitted it on ~25 tables.)
2. **Define the 6 missing tables** referenced but never specified: `source_health_events`, `content_traction_signals`, `content_plan_reviews`, `groups`, `group_role_mappings`, `reports` (V0's `report_index` is the model for `reports`).
3. **Name fix:** `model_provider_configs` (data-model) vs `tenant_model_provider_configs` (channels doc) → use `model_provider_configs` WITH `tenant_id`.
4. `*_ids` array fields → JSONB initially, with CHECK non-empty where the invariant demands evidence; promote hot paths to join tables only when queries need it.
5. `permissions` stays global (catalog); `roles` tenant-scoped — matches RBAC intent.

### D3. Claude provider: `claude -p` adapter (spec §10)
- CLI already on host; needs fresh auth. Adapter runs ON HOST (not in container) via a thin localhost HTTP shim (`cios-claude-shim`, FastAPI, 127.0.0.1 only) so container code can call it; alternative (docker exec from container) rejected — wrong direction of trust.
- Env: `CLAUDE_CODE_OAUTH_TOKEN` (add to env-spec; not an API key). Adapter backs off on 429 (shared Max subscription limits).
- Router aliases per env-spec (`CIOS_MODEL_DEFAULT/STANDARD/HIGH/IMAGE`) extended: `CIOS_MODEL_JUDGMENT=claude-opus` (synthesis/thesis/quality/FN-audit), providers `google,anthropic-cli` allowed. One routing config file, no model ids in skills (constraint #4).

### D4. Code home: the CI-OS repo (this repo) is canonical
- New code lives here under a real src tree; deployed to VPS at `/opt/data/apps/cios/` (container-visible path) via git. The existing `algolia-competitive-intelligence` repo is a donor (see reuse), not the future home — it predates multi-tenancy and the Argus skill architecture.
- Layout:
```
CI-OS/
├── src/cios/
│   ├── platform/      # tenants, identity, ACL, audit, channel + model adapters, router
│   ├── ledger/        # competitors, sources, observations, scan runs, rollups
│   ├── collect/       # intel collector, exec speech scanner (V0 extraction logic migrated here)
│   ├── brain/         # semantic synthesizer, claim ledger, thesis engine, quality reviewer, FN auditor
│   ├── learn/         # learning loop, improvement queue
│   ├── deliver/       # action router, delivery commander, channel renderers (telegram-rich, email)
│   └── db/            # migrations (alembic), RLS policies, session/tenant context
├── skills/            # Argus SKILL.md packages + evals (official skill-creator workflow)
├── apps/dashboard/    # cockpit (renders from semantic state)
├── workers/           # cron entrypoints (thin; call src/cios)
├── tests/
└── deploy/            # docker-compose (cios-postgres, cios-claude-shim), Caddy snippets, runbooks
```

### D5. Scheduling stays Hermes cron
- Hermes-internal cron (proven, delivering daily since 06-30) triggers thin workers. No new scheduler. Agent-backed cron only for judgment jobs per Hermes config spec.

---

## 3. Reuse-vs-rebuild decision (constraint: Reuse-First)

| Component | Verdict | Why |
|---|---|---|
| V0 extraction/collection logic (post-hotfix `ci_core.py` collectors) | **REUSE — migrate** into `src/cios/collect/` | Just root-fixed and proven (39 snapshots/day, 8 signals dry-run); rewriting invites regressions |
| V0 Algolia HTML template + `render_html_report` | **REUSE** for email + reports | Brand-correct, works; Telegram-rich gets its own renderer |
| V0 Gemini wiring + preflight | **REUSE** as the `google` provider adapter's seed | Healthy key, working call path |
| Hermes cron + Telegram gateway | **REUSE** unchanged | Delivering reliably since 06-30 |
| `algolia-competitive-intelligence` repo (`packages/ci-core`, workers, dashboard seed) | **DONOR** — harvest source registry, report renderers, tests, runbooks; do not build on it | Single-tenant, pre-spec architecture; two parallel "ci-core"s would recreate the V0-vs-spec split this project exists to kill |
| `ci.sqlite` data (43 sources, 351 snapshots, 86 deltas, 13 facts) | **MIGRATE** into Postgres as Algolia-tenant history | Real evidence baseline; feeds Gate 4 eval fixtures |
| V0 monolith structure + quiet-day fallback + `bot_deliveries` "queued" writes | **RETIRE** at Gate 6 cutover | The rot this build replaces |
| ci.chowmes.com Caddy site + port 8662 | **REUSE** the domain; new dashboard app takes over the port at Gate 5 | Domain + TLS already live |

---

## 4. Gate execution plan (orchestration per gate)

Budgets are estimates, declared per guardrail #8; supervisor = main loop; kill condition per fan-out = all agents reported or 20 min.

- **Gate 1** (platform): schema DDL+RLS (T3 designs, T2 implements), identity/ACL module + tests (T2), channel adapter interface + telegram allowlist (T2), model router + claude-shim + google adapter (T2), verify fan-in (T1 test-runs + T3 review). ~5 agents / ~200k tokens.
- **Gate 2** (ledger+hunter): DDL (in Gate 1 migration), source-hunter skill via skill-creator with evals (T2 build, T1 eval-run, T3 grade), V0 sqlite migration script (T2). ~4 agents / ~150k.
- **Gate 3** (collect): migrate V0 collectors (T2), exec-speech scanner skill (T2), eval runs (T1). ~3 agents / ~120k.
- **Gate 4** (brain — Claude Opus via shim): synthesizer/claim-ledger/thesis/quality-reviewer/FN-auditor skills (T3-heavy), then **adversarial verify panel**: planted-miss test, refute-panel on sample signals, evidence-URL audit (3 verifiers). ~7 agents / ~350k. **BLOCKED until `claude -p` auth fixed.**
- **Gate 5** (learn+dashboard): learning loop (T2), dashboard from semantic state (frontend-builder flow, Luxury Editorial per accepted direction) (T2-T3). ~4 agents / ~200k.
- **Gate 6** (delivery): action router, delivery commander, telegram-rich (`parse_mode=HTML`), email digest, `bot_deliveries` true-state fix, then **V0 cutover** after parity check. ~4 agents / ~150k.
- **Gate 7** (E2E): 3-tenant runs, tenant-bleed test, FN-audit green, fresh-session voice check. ~4 agents / ~150k.

Rough total ≈ 31 agents / ~1.3M tokens across the whole build (spread over gates, each gate reported before the next).

---

## 5. Gate 0 exit report

- **Built:** this plan; V0 inventory (above, from live VPS reads); reuse decision (§3); schema reconciliation list (§2-D2).
- **Verified:** VPS runtime facts read directly (versions, ports, schema dump verbatim, row counts); ci.chowmes.com HTTP 200; `claude -p` tested live → "Not logged in" (auth expired, creds 2026-07-01).
- **Failed / open:** `claude -p` auth — **needs Arijit: run `claude setup-token` locally, hand over token; we install as `CLAUDE_CODE_OAUTH_TOKEN` on the VPS and re-verify.** Blocks Gate 4 only.
- **Safe to continue:** YES for Gates 1-3 (no Claude dependency). Gate 4 blocked on the token.
