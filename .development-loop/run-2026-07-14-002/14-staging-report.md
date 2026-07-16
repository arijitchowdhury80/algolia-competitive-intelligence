# Staging Report

Status: FAILED CANDIDATE RETAINED; DEMAND-PATH REORDER AUTHORIZED

Draft package PR #1 targets the dedicated `ci-os-package-main` source branch.
Its GitHub static/unit and Postgres integration checks pass. The PR remains a
draft, and this automated evidence does not authorize the staging sequence.

## Verified current production baseline

Read-only inspection on 2026-07-14 confirmed:

- `cios` exists as UID 997, primary group `cios`, supplementary group `hermes`.
- `/opt/cios/app` is owned by `cios:cios`.
- `ci-dashboard-static.service` is active on `127.0.0.1:8662`.
- The legacy service runs as root with no memory, CPU, or task limit.
- Its document root is the retained mutable dashboard directory under the
  Algolia Competitive Intelligence package.
- `/opt/cios/public-store` does not yet exist.

No production file, process, service, Caddy route, firewall rule, credential,
Hermes core file, or public response changed during inspection.

### Baseline revalidation

A second read-only inspection at `2026-07-14T10:50Z` found no staging drift:

- `ci-dashboard-static.service` remains active as `root:root`, serving the
  retained mutable dashboard root on `127.0.0.1:8662` with unlimited memory
  and CPU and `TasksMax=9483`.
- `cios-static.service` is not installed or active, and
  `/opt/cios/public-store` remains absent.
- Loopback and public root responses are both HTTP 200, 394,895 bytes, and
  SHA-256 `280b721bb5276394abac2d4ea1547c1883d1b2b6e94a993a919d4b316dff5db7`.
- Caddy runs in the `caddy` Docker container, not as a host systemd unit. Its
  active config is mounted from `/home/chowmesadmin/lab-judge/Caddyfile`; the
  `ci.chowmes.com` route reverse-proxies only to `127.0.0.1:8662`, and
  `caddy validate` reports `Valid configuration`.
- The local candidate archive still hashes to
  `0e83a836fe75689e5ceac1f89fe02337458dc7e65f87e94031e452a6a7ee9298`,
  and candidate tree `47d3bd7^{tree}` remains
  `ef09b04cfe9a0e4d5b3cf5f7008693a10b3a14eb`.

The staging sequence therefore requires no Caddy edit or reload. Cutover and
rollback change only which loopback static service owns port 8662.

## Executed staging evidence

Arijit approved the bounded Stage 12 sequence on 2026-07-14. Execution stopped
before the static-service cutover because the sibling store never produced a
complete decision generation.

### Installation and rollback baseline

- Root-only rollback snapshot:
  `/opt/cios/staging-backups/20260714T134100Z`.
- Legacy unit SHA-256:
  `ef8ec58d139456b09c1cc7612263f91031b865bf5d4c5a35c8824ecf61a90f71`.
- Legacy loopback and public root SHA-256:
  `280b721bb5276394abac2d4ea1547c1883d1b2b6e94a993a919d4b316dff5db7`.
- Candidate archive was reverified on the VPS before extraction and installed
  at `/opt/cios/releases/47d3bd7`.
- Off-route and mounted package preflights both passed in delegated systemd
  cgroups.
- `/opt/cios/public-store` was created as `cios:hermes` mode `2750`; the
  release, store, backup, and diagnostic evidence remain retained.

### Attempt 1: runtime dependency and package-mode failures

- Queue request: `ea34d298445944edb8ab3cae9022b81c`.
- Terminal result: exit code 2 before publication.
- Sanitized cause: the localhost Claude shim was unhealthy because its shared
  virtualenv executable was mode `0750` and inaccessible to `cios-shim`.
- `ExecStopPost` also returned `203/EXEC` because
  `deploy/cios-run-finalize.sh` was archived without an executable bit.
- The shim was repaired with a dedicated `cios-shim` virtualenv while the old
  link was preserved. Its real health check then returned `healthy=true` on
  `127.0.0.1:8663`.
- Candidate runtime scripts were corrected to their documented deployment
  modes before the changed-hypothesis retry.

### Attempt 2: healthy execution, truthful diagnostic publication

- Queue request: `f9a040a200384c3799ce7fed233ecfd4`.
- CI-OS run ID: `cios-20260714T135025Z-1989449`.
- Hermes wrapper result, runner main process, and finalizer: exit code 0.
- Package contract verdict: pass and run-bound.
- Publication integrity verdict: pass and run-bound.
- Demand source gate: fail, with zero processed demand rows and no ready GA4
  or manual export.
- Public run status: `blocked_on_evidence`, `publish_status=blocked`, and
  `public_dashboard_updated=false`.
- The immutable store correctly promoted only
  `latest-diagnostics -> diagnostics/cios-20260714T135025Z-1989449`; it did not
  create a `current` decision pointer.

This is correct product behavior, but it cannot satisfy the Phase 2 exit gate
or support the static-service cutover. The approved plan requires one fresh,
complete decision run in Phase 2 while simultaneously locking GA4/Looker work
until Phase 2 passes. Creating a false `published` status, migrating stale
legacy bytes as fresh evidence, or serving a router with no `current` pointer
would lower the gate and is prohibited.

### Rollback result

- `/opt/cios/app` is again the original
  `/root/.hermes/apps/cios` bind mount.
- The pre-staging `/etc/cios-env`, `/root/.hermes/cios-env`, and `/etc/fstab`
  bytes were restored; publication-v2 flags are absent.
- `ci-dashboard-static.service` was never stopped. Loopback and public hashes
  remain the exact legacy baseline.
- `cios-runner.path`, `cios-admin.service`, and the repaired
  `cios-claude-shim.service` are active and localhost-only.
- Restart exposed a second latent package defect: `cios-admin.service` lacked
  `PYTHONPATH=/opt/cios/app/src`. A minimal systemd drop-in restored the admin
  to HTTP 200. The versioned unit and preflight contract are being corrected
  under TDD.

Candidate `47d3bd7` is not eligible for another staging attempt. Its immutable
tag and files remain evidence; a new candidate must include the executable and
admin import-path fixes and pass CI before use.

## Human decision: bring the demand input forward

On 2026-07-14 Arijit authorized read-only access to the private Algolia Looker
Studio report and manual CSV export so the real demand input can be supplied
before the final Phase 2 publication proof. This is an explicit, narrow
reordering of the Phase 4 demand-input dependency. It does not authorize Scout,
GA4 credential setup, report editing, production UI work, Caddy or firewall
changes, or Hermes core changes.

The authenticated report was inspected without editing it. The selected
current window was 2026-07-07 through 2026-07-13 and the comparison window was
2026-06-30 through 2026-07-06. Raw exports were saved only in the untracked
`data/` directory of the separate local CI-OS checkout and must not be committed
to GitHub. Verified raw evidence:

- `algolia-looker-page-metrics_2026-07-07_2026-07-13.csv`: 100 parsed
  data rows; SHA-256
  `d61c96717f3cb3682baf0c7c2da47b6ca31a41989608c89ff42df8904c50149c`.
- `algolia-looker-landing-page-metrics_2026-07-07_2026-07-13.csv`: 100
  parsed data rows; SHA-256
  `2d641d6071084a05b6a0cfb8a64b3b015f977278b24af429be9c24c097ce2cee`.
- `algolia-looker-campaign-metrics_2026-07-07_2026-07-13.csv`: 100 parsed
  data rows; SHA-256
  `666783216400646be80d7f7a800a3d5db02f7881db9449d9a61652cc5094b48e`.
- `algolia-looker-campaign-metrics_2026-06-30_2026-07-06.csv`: 100 parsed
  data rows; SHA-256
  `8b8444de3f8af844712f402167df30a785771d76555eff13356859368d019124`.
- `algolia-looker-landing-page-device-sessions_2026-06-30_2026-07-06.csv`:
  10,558 parsed data rows; SHA-256
  `ad27f9db658c519035e9e6f6dfd969dba9559c9bd84668d1c4608ee62bbb0243`.

The package `.gitignore` excludes `data/`; private tenant exports are not
package inputs and cannot enter a release through a broad Git add.

The eligible minimum intake row is the current `/products/ai-search` page:
786 sessions in the selected seven-day window, mapped explicitly to the active
Argus topic `Agent Search`. The prior landing-page export contains 751 sessions
for the same path, but it uses a different chart dimension from the current
page export. It is corroborating evidence only; CI-OS must not calculate or
publish a synthetic week-over-week change from unlike dimensions. Coverage is
therefore one directly mapped active topic with a real nonzero metric and
explicit unknown coverage for the remaining topics.

Package-owned local validation against the live Argus plan passed before any
upload: `status=prepared`, `ready_count=1`, `normalized_row_count=1`,
`skipped_row_count=0`, `duplicate_row_count=0`, coverage `covered`, one matched
plan topic, zero missing topics, and zero off-plan rows. The normalized source
fingerprint is
`5ce535e8db8cce5d3decebd6c509706b065b60b6cc3f37ae1b1aba5bb6f79352`.
The focused importer and demand fast-lane suite passed `32 passed`.

Fresh-candidate local verification also passed: the default suite reported
`1321 passed, 3 skipped, 23 deselected`; Ruff passed; Pyright reported zero
errors, warnings, or information findings; strict MyPy passed; and the Hermes
package contract passed. The workstation-wide `pip check` still reports two
unrelated pre-existing `python-jobspy` constraints against the globally
installed NumPy and regex versions. No package dependency changed in this
slice; the clean GitHub Actions environment remains the authoritative package
dependency gate before a new candidate can be tagged or installed.

Candidate `47d3bd7` remains failed and ineligible. The next attempt must use a
fresh immutable candidate containing the package fixes after that tag, import
the verified demand row through the package-owned intake path, and rerun every
remaining Stage 12 gate before public cutover.

## Candidate 707fee5 staging result

Candidate `707fee5` was built from commit
`707fee54de33cf794e5dba2f0d4b1716b6371389`, tagged
`ci-os-phase2-candidate-2026-07-14-r2`, and passed GitHub Actions run
`29348949927`. Its archive SHA-256 was
`176d003fb7abdc269ad88f5241c2a1fb924ebae739c35417d9037c009cda200b`.
Off-route and mounted package preflights passed as `cios`. The real demand
source prepared one ready and normalized `Agent Search` row with no skips or
off-plan rows; against the complete 12-topic live Argus plan the accurate
coverage state is `partial_coverage`, with the other 11 topics explicitly
missing.

The candidate app mount and Hermes-to-cios queue boundary were activated while
`ci-dashboard-static.service` remained active and the public root retained its
legacy hash. Hermes request `332b3a51ef0a4c8ca4eb032a28d0f5b8` then failed
before run creation because the fresh `out/` directory lacked the
`.cios-output-dir` safety marker. No decision pointer moved and no public route
changed. Candidate `707fee5` is failed and ineligible for retry.

TDD now requires `cios-host-permissions.sh` to initialize that marker with
`cios:hermes` ownership and mode `0660`; the package verifier independently
enforces all three invariants. Local verification passed `1322 passed, 3
skipped, 23 deselected`, scoped Ruff, Pyright, strict MyPy, and package
preflight. The next staging attempt requires a fresh immutable candidate from
this post-`707fee5` fix and a clean GitHub CI run.

## Candidate 1ea8c68 staging result

Candidate `1ea8c68`, tagged `ci-os-phase2-candidate-2026-07-14-r3`, passed
GitHub Actions run `29350795379`. Archive SHA-256 was
`d4a48c2cb7936e322d4d6f4011876eb14b0496e191654adffcf52c32405081bd`.
Its off-route and mounted package checks passed, the output marker was
`cios:hermes` mode `0660`, and the real Hermes-owned run crossed to the `cios`
runner without timeout, orphan work, or public route change.

Run `cios-20260714T164836Z-2116876` generated a watch decision with product,
conversation, and one audience-demand signal present. Because the current
product scan regenerated the Argus topic plan, the truthful `Agent Search`
signal remained processed but unmapped; the decision correctly retained an
incomplete-coverage blocker. Publication then failed closed on internal local
paths in the semantic dashboard JSON. The exact validator reason was
`unsafe artifact data/semantic-dashboard.json: local_path`. No decision
generation was installed, `current` remained absent, and the legacy public
service stayed active with its original hash.

TDD now makes `publish_generation.py` create temporary, local-path-redacted
copies of JSON artifacts while preserving the internal runbook source files.
The immutable scanner remains authoritative and still rejects unsafe text,
secrets, credentials, malformed files, and symlinks. Local verification passed
`1322 passed, 3 skipped, 23 deselected`, focused publication `25 passed`, scoped
Ruff, Pyright, strict MyPy, and package preflight. A fresh candidate and clean
GitHub CI run are required before the next Stage 12 attempt.

## Proposed bounded staging sequence

1. Install immutable Phase 2 candidate `47d3bd7` under
   `/opt/cios/releases/47d3bd7` after verifying archive SHA-256
   `0e83a836fe75689e5ceac1f89fe02337458dc7e65f87e94031e452a6a7ee9298`,
   then point `/opt/cios/app` at it as `cios`.
2. Back up the exact legacy `ci-dashboard-static.service` unit and record the
   legacy root plus public response hashes. Do not remove either rollback target.
3. Create `/opt/cios/public-store` as `cios:hermes` mode `2750` and run package
   preflight as `cios`.
4. Enable `CIOS_PUBLICATION_V2=1` with the exact package version, trigger one
   real Hermes-owned CI-OS run, and validate the sibling store before changing
   the live route.
5. Probe the candidate `served/` root on a temporary loopback port, then stop
   the probe.
6. Stop only `ci-dashboard-static.service`, install/start `cios-static.service`
   on the same loopback port, and leave Caddy/firewall unchanged.
7. Verify process user/group, cgroup limits, root and `/v2` hashes, public-safe
   status, package/publication/click/launch verdicts, and Playwright desktop and
   mobile journeys.
8. Execute the approved stale/mismatched/partial/symlink/path/secret defect
   matrix and verify every case fails without moving the decision pointer.
9. Execute the rollback drill below, verify the legacy public response, then
   return to the candidate only if every rollback check passes.

## Rollback drill

Trigger rollback on any failed health, ownership, route, hash, click, launch,
or process-limit check:

1. Stop and disable only `cios-static.service`.
2. Restore the backed-up legacy unit if its bytes changed.
3. Start `ci-dashboard-static.service` against the retained legacy root.
4. Verify `127.0.0.1:8662`, `https://ci.chowmes.com/`, service user/root,
   response hashes, and Caddy health.
5. Leave the failed immutable release and sibling store intact for diagnosis;
   do not delete evidence during rollback.

## 2026-07-16 Stage 12 replay addendum

Candidate `1cdc816` was installed as the active `/opt/cios/app` bind mount and
one Hermes-owned run completed as `cios-20260716T054431Z-3718076`. Package and
publication integrity verdicts both passed with exit code `0`; publication
store `current` points at that run. The public route was not cut over:
`ci-dashboard-static.service` stayed active and `cios-static.service` stayed
inactive.

Two launch-readiness false negatives were isolated with live artifacts and fixed
locally under TDD:

- Processed demand with zero rising topics is now classified as
  `processed_no_rising_demand` coverage while the demand plane remains
  `processed`, instead of incorrectly blocking as `processed_unmapped_demand`.
- `limited_by_product_surface_evidence` now satisfies product-reality presence
  when the plane has product proof and explicitly does not block action.

Verification:

- Targeted red/green regressions passed.
- Focused readiness/data-plane/launch tests: `35 passed`.
- Ruff over changed scripts/tests: pass.
- Full suite: `1325 passed, 3 skipped, 23 deselected`.
- Pyright phase-2 project: `0 errors, 0 warnings, 0 informations`.
- Strict MyPy over `src/cios/publication`: success.

Local replay of the live run after the fixes shows these gates passing:
audience demand processed, product reality present, product extraction
complete, dashboard click validation passed against copied publication bytes,
Hermes package contract passed, publication integrity passed, publication
manifest bound, public safety passed, source coverage complete.

The replay still fails launch readiness for two remaining reasons:

1. Public status is `limited_by_evidence`, not `published`, because the product
   muscle queue still has confidence-limiting matrix cells. This belongs to the
   documented Phase 3 product muscle scope unless the Phase 2 gate is amended to
   accept a limited diagnostic decision surface.
2. Source failure budget is `1` while the launch gate allows `0`. The failed
   active source is Community forum RSS
   `https://old.reddit.com/r/ecommerce/.rss`; read-only probes showed Reddit
   can alternate between HTTP 200 and HTTP 429 depending on rate limiting, so
   this requires either source repair/retry policy or an explicit degradation
   decision.

Phase 2 still cannot be called passed. The corrected publication boundary is
working, but final launch readiness remains blocked by a real source-degradation
decision and a phase-order conflict with Phase 3 product muscle confidence.

## 2026-07-16 candidate 12dfb08 staging result

Candidate `12dfb08`, commit
`12dfb0855f2dd0fc41d34273c2dc81e794ba8c63`, was created after the `ec6ad5e`
staging mount exposed a real host-permissions defect. The candidate fixes the
immutable-release staging path by adding `CIOS_MANAGE_APP_BIND=0`, preventing
the host permissions script from re-adding the stale `/root/.hermes/apps/cios`
app bind when `/opt/cios/app` is already mounted to a release. It also
explicitly restores the queue boundary: `/opt/cios/app/run-queue` is
`cios:hermes` mode `3770`, while `.state` remains `cios:cios` mode `0700`.

Verification before staging:

- Focused deploy/package tests first failed red, then passed: `89 passed`.
- Expanded deploy/package/cgroup suite: `101 passed`.
- Full local suite: `1327 passed, 3 skipped, 23 deselected`.
- Ruff over changed Python files: pass.
- Pyright phase-2 project: `0 errors, 0 warnings, 0 informations`.
- Strict MyPy over `scripts/verify_hermes_package_contract.py`: success.
- Local archive SHA-256:
  `064d714e6fdd01c91ed6752f8b6def4690c57d092326369e77c9d2e8a3bf263f`.
- Local archive package preflight: pass.
- GitHub Actions run `29477068248`: success.

VPS staging:

- Uploaded archive SHA-256 matched
  `064d714e6fdd01c91ed6752f8b6def4690c57d092326369e77c9d2e8a3bf263f`.
- Installed off-route at `/opt/cios/releases/12dfb08`; off-route package
  preflight passed as `cios`.
- Flattened the prior stacked `/opt/cios/app` bind mounts and mounted only
  `/opt/cios/releases/12dfb08` plus the run-queue bind.
- Cleaned `/etc/fstab` to the three expected CI-OS entries:
  `/opt/cios/releases/12dfb08 /opt/cios/app`,
  dashboard public bind, and
  `/root/.hermes/apps/cios/run-queue /opt/cios/app/run-queue`.
- Mounted preflight passed, `cios-admin` health returned `{"status":"ok"}`,
  `cios-runner.path` was active, `ci-dashboard-static` remained active, and
  `cios-static` remained inactive.
- A direct `hermes` write probe to `/opt/cios/app/run-queue` succeeded.

Hermes-owned staging run:

- Queue request: `2652fb61a28848f2afc71ecd01e2d692`.
- CI-OS run ID: `cios-20260716T064031Z-3761895`.
- Queue result: `0`; `.state/active-run` cleared.
- Package contract verdict: pass.
- Publication integrity verdict: pass.
- Public-store `current` points to
  `/opt/cios/public-store/releases/cios-20260716T064031Z-3761895`.
- Public status in the sibling store is `publish_status=published`,
  `status=limited_by_evidence`, and `public_dashboard_updated=true`.
- Legacy public loopback on `127.0.0.1:8662` remained HTTP 200 with SHA-256
  `280b721bb5276394abac2d4ea1547c1883d1b2b6e94a993a919d4b316dff5db7`;
  no public route cutover occurred.

Click validation was run locally against an SSH-copied tarball of the exact
staged sibling-store `current` bytes. Bundle SHA-256 was
`83a7a92c5b92b3ef7ade73a3dea32ab961607af30b90b6452f99c4eb6bec85be`.
The validator passed structure, nav targets, timeline, semantic layer,
priority selection, brief routing, appendices, and 390px, 768px, and 1280px
viewports.

Launch readiness still failed for two real blockers:

- `public_status_publishable=false` because the public status is
  `publish_status=published status=limited_by_evidence`.
- `source_failure_budget_ok=false` because `failed_source_count=1` and the
  gate currently allows `max_failed_sources=0`; the failing active source in
  this run was Community forum RSS
  `https://old.reddit.com/r/ecommerce/.rss`, returning HTTP `403`.

All other launch-readiness checks passed: audience demand processed, product
reality present, product extraction complete, dashboard click validation
passed, package contract passed, publication integrity passed, manifest bound,
public safety passed, current-run status bound, and source coverage complete.

Phase 2 remains blocked. Public cutover is not authorized. The next explicit
human decision is whether to keep Phase 2 strict and repair the product/source
evidence blockers before cutover, or amend the Phase 2 gate to accept a
limited diagnostic decision surface and a documented source degradation budget.

## 2026-07-16 candidates f365d8b and bb79963 staging result

Candidate `f365d8b`, commit
`f365d8bbc408ed01878bdb83326e08d68a9d6db2`, fixed the run-health source
coverage accounting defect exposed by `cbff41b`: checked platform-policy
dispositions now count as disposed rather than failed. Verification:

- Focused source-coverage regressions: `6 passed, 118 deselected`.
- Phase 2 readiness/export suite: `159 passed, 1 skipped`.
- Full local suite: `1331 passed, 3 skipped, 23 deselected`.
- Ruff: pass.
- Pyright phase-2 project: `0 errors, 0 warnings, 0 informations`.
- GitHub Actions run `29480125505`: success.
- Archive SHA-256:
  `4d172a5a11495581e66912d21d96bd648d33450a17af28d4aee1e96dfea9824b`.

The `f365d8b` staging run used queue request
`fa248c4e66ed4c50b4bb5356078ec5c0` and run ID
`cios-20260716T074225Z-3816412`. The main daily runner completed source
coverage and product-market execution, but the post-run readiness export failed
when `export_argus_demand_readiness.py` attempted to create
`/opt/cios/app/data/looker/algolia` under a root-owned immutable release. This
was a release-permission contract gap, not a data-source or model failure.

Candidate `bb79963`, commit
`bb799633bfb47c960b6ebed47c7dca4c3be57edf`, fixes that gap by making
`deploy/cios-host-permissions.sh` provision `$APP/data` and `$APP/data/looker`
as `cios:hermes` mode `2775`, and by adding package-contract coverage so the
defect cannot recur silently. Verification:

- Targeted package/deploy tests: `3 passed, 88 deselected`.
- Package/deploy test suite: `91 passed`.
- Phase 2 readiness plus package-contract suite: `250 passed, 1 skipped`.
- Full local suite: `1333 passed, 3 skipped, 23 deselected`.
- Shell syntax: `bash -n deploy/cios-host-permissions.sh` passed.
- Ruff over changed Python tests/scripts: pass.
- Pyright phase-2 project: `0 errors, 0 warnings, 0 informations`.
- GitHub Actions run `29481810029`: success.
- Archive SHA-256:
  `813bf5a2d236dc82953751ca13f2ff0ceddabc3f3a567d8894194c0ed7200940`.

VPS staging for `bb79963`:

- `/opt/cios/app` is bound to `/opt/cios/releases/bb79963`.
- `/opt/cios/app/run-queue` is bound to
  `/root/.hermes/apps/cios/run-queue`.
- `/etc/fstab` points `/opt/cios/app` at `/opt/cios/releases/bb79963`.
- `cios-admin.service` is active and `http://127.0.0.1:8765/health` returned
  `{"status":"ok"}`.
- `cios-runner.path` is active.
- `ci-dashboard-static.service` remains active and `cios-static.service`
  remains inactive; no public route cutover occurred.

Hermes-owned `bb79963` staging run:

- Queue request: `f4dd3566cd4e4fdb9757d9494c124bfa`.
- CI-OS run ID: `cios-20260716T080213Z-3835332`.
- Queue result: `0`; `.state/active-run` cleared.
- Package contract verdict: pass.
- Publication integrity verdict: pass.
- Source coverage: `active_source_count=42`, `checked_source_count=42`,
  `failed_source_count=0`, `disposed_source_count=0`.
- Product extraction: complete.
- Audience demand: processed.
- Product reality: present.
- Public status: `publish_status=published`,
  `status=limited_by_evidence`, `public_dashboard_updated=true`.
- Product-muscle work queue: `work_item_count=39`, `blocking_count=0`,
  `limiting_count=39`.
- Product-muscle gap discovery: `candidate_url_count=89`,
  `validated_count=0`, `rejected_count=89`, `stored_candidate_count=0`.

Dashboard click validation was run locally against an SSH-copied tarball of the
exact generated `bb79963` run output. The generated cockpit was served as
`index.html` on localhost because the validator canonicalizes the supplied URL
as a route root. The click verdict is run-bound to
`cios-20260716T080213Z-3835332` and passed structure, nav targets, timeline,
semantic layer, quiet-run priority selection, brief routing, appendices, and
390px, 768px, and 1280px viewports.

Strict launch readiness for `bb79963` still fails:

- `public_status_publishable=false` because status is
  `publish_status=published status=limited_by_evidence`.
- `publication_manifest_bound=false` because the served manifest is not a final
  decision manifest while the run remains limited by evidence.

All other strict readiness checks pass after the refreshed package verdict and
click verdict: current public status, source coverage, source failure budget,
audience demand, product reality, product extraction, dashboard clicks, package
contract, publication integrity, and public safety.

Phase 2 remains blocked, but the blocker has narrowed. The earlier Reddit RSS
source failure is fixed. The immutable-release Looker data-root permission
failure is fixed. The remaining boundary is a human/product policy decision:
whether Phase 2 requires zero `limits_confidence` product-muscle work items
before cutover, or whether a controlled monitored pilot may publish with zero
blocking items and disclosed confidence-limiting follow-up work.

## Original human gate

Approval authorizes the bounded staging sequence, including backing up the
legacy service, creating the sibling store, one real Hermes CI-OS run, the
single static-service cutover, live Playwright verification, planted defects,
and the mandatory rollback drill. It does not authorize Caddy/firewall changes,
Hermes core edits, credential changes, data deletion, Scout/GA4 work, or a
launch-ready claim.
