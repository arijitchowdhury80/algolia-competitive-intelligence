# Argus CI data contract

This contract keeps the CI loop honest: reports, dashboard cards, action items,
and Telegram delivery status must all come from structured ledger state, not
from rereading prose and hoping the formatting stayed convenient.

## Semantic delta

Source table: `semantic_deltas`.

Required fields:

- `competitor`
- `source_url`
- `delta_type`
- `detected_date`
- `delta_summary`
- `materiality_score`
- `materiality_reason`
- `algolia_implication`
- `action_owner`
- `recommended_action`
- `evidence_urls`
- `quality_status`

Only rows with `quality_status = 'publish'` can create executive findings or
workflow actions. Suppressed rows are trust diagnostics only.

## Action item

Source table: `action_items`.

Required fields:

- `report_id`
- `title`
- `owner`
- `recommendation`
- `status`
- `priority`
- `source_delta_ids`
- `due_window`
- `confidence`

Allowed owners are Product, Product Marketing, Sales Enablement, Partner
Enablement, Competitive Intelligence, and Executive Review. Weekly reports may
summarize owner routes only when matching action rows exist.

## Delivery event

Source table: `bot_deliveries`.

Required fields:

- `report_id`
- `cadence`
- `bot_profile`
- `channel`
- `recipient`
- `status`
- `message_kind`
- `markdown_path`
- `html_path`
- `dashboard_url`
- `artifact_paths`
- `delivery_metadata`
- `delivered_at`

The Argus cron wrapper records `queued_for_telegram` because Hermes owns the
actual stdout-to-Telegram handoff. Direct `hermes send` smoke tests may record
known-send outcomes separately.

## Dashboard export

Public file: `apps/dashboard/public/data/semantic-dashboard.json`.

Required top-level fields:

- `daily_state`
- `weekly_state`
- `material_deltas`
- `suppressed_diagnostics`
- `source_health`
- `action_queue`
- `delivery_status`
- `report_archive`
- `coverage_limits`

The dashboard must render from this export first. Archived Markdown remains
available for traceability, not as the dashboard's source of truth.

## Coverage limits

The production CI system is public-source only. Gong, Salesforce, Slack, G2
paid API, Semrush API, and internal win/loss are intentionally not connected.
This is a coverage limit, not a run failure.
