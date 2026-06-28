# ADR: Build Narrow Algolia-Specific CI Wedge, Not A Generic CI Platform

**Date:** 2026-06-27
**Status:** Accepted

## Context

The prior CI roadmap was wrongly ordered. It put product build steps before deep market truth. Arijit correctly challenged that building dashboards, bots, source repair, and reports before understanding professional CI tools would be building from assumptions.

The market benchmark shows that professional tools already cover broad CI capabilities:

- Klue, Crayon, and Kompyte cover competitive enablement, battlecards, seller workflows, monitoring, and revenue/adoption analytics.
- Contify and AlphaSense cover broader market intelligence and premium/curated intelligence workflows.
- Similarweb and Semrush cover digital, traffic, SEO, and share-of-voice intelligence.
- G2 covers review, category, buyer intent, and customer voice inputs.

Therefore, Chowmes CI should not attempt to recreate the existing category.

## Decision

Build only a narrow Algolia-specific decision layer.

Do not build a generic CI platform.

Do not continue CI product build work until the research benchmark and differentiation thesis are treated as the roadmap foundation.

## What The Narrow Wedge Means

Chowmes CI should focus on:

1. Algolia-specific interpretation.
2. Agentic follow-up.
3. Evidence and claim-quality governance.
4. Owner-specific action routing.
5. Athena quality supervision.
6. Usefulness feedback.
7. Optional future ingestion of paid-tool/internal outputs if explicitly approved.

## What We Will Not Build

Not in the current strategic direction:

- A generic Klue/Crayon/Kompyte replacement.
- A broad market intelligence platform like Contify/AlphaSense.
- A traffic/SEO platform like Similarweb/Semrush.
- A review/buyer-intent platform like G2.
- A stakeholder-facing Algolia product before evidence, access, and claim-quality controls exist.

## Rationale

The paid CI market already covers monitoring, battlecards, dashboards, alerts, source breadth, win/loss, digital intelligence, and premium research. Chowmes can become valuable only where generic tools are weak:

- Translating signals into Algolia-specific implications.
- Challenging weak or unsupported claims.
- Routing actions across Product, PMM, Sales Enablement, Partnerships, Exec, and CI Ops.
- Letting Arijit ask follow-up questions in a private agentic workflow.
- Combining public evidence with approved internal or paid-tool context later.

## Consequences

- The roadmap is reordered: market truth and differentiation are Build 0.
- Existing CI code remains a prototype and evidence source, not the validated product strategy.
- The next implementation work must improve signal interpretation and report validity, not just UI.
- Future dashboard/bot work must be justified by the differentiation thesis.

## Acceptance Criteria For Continuing Build

Build work may resume only when it serves the narrow wedge:

- Semantic delta extraction.
- Algolia-specific implication mapping.
- Evidence/claim quality scoring.
- Action routing.
- Feedback/usefulness tracking.
- Private analyst workflow.

If a proposed feature only recreates generic CI tooling, reject or defer it.
