# CI-OS × Hermes Integration Study

Date: 2026-07-08
Author: architecture study (opus), assigned by Arijit via the product doctrine addendum
Status: study for review — no build decision taken
Measured against: `docs/planning/CI-OS-product-doctrine-2026-07-08.md` (the doctrine outranks this)

## Executive summary

The question is whether Hermes (NousResearch hermes-agent) and the V2 `cios`
codebase can become one product with one spine of execution, CI-OS being
Hermes's first flagship use case. The short answer: yes, and the original
CI-OS design already said so. `Argus-agent-operating-model.md` (2026-07-01,
line 8) states plainly that "Hermes provides execution, memory, review,
delivery, and the conversational layer." The V2 overnight build drifted away
from that: it stood up its own channel adapters, its own cron, its own model
router with a `claude-shim`, and its own identity layer, and now runs BESIDE
Hermes on the VPS rather than ON it. Most of that platform code is a
re-implementation of things Hermes already ships.

There is exactly one thing cios built that Hermes genuinely does not have:
an enterprise identity / ACL / multi-tenant plane (`src/cios/platform/identity/`
plus the `tenant_id` schema). Hermes is architecturally a single-user personal
agent — its "identity" is a Honcho model of one owner, and its isolation
primitive is a per-profile home directory (`~/.hermes/profiles/<name>`), not
role-based multi-tenant access control. That single gap is the whole reason a
naive "merge everything into Hermes" does not satisfy the doctrine's
sellable-multi-tenant-product requirement.

The recommendation is **Architecture A: Hermes as the runtime spine
(gateway, channels, cron, webhooks, agent loop, model routing, subagent
parallelism), cios as the domain brain plus the identity/product layer that
Hermes lacks.** Not a full dissolve-into-Hermes-skills (an enterprise SSO/RBAC
SaaS cannot live inside a personal agent's skill folder), and not
cios-as-core-with-Hermes-as-optional-frontend (that throws away Hermes's cron
and webhook engine, which are precisely the freshness enablers). Multi-tenancy
starts as one Hermes profile per tenant and only grows a cios-owned identity
plane above Hermes if the multi-tenant SaaS actually materializes.

On the freshness USP (signal-to-action in ≤30 minutes): Hermes already has the
machinery — a 60-second cron tick, pre-agent script injection with a `[SILENT]`
no-spam pattern, and an HMAC webhook adapter with a `deliver_only` mode that
pushes in sub-second time at zero LLM cost. cios built none of this. The honest
constraint is that most competitive-intelligence sources are pull, not push, so
"true webhook" freshness only applies to the few sources that emit events; for
everything else the realistic mechanism is a short-interval Hermes watch-loop
with change-detection and `[SILENT]`. That is still a large step up from today's
once-a-day batch, and it is a Hermes capability, not a cios one.

## 1. Capability overlap matrix

Ground truth: I read `src/cios/platform/{channels,identity,models}/`,
`deploy/claude-shim/`, and the goal spec; and Hermes `gateway/platforms/`,
`cron/scheduler.py`, `gateway/platforms/webhook.py`, `hermes_constants.py`
(profiles), and `providers/`.

| Concern | Hermes provides | cios V2 built | Verdict |
|---|---|---|---|
| **Channels / Telegram** | `gateway/platforms/`: telegram, signal, `whatsapp_cloud.py` (official Business Cloud API), `bluebubbles.py` (iMessage), qqbot, weixin, plus a generic inbound gateway. `ADDING_A_PLATFORM.md` = documented extension path. | `src/cios/platform/channels/` — adapter interface + `adapters/telegram.py` and `adapters/email_smtp.py` only. | **DUPLICATE. Hermes stronger** on breadth and inbound routing. cios's only net-new is `email_smtp` (Hermes email delivery unconfirmed) and an envelope bound to its identity layer. |
| **Scheduling / cron** | `cron/scheduler.py` (60s tick, file-locked), cron expressions + human intervals, pre-agent Python script injection, `[SILENT]` pattern, `blueprint_catalog.py`. | Own cron path (system cron / `scripts/daily_production_run.py`), the 09:15 UTC daily. | **DUPLICATE. Hermes stronger.** The goal spec (§7, line 147) *already says* keep "Hermes cron mechanics as the deterministic-job substrate." V2 drifted off it. |
| **Webhooks / near-real-time** | `gateway/platforms/webhook.py`: HMAC-validated inbound, per-route rate limit, idempotency cache, `deliver_only` sub-second zero-LLM push. `msgraph_webhook.py`. | None. cios has no inbound-signal webhook receiver. | **Hermes ONLY. This is the freshness enabler cios lacks.** |
| **Agent loop / subagents** | `run_agent.py` core loop, tool invocation, isolated subagent spawning, RPC scripts-call-tools. | `brain/` is a deterministic pipeline that makes LLM calls via the shim; no persistent agentic loop or subagent spawning. | **Different shape.** Hermes is the agent runtime; cios brain is a pipeline. cios does not need to own an agent loop. |
| **Model providers** | `providers/` model-agnostic abstraction, `hermes model` switch, per-automation model choice. | `platform/models/` router + `providers/claude_cli.py` → `deploy/claude-shim` (FastAPI wrapper around `claude -p`, 127.0.0.1:8663). | **PARTIAL DUPLICATE with a real root cause.** cios built the shim only because Hermes's OpenRouter/Nous keys were dead and Arijit chose the Claude Code Max subscription via CLI OAuth (goal spec §10). This is a *provider gap*, not an architectural need for a second router. |
| **Identity / ACL / multi-tenant / SSO** | Single-user personal model (Honcho "who YOU are"). Profiles = filesystem isolation (`~/.hermes/profiles/<name>`), NOT RBAC/SSO/tenant. | `platform/identity/` (`acl.py`, `resolver.py`) + `db/schema.sql` `tenant_id`, roles, permissions, channel-identity resolution. | **cios ONLY. Genuine gap in Hermes.** This is the enterprise-product plane and the reason for not fully dissolving into Hermes. |
| **Persistence** | `hermes_state.py` (SQLite: sessions, memory, user model, history). | Own Postgres: domain schema (competitors, sources, evidence, claims, theses, deliveries), multi-tenant columns. | **Different purposes, not a duplicate.** cios Postgres is the product's system of record; Hermes SQLite is agent-runtime state. |
| **Memory / learning loop** | Closed learning loop: skill self-creation/improvement, FTS session recall, memory nudges. | `learn/` — domain learning (source priority, retirement, candidate sources, improvement queue). | **Complementary, different domains.** Hermes learns how to operate; cios learns the CI domain. |

Bottom line: of cios's `platform/` layer, **channels and cron are pure
duplication, the model router is duplication forced by a provider gap, and only
identity/ACL/multi-tenant is irreplaceable.** The domain modules
(`hunter`, `collect`, `execspeech`, `brain`, `learn`, `delivery` action-routing,
`dashboard`, `db`, `migration`) are the actual product value and have no Hermes
equivalent.

## 2. Integration architectures

### A. Hermes = runtime spine, cios = domain brain + identity plane (RECOMMENDED)

Hermes owns execution: gateway/channels, cron, webhooks, the agent loop,
subagent parallelism, model routing. cios becomes (1) a domain library the
Hermes agent calls (as skills or an imported package) and (2) the
identity/tenant/dashboard product layer that wraps Hermes.

- **Code that moves/dies:** `platform/channels/` retired in favor of Hermes
  platforms (keep only the `email_smtp` adapter if Hermes lacks email). cios's
  own cron retired; pipeline stages become Hermes cron jobs. `platform/models/`
  demoted — ideally register Claude-CLI as a Hermes provider and route through
  Hermes; at minimum keep the shim as the single shared Claude backend.
  **Kept and elevated:** `platform/identity/` (the plane above Hermes),
  `brain/`, `hunter/`, `collect/`, `execspeech/`, `learn/`, `delivery`
  action-routing, `db/`, `dashboard/`.
- **Migration effort:** **M** (retire duplicated platform code, re-wire
  scheduling/delivery through Hermes; identity plane already exists).
- **Risk:** Medium. Main risks are Hermes single-user identity vs multi-tenant
  (handled by keeping cios's identity plane), Claude Max licensing for a sold
  product, and coupling to a fast-moving upstream (pin/vendor it).
- **Doctrine fit:** Strong. Keeps the intelligence layer domain-agnostic (brain
  never learns Hermes specifics), supports seller-side pre-seeding via
  profile-per-tenant (no feeder screen), and is sellable as one packaged
  product. Freshness and interactive chat both come "for free" from the spine.

### B. cios = product core, Hermes = optional conversational front-end

cios keeps its own runtime and Hermes is bolted on only as a Telegram/chat face.

- **Code that moves/dies:** almost nothing dies; you add a thin Hermes bridge.
- **Migration effort:** **S** to bolt on chat, but **L** in the long run because
  you keep maintaining cios's own cron, channels, and model plumbing forever.
- **Risk:** High *strategic* risk. You permanently carry the duplication the
  doctrine's "one spine" explicitly wants to end, and you forfeit Hermes's
  webhook/watch-loop freshness engine and cron script-injection.
- **Doctrine fit:** Weak on "one common spine of execution." Fails the stated
  packaging intent.

### C. Full merge — cios dissolved into Hermes skills/plugins

Everything becomes Hermes skills under an `argus` profile; no separate cios
service; Postgres accessed from skills.

- **Code that moves/dies:** `platform/channels`, `platform/models`, cios cron
  all die. Domain modules become skills. **Identity/ACL/multi-tenant has
  nowhere clean to live** — Hermes has no tenant/RBAC/SSO concept.
- **Migration effort:** **L**, and it strands the enterprise identity
  requirement.
- **Risk:** High. A sellable multi-tenant SSO/RBAC/SCIM SaaS cannot sit inside a
  personal agent's skill folder; per-profile filesystem isolation is not tenant
  isolation with audit and role scoping.
- **Doctrine fit:** Good for a single-tenant internal Algolia deployment, bad for
  the sellable multi-tenant product the doctrine demands. Viable only as the
  *interactive-chat slice*, not as the whole product.

## 3. Freshness USP (≤30-min signal-to-action)

What each architecture needs, and the honest constraint:

- **The enablers already exist in Hermes, not cios.** `cron/scheduler.py` ticks
  every 60s; a cron job can run a Python script *before* the agent and emit
  `[SILENT]` when nothing changed (no spam); `gateway/platforms/webhook.py`
  accepts HMAC-signed inbound events and, with `deliver_only`, pushes a rendered
  message in sub-second time at zero LLM cost. That is the ≤30-min path.
- **The honest limit:** competitive-intelligence sources are mostly *pull*
  (blogs, changelogs, careers pages, most social). True webhooks only apply to
  the few sources that emit events. For the rest, freshness = a short-interval
  Hermes watch-loop (e.g., every 10–15 min) with change-detection + `[SILENT]`,
  then trigger the cios brain for just that lane. This must be stated plainly —
  it is near-real-time change detection, not universal push.
- **Architecture A gets there directly** (the spine owns cron + webhooks).
  Architecture B would require cios to build a webhook/watch-loop engine it does
  not have. Architecture C also works technically but strands identity.
- **Pragmatic first step:** pick the single highest-velocity competitor lane,
  register a Hermes cron watch-loop at ~15-min interval with a diff script that
  returns `[SILENT]` unless the page changed; on change, invoke the cios
  per-lane synthesis and push via `deliver_only`. Prove one lane end-to-end
  under 30 minutes before generalizing. This is a Gate-sized task, not a rewrite.

## 4. Interactive Argus chat ("ask Argus about a competitor" over Telegram)

Architecture A (and its C-flavored chat slice) reach this fastest, because the
conversational gateway already exists in Hermes and **V0's `argus` profile is
already running there** (profiles live at `~/.hermes/profiles/<name>`; the task
brief confirms `argus` and `vulcan` profiles exist). The path: inbound Telegram
message → Hermes gateway resolves the session on the `argus` profile → the
agent calls a cios skill/package → the skill queries the cios Postgres
(evidence, theses, claims) → Argus answers in-voice with evidence links.

cios's own `platform/channels/adapters/telegram.py` is built for *outbound
delivery*, not interactive Q&A; building a full inbound conversational loop
inside cios would re-invent Hermes's gateway. So interactive chat is a strong
independent argument for Architecture A. The one gate to add: ACL must run
before the skill answers — the cios identity resolver maps the Telegram
identity to a canonical user/role, exactly as the channels/identity spec
already specifies (line 121: "Every inbound channel message resolves to a
canonical user and permission set before Argus or any skill runs").

## 5. Recommendation and phased path

**Adopt Architecture A.** Hermes is the single spine of execution; cios is the
domain brain plus the thin identity/tenant/dashboard product layer above it.
This is the original 2026-07-01 design intent, it ends the duplication the
doctrine wants gone, it inherits freshness and interactive chat from the spine,
and it preserves the one thing Hermes cannot provide (enterprise multi-tenant
identity). Reject B (permanent duplication, forfeits freshness engine) and
reject C as an end-state (strands enterprise identity), while using C's
technique — cios domain logic as Hermes skills — for the interactive-chat slice
inside Architecture A.

**Phased path from today's parallel-run state:**

- **Phase 0 — today.** V0 (Hermes skill + argus/vulcan profiles) and V2 (beside
  it: own venv, Postgres, cron, shim) run in parallel. Duplication is live.
- **Phase 1 — consolidate the spine (effort M).** Drive cios pipeline stages via
  Hermes cron jobs (goal spec already intends this); route delivery through
  Hermes delivery targets; retire cios's own cron and its telegram delivery
  adapter. Make the Claude backend single: register Claude-CLI as a Hermes
  provider if feasible, else keep the shim as the one shared Claude service both
  use. Keep cios's tier-routing *config* but back it by Hermes providers.
- **Phase 2 — freshness (effort S per lane).** Add Hermes short-interval
  watch-loops with change-detection + `[SILENT]` for the highest-velocity lanes;
  on change, trigger per-lane cios synthesis and `deliver_only` push. Prove one
  lane ≤30 min end-to-end.
- **Phase 3 — interactive Argus (effort M).** Expose cios brain as Hermes skills
  loaded into the `argus` profile; interactive Q&A over Telegram front-ended by
  the gateway, answered from Postgres, ACL-gated by the cios identity resolver.
- **Phase 4 — productize multi-tenant (effort M–L, only if the SaaS is real).**
  Profile-per-tenant for isolation; cios keeps the identity/ACL/SSO plane for
  enterprise IT; swap the personal Claude Max shim for a metered API key per
  tenant (goal spec §10 already anticipates exactly this). Do not resell a
  personal Max subscription — that is a licensing hard stop for a sold product.

**Risks to track:** (1) Hermes single-user identity vs enterprise multi-tenant —
mitigated by keeping cios's identity plane above Hermes. (2) Claude Max
subscription is fine internally but cannot back a sold product — must become
per-tenant metered keys at Phase 4. (3) Upstream Hermes churn — pin/vendor it,
treat as a dependency, not a fork. (4) Hermes is a large general runtime; carry
only what CI-OS uses.

## Provenance / unknowns

- Confirmed by direct read: cios `platform/{channels,identity,models}/`,
  `deploy/claude-shim/{README.md,shim.py,cios-claude-shim.service}`,
  `platform/models/providers/claude_cli.py`; Hermes `gateway/platforms/`
  (signal, whatsapp_cloud, bluebubbles, webhook, msgraph_webhook),
  `cron/scheduler.py`, `gateway/platforms/webhook.py`, `hermes_constants.py`
  (profile homes), `providers/`; goal spec §7/§10; operating-model line 8;
  channels/identity spec line 121; `hermes-already-has-routines.md`.
- **UNKNOWN (verify before building):** whether Hermes ships an email delivery
  target (cios `email_smtp` may be net-new); whether the current V2 09:15 UTC
  job runs under Hermes cron or a separate system cron on the VPS (goal spec
  intends Hermes cron; SESSION.md does not state which is live) — confirm on the
  VPS; whether Claude-CLI can be registered as a first-class Hermes provider vs
  keeping the standalone shim.
