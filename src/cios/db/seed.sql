-- ============================================================================
-- CI-OS seed data (v1 baseline).
-- Run as a superuser / DB owner (RLS is FORCED; superuser bypasses it).
-- Idempotent: safe to re-run (ON CONFLICT DO NOTHING throughout).
--
-- Seeds:
--   * 3 tenants: algolia, spryker, amplitude
--   * global permission catalog (from channels doc permission families)
--   * 10 roles per tenant (owner ... guest_viewer) with sensible grants
--   * one owner user for tenant algolia (arijit.chowdhury@algolia.com)
--     with a linked Telegram channel_identity (channel_user_id 6789423537)
-- No secrets. No provider model ids.
-- ============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- Tenants
-- ---------------------------------------------------------------------------
INSERT INTO tenants (name, slug, primary_domain) VALUES
    ('Algolia',   'algolia',   'algolia.com'),
    ('Spryker',   'spryker',   'spryker.com'),
    ('Amplitude', 'amplitude', 'amplitude.com')
ON CONFLICT (slug) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Global permission catalog
-- ---------------------------------------------------------------------------
INSERT INTO permissions (key, description) VALUES
    ('view_daily_reports',           'View daily intelligence reports'),
    ('view_weekly_reports',          'View weekly intelligence reports'),
    ('view_evidence',                'View underlying evidence and source snapshots'),
    ('view_source_health',           'View source health and coverage'),
    ('view_content_recommendations', 'View weekly content recommendations'),
    ('edit_action_items',            'Create or edit action items'),
    ('manage_competitors',           'Manage the competitor registry'),
    ('manage_sources',               'Manage the source ledger'),
    ('manage_users',                 'Manage users, roles, and access'),
    ('manage_integrations',          'Manage channel and provider integrations'),
    ('manage_model_routing',         'Manage model routing and policy'),
    ('trigger_runs',                 'Trigger collection/synthesis runs'),
    ('approve_skill_changes',        'Approve skill / threshold / policy changes'),
    ('view_operational_logs',        'View operator logs and secret status')
ON CONFLICT (key) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Roles per tenant (10 roles x 3 tenants)
-- ---------------------------------------------------------------------------
INSERT INTO roles (tenant_id, name, description)
SELECT t.id, r.name, r.description
FROM tenants t
CROSS JOIN (VALUES
    ('owner',                  'Full control of the tenant'),
    ('operator_admin',         'Operates CI-OS: users, integrations, model routing, runs'),
    ('ci_operator',            'Runs and curates competitive intelligence'),
    ('executive_viewer',       'Reads reports and action items (exec)'),
    ('gtm_viewer',             'Reads GTM/narrative intelligence'),
    ('pmm_user',               'Product marketing: content + evidence'),
    ('marketer',               'Marketing: content recommendations'),
    ('product_user',           'Product: reports and evidence'),
    ('sales_enablement_user',  'Sales enablement: reports and action items'),
    ('guest_viewer',           'Limited read of daily reports only')
) AS r(name, description)
ON CONFLICT (tenant_id, name) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Role -> permission grants (applied to every tenant's role set)
-- ---------------------------------------------------------------------------
INSERT INTO role_permissions (tenant_id, role_id, permission_id)
SELECT r.tenant_id, r.id, p.id
FROM roles r
JOIN (VALUES
    -- owner: everything
    ('owner','view_daily_reports'),('owner','view_weekly_reports'),('owner','view_evidence'),
    ('owner','view_source_health'),('owner','view_content_recommendations'),('owner','edit_action_items'),
    ('owner','manage_competitors'),('owner','manage_sources'),('owner','manage_users'),
    ('owner','manage_integrations'),('owner','manage_model_routing'),('owner','trigger_runs'),
    ('owner','approve_skill_changes'),('owner','view_operational_logs'),
    -- operator_admin: operate everything except skill approval is shared with owner
    ('operator_admin','view_daily_reports'),('operator_admin','view_weekly_reports'),('operator_admin','view_evidence'),
    ('operator_admin','view_source_health'),('operator_admin','view_content_recommendations'),('operator_admin','edit_action_items'),
    ('operator_admin','manage_competitors'),('operator_admin','manage_sources'),('operator_admin','manage_users'),
    ('operator_admin','manage_integrations'),('operator_admin','manage_model_routing'),('operator_admin','trigger_runs'),
    ('operator_admin','approve_skill_changes'),('operator_admin','view_operational_logs'),
    -- ci_operator: run + curate intel, no user/integration admin
    ('ci_operator','view_daily_reports'),('ci_operator','view_weekly_reports'),('ci_operator','view_evidence'),
    ('ci_operator','view_source_health'),('ci_operator','view_content_recommendations'),('ci_operator','edit_action_items'),
    ('ci_operator','manage_competitors'),('ci_operator','manage_sources'),('ci_operator','trigger_runs'),
    ('ci_operator','view_operational_logs'),
    -- executive_viewer
    ('executive_viewer','view_daily_reports'),('executive_viewer','view_weekly_reports'),
    ('executive_viewer','view_evidence'),('executive_viewer','view_content_recommendations'),
    -- gtm_viewer
    ('gtm_viewer','view_daily_reports'),('gtm_viewer','view_weekly_reports'),
    ('gtm_viewer','view_evidence'),('gtm_viewer','view_content_recommendations'),
    -- pmm_user
    ('pmm_user','view_daily_reports'),('pmm_user','view_weekly_reports'),('pmm_user','view_evidence'),
    ('pmm_user','view_content_recommendations'),('pmm_user','edit_action_items'),
    -- marketer
    ('marketer','view_daily_reports'),('marketer','view_weekly_reports'),
    ('marketer','view_content_recommendations'),
    -- product_user
    ('product_user','view_daily_reports'),('product_user','view_weekly_reports'),('product_user','view_evidence'),
    -- sales_enablement_user
    ('sales_enablement_user','view_daily_reports'),('sales_enablement_user','view_weekly_reports'),
    ('sales_enablement_user','view_evidence'),('sales_enablement_user','edit_action_items'),
    -- guest_viewer
    ('guest_viewer','view_daily_reports')
) AS grant_map(role_name, perm_key) ON grant_map.role_name = r.name
JOIN permissions p ON p.key = grant_map.perm_key
ON CONFLICT (tenant_id, role_id, permission_id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Owner user for tenant algolia + Telegram channel identity
-- ---------------------------------------------------------------------------
INSERT INTO users (tenant_id, email, display_name, status)
SELECT t.id, 'arijit.chowdhury@algolia.com', 'Arijit Chowdhury', 'active'
FROM tenants t WHERE t.slug = 'algolia'
ON CONFLICT (tenant_id, email) DO NOTHING;

INSERT INTO user_role_assignments (tenant_id, user_id, role_id)
SELECT t.id, u.id, r.id
FROM tenants t
JOIN users u ON u.tenant_id = t.id AND u.email = 'arijit.chowdhury@algolia.com'
JOIN roles r ON r.tenant_id = t.id AND r.name = 'owner'
WHERE t.slug = 'algolia'
ON CONFLICT (tenant_id, user_id, role_id) DO NOTHING;

INSERT INTO channel_identities (tenant_id, user_id, channel, channel_user_id, status, linked_at)
SELECT t.id, u.id, 'telegram', '6789423537', 'linked', now()
FROM tenants t
JOIN users u ON u.tenant_id = t.id AND u.email = 'arijit.chowdhury@algolia.com'
WHERE t.slug = 'algolia'
ON CONFLICT (tenant_id, channel, channel_user_id) DO NOTHING;

COMMIT;
