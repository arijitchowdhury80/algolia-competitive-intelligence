# Argus Skill Build Matrix

Date: 2026-07-01
Status: Planning baseline
Skill home: `/Users/arijitchowdhury/Dropbox/AI-Development/CI-OS/skills`

## Skill Creation Standard

Every skill must be created using the official skill-creator workflow:

1. Capture intent and triggers.
2. Define inputs, outputs, served user, dependencies, and success criteria.
3. Write `SKILL.md`.
4. Add scripts and references only where they improve reliability.
5. Create eval prompts.
6. Run baseline without skill.
7. Run with skill.
8. Grade and review outputs.
9. Iterate until the skill measurably improves performance.

No skill is production-ready until its eval file and review notes exist.

## Build Order

| Phase | Skill | Purpose | Why this order |
|-------|-------|---------|----------------|
| 1 | `argus-source-hunter` | Find, validate, upsert, and retire competitor sources | Nothing downstream works without source truth. |
| 2 | `argus-intel-collector` | Fetch evidence from active sources | Collection depends on the source ledger. |
| 3 | `argus-executive-speech-scanner` | Track public executive interviews and quotes | Adds strategic market direction signals. |
| 4 | `argus-gtm-narrative-radar` | Monitor messaging, pages, campaigns, and positioning | Converts updates into GTM pattern awareness. |
| 5 | `argus-content-intelligence` | Analyze competitor content traction and create Algolia content recommendations | Required for weekly content planning. |
| 6 | `argus-linkedin-company-monitor` | Track public company LinkedIn posts and engagement where allowed | Feeds GTM and content intelligence. |
| 7 | `argus-semantic-synthesizer` | Turn findings into semantic deltas, implications, and confidence | Creates meaning from evidence. |
| 8 | `argus-claim-ledger` | Track competitor claims and response status | Supports battlecards and content angles. |
| 9 | `argus-competitor-thesis-engine` | Maintain living competitor theses | Weekly strategic memory. |
| 10 | `argus-quality-reviewer` | Check evidence, false quiet, and report quality | Prevents embarrassing empty reports. |
| 11 | `argus-false-negative-auditor` | Investigate suspicious quiet periods | Directly addresses the current failure mode. |
| 12 | `argus-action-router` | Create workflow-backed action items | Makes accountability durable. |
| 13 | `argus-delivery-commander` | Deliver through approved channels and record delivery status | Makes delivery observable. |
| 14 | `argus-learning-loop` | Turn misses, feedback, and run data into improvements | Makes CI-OS self-improving. |

## Skill Specs

### `argus-source-hunter`

- Serves: Argus, Intel Collector, False-Negative Auditor.
- Inputs: competitor registry, known domains, sitemap URLs, parent pages, discovery queries, prior source ledger.
- Outputs: active sources, candidate sources, retired sources, source scan rollups, source health events.
- Writes: `competitors`, `sources`, `source_scan_runs`, `source_observations`, `source_candidates`, `competitor_scan_rollups`.
- Eval examples: discover source families for Elastic, Coveo, Bloomreach; avoid singleton hardcoding; retire only after three misses.

### `argus-intel-collector`

- Serves: Semantic Synthesizer, Dashboard, Quality Reviewer.
- Inputs: active source ledger, previous snapshots, fetch rules, source family.
- Outputs: snapshots, raw findings, diffs, fetch failures.
- Writes: `intel_fetch_runs`, `source_snapshots`, `raw_findings`, `source_health_events`.
- Eval examples: fetch blog, changelog, pricing, docs, case study, partner page updates without making strategy claims.

### `argus-executive-speech-scanner`

- Serves: Weekly synthesis, Competitor Thesis Engine, GTM Narrative Radar.
- Inputs: executive list, company names, public news queries, YouTube and podcast source candidates.
- Outputs: executive quote signals, market claims, customer demand commentary, strategic direction shifts.
- Writes: `executive_speech_signals`, `raw_findings`, `semantic_facts`.
- Eval examples: detect CEO interview market commentary and separate it from journalist framing.

### `argus-gtm-narrative-radar`

- Serves: PMM, content planning, weekly strategy.
- Inputs: blogs, news, landing pages, case studies, analyst pages, campaigns, public social posts.
- Outputs: narrative themes, messaging changes, audience focus, campaign posture.
- Writes: `gtm_narrative_signals`, `semantic_facts`, `content_observations`.
- Eval examples: distinguish product launch from thought leadership from demand-generation content.

### `argus-content-intelligence`

- Serves: Algolia content strategy, Argus weekly report, GTM planning.
- Inputs: competitor blog posts, LinkedIn posts, public engagement counts where available, YouTube metadata, news resonance, prior content performance observations.
- Outputs: content suggestions, hooks, outlines, recommended formats, target audience, evidence links, rationale.
- Writes: `content_observations`, `content_traction_signals`, `content_recommendations`, `weekly_content_plan`.
- Eval examples: produce a next-week Algolia content plan from observed competitor movement without copying competitor content.

### `argus-linkedin-company-monitor`

- Serves: GTM Narrative Radar, Content Intelligence.
- Inputs: public company LinkedIn URLs, post metadata, engagement numbers where available and compliant.
- Outputs: post observations, theme tags, engagement signals, audience resonance notes.
- Writes: `social_observations`, `content_traction_signals`, `source_health_events`.
- Eval examples: classify high-engagement posts and infer likely audience appeal with evidence limits.

### `argus-semantic-synthesizer`

- Serves: Dashboard, channel delivery, weekly report.
- Inputs: raw findings, source health, executive speech signals, GTM signals, claims, prior semantic facts.
- Outputs: material deltas, suppressed diagnostics, implications, recommended moves, confidence.
- Writes: `semantic_facts`, `semantic_deltas`, `suppressed_diagnostics`.
- Eval examples: quiet day with healthy coverage, quiet day with weak coverage, material competitor launch.

### `argus-quality-reviewer`

- Serves: Argus, delivery gate.
- Inputs: source coverage, findings, semantic deltas, report draft, delivery metadata.
- Outputs: pass/fail review, risk notes, required fixes, false-quiet warning.
- Writes: `quality_reviews`, `false_negative_audits`, `improvement_queue`.
- Eval examples: reject a report claiming "nothing happened" when source coverage is missing.

### `argus-content-plan-reviewer`

- Serves: Algolia content workflow.
- Inputs: weekly content recommendations, evidence, competitor movement, brand rules.
- Outputs: approved content plan, rejected weak ideas, risk notes, refinement suggestions.
- Writes: `content_plan_reviews`, `weekly_content_plan`.
- Eval examples: remove generic content ideas and keep only evidence-backed recommendations.

## Required Files Per Skill

Each skill directory should contain:

- `SKILL.md`
- `evals/eval-prompts.jsonl`
- `evals/baseline-results.json`
- `evals/with-skill-results.json`
- `evals/review-notes.md`
- `README.md`
- `references/` only when needed
- `scripts/` only when deterministic execution is needed
