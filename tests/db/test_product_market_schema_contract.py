"""Static schema contract for the Argus product-market intelligence spine.

The live DB integration test proves the full schema applies. These tests make
the new product/demand storage contract cheap to check while iterating.
"""

from __future__ import annotations

from pathlib import Path


SCHEMA = Path("src/cios/db/schema.sql").read_text()


def test_product_market_tables_exist_in_schema() -> None:
    for table in [
        "product_surfaces",
        "product_change_events",
        "feature_capabilities",
        "company_feature_positions",
        "feature_evidence_links",
        "conversation_themes",
        "demand_signals",
        "pattern_observations",
        "argus_recommendations",
        "product_market_run_intelligence",
        "run_stage_ledgers",
        "run_stage_events",
    ]:
        assert f"CREATE TABLE {table}" in SCHEMA


def test_evidence_backed_tables_have_evidence_constraints() -> None:
    for constraint in [
        "product_change_event_needs_evidence",
        "conversation_theme_needs_evidence",
        "demand_signal_needs_evidence",
        "pattern_observation_needs_evidence",
        "argus_recommendation_needs_evidence",
    ]:
        assert constraint in SCHEMA


def test_argus_recommendations_have_backend_scorecard_contract() -> None:
    recommendation_block = SCHEMA.split("CREATE TABLE argus_recommendations", maxsplit=1)[1].split(
        "CREATE INDEX idx_argus_recommendations_tenant_status",
        maxsplit=1,
    )[0]
    assert "scorecard" in recommendation_block
    assert "argus_recommendation_needs_scorecard" in recommendation_block
    assert "total_score" in recommendation_block
    assert "dimension_scores" in recommendation_block


def test_run_intelligence_has_brain_readable_brief_contract() -> None:
    run_block = SCHEMA.split("CREATE TABLE product_market_run_intelligence", maxsplit=1)[1].split(
        "CREATE INDEX idx_product_market_run_intelligence_tenant_created",
        maxsplit=1,
    )[0]
    assert "intelligence_brief" in run_block
    assert "product_market_run_intelligence_has_brief" in run_block
    assert "top_insight" in run_block
    assert "confidence_limits" in run_block
    assert "learning_instruction_improvement_ids" in run_block


def test_run_intelligence_has_canonical_argus_packet_contract() -> None:
    run_block = SCHEMA.split("CREATE TABLE product_market_run_intelligence", maxsplit=1)[1].split(
        "CREATE INDEX idx_product_market_run_intelligence_tenant_created",
        maxsplit=1,
    )[0]
    assert "argus_packet" in run_block
    assert "product_market_run_intelligence_has_packet" in run_block
    assert "packet_id" in run_block
    assert "run" in run_block
    assert "executive_read" in run_block


def test_pattern_observations_allow_product_without_market_conversation_pattern() -> None:
    pattern_block = SCHEMA.split("CREATE TABLE pattern_observations", maxsplit=1)[1].split(
        "CREATE INDEX idx_pattern_observations_tenant_created",
        maxsplit=1,
    )[0]
    assert "product_without_market_conversation" in pattern_block


def test_product_surfaces_have_seed_upsert_key() -> None:
    assert "uq_product_surfaces_tenant_normalized_url" in SCHEMA
    assert "ON product_surfaces (tenant_id, normalized_url)" in SCHEMA


def test_new_tables_are_rls_protected() -> None:
    rls_block = SCHEMA.split("tenant_tables text[] := ARRAY[", maxsplit=1)[1]
    for table in [
        "product_surfaces",
        "product_change_events",
        "feature_capabilities",
        "company_feature_positions",
        "feature_evidence_links",
        "conversation_themes",
        "demand_signals",
        "pattern_observations",
        "argus_recommendations",
        "product_market_run_intelligence",
        "run_stage_ledgers",
        "run_stage_events",
    ]:
        assert f"'{table}'" in rls_block


def test_run_stage_events_have_parent_and_status_contract() -> None:
    ledger_block = SCHEMA.split("CREATE TABLE run_stage_ledgers", maxsplit=1)[1].split(
        "CREATE INDEX idx_run_stage_ledgers_tenant_started",
        maxsplit=1,
    )[0]
    events_block = SCHEMA.split("CREATE TABLE run_stage_events", maxsplit=1)[1].split(
        "CREATE INDEX idx_run_stage_events_tenant_ledger_order",
        maxsplit=1,
    )[0]
    assert "run_id" in ledger_block
    assert "package_name" in ledger_block
    assert "CHECK (status IN ('running','completed','failed','skipped'))" in ledger_block
    assert "ledger_id" in events_block
    assert "REFERENCES run_stage_ledgers(id)" in events_block
    assert "stage_order" in events_block
    assert "CHECK (status IN ('running','completed','failed','skipped'))" in events_block
    assert "error_type" in events_block
    assert "error" in events_block
