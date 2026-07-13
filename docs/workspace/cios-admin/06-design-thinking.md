# CI-OS Admin Design Thinking

Mental model: operations console. The user expects a registry table, status controls, and direct add/edit forms. A marketing-style hero would be confusing.

Information architecture:
- Primary: monitored competitors table, source rows, add competitor, add source.
- Secondary: source health, last checked time, status, domain/category.
- Supporting: tenant slug, source family, URL, update timestamps.

Interaction flow:
1. Open local admin for a tenant.
2. Review all competitors and source coverage.
3. Add/edit/pause/retire a competitor or source.
4. Run the next Hermes sweep and confirm the public dashboard reflects it.

Cognitive load: one registry table plus one add-competitor form and one add-source form. Source rows are nested under each competitor to keep visible chunks under control.

Emotional arc: frustration about missing competitors should turn into control and traceability. Every write action should make it clear what changed.

Design pre-mortem:
- Risk: accidental public writes. Mitigation: loopback-only guard and optional token.
- Risk: table overload on mobile. Mitigation: rows collapse into stacked blocks.
- Risk: operator cannot see if a source is failing. Mitigation: status pill and latest health detail next to every source.
