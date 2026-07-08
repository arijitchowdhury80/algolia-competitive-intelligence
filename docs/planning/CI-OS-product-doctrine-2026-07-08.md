# CI-OS Product Doctrine — Arijit, verbatim intent (2026-07-08 morning)

> Recorded on Arijit's explicit order: "record all this shit... this is the gold."
> This document outranks any implementation detail. Every brief, dashboard, and
> module gets measured against THIS, not against what V0 did or what any
> competitor tool does.

## The motto

**"What is my competitor doing, and based on that, what intelligent task and
step and work should I do?"**

It is called INTELLIGENCE, not data mining. Data is mined every single day to
BUILD intelligence.

## The persona and the moment (the whole product in one scene)

I am the CMO of a company. I come in, I log in, and my CI-OS shows me, in very
clear visual terms:

- "This is what YOUR company is doing."
- "This is what THAT competitor did."
- "This is what is relevant to you FOR TODAY, for you to take action and
  involve this team and that team."

Where your competitor is. Where you are. Where you think they could go.

## Hard product rules (Arijit's words, normalized)

1. **NOT Algolia-specific.** Algolia is just the experiment currently running.
   CI-OS is a software product: modular, sellable to any company. Nothing in
   the intelligence layer may hardcode Algolia's vertical, competitors, or
   vocabulary.
2. **No feeder screen. No onboarding questionnaire.** "That's the 1950s."
   When CI-OS is sold to a company (target price point: ~$10,000), the seller
   has already researched the buyer's business and pre-built the competitor
   set. The customer logs in and it already knows who they are.
3. **Completely autonomous.** Monitor all competitors, check what they're
   doing online, grab the signals, transform signals into something that
   triggers an action for marketing (content or otherwise). No babysitting.
4. **Own scouting capability.** Learn by scouting the web ourselves: features,
   functionality, posts, everything, on a scripted 24-hour cycle.
5. **The cadence ladder — mine daily, boil upward:**
   - **Daily (24h):** digest everything learned, deliver succinct, lucid
     intelligence to marketing leadership: "In the last 24 hours, THIS
     happened; THIS is where you should pay attention."
   - **Weekly:** summarize, identify PATTERNS, provide a summarized action
     plan.
   - **Monthly:** boil the weekly up another level.
6. **Every signal lands as an action** naming which team gets involved
   (marketing, content, product, exec...). Signal without an action trigger is
   noise.
7. **Business stakes:** "based on these capabilities, our business, our
   product, is going to fail or bomb or be successful." This doctrine is the
   success criterion.

## What this changes in the build (translation to work items)

- The daily brief template is written to the CMO persona: your-company vs
  competitor framing, today's attention items, team-level action triggers.
  Tenant = "your company"; the brief speaks to the reader as the leader of
  that company, never as an Algolia analyst.
- Weekly synthesis = pattern detection over the daily ledger + action plan.
  Monthly = roll-up of weeklies. Both are first-class pipeline outputs, not
  afterthoughts.
- The dashboard's first screen answers: where competitor is / where you are /
  where they could go — the "three positions" view.
- Tenant onboarding is a seller-side pre-build (competitor set researched and
  seeded before the customer ever logs in), not a customer-side wizard.
- Modularity: intelligence layer must be domain-agnostic; Algolia's competitor
  set is seed data, never logic.
