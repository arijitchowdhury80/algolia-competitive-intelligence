-- ============================================================================
-- CI-OS (Argus) — Postgres schema, v1 baseline
-- Multi-tenant Competitive Intelligence operating system.
--
-- Decisions implemented (Gate 0 §2 D1/D2, LOCKED):
--   * Dedicated Postgres 16, database `cios`.
--   * tenant_id NOT NULL on every tenant-scoped table + Postgres RLS.
--   * `permissions` is a GLOBAL catalog (no tenant_id); `roles` is tenant-scoped.
--   * `model_provider_configs` (not tenant_model_provider_configs) WITH tenant_id.
--   * 6 previously-unspecified tables defined: source_health_events,
--     content_traction_signals, content_plan_reviews, groups,
--     group_role_mappings, reports (modeled on V0 report_index).
--   * *_ids / metadata / capabilities fields are JSONB; evidence arrays carry
--     CHECK (jsonb_array_length(...) > 0) where the invariant demands evidence.
--   * No provider model ids and no secrets anywhere in this file.
--
-- Migration policy: this file is the v1 baseline (apply once on a fresh DB).
-- From v2 onward, schema changes go through Alembic migrations. See README.md.
--
-- RLS contract: every tenant-scoped table has RLS ENABLED + FORCED with a
-- policy USING (tenant_id = current_setting('app.tenant_id')::bigint). The
-- application connects as role `cios_app` (NOT superuser, NOT BYPASSRLS) and
-- MUST `SET app.tenant_id = '<id>'` per connection/transaction. Superuser
-- (postgres) bypasses RLS and is used for schema + seed only.
-- ============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- Application role. Owns no objects; subject to RLS. Password is set out of
-- band (deploy step / env), never in this file.
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cios_app') THEN
        CREATE ROLE cios_app LOGIN NOBYPASSRLS;
    ELSE
        ALTER ROLE cios_app NOBYPASSRLS;
    END IF;
END
$$;

-- ============================================================================
-- GLOBAL (non-tenant) tables — no RLS.
-- ============================================================================

-- Tenants: the top-level isolation boundary (Algolia, Spryker, Amplitude, ...).
CREATE TABLE tenants (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name           text        NOT NULL UNIQUE,
    slug           text        NOT NULL UNIQUE,
    status         text        NOT NULL DEFAULT 'active'
                     CHECK (status IN ('active','suspended','retired')),
    primary_domain text,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now()
);

-- Permissions: GLOBAL capability catalog referenced by tenant-scoped roles.
CREATE TABLE permissions (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    key         text NOT NULL UNIQUE,
    description text
);

-- ============================================================================
-- IDENTITY, ROLES, ACL (tenant-scoped)
-- ============================================================================

-- Users: canonical CI-OS identity within a tenant (channels resolve to this).
CREATE TABLE users (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id    bigint NOT NULL REFERENCES tenants(id),
    email        text   NOT NULL,
    display_name text,
    status       text   NOT NULL DEFAULT 'active'
                   CHECK (status IN ('invited','active','suspended','offboarded')),
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, email)
);
CREATE INDEX idx_users_tenant ON users (tenant_id);

-- User identities: SSO/OIDC/SAML subjects mapped to a canonical user.
CREATE TABLE user_identities (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id        bigint NOT NULL REFERENCES tenants(id),
    user_id          bigint NOT NULL REFERENCES users(id),
    provider         text   NOT NULL,
    provider_subject text   NOT NULL,
    email            text,
    linked_at        timestamptz NOT NULL DEFAULT now(),
    last_seen_at     timestamptz,
    UNIQUE (tenant_id, provider, provider_subject)
);
CREATE INDEX idx_user_identities_tenant_user ON user_identities (tenant_id, user_id);

-- Roles: tenant-scoped named bundles of permissions (RBAC).
CREATE TABLE roles (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id   bigint NOT NULL REFERENCES tenants(id),
    name        text   NOT NULL,
    description text,
    UNIQUE (tenant_id, name)
);
CREATE INDEX idx_roles_tenant ON roles (tenant_id);

-- Role -> permission grants (tenant-scoped join; permissions themselves global).
CREATE TABLE role_permissions (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id     bigint NOT NULL REFERENCES tenants(id),
    role_id       bigint NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id bigint NOT NULL REFERENCES permissions(id),
    UNIQUE (tenant_id, role_id, permission_id)
);
CREATE INDEX idx_role_permissions_tenant_role ON role_permissions (tenant_id, role_id);

-- User -> role assignments (tenant-scoped).
CREATE TABLE user_role_assignments (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id   bigint NOT NULL REFERENCES tenants(id),
    user_id     bigint NOT NULL REFERENCES users(id),
    role_id     bigint NOT NULL REFERENCES roles(id),
    assigned_by bigint REFERENCES users(id),
    assigned_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, user_id, role_id)
);
CREATE INDEX idx_user_role_assignments_tenant_user ON user_role_assignments (tenant_id, user_id);

-- Groups: IdP-provisioned groups (SCIM/JIT) that map to roles.
CREATE TABLE groups (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id    bigint NOT NULL REFERENCES tenants(id),
    external_id  text,
    name         text   NOT NULL,
    source       text   NOT NULL DEFAULT 'manual'
                   CHECK (source IN ('manual','scim','oidc','saml')),
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, name)
);
CREATE INDEX idx_groups_tenant ON groups (tenant_id);

-- Group -> role mapping: how IdP groups grant CI-OS roles.
CREATE TABLE group_role_mappings (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id  bigint NOT NULL REFERENCES tenants(id),
    group_id   bigint NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    role_id    bigint NOT NULL REFERENCES roles(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, group_id, role_id)
);
CREATE INDEX idx_group_role_mappings_tenant_group ON group_role_mappings (tenant_id, group_id);

-- Identity provider configs: per-tenant SSO wiring (issuer/client only; secrets by ref).
CREATE TABLE identity_provider_configs (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id     bigint NOT NULL REFERENCES tenants(id),
    provider_type text   NOT NULL CHECK (provider_type IN ('google_oidc','oidc','saml')),
    issuer        text,
    client_id     text,
    status        text   NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active','disabled')),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_idp_configs_tenant ON identity_provider_configs (tenant_id);

-- Audit events: structured operator/compliance trail (logins, ACL denials, admin changes).
CREATE TABLE audit_events (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id     bigint NOT NULL REFERENCES tenants(id),
    user_id       bigint REFERENCES users(id),
    event_type    text   NOT NULL,
    resource_type text,
    resource_id   text,
    channel       text,
    metadata      jsonb  NOT NULL DEFAULT '{}'::jsonb,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_events_tenant_created ON audit_events (tenant_id, created_at DESC);

-- ============================================================================
-- CHANNEL MESSAGING (tenant-scoped)
-- ============================================================================

-- Channel accounts: a tenant's configured presence on a channel (bot, number, ...).
CREATE TABLE channel_accounts (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id    bigint NOT NULL REFERENCES tenants(id),
    channel      text   NOT NULL
                   CHECK (channel IN ('web','telegram','whatsapp','apple_messages_business','email')),
    display_name text,
    status       text   NOT NULL DEFAULT 'active'
                   CHECK (status IN ('active','disabled')),
    config_ref   text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_channel_accounts_tenant ON channel_accounts (tenant_id);

-- Channel identities: a user's per-channel handle (Telegram user id, etc.).
CREATE TABLE channel_identities (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id       bigint NOT NULL REFERENCES tenants(id),
    user_id         bigint REFERENCES users(id),
    channel         text   NOT NULL
                      CHECK (channel IN ('web','telegram','whatsapp','apple_messages_business','email')),
    channel_user_id text   NOT NULL,
    status          text   NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending','linked','blocked','unlinked')),
    linked_at       timestamptz,
    last_seen_at    timestamptz,
    UNIQUE (tenant_id, channel, channel_user_id)
);
CREATE INDEX idx_channel_identities_tenant_user ON channel_identities (tenant_id, user_id);

-- Channel threads: conversation containers per channel.
CREATE TABLE channel_threads (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id         bigint NOT NULL REFERENCES tenants(id),
    user_id           bigint REFERENCES users(id),
    channel           text   NOT NULL,
    channel_thread_id text   NOT NULL,
    status            text   NOT NULL DEFAULT 'open'
                        CHECK (status IN ('open','closed')),
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, channel, channel_thread_id)
);
CREATE INDEX idx_channel_threads_tenant_user ON channel_threads (tenant_id, user_id);

-- Channel messages: normalized inbound/outbound messages.
CREATE TABLE channel_messages (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id         bigint NOT NULL REFERENCES tenants(id),
    user_id           bigint REFERENCES users(id),
    channel_thread_id bigint NOT NULL REFERENCES channel_threads(id),
    direction         text   NOT NULL CHECK (direction IN ('inbound','outbound')),
    message_type      text   NOT NULL DEFAULT 'text',
    body              text,
    metadata          jsonb  NOT NULL DEFAULT '{}'::jsonb,
    created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_channel_messages_tenant_thread ON channel_messages (tenant_id, channel_thread_id, created_at);

-- Delivery attempts: per-channel outbound delivery state (status webhooks land here).
CREATE TABLE delivery_attempts (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id    bigint NOT NULL REFERENCES tenants(id),
    user_id      bigint REFERENCES users(id),
    channel      text   NOT NULL,
    status       text   NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending','sent','delivered','read','failed')),
    delivery_ref text,
    error        text,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_delivery_attempts_tenant ON delivery_attempts (tenant_id, created_at DESC);

-- Access requests: unlinked-channel access asks awaiting operator review.
CREATE TABLE access_requests (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id          bigint NOT NULL REFERENCES tenants(id),
    channel            text   NOT NULL,
    requested_identity text,
    requested_email    text,
    status             text   NOT NULL DEFAULT 'pending'
                         CHECK (status IN ('pending','approved','denied')),
    requested_at       timestamptz NOT NULL DEFAULT now(),
    reviewed_by        bigint REFERENCES users(id),
    reviewed_at        timestamptz
);
CREATE INDEX idx_access_requests_tenant_status ON access_requests (tenant_id, status);

-- ============================================================================
-- MODEL PROVIDERS (tenant-scoped)
-- ============================================================================

-- Model provider configs: per-tenant provider policy (secrets by ref; no model ids).
CREATE TABLE model_provider_configs (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id       bigint NOT NULL REFERENCES tenants(id),
    provider        text   NOT NULL,
    status          text   NOT NULL DEFAULT 'active'
                      CHECK (status IN ('active','disabled')),
    secret_ref      text,
    capabilities    jsonb  NOT NULL DEFAULT '[]'::jsonb,
    default_aliases jsonb  NOT NULL DEFAULT '{}'::jsonb,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, provider)
);
CREATE INDEX idx_model_provider_configs_tenant ON model_provider_configs (tenant_id);

-- Model provider runs: per-call telemetry for cost/quality governance (aliases only, no hardcoded ids).
CREATE TABLE model_provider_runs (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id         bigint NOT NULL REFERENCES tenants(id),
    run_id            text,
    provider          text   NOT NULL,
    model_alias       text   NOT NULL,
    provider_model_id text,
    task_profile      text,
    selection_reason  text,
    input_tokens      integer,
    output_tokens     integer,
    estimated_cost    numeric(12,6),
    latency_ms        integer,
    quality_status    text,
    created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_model_provider_runs_tenant_created ON model_provider_runs (tenant_id, created_at DESC);

-- ============================================================================
-- COMPETITOR REGISTRY + SOURCE LEDGER (tenant-scoped)
-- ============================================================================

-- Competitors: per-tenant competitor registry.
CREATE TABLE competitors (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id        bigint NOT NULL REFERENCES tenants(id),
    name             text   NOT NULL,
    domain           text,
    category         text,
    priority         integer NOT NULL DEFAULT 3,
    status           text   NOT NULL DEFAULT 'active'
                       CHECK (status IN ('active','paused','retired')),
    known_products   jsonb  NOT NULL DEFAULT '[]'::jsonb,
    known_executives jsonb  NOT NULL DEFAULT '[]'::jsonb,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, name)
);
CREATE INDEX idx_competitors_tenant ON competitors (tenant_id);

-- Sources: the monitored source ledger per competitor.
CREATE TABLE sources (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id           bigint NOT NULL REFERENCES tenants(id),
    competitor_id       bigint NOT NULL REFERENCES competitors(id),
    source_family       text   NOT NULL,
    url                 text   NOT NULL,
    normalized_url      text   NOT NULL,
    title               text,
    status              text   NOT NULL DEFAULT 'candidate'
                          CHECK (status IN ('active','candidate','blocked','missing','retired','needs_credentials','not_applicable')),
    first_seen_at       timestamptz NOT NULL DEFAULT now(),
    last_seen_at        timestamptz,
    last_checked_at     timestamptz,
    missing_streak_days integer NOT NULL DEFAULT 0,
    retired_at          timestamptz,
    evidence            jsonb  NOT NULL DEFAULT '{}'::jsonb,
    -- upsert-not-duplicate invariant (Gate 2): one row per normalized url per tenant.
    UNIQUE (tenant_id, normalized_url)
);
CREATE INDEX idx_sources_tenant_competitor ON sources (tenant_id, competitor_id);
CREATE INDEX idx_sources_tenant_status ON sources (tenant_id, status);

-- Source scan runs: one row per source-hunter sweep.
CREATE TABLE source_scan_runs (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id           bigint NOT NULL REFERENCES tenants(id),
    started_at          timestamptz NOT NULL DEFAULT now(),
    finished_at         timestamptz,
    status              text   NOT NULL DEFAULT 'running'
                          CHECK (status IN ('running','completed','failed')),
    competitors_scanned integer,
    sources_found       integer,
    sources_added       integer,
    sources_retired     integer,
    errors              jsonb  NOT NULL DEFAULT '[]'::jsonb
);
CREATE INDEX idx_source_scan_runs_tenant ON source_scan_runs (tenant_id, started_at DESC);

-- Source observations: per-scan liveness observation of a source.
CREATE TABLE source_observations (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id    bigint NOT NULL REFERENCES tenants(id),
    source_id    bigint NOT NULL REFERENCES sources(id),
    scan_run_id  bigint REFERENCES source_scan_runs(id),
    observed_at  timestamptz NOT NULL DEFAULT now(),
    status       text,
    http_status  integer,
    content_hash text,
    notes        text
);
CREATE INDEX idx_source_observations_tenant_source ON source_observations (tenant_id, source_id, observed_at DESC);

-- Source candidates: discovered-but-unpromoted source URLs.
CREATE TABLE source_candidates (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id     bigint NOT NULL REFERENCES tenants(id),
    competitor_id bigint NOT NULL REFERENCES competitors(id),
    url           text   NOT NULL,
    source_family text,
    confidence    numeric(4,3),
    reason        text,
    status        text   NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','promoted','rejected')),
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    promoted_at   timestamptz
);
CREATE INDEX idx_source_candidates_tenant_competitor ON source_candidates (tenant_id, competitor_id);

-- Competitor scan rollups: per-competitor daily coverage snapshot.
CREATE TABLE competitor_scan_rollups (
    id                    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id             bigint NOT NULL REFERENCES tenants(id),
    competitor_id         bigint NOT NULL REFERENCES competitors(id),
    scan_date             date   NOT NULL,
    active_source_count   integer,
    candidate_source_count integer,
    missing_source_count  integer,
    coverage_score        numeric(5,4),
    last_scan_at          timestamptz,
    UNIQUE (tenant_id, competitor_id, scan_date)
);
CREATE INDEX idx_competitor_scan_rollups_tenant ON competitor_scan_rollups (tenant_id, scan_date DESC);

-- Source health events: fetch failures / recoveries — a miss is a failure event, not a quiet day.
CREATE TABLE source_health_events (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id    bigint NOT NULL REFERENCES tenants(id),
    source_id    bigint NOT NULL REFERENCES sources(id),
    fetch_run_id bigint,
    event_type   text   NOT NULL
                   CHECK (event_type IN ('ok','fetch_error','http_error','timeout','empty','recovered','retired')),
    http_status  integer,
    detail       text,
    metadata     jsonb  NOT NULL DEFAULT '{}'::jsonb,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_source_health_events_tenant_source ON source_health_events (tenant_id, source_id, created_at DESC);

-- ============================================================================
-- EVIDENCE COLLECTION (tenant-scoped)
-- ============================================================================

-- Intel fetch runs: one row per collection sweep.
CREATE TABLE intel_fetch_runs (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id      bigint NOT NULL REFERENCES tenants(id),
    started_at     timestamptz NOT NULL DEFAULT now(),
    finished_at    timestamptz,
    status         text   NOT NULL DEFAULT 'running'
                     CHECK (status IN ('running','completed','failed')),
    source_count   integer,
    snapshot_count integer,
    finding_count  integer,
    errors         jsonb  NOT NULL DEFAULT '[]'::jsonb
);
CREATE INDEX idx_intel_fetch_runs_tenant ON intel_fetch_runs (tenant_id, started_at DESC);

-- Source snapshots: captured content per source per fetch run (evidence store).
CREATE TABLE source_snapshots (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id    bigint NOT NULL REFERENCES tenants(id),
    source_id    bigint NOT NULL REFERENCES sources(id),
    fetch_run_id bigint REFERENCES intel_fetch_runs(id),
    captured_at  timestamptz NOT NULL DEFAULT now(),
    content_hash text,
    title        text,
    text_path    text,
    raw_path     text,
    metadata     jsonb  NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX idx_source_snapshots_tenant_source ON source_snapshots (tenant_id, source_id, captured_at DESC);

-- Raw findings: atomic evidence units extracted from snapshots (no claims yet).
CREATE TABLE raw_findings (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id      bigint NOT NULL REFERENCES tenants(id),
    competitor_id  bigint NOT NULL REFERENCES competitors(id),
    source_id      bigint REFERENCES sources(id),
    snapshot_id    bigint REFERENCES source_snapshots(id),
    finding_type   text,
    observed_at    timestamptz NOT NULL DEFAULT now(),
    summary        text,
    evidence_url   text   NOT NULL,   -- evidence-or-silence: a finding must cite a URL
    evidence_text  text,
    confidence     numeric(4,3),
    quality_status text   NOT NULL DEFAULT 'unreviewed'
                     CHECK (quality_status IN ('unreviewed','accepted','rejected','suppressed'))
);
CREATE INDEX idx_raw_findings_tenant_competitor ON raw_findings (tenant_id, competitor_id, observed_at DESC);

-- ============================================================================
-- SPEECH, SOCIAL, CONTENT INTELLIGENCE (tenant-scoped)
-- ============================================================================

-- Executive speech signals: exec quotes/claims with source evidence.
CREATE TABLE executive_speech_signals (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id           bigint NOT NULL REFERENCES tenants(id),
    competitor_id       bigint NOT NULL REFERENCES competitors(id),
    executive_name      text,
    executive_role      text,
    source_url          text   NOT NULL,
    published_at        timestamptz,
    quote               text,
    claim               text,
    market_signal       text,
    confidence          numeric(4,3),
    evidence_finding_id bigint REFERENCES raw_findings(id)
);
CREATE INDEX idx_exec_speech_tenant_competitor ON executive_speech_signals (tenant_id, competitor_id, published_at DESC);

-- GTM narrative signals: positioning/campaign shifts observed on sources.
CREATE TABLE gtm_narrative_signals (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id           bigint NOT NULL REFERENCES tenants(id),
    competitor_id       bigint NOT NULL REFERENCES competitors(id),
    source_id           bigint REFERENCES sources(id),
    theme               text,
    audience            text,
    tone                text,
    positioning_shift   text,
    campaign_type       text,
    observed_at         timestamptz NOT NULL DEFAULT now(),
    evidence_finding_id bigint REFERENCES raw_findings(id)
);
CREATE INDEX idx_gtm_signals_tenant_competitor ON gtm_narrative_signals (tenant_id, competitor_id, observed_at DESC);

-- Social observations: public social posts with disclosed engagement only.
CREATE TABLE social_observations (
    id                     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id              bigint NOT NULL REFERENCES tenants(id),
    competitor_id          bigint NOT NULL REFERENCES competitors(id),
    platform               text,
    source_url             text   NOT NULL,
    posted_at              timestamptz,
    text_summary           text,
    engagement_public_count integer,
    theme                  text,
    audience               text,
    evidence_limit         text
);
CREATE INDEX idx_social_observations_tenant_competitor ON social_observations (tenant_id, competitor_id, posted_at DESC);

-- Content observations: competitor content pieces observed in the wild.
CREATE TABLE content_observations (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id       bigint NOT NULL REFERENCES tenants(id),
    competitor_id   bigint NOT NULL REFERENCES competitors(id),
    content_url     text   NOT NULL,
    content_type    text,
    topic           text,
    hook            text,
    format          text,
    audience        text,
    published_at    timestamptz,
    observed_at     timestamptz NOT NULL DEFAULT now(),
    traction_signal text
);
CREATE INDEX idx_content_observations_tenant_competitor ON content_observations (tenant_id, competitor_id, observed_at DESC);

-- Content traction signals: measured engagement/traction backing a content observation.
CREATE TABLE content_traction_signals (
    id                    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id             bigint NOT NULL REFERENCES tenants(id),
    content_observation_id bigint REFERENCES content_observations(id),
    competitor_id         bigint REFERENCES competitors(id),
    signal_type           text   NOT NULL,
    metric_value          numeric(18,4),
    metric_unit           text,
    source_url            text   NOT NULL,
    observed_at           timestamptz NOT NULL DEFAULT now(),
    metadata              jsonb  NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX idx_content_traction_tenant ON content_traction_signals (tenant_id, observed_at DESC);

-- Content recommendations: weekly content ideas — must cite evidence (invariant).
CREATE TABLE content_recommendations (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id         bigint NOT NULL REFERENCES tenants(id),
    week_start        date   NOT NULL,
    title             text   NOT NULL,
    target_audience   text,
    hook              text,
    layout            text,
    recommended_format text,
    why_now           text,
    evidence_ids      jsonb  NOT NULL DEFAULT '[]'::jsonb,
    confidence        numeric(4,3),
    status            text   NOT NULL DEFAULT 'proposed'
                        CHECK (status IN ('proposed','approved','rejected','shipped')),
    created_at        timestamptz NOT NULL DEFAULT now(),
    -- invariant: no content recommendation without source/traction evidence.
    CONSTRAINT content_rec_needs_evidence CHECK (jsonb_array_length(evidence_ids) > 0)
);
CREATE INDEX idx_content_recommendations_tenant_week ON content_recommendations (tenant_id, week_start DESC);

-- Weekly content plan: the curated set of recommendations for a week.
CREATE TABLE weekly_content_plan (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id          bigint NOT NULL REFERENCES tenants(id),
    week_start         date   NOT NULL,
    summary            text,
    recommendation_ids jsonb  NOT NULL DEFAULT '[]'::jsonb,
    review_status      text   NOT NULL DEFAULT 'draft'
                         CHECK (review_status IN ('draft','in_review','approved','published')),
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, week_start)
);
CREATE INDEX idx_weekly_content_plan_tenant ON weekly_content_plan (tenant_id, week_start DESC);

-- Content plan reviews: human review decisions on a weekly content plan.
CREATE TABLE content_plan_reviews (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id     bigint NOT NULL REFERENCES tenants(id),
    plan_id       bigint NOT NULL REFERENCES weekly_content_plan(id) ON DELETE CASCADE,
    reviewer_id   bigint REFERENCES users(id),
    decision      text   NOT NULL CHECK (decision IN ('approved','changes_requested','rejected')),
    notes         text,
    reviewed_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_content_plan_reviews_tenant_plan ON content_plan_reviews (tenant_id, plan_id);

-- ============================================================================
-- SEMANTIC LAYER (tenant-scoped)
-- ============================================================================

-- Semantic facts: durable statements about a competitor with evidence.
CREATE TABLE semantic_facts (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id     bigint NOT NULL REFERENCES tenants(id),
    competitor_id bigint NOT NULL REFERENCES competitors(id),
    fact_type     text,
    statement     text   NOT NULL,
    evidence_ids  jsonb  NOT NULL DEFAULT '[]'::jsonb,
    confidence    numeric(4,3),
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at  timestamptz,
    -- a fact is an assertion; it must be evidence-backed.
    CONSTRAINT semantic_fact_needs_evidence CHECK (jsonb_array_length(evidence_ids) > 0)
);
CREATE INDEX idx_semantic_facts_tenant_competitor ON semantic_facts (tenant_id, competitor_id);

-- Semantic deltas: scored changes; published rows MUST carry evidence (invariant).
CREATE TABLE semantic_deltas (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id         bigint NOT NULL REFERENCES tenants(id),
    competitor_id     bigint NOT NULL REFERENCES competitors(id),
    delta_type        text,
    materiality_score numeric(5,4),
    what_changed      text,
    why_it_matters    text,
    implication       text,
    recommended_action text,
    evidence_ids      jsonb  NOT NULL DEFAULT '[]'::jsonb,
    quality_status    text   NOT NULL DEFAULT 'draft'
                        CHECK (quality_status IN ('draft','review','published','suppressed','rejected')),
    confidence        numeric(4,3),
    created_at        timestamptz NOT NULL DEFAULT now(),
    -- evidence-or-silence: a published delta must cite evidence.
    CONSTRAINT semantic_delta_published_needs_evidence
        CHECK (quality_status <> 'published' OR jsonb_array_length(evidence_ids) > 0)
);
CREATE INDEX idx_semantic_deltas_tenant_competitor ON semantic_deltas (tenant_id, competitor_id, created_at DESC);
CREATE INDEX idx_semantic_deltas_tenant_status ON semantic_deltas (tenant_id, quality_status);

-- Suppressed diagnostics: findings intentionally suppressed, with reason (audit trail).
CREATE TABLE suppressed_diagnostics (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id     bigint NOT NULL REFERENCES tenants(id),
    reason        text   NOT NULL,
    finding_ids   jsonb  NOT NULL DEFAULT '[]'::jsonb,
    suppressed_at timestamptz NOT NULL DEFAULT now(),
    notes         text
);
CREATE INDEX idx_suppressed_diagnostics_tenant ON suppressed_diagnostics (tenant_id, suppressed_at DESC);

-- ============================================================================
-- CLAIMS AND THESES (tenant-scoped)
-- ============================================================================

-- Claims: competitor claims tracked over time — must carry evidence (invariant).
CREATE TABLE claims (
    id                     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id              bigint NOT NULL REFERENCES tenants(id),
    competitor_id          bigint NOT NULL REFERENCES competitors(id),
    claim_text             text   NOT NULL,
    claim_type             text,
    first_seen_at          timestamptz NOT NULL DEFAULT now(),
    last_seen_at           timestamptz,
    evidence_ids           jsonb  NOT NULL DEFAULT '[]'::jsonb,
    algolia_response_status text,
    -- no claim without evidence ids.
    CONSTRAINT claim_needs_evidence CHECK (jsonb_array_length(evidence_ids) > 0)
);
CREATE INDEX idx_claims_tenant_competitor ON claims (tenant_id, competitor_id);

-- Claim observations: each time a claim was seen, with context + evidence url.
CREATE TABLE claim_observations (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id    bigint NOT NULL REFERENCES tenants(id),
    claim_id     bigint NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    source_id    bigint REFERENCES sources(id),
    observed_at  timestamptz NOT NULL DEFAULT now(),
    context      text,
    evidence_url text   NOT NULL
);
CREATE INDEX idx_claim_observations_tenant_claim ON claim_observations (tenant_id, claim_id);

-- Competitor theses: living hypotheses with supporting/contradicting deltas.
CREATE TABLE competitor_theses (
    id                    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id             bigint NOT NULL REFERENCES tenants(id),
    competitor_id         bigint NOT NULL REFERENCES competitors(id),
    thesis                text   NOT NULL,
    status                text   NOT NULL DEFAULT 'active'
                            CHECK (status IN ('active','confirmed','weakened','retired')),
    confidence            numeric(4,3),
    supporting_delta_ids  jsonb  NOT NULL DEFAULT '[]'::jsonb,
    contradicting_delta_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
    updated_at            timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_competitor_theses_tenant_competitor ON competitor_theses (tenant_id, competitor_id);

-- ============================================================================
-- WORKFLOW AND QUALITY (tenant-scoped)
-- ============================================================================

-- Reports: rendered daily/weekly report index (modeled on V0 report_index).
CREATE TABLE reports (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id     bigint NOT NULL REFERENCES tenants(id),
    cadence       text   NOT NULL CHECK (cadence IN ('daily','weekly','ad_hoc')),
    report_date   date   NOT NULL,
    title         text,
    status        text   NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft','rendered','delivered')),
    markdown_path text,
    html_path     text,
    json_path     text,
    summary       text,
    metadata      jsonb  NOT NULL DEFAULT '{}'::jsonb,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_reports_tenant_date ON reports (tenant_id, report_date DESC);

-- Action items: the decision layer — every owned action has a row (invariant).
CREATE TABLE action_items (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id       bigint NOT NULL REFERENCES tenants(id),
    owner           text,
    recommendation  text   NOT NULL,
    evidence_ids    jsonb  NOT NULL DEFAULT '[]'::jsonb,
    source_delta_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
    priority        text,
    confidence      numeric(4,3),
    due_window      text,
    status          text   NOT NULL DEFAULT 'open'
                      CHECK (status IN ('open','in_progress','done','dismissed')),
    report_id       bigint REFERENCES reports(id),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    -- every routed action must trace to evidence.
    CONSTRAINT action_item_needs_evidence CHECK (jsonb_array_length(evidence_ids) > 0)
);
CREATE INDEX idx_action_items_tenant_status ON action_items (tenant_id, status);

-- Quality reviews: per-run quality gate results.
CREATE TABLE quality_reviews (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id      bigint NOT NULL REFERENCES tenants(id),
    run_id         text,
    review_type    text,
    status         text   NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending','passed','failed')),
    findings       jsonb  NOT NULL DEFAULT '[]'::jsonb,
    required_fixes jsonb  NOT NULL DEFAULT '[]'::jsonb,
    reviewed_at    timestamptz
);
CREATE INDEX idx_quality_reviews_tenant ON quality_reviews (tenant_id, reviewed_at DESC);

-- False negative audits: coverage-aware "was it really quiet?" checks.
CREATE TABLE false_negative_audits (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id         bigint NOT NULL REFERENCES tenants(id),
    run_id            text,
    quiet_period_days integer,
    coverage_score    numeric(5,4),
    audit_status      text   NOT NULL DEFAULT 'pending'
                        CHECK (audit_status IN ('pending','clean','at_risk','failed')),
    risk_reason       text,
    recommended_recheck jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_false_negative_audits_tenant ON false_negative_audits (tenant_id, created_at DESC);

-- Learning events: lessons + proposed changes from a run.
CREATE TABLE learning_events (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id      bigint NOT NULL REFERENCES tenants(id),
    run_id         text,
    event_type     text,
    lesson         text,
    proposed_change text,
    status         text   NOT NULL DEFAULT 'open'
                     CHECK (status IN ('open','applied','rejected')),
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_learning_events_tenant ON learning_events (tenant_id, created_at DESC);

-- Improvement queue: gated code/threshold/policy change proposals.
CREATE TABLE improvement_queue (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id    bigint NOT NULL REFERENCES tenants(id),
    source       text,
    problem      text   NOT NULL,
    proposed_fix text,
    priority     text,
    status       text   NOT NULL DEFAULT 'open'
                   CHECK (status IN ('open','approved','applied','rejected')),
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_improvement_queue_tenant_status ON improvement_queue (tenant_id, status);

-- ============================================================================
-- DELIVERY AND DASHBOARD (tenant-scoped)
-- ============================================================================

-- Bot deliveries: one row per outbound brief; records TRUE send state (Gate 6 fix).
CREATE TABLE bot_deliveries (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id         bigint NOT NULL REFERENCES tenants(id),
    cadence           text   NOT NULL CHECK (cadence IN ('daily','weekly','ad_hoc','alert')),
    bot_profile       text,
    channel           text   NOT NULL,
    recipient_redacted text,
    status            text   NOT NULL DEFAULT 'queued'
                        CHECK (status IN ('queued','sending','sent','delivered','failed')),
    markdown_path     text,
    html_path         text,
    dashboard_url     text,
    report_id         bigint REFERENCES reports(id),
    error             text,
    created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_bot_deliveries_tenant ON bot_deliveries (tenant_id, created_at DESC);

-- Dashboard state: the semantic snapshot the cockpit renders from (not scraped prose).
CREATE TABLE dashboard_state (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id         bigint NOT NULL REFERENCES tenants(id),
    generated_at      timestamptz NOT NULL DEFAULT now(),
    daily_state       jsonb  NOT NULL DEFAULT '{}'::jsonb,
    weekly_state      jsonb  NOT NULL DEFAULT '{}'::jsonb,
    material_delta_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
    action_item_ids   jsonb  NOT NULL DEFAULT '[]'::jsonb,
    delivery_ids      jsonb  NOT NULL DEFAULT '[]'::jsonb,
    coverage_limits   jsonb  NOT NULL DEFAULT '{}'::jsonb,
    json_path         text
);
CREATE INDEX idx_dashboard_state_tenant ON dashboard_state (tenant_id, generated_at DESC);

-- ============================================================================
-- ROW LEVEL SECURITY
-- Enable + FORCE RLS on every tenant-scoped table and attach a uniform policy.
-- current_setting('app.tenant_id', true) returns NULL when unset -> the
-- comparison yields NULL -> zero rows (fail-closed). Superuser bypasses RLS
-- (used for schema/seed). cios_app is NOBYPASSRLS so it is always scoped.
-- ============================================================================
DO $$
DECLARE
    t text;
    tenant_tables text[] := ARRAY[
        'users','user_identities','roles','role_permissions','user_role_assignments',
        'groups','group_role_mappings','identity_provider_configs','audit_events',
        'channel_accounts','channel_identities','channel_threads','channel_messages',
        'delivery_attempts','access_requests','model_provider_configs','model_provider_runs',
        'competitors','sources','source_scan_runs','source_observations','source_candidates',
        'competitor_scan_rollups','source_health_events','intel_fetch_runs','source_snapshots',
        'raw_findings','executive_speech_signals','gtm_narrative_signals','social_observations',
        'content_observations','content_traction_signals','content_recommendations',
        'weekly_content_plan','content_plan_reviews','semantic_facts','semantic_deltas',
        'suppressed_diagnostics','claims','claim_observations','competitor_theses',
        'reports','action_items','quality_reviews','false_negative_audits','learning_events',
        'improvement_queue','bot_deliveries','dashboard_state'
    ];
BEGIN
    FOREACH t IN ARRAY tenant_tables LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY;', t);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY;', t);
        -- current_setting('app.tenant_id', true) returns '' (empty string),
        -- NOT NULL, when the GUC has never been set in this session/tx --
        -- discovered by running this against a live Postgres 16 for the
        -- first time (the doc comment above assumed NULL). ''::bigint
        -- raises a hard error rather than failing closed, so NULLIF(...,'')
        -- converts the unset case to a real NULL first; the NULL = NULL
        -- comparison then correctly yields NULL -> zero rows (fail-closed).
        EXECUTE format($f$
            CREATE POLICY tenant_isolation ON %I
            USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::bigint)
            WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::bigint);
        $f$, t);
        -- grant CRUD to the app role (RLS still constrains rows to the tenant).
        EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON %I TO cios_app;', t);
    END LOOP;
END
$$;

-- Schema usage: Postgres 15+ no longer grants USAGE on the `public` schema
-- to PUBLIC by default, so without this the (non-superuser) cios_app role
-- cannot see ANY table in `public` -- every query fails with "relation ...
-- does not exist" (not a permissions error; RLS grants above are moot
-- without this). Found by running this schema against a live Postgres 16
-- for the first time.
GRANT USAGE ON SCHEMA public TO cios_app;

-- Global tables: readable by the app role (permissions catalog + tenant lookup).
GRANT SELECT ON tenants, permissions TO cios_app;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO cios_app;
-- Ensure future sequences (from identity columns) are usable by the app role.
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE ON SEQUENCES TO cios_app;

COMMIT;
