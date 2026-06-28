# Architecture

## Boundary Decision

Algolia Competitive Intelligence is a standalone software product.

Hermes/Chowmes executes CI, but does not own the CI product code. Scout acquires content, but does not own source strategy or reporting. Vercel serves the dashboard, but does not run long-lived collection jobs.

## Components

| Component | Responsibility | Runs where |
|---|---|---|
| Scout | Web acquisition, cleanup, quality metadata | Chowmes VPS |
| CI core | Collector router, ledger, scoring, synthesis, report rendering | Local, Chowmes worker |
| Daily worker | Scheduled daily collection and report generation | Chowmes/Hermes |
| Weekly worker | Scheduled weekly synthesis | Chowmes/Hermes |
| Dashboard app | Decision and report surface | Vercel |
| Vault | Strategy, research, decisions, operating memory | Obsidian vault |

## Current Product Gap

The imported dashboard is an operational dashboard. The next product version must become a decision dashboard:

- What changed this week?
- Why does it matter to Algolia?
- What action should be accepted, rejected, assigned, or deferred?
- What evidence supports the recommendation?
- Can the report be trusted given source health?

