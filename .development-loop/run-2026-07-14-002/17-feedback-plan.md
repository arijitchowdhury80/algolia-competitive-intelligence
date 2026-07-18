# CI-OS Phase 2 Feedback Plan

Date: 2026-07-17
Stage: Development-Loop Stage 14 Feedback
Pilot route: `https://ci.chowmes.com/`
Cutover run: `cios-20260717T130034Z-890867`
Package: `11dc7df`

## Cutover Summary

Arijit approved the Phase 2 controlled monitored pilot cutover on 2026-07-17.
The cutover did not change firewall rules, Caddy listeners, Hermes core,
credentials, or public ports. The only production route change was repointing
`ci-dashboard-static.service` from the legacy dashboard directory to the
publication store served tree:

- Before:
  `/root/.hermes/apps/algolia-competitive-intelligence/apps/dashboard/public`
- After:
  `/opt/cios/public-store/served`
- Backup:
  `/opt/cios/staging-backups/phase2-cutover-20260717T150029Z/ci-dashboard-static.service.before`

## First 15 Minutes

The post-cutover 15-minute window passed.

| Minute | Result |
| --- | --- |
| 0 | Public dashboard HTTP 200; publication manifest HTTP 200; run `cios-20260717T130034Z-890867`; status `published`; source coverage `42/42`, failed `0`; services active; no warnings/errors. |
| 2 | Same as minute 0. |
| 4 | Same as minute 0. |
| 6 | Same as minute 0. |
| 8 | Same as minute 0. |
| 10 | Same as minute 0. |
| 12 | Same as minute 0. |
| 15 | Same as minute 0; strict readiness rerun returned `status=pass`, `exit_code=0`, `blockers=[]`. |

Additional interaction validation:

- `scripts/validate_dashboard_clicks.py --url https://ci.chowmes.com/ --run-id cios-20260717T130034Z-890867`
  returned `PASS dashboard_click_validation`.
- Public served manifest SHA:
  `fbcb2ffd36f60f939dee1180d3b3216dec9eab57c3d32d93d604d183cf01d122`.
- Public latest status SHA:
  `7e15d686a0b8d5699282853af5c967f39fd515af62007ca946b263ecc60cd1dc`.

## 48-72 Hour Monitoring

Monitor from 2026-07-17 11:00 ET through at least 2026-07-19 11:00 ET, and
preferably through 2026-07-20 11:00 ET if any anomaly appears.

| Signal | Cadence | Pass Criteria | Rollback Trigger |
| --- | --- | --- | --- |
| Public route health | Hourly for first 6h, then every 6h | `https://ci.chowmes.com/` returns HTTP 200 with current served bundle | Non-200, wrong content length, stale legacy bundle |
| Run binding | Hourly for first 6h, then every 6h | `data/argus-latest-run-status.json` remains published and current-run bound | Run ID mismatch, stale status, `public_dashboard_updated=false` |
| Strict readiness | After each Hermes-owned run and at 24h/48h | `status=pass`, `exit_code=0`, `blockers=[]` | Any blocker |
| Source coverage | After each Hermes-owned run | Active equals checked plus disposed; failed remains `0` | Failed source count greater than `0` without explicit disposition |
| Dashboard interaction | At 24h/48h, and after next daily run | Click validator passes for public URL | Any failed navigation, brief route, appendices, or viewport check |
| Product caveats | After each Hermes-owned run | Phase 3 limiter caveats remain visible and nonblocking | Caveats hidden, `blocking_count>0`, or operator confusion |
| Logs | Hourly for first 6h, then every 6h | No new warnings/errors for CI static/admin/runner around public route | New service errors or repeated restarts |
| Public safety | After each Hermes-owned run | No secret, internal path, or private Looker export leakage | Any secret/path/private export leak |

## Feedback Collection

Capture the following before opening Phase 3 implementation:

- Does Arijit see the current July 17 dashboard on `https://ci.chowmes.com/`?
- Are the visible Phase 3 product-muscle caveats understandable rather than
  looking like a launch failure?
- Do named business teams have enough context to understand why no
  recommendation was promoted yet, given `recommendation_count=0`?
- Does the public surface clearly distinguish Product Reality, Competitor
  Conversation, Audience Demand, and Argus reasoning?
- Are the top next actions too technical for PMM/Product/Sales/Exec users?

## Iteration Triggers

Move into Phase 3 only after this feedback window has no rollback-triggering
findings or after any findings are recorded and accepted. Phase 3 should start
from the visible product-muscle limiter set, not by hiding or bypassing it.

Immediate rollback remains required if any run produces stale publication,
manifest mismatch, public safety failure, or a failed strict readiness gate.

