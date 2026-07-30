"""Static schema contract for packet-aware delivery ledger fields."""

from __future__ import annotations

from pathlib import Path


SCHEMA = Path("src/cios/db/schema.sql").read_text()
PRODUCT_MARKET_APPLY_SCRIPT = Path("scripts/apply_product_market_schema.py").read_text()


def test_bot_deliveries_preserve_packet_and_run_identity() -> None:
    delivery_block = SCHEMA.split("CREATE TABLE bot_deliveries", maxsplit=1)[1].split(
        "CREATE INDEX idx_bot_deliveries_tenant",
        maxsplit=1,
    )[0]

    assert "packet_id" in delivery_block
    assert "run_id" in delivery_block
    assert "idx_bot_deliveries_tenant_packet" in SCHEMA


def test_schema_apply_bridge_adds_packet_identity_to_existing_bot_deliveries() -> None:
    assert "ALTER TABLE bot_deliveries" in PRODUCT_MARKET_APPLY_SCRIPT
    assert "ADD COLUMN IF NOT EXISTS packet_id" in PRODUCT_MARKET_APPLY_SCRIPT
    assert "ADD COLUMN IF NOT EXISTS run_id" in PRODUCT_MARKET_APPLY_SCRIPT
    assert "idx_bot_deliveries_tenant_packet" in PRODUCT_MARKET_APPLY_SCRIPT
