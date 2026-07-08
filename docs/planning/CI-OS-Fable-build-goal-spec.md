# CI-OS — Fable Build Goal Spec (Handoff)

Date: 2026-07-07
Status: AUTHORIZED FOR BUILD — hand this to Fable as a long-running goal
Author: Claude (Opus 4.8) with Arijit
Supersedes the "do not build yet" pause in `CI-OS-handoff-2026-07-01.md`

---

## 0. How to read this document

This is the single entry prompt for Fable's long-running autonomous build of CI-OS.
It does three things:

1. Records the **verified ground truth** of what exists today (a running-but-off-spec V0 on Hermes) so Fable does not build from chat memory.
2. Records the **decisions** Arijit made on 2026-07-07 that lock scope, tenancy, models, channels, and sequencing.
3. Gives Fable a **gated build order** (core-first) with an acceptance bar per gate.

Fable MUST read, in this order, before writing any code:
1. `index.md`
2. `docs/planning/Argus-project-manifesto.md` (the full capability spec — do not restate, obey)
3. `docs/planning/CI-OS-project-overview.md`
4. `docs/planning/CI-OS-data-model-spec.md`
5. `docs/planning/CI-OS-channels-identity-acl-and-model-provider-architecture.md`
6. `docs/planning/Hermes-Argus-configuration-spec.md`
7. `docs/planning/Argus-agent-operating-model.md`
8. `docs/planning/CI-OS-evaluation-plan.md`
9. `../../Research/docs/Competitive-Intel-Proof.md` (the competitor teardown + copy/avoid list)
10. This document.

---

## 1. Verified ground truth (as of 2026-07-07, read directly off the live VPS)

There are THREE assets today, and they do not talk to each other:

**A. The spec (excellent).** The manifesto + planning packet in `docs/planning/` describe a genuinely differentiated CI operating system. This is the north star.

**B. A running V0 on Hermes (real, but off-spec and was silently broken).**
- It is NOT in this repo. It lives inside the `hermes` Docker container at
  `/opt/data/knowledge/obsidian/MyOS/Projects/Competitive Intelligence/skills/competitive-research/`.
- It is a monolithic `ci_core.py` (~171 KB) + `daily-research-run.py` + `weekly-review.py`, a `ci.sqlite` ledger, an Algolia-branded HTML template, and two Hermes-internal cron jobs (daily `0 9 * * *` ET, weekly `0 9 * * 0` ET) delivering to Telegram chat `6789423537`.
- **It was shipping an identical empty "quiet day" brief every day.** Root cause (now FIXED on 2026-07-07, see §2): the delta→signal promotion path never promoted any of the ~15 daily semantic deltas, so synthesis always hit the deterministic quiet-day fallback.
- Delivery was never dead — the pipe (cron → Gemini synth → Telegram) works. The intelligence was empty.
- Model path: Gemini (`gemini-2.5-flash`) direct, key healthy. OpenRouter + Nous keys are dead (credit) but only affect interactive Argus chat, not the digest.

**C. A dashboard mockup (paused mid-design).** `docs/mockups/ci-os-dashboard-app-mockup.html` — Luxury Editorial cockpit, Competitor Attention Barometer, "The eye behind the lenses" evidence section. Directionally accepted, not final.

**The core problem to solve is the disconnect, not a single bug.** V0 was a stopgap that rotted because it had no shared source of truth with the spec. Fable's job is to build the real CI-OS from the spec, adopt V0's working pieces (the collector, the Telegram delivery, the Algolia template, the Gemini synth wiring) where they are genuinely good, and retire the monolith.

---

## 2. What was already fixed on 2026-07-07 (do not redo; build on it)

A production hotfix was applied to the live V0 `ci_core.py` (backup: `ci_core.py.bak-20260707`). Three coupled defects were root-caused and fixed:
1. **Blob-vs-line extraction** — pages stored as one whitespace-collapsed blob yielded 1 line → 0 facts. Fixed by segmenting blobs on separators/sentences.
2. **Premature `break`** — extractor stopped at the first (static header) match. Fixed by scanning all segments + skipping generic headers.
3. **Narrow topic whitelist** — real search-domain content scored below the 0.65 publish gate. Fixed by broadening the on-topic whitelist (vector/neural/semantic search, RAG, MCP, merchandising, personalization). The 0.65 gate itself was left intact (still suppresses noise).

Dry-run on real 2026-07-07 data: **0 → 8 genuine signals** (Vertex AI agents/AlloyDB/MCP, Elastic org change + Forrester, etc.), brief 10,430 → 13,421 bytes, quiet-day branch no longer fires. **Live verification is tomorrow's 09:00 ET run** — Arijit must eyeball signal quality.

**Still open from the hotfix (carry into the build):**
- Telegram sends the brief as plain text + HTML attachment because the send layer (in Hermes core, not the scripts) does not pass `parse_mode="HTML"`. Making the *message itself* the rich brief is a known small change — owned by Gate 6.
- `bot_deliveries` never advances past `queued_for_telegram` — observability gap, owned by Gate 6.
- No Telegram user allowlist configured — owned by Gate 1 (identity/ACL).

---

## 3. Locked decisions (Arijit, 2026-07-07)

| Decision | Choice | Implication for Fable |
|---|---|---|
| **Sequencing** | Hotfix now + rebuild for Fable | Hotfix done (§2). Fable builds the real CI-OS as the replacement; keep V0 running until the rebuild reaches parity, then cut over. |
| **Tenancy** | Multi-tenant from day 1 | Build `tenants`/`users`/`identities`/`roles`/`ACL` foundation first. Algolia, Spryker, Amplitude are three tenants, not three forks. |
| **Model strategy** | Tiered by task, router-abstracted | Cheap tier (Gemini-flash / Haiku) for collection + extraction + classification. Claude Opus for semantic synthesis, thesis engine, quality review, false-negative audit. Everything behind the provider router so a tenant/eval can swap providers by config. |
| **Delivery surfaces** | Telegram (rich) + Web dashboard + Email + WhatsApp/iMessage | Priority order below. Telegram-rich + Email are near-term (email renders the HTML template that Telegram can't). Dashboard is the primary product surface. WhatsApp/Apple Messages are adapters behind the same delivery layer. |
| **Scope for Fable** | Full platform per spec, gated | Build the whole manifesto, but core-first (§5). Intelligence brain must be genuinely good before identity/channels/dashboard polish. |
| **Deadline** | Spec handoff by 2026-07-07 12:00 ET | This document IS the deadline deliverable. Fable's build runs after handoff. |

---

## 4. Pilot tenants + competitor sets (V1 DRAFT — Arijit to redline)

Three parallel pilots. Each is a tenant with its own competitor registry, source families, and branding. Argus voice is shared; the competitor sets differ.

**Tenant 1 — Algolia (search & discovery).** Arijit is the domain expert; this is the reference tenant.
Competitors: Coveo, Constructor, Bloomreach Discovery, Elastic/Elasticsearch, Lucidworks, Searchspring, Klevu, Google Vertex AI Search, Typesense, Meilisearch, Yext, Attraqt/Fredhopper. AI-search threat lane: Vertex, Perplexity/OpenAI-style answer engines.

**Tenant 2 — Spryker (composable / enterprise commerce).** Partner pilot.
Competitors: commercetools, SAP Commerce Cloud, Salesforce Commerce Cloud, Adobe Commerce (Magento), BigCommerce, VTEX, Elastic Path, fabric, Medusa, Shopify (Plus/Hydrogen), Emporix.

**Tenant 3 — Amplitude (product / digital analytics).** Partner pilot.
Competitors: Mixpanel, Heap (Contentsquare), Pendo, PostHog, Statsig, Snowplow, June, Adobe Analytics, GA4, Segment (Twilio), FullStory, Hotjar.

Source families per competitor (from manifesto §Phase 1): news, blog, case study, customer, pricing, product, launch, docs, changelog, release notes, partner, marketplace, community, resources/reports, analyst, LinkedIn, X, YouTube, GitHub releases, open-web discovery.

---

## 5. Gated build order (core-first) + acceptance bar

Fable stops at each gate, reports (built / files changed / tests run / verbatim verification / what failed / safe-to-continue), and does not advance on an unverified foundation.

**Gate 0 — Orientation.** Read the packet. Map the live V0 on Hermes (do not assume; SSH and confirm). Write the implementation plan + the data-contract diff between V0's `ci.sqlite` and the spec's data model. Decide reuse-vs-rebuild per V0 component, in writing.
Acceptance: plan on disk; V0 inventory on disk; reuse decision justified.

**Gate 1 — Platform foundation (multi-tenant).** `tenants`, `users`, `user_identities`, `roles`, `permissions`, ACL checks, channel adapter interface, audit events, model-provider adapters + router. Configure the Telegram user allowlist here.
Acceptance: three tenants seeded; an ACL check denies a cross-tenant read; the model router selects tier-by-task from config; audit rows written.

**Gate 2 — Ledger + source hunter.** `competitors`, `sources`, `source_observations`, `source_candidates`, `source_scan_runs`, `competitor_scan_rollups`; the `argus-source-hunter` skill (discover/validate/upsert/retire, never duplicate, retire after 3 missing days).
Acceptance: Algolia tenant's full competitor set has a source ledger; upsert-not-duplicate proven; a killed source is retired after the streak; coverage matrix renders.

**Gate 3 — Intel collector + executive speech.** `argus-intel-collector` (evidence only, no claims) + `argus-executive-speech-scanner`. Reuse V0's working collector where sound.
Acceptance: daily snapshots land for all active sources; fetch errors recorded as health events not silent gaps; ≥1 real executive-speech signal captured with source URL.

**Gate 4 — Semantic brain (the differentiator).** `argus-semantic-synthesizer` (delta→materiality→signal, on Claude Opus), `argus-claim-ledger`, `argus-competitor-thesis-engine`, `argus-quality-reviewer`, `argus-false-negative-auditor`. This is where the manifesto's edge lives: coverage-aware quiet detection, evidence-or-silence, living theses, self-audit.
Acceptance (HARD): on a known-active day the system promotes real signals (not the V0 empty-brief failure); on a genuinely quiet lane it says quiet ONLY if coverage ran clean; the false-negative auditor catches a planted miss; every published claim carries a source URL; a competitor thesis updates with evidence + confidence.

**Gate 5 — Learning loop + dashboard.** `argus-learning-loop` (auto-update source priority/retirement/candidates; gate code/threshold/policy changes behind approval) + the cockpit dashboard rendering from semantic state (not scraped markdown), per the accepted Luxury Editorial direction + Barometer + "eye behind the lenses."
Acceptance: dashboard updates automatically from DB; a run's misses produce learning events; no green "quiet" unless all lanes ran.

**Gate 6 — Delivery commander (all channels).** `argus-action-router` + `argus-delivery-commander`. Telegram-rich (`parse_mode=HTML`, message-as-brief), Email digest (HTML template renders natively), dashboard ping, WhatsApp + Apple Messages for Business adapters behind the delivery interface. Fix `bot_deliveries` to record true send state.
Acceptance: daily 9 AM + weekly brief delivered rich on Telegram AND email; delivery state auditable end-to-end; a high-confidence material alert can interrupt off-schedule.

**Gate 7 — E2E certification.** Full daily + weekly runs across all three tenants; false-negative audit green; Argus voice verified in a fresh session; delivery + dashboard + learning all observable.
Acceptance: the manifesto's Acceptance Standard (§manifesto) is met for the Algolia tenant end-to-end, and Spryker + Amplitude run without tenant bleed.

**Deadline-fit note:** Fable's hard-deliverable priority order if time-constrained is Gate 4 (the brain) > Gate 6 (rich delivery) > Gate 2/3 (coverage) > Gate 5/1 (dashboard/platform) > multi-tenant fan-out. A great single-tenant brain beats a broad empty platform. Multi-tenant scaffolding (Gate 1) must exist structurally but need not be fully fleshed before the brain is proven.

---

## 6. Non-negotiable product doctrine (from manifesto + research)

- **Evidence or silence.** No claim without a source URL. LLM summaries are NOT evidence (research: top failure mode).
- **Coverage before "quiet."** Never say "market quiet" unless every required lane provably ran. Missing source = failure event, not a quiet day.
- **Decision layer, not a feed.** Every signal routes to an owner/action or it is noise (research: "another noisy feed with no decision layer" is the thing to avoid).
- **Materiality before urgency; meaning before volume.**
- **Argus voice:** skeptical, witty, commercially sharp, evidence-led. No generic AI slop. No em dashes in reader-facing text.
- **Public-source-only for V1.** No Gong/Salesforce/private feeds. Public is fine; pretending it is complete is not.
- **Secrets never in Markdown or the repo.** Env var names only.

---

## 7. What to reuse from V0 (Reuse-First)

- The **collector** (post-hotfix extraction logic) — sound, migrate into `argus-intel-collector`.
- The **Algolia-branded HTML template** — reuse for email + dashboard.
- The **Gemini synth wiring + Hermes cron mechanics** — keep as the deterministic-job substrate; add Claude-tier synthesis on top.
- The **Telegram delivery path** — keep, add `parse_mode=HTML`.
- **Retire:** the 171 KB monolith structure — decompose into the skill set with the official skill-creator workflow + evals per manifesto §Skill Creation Standard.

---

## 8. The goal prompt to paste into Fable

```text
/goal Build CI-OS end to end from the planning packet at
/Users/arijitchowdhury/Dropbox/AI-Development/CI-OS.

Read docs/planning/CI-OS-Fable-build-goal-spec.md FIRST (it indexes everything,
records verified ground truth, the locked decisions, and the gated build order),
then read every doc it lists before writing code.

Execution rules:
1. Do not build from chat memory. Build from disk + the live VPS reality.
   SSH to Hermes (chowmes) and confirm the V0 state yourself at Gate 0.
2. Multi-tenant from day 1. Tiered models (cheap for collection, Claude Opus for
   synthesis/thesis/quality) behind the provider router.
3. Every Argus skill via the official skill-creator workflow, with evals.
4. TDD for implementation.
5. Stop at Gates 0-7 (see spec §5). At each gate report built / files changed /
   tests run / verbatim verification / what failed / safe-to-continue.
6. Reuse V0's collector, template, Gemini/cron substrate, Telegram path; retire the monolith.
7. Do not claim completion without live verification output.
8. No secrets in Markdown or commits. Public-source-only for V1.
9. Preserve Argus voice: evidence-led, skeptical, witty, commercially sharp. No em dashes.
10. If time-constrained, prioritize the brain (Gate 4) and rich delivery (Gate 6)
    over breadth. A great single-tenant brain beats a broad empty platform.
```

---

## 9. Status of open items (as of 2026-07-07 handoff)

1. **Competitor sets (§4): APPROVED as drafted** unless Arijit redlines. Fable proceeds with them.
2. **Cutover policy: LOCKED** — V0 keeps running unchanged (with the 2026-07-07 hotfix) until Fable's Gate 6 reaches delivery parity, then cut over to the rebuild. Do not disable V0 before then.
3. **Delivery priority after Telegram-rich: Email next** (renders the HTML template natively), then dashboard ping, then WhatsApp/Apple Messages adapters.
4. **Research corpus: `Research/docs/Competitive-Intel-Proof.md`** is the confirmed CI research. No other corpus identified.

## 10. HARD PRECONDITION before Gate 4 (the brain) — Claude via `claude -p` (DECIDED 2026-07-07)

The tiered-model plan runs synthesis/thesis/quality on **Claude Opus**. The Hermes OpenRouter and Nous keys are dead (payment/credit error) — and Arijit's decision is to NOT revive them or buy an API key. **The Claude provider on the VPS is Claude Code CLI in headless mode (`claude -p`), authenticated with Arijit's existing Claude OAuth (Max subscription).**

Implementation at Gate 0/1:
1. Install Claude Code CLI on the chowmes VPS (host or inside the hermes container, whichever the provider adapter calls).
2. Authenticate with Arijit's OAuth: run `claude setup-token` locally to mint a long-lived token and place it on the VPS (env `CLAUDE_CODE_OAUTH_TOKEN`), or copy `~/.claude/.credentials.json`. This step needs Arijit once — it is interactive.
3. The model-provider router's "claude" adapter shells out to `claude -p "<prompt>" --output-format json` (add `--model opus|sonnet|haiku` per tier). Treat it like any other provider behind the adapter interface: timeouts, retries, health checks, eval-backed switching still apply.
4. Verify at Gate 0 with a live `claude -p 'ping'` on the VPS and BLOCK Gate 4 if it fails. Do not silently downgrade the brain to Gemini.

Notes: subscription rate limits are shared with Arijit's interactive use — the adapter must back off gracefully on 429s and the cheap tier (Gemini for collection/extraction) stays as-is to keep Claude usage for judgment work only. If CI-OS later becomes a multi-tenant sellable product, swap this adapter for a metered API key per tenant — the router abstraction is exactly for that.
