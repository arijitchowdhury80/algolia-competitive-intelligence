# CI-OS Implementation Roadmap

Date: 2026-07-01
Status: Planning baseline

## Phase 0: Project Scaffolding

Deliverables:

- Project overview.
- Hermes Argus configuration spec.
- Skill build matrix.
- Data model spec.
- Agent operating model.
- Evaluation plan.
- Environment and secrets spec.
- Channel, identity, ACL, SSO, and model-provider architecture.
- `skills/` directory.

Acceptance:

- Local and vault planning copies exist.
- Docs agree on naming: CI-OS system, Argus voice, Chowmes host.

## Phase 0.5: Platform Foundation

Deliverables:

- Tenant-aware schema foundation.
- User, role, permission, and audit tables.
- Channel adapter interfaces.
- Model provider interfaces.
- Model router aliases.
- SSO design for Google OIDC, enterprise OIDC, SAML, and SCIM.

Acceptance:

- No channel request can bypass identity resolution.
- No Argus skill can access data without an allowed scope.
- Gemini is configured as first provider, but provider switching does not require business-logic rewrites.
- WhatsApp and Apple Messages for Business can be added as adapters without changing Argus core.

## Phase 1: Ledger Foundation

Deliverables:

- Competitor registry.
- Source ledger tables.
- Source scan run tables.
- Source observation tables.
- Upsert and retirement rules.
- Coverage scoring.

Acceptance:

- Each competitor has one rollup row per scan date.
- Sources upsert by normalized URL.
- Missing sources retire only after three consecutive missing days.

## Phase 2: Source Hunting Skill

Deliverables:

- `argus-source-hunter` skill built with skill-creator.
- Evals for source discovery, dedupe, parent-category scanning, and retirement.
- Daily scheduled source scan.

Acceptance:

- Finds source families, not singleton one-off report URLs.
- Stores active, candidate, missing, and retired source state.
- Can explain coverage limits.

## Phase 3: Intel Collection

Deliverables:

- `argus-intel-collector` skill.
- Snapshot storage.
- Raw findings extraction.
- Fetch health events.

Acceptance:

- Known active sources are fetched daily.
- Findings are evidence-only, not strategic claims.
- Fetch failures become visible diagnostics.

## Phase 4: Speech, GTM, And Content Signals

Deliverables:

- `argus-executive-speech-scanner`.
- `argus-gtm-narrative-radar`.
- `argus-linkedin-company-monitor`.
- `argus-content-intelligence`.
- Content observation and recommendation tables.

Acceptance:

- Public executive interviews and quotes become structured signals.
- Competitor content themes and traction are tracked.
- Weekly Algolia content recommendations are evidence-backed.

## Phase 5: Semantic Intelligence

Deliverables:

- `argus-semantic-synthesizer`.
- Semantic facts.
- Semantic deltas.
- Suppressed diagnostics.
- Confidence and materiality scoring.

Acceptance:

- Dashboard and reports render from semantic objects.
- Quiet daily state does not borrow weekly pattern.
- Weak signals are labeled as weak.

## Phase 6: Claims, Theses, And Strategic Memory

Deliverables:

- `argus-claim-ledger`.
- `argus-competitor-thesis-engine`.
- Living competitor thesis records.
- Weekly thesis change log.

Acceptance:

- Competitor claims are tracked with evidence.
- Argus can say what changed in a competitor thesis and why.

## Phase 7: Quality Gates

Deliverables:

- `argus-quality-reviewer`.
- `argus-false-negative-auditor`.
- Quality review records.
- False quiet detection.

Acceptance:

- Empty reports cannot pass without coverage proof.
- Suspicious quiet periods trigger recheck recommendations.
- Quality failures are user-readable, not raw stack traces.

## Phase 8: Dashboard And Delivery

Deliverables:

- Semantic dashboard export.
- Delivery records.
- Telegram readout.
- Dashboard freshness indicators.
- Public-source coverage limits.

Acceptance:

- Dashboard updates automatically from the database.
- Telegram delivery writes `bot_deliveries`.
- Dashboard shows latest report, actions, delivery state, and source health.

## Phase 9: Weekly Content Planning

Deliverables:

- Weekly content plan generation.
- Content plan review.
- Suggested hooks, layouts, formats, and rationale.
- Algolia brand and positioning guardrails.

Acceptance:

- Weekly report includes next-week content recommendations when evidence supports them.
- Recommendations are not copied from competitors.
- Each idea links back to observed market movement.

## Phase 10: Learning Loop

Deliverables:

- `argus-learning-loop`.
- Improvement queue.
- User feedback ingestion.
- Eval updates from misses.

Acceptance:

- Every recurring miss becomes a queued improvement.
- Approved improvements update source strategy, skill prompts, evals, or rules.

## Phase 11: Hermes Hardening

Deliverables:

- Model escalation router.
- Cron configuration.
- Argus session refresh SOP.
- Telegram verification SOP.
- Failure-mode runbook.

Acceptance:

- Low, standard, high, and image model use is observable.
- Cron jobs are bounded and recoverable.
- Argus voice is verified from a fresh session after changes.

## Phase 12: Production Certification

Deliverables:

- E2E status command.
- Daily forced run.
- Weekly forced run.
- Dashboard HTTP check.
- Delivery record check.
- Voice smoke test.
- Source coverage audit.

Acceptance:

- Argus can be certified with evidence, not vibes.
