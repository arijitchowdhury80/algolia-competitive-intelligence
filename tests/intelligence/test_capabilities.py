"""Tests for canonical product-market capability normalization."""

from __future__ import annotations

from cios.intelligence.capabilities import capability_key


def test_capability_key_filters_non_feature_market_metadata() -> None:
    assert capability_key("product positioning") == ""
    assert capability_key("product_positioning") == ""
    assert capability_key("new_content_narrative") == ""
    assert capability_key("new customer proof") == ""
    assert capability_key("Algolia Academy") == ""


def test_capability_key_removes_vendor_and_support_scaffolding() -> None:
    assert capability_key("Algolia Model Context Protocol (MCP) Support") == "model context protocol"
    assert capability_key("Algolia AI: Dynamic Re-Ranking") == "dynamic re ranking"
