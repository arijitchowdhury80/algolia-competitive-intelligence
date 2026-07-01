# CI-OS Evaluation Plan

Date: 2026-07-01
Status: Planning baseline

## Evaluation Philosophy

The system failed before because surface health was mistaken for intelligence health. CI-OS must evaluate the whole loop:

- source coverage
- collection quality
- semantic judgment
- Argus voice
- dashboard rendering
- delivery observability
- identity, ACL, and channel routing
- model-provider abstraction
- false-negative resistance
- learning-loop improvement

## Skill Evaluation Standard

Every Argus skill must include:

- baseline prompts without the skill
- with-skill prompts
- grading assertions
- qualitative review notes
- pass/fail criteria
- regression cases

Minimum eval files:

- `evals/eval-prompts.jsonl`
- `evals/baseline-results.json`
- `evals/with-skill-results.json`
- `evals/review-notes.md`

## System Evals

### Source Hunter Evals

Questions:

- Does it find parent source categories instead of hardcoded singleton URLs?
- Does it identify blogs, news, docs, changelogs, pricing, case studies, partners, community, LinkedIn, X, YouTube, GitHub, and analyst pages?
- Does it upsert without duplicates?
- Does it retire only after policy threshold?

Pass criteria:

- No duplicate normalized URLs.
- Parent category sources preferred over one-off report URLs.
- Coverage gaps explicitly stated.

### Intel Collector Evals

Questions:

- Does it fetch active sources reliably?
- Does it distinguish page failure from market quiet?
- Does it write raw findings without unsupported interpretation?

Pass criteria:

- Every fetch outcome is recorded.
- Every raw finding has a source id and evidence URL.

### Executive Speech Evals

Questions:

- Does it detect public executive commentary?
- Does it separate direct quote, paraphrase, and journalist framing?
- Does it extract market-direction signals?

Pass criteria:

- No unattributed quotes.
- Quote signals include source URL and confidence.

### Content Intelligence Evals

Questions:

- Does it identify competitor content themes?
- Does it use public traction signals where available?
- Does it create Algolia content recommendations that are original and useful?

Pass criteria:

- Every recommendation has evidence ids.
- Output includes hook, layout, format, audience, why now, and confidence.
- No copying competitor phrasing.

### Semantic Synthesis Evals

Questions:

- Does it identify material deltas?
- Does it suppress noise?
- Does it avoid fake urgency?
- Does it separate daily state from weekly pattern?

Pass criteria:

- Material deltas include implication and evidence.
- Suppressed diagnostics never appear as findings.
- Quiet day requires healthy coverage and false-negative audit.

### Argus Voice Evals

Questions:

- Does Argus sound like Argus?
- Does he avoid generic assistant filler?
- Does he lead with useful truth?
- Does he challenge weak assumptions?

Pass criteria:

- Live fresh-session smoke response passes human review.
- No "comprehensive overview" tone.
- No fake apology sludge.
- Witty or dry only when it sharpens judgment.

### Dashboard Evals

Questions:

- Does dashboard render from semantic data?
- Does it show delivery and freshness?
- Does it display public-source limits?
- Does it avoid fake controls?

Pass criteria:

- Dashboard JSON exists and validates.
- Dashboard HTTP check passes.
- Quiet state is clear and not inflated.

### Identity, ACL, And Channel Evals

Questions:

- Does a Telegram, WhatsApp, Apple Messages for Business, or web-app request resolve to a canonical user before Argus answers?
- Does an unlinked channel identity create an access request rather than receiving data?
- Does ACL block evidence, settings, source health, and admin actions for users without permission?
- Are denied requests audited?

Pass criteria:

- Default deny works.
- Cross-channel identity links to the same canonical user.
- No channel bypasses ACL.
- Audit records exist for allow and deny decisions.

### Model Provider Evals

Questions:

- Can the same task run through Gemini and OpenAI provider adapters without changing business logic?
- Does the model router select by capability, tier, tenant policy, and task profile?
- Are provider-specific model ids isolated to config/adapters?
- Do evals run before a provider becomes production default?

Pass criteria:

- Provider switching is config-driven.
- Provider runs are recorded.
- Quality comparisons are available before changing defaults.

## E2E Certification

Daily certification:

- Source scan run complete.
- Intel fetch run complete.
- Semantic synthesis complete.
- False-negative audit complete.
- Quality review pass or explicit degraded mode.
- Dashboard export exists.
- Channel delivery row exists.
- Identity and ACL checks pass for delivery recipients.
- Argus voice check passes after prompt changes.

Weekly certification:

- Weekly synthesis uses high model when activity or ambiguity justifies it.
- Competitor theses updated.
- Content plan generated or intentionally skipped with reason.
- Action items match workflow records.
- Delivery row exists.

## False-Negative Audit

A quiet report is suspicious when:

- More than two days pass with no material findings.
- Source coverage is below threshold.
- Fetch failures cluster by competitor or source family.
- Competitor social/news channels show public activity.
- External search finds recent activity not in the ledger.

The auditor should trigger:

- source hunter re-run
- competitor-specific open-web search
- source family coverage check
- improvement queue item if missed source is confirmed

## Human Acceptance

The system can pass automated checks and still fail the product if Argus sounds generic or the output lacks meaning. Human review remains required for:

- Argus voice calibration.
- First weekly content plans.
- New source families.
- Model escalation policy changes.
- Any private data connector proposal.
