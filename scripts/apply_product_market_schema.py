#!/usr/bin/env python3
"""Apply the idempotent CI-OS product-market schema patch.

This is the production bridge for databases created before the product-market
intelligence spine existed. Fresh installs still use src/cios/db/schema.sql.
"""

from __future__ import annotations

import argparse
import os
import sys

import psycopg


PRODUCT_MARKET_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS product_surfaces (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id       bigint NOT NULL REFERENCES tenants(id),
    competitor_id   bigint REFERENCES competitors(id),
    company_name    text   NOT NULL,
    company_role    text   NOT NULL DEFAULT 'competitor'
                      CHECK (company_role IN ('own','competitor','partner')),
    surface_family  text   NOT NULL
                      CHECK (surface_family IN ('changelog','docs','release_notes','product_page','pricing','api_docs','integration','other')),
    url             text   NOT NULL,
    normalized_url  text,
    title           text,
    status          text   NOT NULL DEFAULT 'active'
                      CHECK (status IN ('active','candidate','paused','retired','failed')),
    last_checked_at timestamptz,
    metadata        jsonb  NOT NULL DEFAULT '{}'::jsonb,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_product_surfaces_tenant_company ON product_surfaces (tenant_id, company_role, company_name);
CREATE INDEX IF NOT EXISTS idx_product_surfaces_tenant_status ON product_surfaces (tenant_id, status);
CREATE UNIQUE INDEX IF NOT EXISTS uq_product_surfaces_tenant_normalized_url ON product_surfaces (tenant_id, normalized_url);

CREATE TABLE IF NOT EXISTS feature_capabilities (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id      bigint NOT NULL REFERENCES tenants(id),
    canonical_name text   NOT NULL,
    taxonomy_path  text,
    description    text,
    status         text   NOT NULL DEFAULT 'active'
                     CHECK (status IN ('active','candidate','retired')),
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, canonical_name)
);
CREATE INDEX IF NOT EXISTS idx_feature_capabilities_tenant ON feature_capabilities (tenant_id, status);

CREATE TABLE IF NOT EXISTS product_change_events (
    id                    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id             bigint NOT NULL REFERENCES tenants(id),
    product_surface_id    bigint REFERENCES product_surfaces(id),
    competitor_id         bigint REFERENCES competitors(id),
    feature_capability_id bigint REFERENCES feature_capabilities(id),
    company_name          text   NOT NULL,
    company_role          text   NOT NULL DEFAULT 'competitor'
                            CHECK (company_role IN ('own','competitor','partner')),
    capability_text       text   NOT NULL,
    change_type           text   NOT NULL
                            CHECK (change_type IN ('release','docs_update','pricing_change','integration','deprecation')),
    summary               text   NOT NULL,
    observed_at           timestamptz NOT NULL DEFAULT now(),
    evidence_refs         jsonb  NOT NULL DEFAULT '[]'::jsonb,
    confidence            numeric(4,3),
    metadata              jsonb  NOT NULL DEFAULT '{}'::jsonb,
    created_at            timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT product_change_event_needs_evidence CHECK (jsonb_array_length(evidence_refs) > 0)
);
CREATE INDEX IF NOT EXISTS idx_product_change_events_tenant_company ON product_change_events (tenant_id, company_role, company_name, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_product_change_events_tenant_capability ON product_change_events (tenant_id, feature_capability_id, observed_at DESC);

CREATE TABLE IF NOT EXISTS company_feature_positions (
    id                    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id             bigint NOT NULL REFERENCES tenants(id),
    feature_capability_id bigint NOT NULL REFERENCES feature_capabilities(id),
    competitor_id         bigint REFERENCES competitors(id),
    company_name          text   NOT NULL,
    company_role          text   NOT NULL DEFAULT 'competitor'
                            CHECK (company_role IN ('own','competitor','partner')),
    position_status       text   NOT NULL DEFAULT 'unknown'
                            CHECK (position_status IN ('unknown','proven','claimed','gap','disproven')),
    summary               text,
    last_seen_at          timestamptz,
    evidence_refs         jsonb  NOT NULL DEFAULT '[]'::jsonb,
    confidence            numeric(4,3),
    updated_at            timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, feature_capability_id, company_role, company_name),
    CONSTRAINT company_feature_position_claim_needs_evidence
        CHECK (position_status = 'unknown' OR jsonb_array_length(evidence_refs) > 0)
);
CREATE INDEX IF NOT EXISTS idx_company_feature_positions_tenant_feature ON company_feature_positions (tenant_id, feature_capability_id, company_role);

CREATE TABLE IF NOT EXISTS feature_evidence_links (
    id                      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id               bigint NOT NULL REFERENCES tenants(id),
    feature_capability_id   bigint REFERENCES feature_capabilities(id),
    product_change_event_id bigint REFERENCES product_change_events(id),
    raw_finding_id          bigint REFERENCES raw_findings(id),
    source_url              text   NOT NULL,
    captured_at             timestamptz NOT NULL DEFAULT now(),
    method                  text   NOT NULL,
    evidence_text           text,
    metadata                jsonb  NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_feature_evidence_links_tenant_feature ON feature_evidence_links (tenant_id, feature_capability_id, captured_at DESC);

CREATE TABLE IF NOT EXISTS conversation_themes (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id      bigint NOT NULL REFERENCES tenants(id),
    competitor_id  bigint REFERENCES competitors(id),
    company_name   text,
    theme          text   NOT NULL,
    summary        text   NOT NULL,
    intensity      numeric(4,3),
    observed_at    timestamptz NOT NULL DEFAULT now(),
    evidence_refs  jsonb  NOT NULL DEFAULT '[]'::jsonb,
    metadata       jsonb  NOT NULL DEFAULT '{}'::jsonb,
    created_at     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT conversation_theme_needs_evidence CHECK (jsonb_array_length(evidence_refs) > 0)
);
CREATE INDEX IF NOT EXISTS idx_conversation_themes_tenant_theme ON conversation_themes (tenant_id, theme, observed_at DESC);

CREATE TABLE IF NOT EXISTS demand_signals (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id      bigint NOT NULL REFERENCES tenants(id),
    topic          text   NOT NULL,
    metric         text   NOT NULL,
    value          numeric(18,4) NOT NULL,
    change_pct     numeric(8,4),
    period_start   timestamptz NOT NULL,
    period_end     timestamptz NOT NULL,
    source_label   text   NOT NULL,
    evidence_refs  jsonb  NOT NULL DEFAULT '[]'::jsonb,
    metadata       jsonb  NOT NULL DEFAULT '{}'::jsonb,
    created_at     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT demand_signal_needs_evidence CHECK (jsonb_array_length(evidence_refs) > 0)
);
CREATE INDEX IF NOT EXISTS idx_demand_signals_tenant_topic ON demand_signals (tenant_id, topic, period_end DESC);

CREATE TABLE IF NOT EXISTS pattern_observations (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id          bigint NOT NULL REFERENCES tenants(id),
    pattern_type       text   NOT NULL
                         CHECK (pattern_type IN ('own_narrative_gap','own_product_gap','product_without_market_conversation','conversation_without_product_proof','competitive_pressure')),
    capability_text    text   NOT NULL,
    summary            text   NOT NULL,
    involved_companies jsonb  NOT NULL DEFAULT '[]'::jsonb,
    confidence         numeric(4,3),
    evidence_refs      jsonb  NOT NULL DEFAULT '[]'::jsonb,
    created_at         timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT pattern_observation_needs_evidence CHECK (jsonb_array_length(evidence_refs) > 0)
);
CREATE INDEX IF NOT EXISTS idx_pattern_observations_tenant_created ON pattern_observations (tenant_id, created_at DESC);

CREATE TABLE IF NOT EXISTS argus_recommendations (
    id                     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id              bigint NOT NULL REFERENCES tenants(id),
    pattern_observation_id bigint REFERENCES pattern_observations(id),
    owner                  text   NOT NULL CHECK (owner IN ('PMM','Product','Sales','Content','Executive')),
    action                 text   NOT NULL,
    why_now                text   NOT NULL,
    urgency                text   NOT NULL DEFAULT 'this_week'
                             CHECK (urgency IN ('act_now','this_week','this_month')),
    confidence             numeric(4,3),
    scorecard              jsonb  NOT NULL DEFAULT '{"total_score":0,"verdict":"insufficient","summary":"No backend scorecard published.","dimension_scores":[]}'::jsonb,
    evidence_refs          jsonb  NOT NULL DEFAULT '[]'::jsonb,
    status                 text   NOT NULL DEFAULT 'open'
                             CHECK (status IN ('open','accepted','dismissed','done')),
    created_at             timestamptz NOT NULL DEFAULT now(),
    updated_at             timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT argus_recommendation_needs_evidence CHECK (jsonb_array_length(evidence_refs) > 0),
    CONSTRAINT argus_recommendation_needs_scorecard CHECK (
        jsonb_typeof(scorecard) = 'object'
        AND scorecard ? 'total_score'
        AND scorecard ? 'dimension_scores'
        AND jsonb_typeof(scorecard->'dimension_scores') = 'array'
    )
);
CREATE INDEX IF NOT EXISTS idx_argus_recommendations_tenant_status ON argus_recommendations (tenant_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS product_market_run_intelligence (
    id                                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id                           bigint NOT NULL REFERENCES tenants(id),
    verdict                             text   NOT NULL CHECK (verdict IN ('actionable','watch','quiet')),
    intelligence_brief                  jsonb  NOT NULL DEFAULT '{}'::jsonb,
    argus_packet                        jsonb  NOT NULL,
    product_event_count                 integer NOT NULL DEFAULT 0,
    conversation_theme_count            integer NOT NULL DEFAULT 0,
    demand_signal_count                 integer NOT NULL DEFAULT 0,
    feature_position_count              integer NOT NULL DEFAULT 0,
    pattern_count                       integer NOT NULL DEFAULT 0,
    recommendation_count                integer NOT NULL DEFAULT 0,
    learning_instruction_count          integer NOT NULL DEFAULT 0,
    learning_instruction_improvement_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at                          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT product_market_run_intelligence_has_brief CHECK (
        jsonb_typeof(intelligence_brief) = 'object'
        AND intelligence_brief ? 'top_insight'
        AND intelligence_brief ? 'confidence_limits'
        AND jsonb_typeof(intelligence_brief->'confidence_limits') = 'array'
    ),
    CONSTRAINT product_market_run_intelligence_has_learning_ids CHECK (
        jsonb_typeof(learning_instruction_improvement_ids) = 'array'
    ),
    CONSTRAINT product_market_run_intelligence_has_packet CHECK (
        jsonb_typeof(argus_packet) = 'object'
        AND argus_packet ? 'packet_id'
        AND argus_packet ? 'run'
        AND argus_packet ? 'executive_read'
        AND jsonb_typeof(argus_packet->'run') = 'object'
        AND (argus_packet->'run') ? 'run_id'
    )
);
CREATE INDEX IF NOT EXISTS idx_product_market_run_intelligence_tenant_created
    ON product_market_run_intelligence (tenant_id, created_at DESC, id DESC);

ALTER TABLE product_market_run_intelligence
    ADD COLUMN IF NOT EXISTS argus_packet jsonb;
UPDATE product_market_run_intelligence
SET argus_packet = jsonb_build_object(
    'schema_version', 1,
    'packet_id', 'legacy-product-market-run-' || id::text,
    'run', jsonb_build_object('run_id', 'legacy-product-market-run-' || id::text),
    'executive_read', jsonb_build_object(
        'headline', COALESCE(intelligence_brief->>'top_insight', 'Legacy run intelligence'),
        'plain_read', COALESCE(intelligence_brief->>'top_insight', 'Legacy run intelligence')
    )
)
WHERE argus_packet IS NULL;
ALTER TABLE product_market_run_intelligence
    ALTER COLUMN argus_packet SET NOT NULL;

ALTER TABLE bot_deliveries
    ADD COLUMN IF NOT EXISTS packet_id text,
    ADD COLUMN IF NOT EXISTS run_id text;
CREATE INDEX IF NOT EXISTS idx_bot_deliveries_tenant_packet
    ON bot_deliveries (tenant_id, run_id, packet_id);

CREATE TABLE IF NOT EXISTS run_stage_ledgers (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id    bigint NOT NULL REFERENCES tenants(id),
    run_id       text   NOT NULL,
    package_name text   NOT NULL,
    status       text   NOT NULL DEFAULT 'running'
                   CHECK (status IN ('running','completed','failed','skipped')),
    started_at   timestamptz,
    ended_at     timestamptz,
    metadata     jsonb  NOT NULL DEFAULT '{}'::jsonb,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_run_stage_ledgers_tenant_started
    ON run_stage_ledgers (tenant_id, package_name, started_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS run_stage_events (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id     bigint NOT NULL REFERENCES tenants(id),
    ledger_id     bigint NOT NULL REFERENCES run_stage_ledgers(id) ON DELETE CASCADE,
    stage_order   integer NOT NULL,
    stage         text    NOT NULL,
    status        text    NOT NULL CHECK (status IN ('running','completed','failed','skipped')),
    started_at    timestamptz,
    ended_at      timestamptz,
    elapsed_s     numeric(12,3),
    error_type    text,
    error         text,
    metadata      jsonb   NOT NULL DEFAULT '{}'::jsonb,
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, ledger_id, stage_order)
);
CREATE INDEX IF NOT EXISTS idx_run_stage_events_tenant_ledger_order
    ON run_stage_events (tenant_id, ledger_id, stage_order);

DO $$
DECLARE
    t text;
    tenant_tables text[] := ARRAY[
        'product_surfaces','feature_capabilities','product_change_events',
        'company_feature_positions','feature_evidence_links','conversation_themes',
        'demand_signals','pattern_observations','argus_recommendations',
        'product_market_run_intelligence','run_stage_ledgers','run_stage_events'
    ];
BEGIN
    FOREACH t IN ARRAY tenant_tables LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY;', t);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY;', t);
        EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I;', t);
        EXECUTE format($f$
            CREATE POLICY tenant_isolation ON %I
            USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::bigint)
            WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::bigint);
        $f$, t);
        EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON %I TO cios_app;', t);
    END LOOP;
END
$$;

GRANT USAGE ON SCHEMA public TO cios_app;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO cios_app;
"""


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", default=os.environ.get("CIOS_DATABASE_URL", ""))
    return parser.parse_args(argv)


def apply_schema(database_url: str) -> None:
    if not database_url:
        raise RuntimeError("CIOS_DATABASE_URL is required to apply product-market schema")
    with psycopg.connect(database_url) as conn:
        conn.execute(PRODUCT_MARKET_SCHEMA_SQL)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        apply_schema(args.database_url)
    except Exception as exc:  # noqa: BLE001 - command-line boundary
        print(f"product-market schema apply failed: {exc}", file=sys.stderr)
        return 1
    print("product-market schema ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
