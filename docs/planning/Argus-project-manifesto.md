# Argus CI-OS Product Build Manifesto

Date: 2026-06-30
Status: Foundational manifesto
Project: CI-OS
Product voice: Argus

## Summary

Argus CI-OS is not a daily report bot. It is a Competitive Intelligence operating system built on Hermes.

Argus is the product voice, CI CEO, orchestration brain, quality reviewer, learning loop, and conversational interface. Deterministic jobs collect and store evidence. Hermes agents and skills create meaning, critique, prioritization, self-improvement, and delivery.

The objective is to build a full public-source CI platform for Algolia's competitive landscape that can discover new sources, monitor known sources, understand GTM and audience movement, track executive speech, synthesize semantic intelligence, route actions, update the dashboard, and deliver Argus-quality insight through approved channels.

## Operating Doctrine

Argus does not merely report competitor movement. Argus runs the competitive intelligence operating system, learns from every cycle, manages specialist skills, challenges weak conclusions, and turns public market movement into decision-grade meaning.

Core doctrine:

- No source, no claim.
- No evidence, no recommendation.
- No complete coverage, no "market quiet."
- No material delta, no fake urgency.
- No owner unless there is a workflow-backed action item.
- No generic AI slop. Argus speaks with judgment, restraint, wit, and commercial sharpness.

## Product Identity

Project/system name: CI-OS.

Product and agent voice: Argus.

Chowmes should become Argus-first for Competitive Intelligence. Athena, Vulcan, Kubera, and other ELT-style agents may remain in a cordoned-off advisory area for Arijit's private strategy and idea discussion, but they should not be the default CI execution path.

Argus owns:

- CI operating model
- source strategy
- daily/weekly/monthly readouts
- dashboard narration
- quality review
- learning loop
- multi-channel delivery
- user feedback interpretation
- action routing

CI-OS must be multi-user and multi-channel from the beginning. Telegram is the first live channel, but WhatsApp, Apple Messages for Business, and the web app must fit through the same identity, ACL, audit, and delivery architecture.

## Hermes Product Architecture

Use Hermes as the CI operating platform:

- Argus profile becomes the main CI product profile.
- Hermes cron runs scheduled skills/jobs for hunting, fetching, synthesis, review, and delivery.
- No-agent cron is used for deterministic scripts where no reasoning is needed.
- Agent-backed cron is used for judgment, review, synthesis, learning, and retrospectives.
- Profile distribution becomes the long-term packaging model for Argus CI-OS.
- Kanban or a durable task board can become phase 2 for multi-agent work management.
- Delegation remains gated in v1. Use role-prompted reviewer agents first. Add live profile swarms only when operationally justified.

Recommended Hermes roles:

- Argus: CI CEO, PM, operator, intelligence lead, delivery voice.
- Source Hunter: source discovery and health.
- Intel Collector: evidence fetching and snapshots.
- Executive Speech Scanner: public executive interviews, quotes, and market commentary.
- GTM Narrative Analyst: content, messaging, tone, audience, LinkedIn, and campaigns.
- Semantic Synthesizer: facts, deltas, meaning, and materiality.
- Claim Ledger Analyst: competitor claims and Algolia response status.
- Quality Reviewer: false-quiet, source, evidence, and action-review gates.
- Action Router: owner, recommendation, confidence, and due window.
- Delivery Commander: channel delivery, dashboard, alert queue, and delivery observability.
- Access Governor: user identity, SSO, roles, permissions, ACL checks, and channel identity linking.
- Model Router: provider-agnostic model selection, model escalation, provider health, and eval-backed switching.
- Learning Loop: post-run improvement, user feedback, and rule/source updates.

## Skill Creation Standard

Every new Argus skill must be created using the official skill-creator workflow:

1. Capture intent and trigger conditions.
2. Define inputs, outputs, audience, dependencies, and success criteria.
3. Write `SKILL.md` with progressive disclosure.
4. Add scripts and references only where deterministic reliability is needed.
5. Create realistic eval prompts.
6. Run with-skill and baseline evals.
7. Grade outputs quantitatively where possible.
8. Review qualitative outputs.
9. Iterate until the skill improves measurable performance.

Each skill must specify:

- what it does
- when it runs
- who it serves
- required inputs
- produced outputs
- database writes
- failure modes
- self-improvement hooks
- eval cases

## Phase 1: Core Ledger And Source Hunting

Build this first because every downstream capability depends on source truth.

### Skill: `argus-source-hunter`

Purpose: discover, validate, upsert, and retire sources.

Inputs:

- competitor registry
- sitemap URLs
- robots.txt
- parent pages
- RSS feeds
- open-web discovery queries
- prior source ledger

Serves:

- Argus
- source quality dashboard
- intel collector
- false-negative auditor

Outputs:

- active sources
- candidate sources
- retired sources
- source observations
- competitor scan rollups
- missing-source streaks
- source health events

Coverage families:

- news
- blogs
- case studies
- customer pages
- pricing
- product pages
- product launch pages
- docs
- changelogs
- release notes
- partner pages
- marketplace and integration pages
- community pages
- resources and reports
- analyst pages
- LinkedIn company pages
- X/Twitter handles
- YouTube channel feeds
- GitHub releases
- open-web discovery

Rules:

- Upsert by normalized URL.
- Never duplicate sources.
- Retire after 3 consecutive missing calendar days.
- Keep historical evidence.
- Mark source status explicitly: active, candidate, blocked, missing, retired, needs_credentials, not_applicable.

## Phase 2: Evidence Collection

### Skill: `argus-intel-collector`

Purpose: fetch latest evidence from all active sources.

Inputs:

- active sources
- candidate sources above threshold
- source family
- previous snapshots
- source health state

Serves:

- synthesis
- dashboard
- alerting
- quality reviewer

Outputs:

- content snapshots
- raw findings
- fetch errors
- source health events
- candidate promotions

Rule: this skill collects evidence only. It does not make strategic claims.

### Skill: `argus-executive-speech-scanner`

Purpose: track public executive interviews, speeches, podcasts, conference talks, earnings commentary, and news quotes.

Inputs:

- executive list per competitor
- company names
- news/search queries
- YouTube/interview sources
- Bloomberg, CNBC, podcast, conference, and public news search results where accessible

Serves:

- strategic thesis engine
- weekly readout
- GTM narrative intelligence
- executive review

Outputs:

- executive quote signals
- market-direction claims
- customer-behavior claims
- macro/industry theses
- cited source URLs
- confidence and source quality

Example signal:

- Elastic CEO says in a public interview that buyer behavior is shifting toward a new search or AI consumption pattern.
- Argus stores who said it, where, when, exact claim, source URL, implication, and confidence.

## Phase 3: GTM, Social, And Audience Intelligence

### Skill: `argus-gtm-narrative-radar`

Purpose: understand competitor messaging, tone, audience pull, and direction changes.

Inputs:

- blogs
- news
- launch pages
- campaign pages
- resource pages
- webinars and events
- LinkedIn company page content
- X posts
- YouTube titles, descriptions, and transcripts where available
- public engagement signals where accessible

Serves:

- Product Marketing
- content strategy
- weekly strategic readout
- dashboard narrative radar
- claim ledger

Outputs:

- `gtm_narrative_signal`
- repeated themes
- tone shifts
- ICP shifts
- claims ledger updates
- content suggestions for Algolia
- messaging threats and opportunities

Tracks:

- what competitors are pushing
- what is resonating
- what audience is responding
- whether direction is changing
- what Algolia should copy, counter, ignore, or preempt

### Skill: `argus-linkedin-company-monitor`

Purpose: monitor public company LinkedIn content and public engagement signals where accessible.

Inputs:

- company LinkedIn page URLs
- public post metadata
- source discovery results
- optional manual/API export if needed later

Serves:

- GTM narrative radar
- audience intelligence
- content recommendations
- PMM

Outputs:

- LinkedIn post signals
- campaign themes
- audience engagement notes
- repeated messaging
- source URLs
- inaccessible or blocked status when applicable

Important: LinkedIn access must be governed. If public access is blocked or scraping is not acceptable, the lane reports a coverage limit instead of pretending.

## Phase 4: Semantic Intelligence And Claim Ledger

### Skill: `argus-semantic-synthesizer`

Purpose: turn raw findings into semantic intelligence.

Inputs:

- raw findings
- content snapshots
- source observations
- executive speech signals
- GTM narrative signals
- prior competitor theses
- Algolia public baseline

Serves:

- dashboard
- Argus daily brief
- action queue
- thesis engine

Outputs:

- semantic facts
- semantic deltas
- materiality scores
- evidence URLs
- recommended actions
- suppressed diagnostics

Semantic types:

- product launch
- product update
- pricing change
- packaging change
- docs change
- changelog update
- release note
- case study
- customer proof
- press release
- newsroom announcement
- blog narrative
- marketing campaign
- analyst positioning
- report publication
- partner announcement
- marketplace integration
- community signal
- GitHub release
- executive speech
- GTM narrative shift
- LinkedIn/social signal
- YouTube signal
- AI-search threat
- industry signal

### Skill: `argus-claim-ledger`

Purpose: track competitor claims over time.

Inputs:

- semantic facts
- executive speech
- GTM narrative signals
- source URLs
- Algolia baseline evidence

Serves:

- PMM
- Sales Enablement
- Product
- Executive Review

Outputs:

- claims
- claim repetition count
- source history
- proof quality
- Algolia response status
- owner routing
- counter-message candidates

## Phase 5: Living Competitor Theses

### Skill: `argus-competitor-thesis-engine`

Purpose: maintain a living strategic thesis for every competitor.

Inputs:

- semantic deltas
- claims
- GTM narrative signals
- executive speech
- customer proof
- partner movement
- source trend history

Serves:

- weekly strategic readout
- PMM
- Sales Enablement
- Product
- Executive Review

Outputs:

- competitor thesis
- thesis changes
- confidence
- evidence
- open questions
- watch triggers

Example:

- Constructor is pushing agentic shopping as a category wedge.
- Coveo is leaning enterprise AI relevance plus ecosystem partnership.
- Google threatens through platform bundling, not point-solution comparison.

The thesis engine is what turns monitoring into intelligence.

## Phase 6: Hermes Review Board And Quality Gates

### Skill: `argus-quality-reviewer`

Purpose: challenge every report before delivery.

Inputs:

- latest synthesis
- coverage matrix
- source health
- suppressed diagnostics
- prior false-negative audits
- report draft

Serves:

- Argus
- delivery gate
- dashboard trust layer

Outputs:

- pass, fail, or warn
- false-quiet risk
- missing evidence
- weak claims
- bad owner routing
- improvement actions

Review roles inside this skill:

- skeptic
- PMM reviewer
- Sales reviewer
- Product reviewer
- executive reviewer
- source-quality reviewer

### Skill: `argus-false-negative-auditor`

Purpose: prevent "quiet market" failure from recurring.

Inputs:

- known recent market events
- open-web discovery results
- missed user-provided examples
- prior daily reports

Serves:

- self-improvement
- source hunting
- semantic synthesis

Outputs:

- would-Argus-have-found-this score
- missed-source reason
- missed-semantic reason
- source patch recommendation
- regression tests

## Phase 7: Self-Improvement System

### Skill: `argus-learning-loop`

Purpose: make Argus improve after every run.

Inputs:

- run logs
- quality review
- failed gates
- user feedback
- missed signals
- noisy signals
- delivery outcomes
- dashboard health

Serves:

- Argus PM
- source hunter
- semantic synthesizer
- dashboard

Outputs:

- learning log
- source priority changes
- candidate source promotions
- source retirement recommendations
- semantic rule improvement queue
- report style improvements
- eval cases for skills
- proposed patches

Allowed auto-updates:

- source priority
- missing streaks
- source retirement status
- candidate-source status
- dashboard freshness status

Requires approval:

- code changes
- semantic thresholds
- new credentials
- action routing policy
- report doctrine
- profile or SOUL changes

## Phase 8: Action, Delivery, And Dashboard

### Skill: `argus-action-router`

Purpose: route material deltas to the right workflow owner.

Inputs:

- semantic deltas
- claim ledger
- competitor thesis
- confidence
- evidence
- materiality

Serves:

- Product
- Product Marketing
- Sales Enablement
- Partner Enablement
- Executive Review
- Competitive Intelligence

Outputs:

- action items
- owner
- due window
- evidence links
- confidence
- approval status

### Skill: `argus-delivery-commander`

Purpose: deliver the right report at the right time.

Inputs:

- certified synthesis
- quality review status
- dashboard URL
- delivery history
- alert queue

Serves:

- Arijit and approved users through web app, Telegram, WhatsApp, and Apple Messages for Business
- dashboard
- report archive

Outputs:

- 9 AM daily channel brief
- weekly strategic readout
- high-confidence material alerts
- stale or incomplete report warning
- delivery records

Alert policy:

- Argus may interrupt outside 9 AM only for high-confidence material alerts.
- Examples: major product launch, pricing change, strong customer proof, partner move, analyst shift, AI-search threat.
- Argus recommends action but does not update battlecards or publish artifacts without approval.

## Dashboard Requirements

The dashboard is the always-current command center.

It must show:

- latest source hunt
- latest intel fetch
- latest synthesis
- latest quality review
- latest Argus delivery
- source coverage matrix
- LinkedIn/X/YouTube lane status
- executive speech signals
- GTM narrative radar
- claim ledger
- living competitor theses
- material deltas
- suppressed diagnostics
- action queue
- coverage limits
- what Argus learned today

No green quiet state unless all required lanes ran cleanly.

## Data Model

Add or extend tables for:

- `tenants`
- `users`
- `user_identities`
- `roles`
- `permissions`
- `user_role_assignments`
- `identity_provider_configs`
- `channel_accounts`
- `channel_identities`
- `channel_threads`
- `channel_messages`
- `delivery_attempts`
- `access_requests`
- `audit_events`
- `model_provider_configs`
- `model_provider_runs`
- `competitors`
- `source_scan_runs`
- `sources`
- `source_observations`
- `source_candidates`
- `competitor_scan_rollups`
- `intel_fetch_runs`
- `content_snapshots`
- `raw_findings`
- `executive_speech_signals`
- `gtm_narrative_signals`
- `claims`
- `claim_observations`
- `competitor_theses`
- `semantic_facts`
- `semantic_deltas`
- `quality_reviews`
- `false_negative_audits`
- `learning_events`
- `improvement_queue`
- `action_items`
- `bot_deliveries`
- `dashboard_state`

## Build Phase Order

1. Platform foundation: tenant, identity, ACL, channels, SSO, model provider abstraction.
2. Ledger schema and source hunter.
3. Competitor intel collector.
4. Executive speech scanner.
5. GTM, LinkedIn, and audience radar.
6. Semantic synthesizer and claim ledger.
7. Competitor thesis engine.
8. Quality reviewer and false-negative auditor.
9. Learning loop and improvement queue.
10. Dashboard command center.
11. Argus delivery commander.
12. Hermes profile distribution for Argus CI-OS.
13. Optional live multi-profile agents or Kanban once stable.

## Hermes Configuration Plan

Configure Argus as the primary CI-OS profile.

- Argus profile owns CI skills, memory, cron, channel delivery, dashboard narration, and delivery.
- Athena/ELT remains cordoned off for private idea discussion only.
- Use no-agent cron for deterministic jobs.
- Use agent-backed cron for review, synthesis, learning, and delivery.
- Keep memory write approval enabled for durable memory changes while tuning.
- Keep conversational channels bounded; dashboard and database are the system of record.
- Keep code execution disabled in Telegram, WhatsApp, Apple Messages for Business, and web chat unless explicitly approved.
- Add xAI/Grok credentials only when ready to certify X monitoring.
- Start YouTube with RSS before API access.

## Acceptance Standard

Argus CI-OS is ready only when:

- new sources are discovered automatically
- known sources are health-checked continuously
- LinkedIn, news, blogs, pricing, product, docs, changelog, partners, community, X, and YouTube are covered or explicitly gated
- executive speech is captured as a signal
- GTM narrative shifts are tracked
- material findings are evidence-backed
- false quiet is blocked
- reports pass quality review
- dashboard updates automatically
- Argus learns from every run
- channel delivery is recorded
- user feedback changes future behavior

## Initial Project Paths

Local project home:

`/Users/arijitchowdhury/Dropbox/AI-Development/CI-OS`

Vault project home:

`/Users/arijitchowdhury/Dropbox/AI-Development/Personal/Obsidian-Vault/Projects/CI-OS`

Manifesto path:

`docs/planning/Argus-project-manifesto.md`
