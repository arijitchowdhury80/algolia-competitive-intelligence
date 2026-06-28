# Competitive intelligence brief template

## Design principles

- Lead with the decision, not the research process.
- Every material claim needs an inline source link and a date.
- Use one paragraph plus bullets. No tables in the daily pulse.
- Keep the daily version scannable in 90 seconds.
- Make the implication specific to Algolia's competitive position first, then to Arijit's OEM, resale, platform, or partner enablement work where relevant.

## Algolia brand language

All output must follow the official Algolia design system located at:

```text
/Users/arijitchowdhury/Library/CloudStorage/GoogleDrive-arijit.chowdhury@gmail.com/My Drive/AI-Projects/Algolia-Design-System
```

Writing rules:

- Voice: confident, technical, outcome-oriented, direct, evidence-backed.
- Use sentence case for headings and labels.
- Do not use emoji, exclamation marks, em dashes, hype, hedging, or generic AI phrasing.
- Use Algolia product language precisely: AI Search, AI Search and Retrieval, Agent Studio, Ask AI, NeuralSearch, MCP Server, Intelligent Data Kit.
- Make numbers concrete and dated.

Visual/report rules:

- HTML/PDF/deck artifacts must use Algolia Blue `#003DFF`, Sora, JetBrains Mono for code, white/cool canvas surfaces, dark ink `#021046`, restrained blue accents, 12-16px cards, 8px controls, and 999px badges only.
- Use official Algolia logo assets when available; never redraw the mark.
- Telegram and Slack remain plain Markdown, but their structure and wording must still feel Algolia: crisp, executive, technical, source-backed.

## Daily report structure v2

### Competitive pulse - YYYY-MM-DD

### Bottom line

One short paragraph. It must answer:

- What changed this period?
- Why does it matter to Algolia's product, GTM, partner, or distribution position?
- Should Arijit act now?
- What is the confidence level?

### Recommended action

One short paragraph. This is the single daily action from the brief. Include the owner, first step, and timeline.

Do not default to Partner Enablement. Choose Product, Product Marketing, Sales Enablement, Partner Enablement, Competitive Intelligence, or a cross-functional owner based on the evidence. If the action is Partner Enablement, say what asset or decision should be produced and why the evidence supports partner ownership. If evidence spans data platforms, protocols, marketplaces, and sales motion, call it distribution readiness or cross-functional GTM/product readiness, not partner-only strategy.

In HTML reports, this section should be displayed as the primary callout. In Telegram and Slack, it stays as plain Markdown.

### Evidence

Use 2-4 bullets, not a table. Each bullet must include:

- Company or threat.
- Date.
- Inline source link.
- Plain-English competitive implication.

Do not use `date not found` in this section. If a finding has no validated publication, announcement, customer-win, detection, or snapshot date, omit it from Evidence and mention the missing date under Research coverage if it matters.

Example:

- **Coveo, Feb. 10, 2026:** [Hosted MCP Server became generally available](https://example.com) for ChatGPT Enterprise and Claude, giving Coveo a cleaner enterprise-agent integration message for partners.

### Watch trigger

Only include triggers that would change the recommendation, urgency, or owner.

- If [specific public trigger], then [specific response].
- If [specific public trigger], then [specific response].

### Research coverage

- Evidence used in this brief: short list of sources that directly support the recommendation.
- Why any Algolia baseline source was used: explain only when Algolia is used to validate a competitive delta.
- Active collection method: SQLite signal ledger, direct URL snapshots/diffs, monitor alerts, targeted search queries, fixture replay, or manual validation. Be precise.
- Broader configured coverage: short category-level list, not every URL.
- V1 exclusions: note that Gong, Salesforce, Slack, G2 paid API, Semrush API, and internal field intel are not connected.
- Known gaps: internal validation gaps or missing public evidence.

## Weekly report structure

### Weekly competitive synthesis - YYYY-MM-DD to YYYY-MM-DD

### What changed

Pattern-first summary of the strongest source-backed changes.

### Strategic pattern

Explain what the changes imply for Algolia. Separate confirmed fact, public-evidence inference, and unknown when needed.

### Recommended actions by owner

Group actions by Product, Product Marketing, Sales Enablement, Partner Enablement, Competitive Intelligence, or Executive Review.

### Battlecard updates

What should change in sales or PMM enablement.

### Coverage gaps

Source blind spots and validation gaps.

## Anti-patterns

- Tables in the daily pulse or weekly synthesis.
- Repeating the same data under different section names.
- Sections named Executive Decision Table, Position Dashboard, Research Scope, Validated Algolia Baseline, AI Threat Radar, Implications for Arijit, Competitive Delta Matrix, Action Plan, Watch List, or Sources & Coverage.
- Raw URLs pasted into the body instead of inline Markdown links.
- Findings without publication or announcement dates.
- `date not found` inside Bottom line or Evidence.
- Assuming the first search result is true enough. Prefer primary sources, official announcements, product docs, changelogs, investor releases, or corroborated authoritative coverage.
- Leading with stale evidence because it forms a cleaner story. The headline should be the freshest strategically material signal unless an older event has new adoption proof, partner motion, or financial/customer validation.
- Saying Algolia lacks MCP. Algolia has MCP; compare packaging, partner motion, positioning, adoption, or documentation clarity.
- Turning every recommendation into a partner-only action because Arijit works on partnerships. Use partner ownership only when the evidence specifically supports it.
- Recommendations without a named owner, audience, or timeline.
- Quiet competitor boilerplate that does not change the decision.
- Long source ledgers in Telegram.
