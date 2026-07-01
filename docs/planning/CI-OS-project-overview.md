# CI-OS Project Overview

Date: 2026-07-01
Status: Planning baseline
Project: CI-OS
Product voice: Argus

## One-Sentence Definition

CI-OS is a Hermes-powered competitive intelligence operating system that continuously discovers sources, collects evidence, synthesizes market meaning, routes actions, updates a dashboard, and delivers Argus-quality intelligence to Arijit.

## Why This Exists

The current CI pipeline behaved too much like a scheduled report generator. That is not enough. A real CI system must know what it monitors, discover what it is missing, detect when "quiet" is actually source failure, and turn competitor movement into commercial judgment.

The product must answer:

- What changed in the competitive market?
- What did not change, and how confident are we?
- What source coverage supports that conclusion?
- What should Algolia do next?
- What should Argus watch more closely tomorrow?

## Product Identity

- System name: CI-OS
- Primary agent and product voice: Argus
- Runtime platform: Hermes
- Host umbrella: Chowmes
- Initial project home: `/Users/arijitchowdhury/Dropbox/AI-Development/CI-OS`
- Vault mirror: `/Users/arijitchowdhury/Dropbox/AI-Development/Personal/Obsidian-Vault/Projects/CI-OS`

Argus is not a generic assistant. Argus is the CI CEO: skeptical, witty, commercially sharp, and evidence-led. He should sound like an operator who has read the room, not a model summarizing pages.

## Primary Users

- Arijit: daily and weekly competitive judgment, strategic pattern recognition, content direction, and executive-level interpretation.
- Algolia GTM and PMM: competitor movement, campaign ideas, positioning shifts, and content recommendations.
- Product and Sales Enablement: competitor claims, pricing changes, feature launches, docs changes, and battlecard evidence.

## V1 Scope

V1 builds a public-source-only competitive intelligence operating loop:

- Multi-user identity, role, and ACL foundation.
- Channel adapter foundation for web app, Telegram, WhatsApp, and Apple Messages for Business.
- Model-provider abstraction so Gemini, OpenAI, Anthropic, Azure OpenAI, or other providers can be swapped by configuration and evals.
- Competitor registry.
- Source hunting and health certification.
- Known-source monitoring.
- Evidence collection.
- Executive speech scanning.
- GTM, content, and audience movement tracking.
- Semantic synthesis.
- False-negative and quality review.
- Dashboard export.
- Multi-channel delivery through Argus, with Telegram first and WhatsApp / Apple Messages for Business planned as adapters.
- Weekly content recommendations for Algolia.
- Learning loop from run outcomes and user feedback.

## Explicit Non-Scope For V1

- No Gong.
- No Salesforce.
- No Slack private data.
- No paid G2, Semrush, or private analyst feeds unless explicitly added later.
- No fake private-data claims.
- No unsupported "market quiet" conclusions.
- No workflow owners unless durable action records exist.

Public-source-only is acceptable. Pretending it is complete market knowledge is not.

## Success Criteria

CI-OS is credible when:

- Every competitor has a source ledger row updated daily.
- Sources are upserted, not duplicated.
- Missing sources are retired only after consistent absence.
- Daily reports distinguish true quiet from coverage failure.
- Weekly reports connect patterns across days.
- Argus produces sharp, useful, non-generic readouts.
- Dashboard renders from semantic data, not scraped Markdown.
- Delivery state is visible and auditable.
- Content recommendations are backed by observed competitor movement and audience traction.
- The system improves source coverage, prompts, evals, and rules from its own misses.

## Product Principles

- Evidence before interpretation.
- Coverage before confidence.
- Materiality before urgency.
- Meaning before volume.
- Argus voice before generic polish.
- Source discovery before source collection.
- Workflow records before prose accountability.

## Operating Cadence

- Source hunting: daily, with optional more frequent lightweight runs.
- Known-source collection: daily, with family-specific schedules.
- Social and content monitoring: daily for public channels where allowed.
- Executive speech scanning: daily for public news and interviews.
- Daily synthesis: every morning before delivery.
- Channel delivery: 9:00 AM local target time, with Telegram first and other channels gated by adapter readiness.
- Weekly synthesis: once per week, with thesis updates and content plan.
- Learning loop: after daily and weekly runs.

## Definition Of Done For The Build

The build is not done when docs exist. It is done when:

- Skills are created with the official skill-creator workflow.
- Skill evals show improvement over baseline.
- Database contracts exist and are populated.
- Dashboard updates automatically from semantic state.
- Argus delivers daily and weekly reports.
- E2E checks verify source health, finding collection, synthesis, delivery, and dashboard state.
- A false-negative audit can catch "quiet but should not be quiet" days.
