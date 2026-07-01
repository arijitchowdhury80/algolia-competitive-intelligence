# CI-OS Data Model Spec

Date: 2026-07-01
Status: Planning baseline

## Principle

The database is the product memory. Reports, dashboard state, Telegram delivery, and weekly content planning must all render from structured data, not from scraped prose.

## Entity Groups

### Tenant, Identity, And Access Control

`tenants`

- `id`
- `name`
- `status`
- `primary_domain`
- `created_at`
- `updated_at`

`users`

- `id`
- `tenant_id`
- `email`
- `display_name`
- `status`
- `created_at`
- `updated_at`

`user_identities`

- `id`
- `tenant_id`
- `user_id`
- `provider`
- `provider_subject`
- `email`
- `linked_at`
- `last_seen_at`

`roles`

- `id`
- `tenant_id`
- `name`
- `description`

`permissions`

- `id`
- `key`
- `description`

`user_role_assignments`

- `id`
- `tenant_id`
- `user_id`
- `role_id`
- `assigned_by`
- `assigned_at`

`identity_provider_configs`

- `id`
- `tenant_id`
- `provider_type`: google_oidc, oidc, saml
- `issuer`
- `client_id`
- `status`
- `created_at`
- `updated_at`

`audit_events`

- `id`
- `tenant_id`
- `user_id`
- `event_type`
- `resource_type`
- `resource_id`
- `channel`
- `metadata`
- `created_at`

### Channel Messaging

`channel_accounts`

- `id`
- `tenant_id`
- `channel`: web, telegram, whatsapp, apple_messages_business
- `display_name`
- `status`
- `config_ref`
- `created_at`
- `updated_at`

`channel_identities`

- `id`
- `tenant_id`
- `user_id`
- `channel`
- `channel_user_id`
- `status`
- `linked_at`
- `last_seen_at`

`channel_threads`

- `id`
- `tenant_id`
- `user_id`
- `channel`
- `channel_thread_id`
- `status`
- `created_at`
- `updated_at`

`channel_messages`

- `id`
- `tenant_id`
- `user_id`
- `channel_thread_id`
- `direction`
- `message_type`
- `body`
- `metadata`
- `created_at`

`delivery_attempts`

- `id`
- `tenant_id`
- `user_id`
- `channel`
- `status`
- `delivery_ref`
- `error`
- `created_at`

`access_requests`

- `id`
- `tenant_id`
- `channel`
- `requested_identity`
- `requested_email`
- `status`
- `requested_at`
- `reviewed_by`
- `reviewed_at`

### Model Providers

`model_provider_configs`

- `id`
- `tenant_id`
- `provider`
- `status`
- `secret_ref`
- `capabilities`
- `default_aliases`
- `created_at`
- `updated_at`

`model_provider_runs`

- `id`
- `tenant_id`
- `run_id`
- `provider`
- `model_alias`
- `provider_model_id`
- `task_profile`
- `selection_reason`
- `input_tokens`
- `output_tokens`
- `estimated_cost`
- `latency_ms`
- `quality_status`
- `created_at`

### Competitor Registry

`competitors`

- `id`
- `tenant_id`
- `name`
- `domain`
- `category`
- `priority`
- `status`
- `known_products`
- `known_executives`
- `created_at`
- `updated_at`

### Source Ledger

`sources`

- `id`
- `competitor_id`
- `source_family`
- `url`
- `normalized_url`
- `title`
- `status`: active, candidate, blocked, missing, retired, needs_credentials, not_applicable
- `first_seen_at`
- `last_seen_at`
- `last_checked_at`
- `missing_streak_days`
- `retired_at`
- `evidence`

`source_scan_runs`

- `id`
- `started_at`
- `finished_at`
- `status`
- `competitors_scanned`
- `sources_found`
- `sources_added`
- `sources_retired`
- `errors`

`source_observations`

- `id`
- `source_id`
- `scan_run_id`
- `observed_at`
- `status`
- `http_status`
- `content_hash`
- `notes`

`source_candidates`

- `id`
- `competitor_id`
- `url`
- `source_family`
- `confidence`
- `reason`
- `status`
- `first_seen_at`
- `promoted_at`

`competitor_scan_rollups`

- `id`
- `competitor_id`
- `scan_date`
- `active_source_count`
- `candidate_source_count`
- `missing_source_count`
- `coverage_score`
- `last_scan_at`

### Evidence Collection

`intel_fetch_runs`

- `id`
- `started_at`
- `finished_at`
- `status`
- `source_count`
- `snapshot_count`
- `finding_count`
- `errors`

`source_snapshots`

- `id`
- `source_id`
- `fetch_run_id`
- `captured_at`
- `content_hash`
- `title`
- `text_path`
- `raw_path`
- `metadata`

`raw_findings`

- `id`
- `competitor_id`
- `source_id`
- `snapshot_id`
- `finding_type`
- `observed_at`
- `summary`
- `evidence_url`
- `evidence_text`
- `confidence`
- `quality_status`

### Speech, Social, And Content Intelligence

`executive_speech_signals`

- `id`
- `competitor_id`
- `executive_name`
- `executive_role`
- `source_url`
- `published_at`
- `quote`
- `claim`
- `market_signal`
- `confidence`
- `evidence_finding_id`

`gtm_narrative_signals`

- `id`
- `competitor_id`
- `source_id`
- `theme`
- `audience`
- `tone`
- `positioning_shift`
- `campaign_type`
- `observed_at`
- `evidence_finding_id`

`social_observations`

- `id`
- `competitor_id`
- `platform`
- `source_url`
- `posted_at`
- `text_summary`
- `engagement_public_count`
- `theme`
- `audience`
- `evidence_limit`

`content_observations`

- `id`
- `competitor_id`
- `content_url`
- `content_type`
- `topic`
- `hook`
- `format`
- `audience`
- `published_at`
- `observed_at`
- `traction_signal`

`content_recommendations`

- `id`
- `week_start`
- `title`
- `target_audience`
- `hook`
- `layout`
- `recommended_format`
- `why_now`
- `evidence_ids`
- `confidence`
- `status`

`weekly_content_plan`

- `id`
- `week_start`
- `summary`
- `recommendation_ids`
- `review_status`
- `created_at`
- `updated_at`

### Semantic Layer

`semantic_facts`

- `id`
- `competitor_id`
- `fact_type`
- `statement`
- `evidence_ids`
- `confidence`
- `first_seen_at`
- `last_seen_at`

`semantic_deltas`

- `id`
- `competitor_id`
- `delta_type`
- `materiality_score`
- `what_changed`
- `why_it_matters`
- `implication`
- `recommended_action`
- `evidence_ids`
- `quality_status`
- `confidence`
- `created_at`

`suppressed_diagnostics`

- `id`
- `reason`
- `finding_ids`
- `suppressed_at`
- `notes`

### Claims And Theses

`claims`

- `id`
- `competitor_id`
- `claim_text`
- `claim_type`
- `first_seen_at`
- `last_seen_at`
- `evidence_ids`
- `algolia_response_status`

`claim_observations`

- `id`
- `claim_id`
- `source_id`
- `observed_at`
- `context`
- `evidence_url`

`competitor_theses`

- `id`
- `competitor_id`
- `thesis`
- `status`
- `confidence`
- `supporting_delta_ids`
- `contradicting_delta_ids`
- `updated_at`

### Workflow And Quality

`action_items`

- `id`
- `owner`
- `recommendation`
- `evidence_ids`
- `source_delta_ids`
- `priority`
- `confidence`
- `due_window`
- `status`
- `report_id`
- `created_at`
- `updated_at`

`quality_reviews`

- `id`
- `run_id`
- `review_type`
- `status`
- `findings`
- `required_fixes`
- `reviewed_at`

`false_negative_audits`

- `id`
- `run_id`
- `quiet_period_days`
- `coverage_score`
- `audit_status`
- `risk_reason`
- `recommended_recheck`
- `created_at`

`learning_events`

- `id`
- `run_id`
- `event_type`
- `lesson`
- `proposed_change`
- `status`
- `created_at`

`improvement_queue`

- `id`
- `source`
- `problem`
- `proposed_fix`
- `priority`
- `status`
- `created_at`

### Delivery And Dashboard

`bot_deliveries`

- `id`
- `cadence`
- `bot_profile`
- `channel`
- `recipient_redacted`
- `status`
- `markdown_path`
- `html_path`
- `dashboard_url`
- `report_id`
- `error`
- `created_at`

`dashboard_state`

- `id`
- `generated_at`
- `daily_state`
- `weekly_state`
- `material_delta_ids`
- `action_item_ids`
- `delivery_ids`
- `coverage_limits`
- `json_path`

## Invariants

- No report claim without evidence ids.
- No action owner without an `action_items` row.
- No "market quiet" without coverage score and false-negative audit status.
- No content recommendation without source observations or content traction signals.
- No delivery claim without a `bot_deliveries` row.
- No model escalation without run metadata.
- No channel request may access data before identity resolution and ACL evaluation.
- No provider-specific model id may be hardcoded into skill logic.
