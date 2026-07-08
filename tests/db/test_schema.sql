-- ============================================================================
-- CI-OS schema smoke tests (plain SQL, no pgTAP). Prints PASS/FAIL lines.
--
-- Run as the SUPERUSER/owner that applied schema.sql + seed.sql, e.g.:
--   psql "$CIOS_DATABASE_URL" -v ON_ERROR_STOP=0 -f tests/db/test_schema.sql
--
-- It temporarily switches to the cios_app role (SET ROLE) to prove RLS, since
-- superusers bypass RLS. Each check emits: "PASS: ..." or "FAIL: ...".
-- ============================================================================
\set ON_ERROR_STOP off
\pset pager off
\set QUIET on
\timing off

-- Helper: assert a boolean, print PASS/FAIL with a label.
CREATE OR REPLACE FUNCTION pg_temp.check(label text, cond boolean)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    IF cond THEN
        RAISE INFO 'PASS: %', label;
    ELSE
        RAISE WARNING 'FAIL: %', label;
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 1. Core tables exist (spot-check across every entity group + the 6 new ones)
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    expected text[] := ARRAY[
        'tenants','permissions','users','user_identities','roles','role_permissions',
        'user_role_assignments','groups','group_role_mappings','identity_provider_configs',
        'audit_events','channel_accounts','channel_identities','channel_threads',
        'channel_messages','delivery_attempts','access_requests','model_provider_configs',
        'model_provider_runs','competitors','sources','source_scan_runs','source_observations',
        'source_candidates','competitor_scan_rollups','source_health_events','intel_fetch_runs',
        'source_snapshots','raw_findings','executive_speech_signals','gtm_narrative_signals',
        'social_observations','content_observations','content_traction_signals',
        'content_recommendations','weekly_content_plan','content_plan_reviews','semantic_facts',
        'semantic_deltas','suppressed_diagnostics','claims','claim_observations',
        'competitor_theses','reports','action_items','quality_reviews','false_negative_audits',
        'learning_events','improvement_queue','bot_deliveries','dashboard_state'
    ];
    missing text[];
BEGIN
    SELECT array_agg(e) INTO missing
    FROM unnest(expected) e
    WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='public' AND table_name=e
    );
    PERFORM pg_temp.check(
        format('all %s expected tables exist', array_length(expected,1)),
        missing IS NULL
    );
    IF missing IS NOT NULL THEN
        RAISE WARNING '  missing: %', missing;
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 2. RLS enabled + forced on tenant-scoped tables (sample the set)
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    sample text[] := ARRAY['users','semantic_deltas','sources','bot_deliveries','audit_events'];
    bad text[];
BEGIN
    SELECT array_agg(c.relname) INTO bad
    FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname='public' AND c.relname = ANY(sample)
      AND NOT (c.relrowsecurity AND c.relforcerowsecurity);
    PERFORM pg_temp.check('RLS enabled+forced on tenant tables', bad IS NULL);
    IF bad IS NOT NULL THEN RAISE WARNING '  not protected: %', bad; END IF;
END $$;

-- Global tables must NOT have RLS.
DO $$
DECLARE r boolean;
BEGIN
    SELECT c.relrowsecurity INTO r FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname='public' AND c.relname='permissions';
    PERFORM pg_temp.check('global table permissions has no RLS', r = false);
END $$;

-- cios_app must not bypass RLS.
DO $$
DECLARE b boolean;
BEGIN
    SELECT rolbypassrls INTO b FROM pg_roles WHERE rolname='cios_app';
    PERFORM pg_temp.check('cios_app is NOT BYPASSRLS', b = false);
END $$;

-- ---------------------------------------------------------------------------
-- 3. Seed sanity
-- ---------------------------------------------------------------------------
DO $$
DECLARE n int;
BEGIN
    SELECT count(*) INTO n FROM tenants WHERE slug IN ('algolia','spryker','amplitude');
    PERFORM pg_temp.check('3 tenants seeded', n = 3);

    SELECT count(*) INTO n FROM permissions;
    PERFORM pg_temp.check('permission catalog seeded (>=14)', n >= 14);

    SELECT count(*) INTO n FROM roles;
    PERFORM pg_temp.check('30 roles seeded (10 x 3 tenants)', n = 30);

    SELECT count(*) INTO n
    FROM channel_identities ci
    JOIN users u ON u.id = ci.user_id
    WHERE ci.channel='telegram' AND ci.channel_user_id='6789423537'
      AND u.email='arijit.chowdhury@algolia.com';
    PERFORM pg_temp.check('algolia owner has telegram identity 6789423537', n = 1);
END $$;

-- ---------------------------------------------------------------------------
-- 4. RLS cross-tenant isolation (as cios_app, not superuser)
--    Set app.tenant_id to Spryker, query users -> must NOT see Algolia's owner.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    algolia_id bigint;
    spryker_id bigint;
    seen_own int;
    seen_cross int;
BEGIN
    SELECT id INTO algolia_id FROM tenants WHERE slug='algolia';
    SELECT id INTO spryker_id FROM tenants WHERE slug='spryker';

    SET LOCAL ROLE cios_app;

    -- Scoped to Algolia: should see the seeded owner.
    PERFORM set_config('app.tenant_id', algolia_id::text, true);
    SELECT count(*) INTO seen_own FROM users WHERE email='arijit.chowdhury@algolia.com';

    -- Scoped to Spryker: must see zero Algolia rows.
    PERFORM set_config('app.tenant_id', spryker_id::text, true);
    SELECT count(*) INTO seen_cross FROM users WHERE email='arijit.chowdhury@algolia.com';

    RESET ROLE;

    PERFORM pg_temp.check('RLS: app sees own-tenant row when scoped', seen_own = 1);
    PERFORM pg_temp.check('RLS: cross-tenant SELECT returns 0 rows', seen_cross = 0);
END $$;

-- ---------------------------------------------------------------------------
-- 5. Evidence CHECK rejects an empty-evidence PUBLISHED delta
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    tid bigint;
    cid bigint;
    rejected boolean := false;
BEGIN
    SELECT id INTO tid FROM tenants WHERE slug='algolia';

    -- ensure a competitor exists to satisfy the FK
    INSERT INTO competitors (tenant_id, name) VALUES (tid, '__test_competitor__')
    ON CONFLICT (tenant_id, name) DO NOTHING;
    SELECT id INTO cid FROM competitors WHERE tenant_id=tid AND name='__test_competitor__';

    BEGIN
        INSERT INTO semantic_deltas (tenant_id, competitor_id, what_changed, quality_status, evidence_ids)
        VALUES (tid, cid, 'test', 'published', '[]'::jsonb);
    EXCEPTION WHEN check_violation THEN
        rejected := true;
    END;
    PERFORM pg_temp.check('evidence CHECK rejects empty-evidence published delta', rejected);

    -- A published delta WITH evidence must be accepted.
    BEGIN
        INSERT INTO semantic_deltas (tenant_id, competitor_id, what_changed, quality_status, evidence_ids)
        VALUES (tid, cid, 'test', 'published', '[123]'::jsonb);
        rejected := false;
    EXCEPTION WHEN check_violation THEN
        rejected := true;
    END;
    PERFORM pg_temp.check('evidence CHECK accepts published delta WITH evidence', rejected = false);

    -- A draft delta with empty evidence must be accepted (invariant is publish-time).
    BEGIN
        INSERT INTO semantic_deltas (tenant_id, competitor_id, what_changed, quality_status, evidence_ids)
        VALUES (tid, cid, 'test', 'draft', '[]'::jsonb);
        rejected := false;
    EXCEPTION WHEN check_violation THEN
        rejected := true;
    END;
    PERFORM pg_temp.check('draft delta with empty evidence allowed', rejected = false);

    -- cleanup
    DELETE FROM semantic_deltas WHERE tenant_id=tid AND competitor_id=cid;
    DELETE FROM competitors WHERE id=cid;
END $$;

\echo '--- test run complete: scan output above for any FAIL lines ---'
