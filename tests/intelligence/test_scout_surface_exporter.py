"""Tests for normalizing Scout extraction responses from product surfaces."""

from __future__ import annotations

import pytest

from cios.intelligence.scout_surface_exporter import (
    ProductSurfaceTarget,
    ScoutSurfaceExtractionError,
    scout_extract_response_to_product_records,
)


def test_scout_extract_response_maps_changes_to_product_market_records() -> None:
    target = ProductSurfaceTarget(
        tenant_id=1,
        company_id=20,
        company_name="Constructor",
        company_role="competitor",
        surface_family="changelog",
        url="https://constructor.com/changelog",
    )
    response = {
        "success": True,
        "url": "https://constructor.com/changelog",
        "metadata": {"crawled_at": "2026-07-10T19:00:00+00:00"},
        "data": {
            "changes": [
                {
                    "capability": "AI Shopping Agent",
                    "change_type": "release",
                    "summary": "Constructor released AI Shopping Agent.",
                    "excerpt": "AI Shopping Agent helps shoppers use natural language.",
                }
            ]
        },
    }

    records = scout_extract_response_to_product_records(response, target)

    assert records == [
        {
            "company_id": 20,
            "company_name": "Constructor",
            "company_role": "competitor",
            "capability": "AI Shopping Agent",
            "change_type": "release",
            "summary": "Constructor released AI Shopping Agent.",
            "source_url": "https://constructor.com/changelog",
            "captured_at": "2026-07-10T19:00:00+00:00",
            "excerpt": "AI Shopping Agent helps shoppers use natural language.",
            "method": "scout_changelog",
            "surface_family": "changelog",
        }
    ]


def test_scout_extract_response_uses_surface_url_and_docs_method_when_needed() -> None:
    target = ProductSurfaceTarget(
        tenant_id=1,
        company_id=30,
        company_name="Elastic",
        company_role="competitor",
        surface_family="api_docs",
        url="https://www.elastic.co/guide/en/search-ui/current/",
    )
    response = {
        "success": True,
        "metadata": {"crawled_at": "2026-07-10T20:00:00+00:00"},
        "data": {
            "changes": [
                {
                    "capability": "context engineering",
                    "change_type": "docs_update",
                    "summary": "Elastic documented context engineering guidance.",
                }
            ]
        },
    }

    records = scout_extract_response_to_product_records(response, target)

    assert records[0]["source_url"] == "https://www.elastic.co/guide/en/search-ui/current/"
    assert records[0]["method"] == "scout_docs"


def test_scout_extract_response_returns_empty_for_no_changes() -> None:
    target = ProductSurfaceTarget(
        tenant_id=1,
        company_id=20,
        company_name="Constructor",
        surface_family="docs",
        url="https://docs.constructor.com/",
    )

    records = scout_extract_response_to_product_records(
        {"success": True, "data": {"changes": []}},
        target,
    )

    assert records == []


def test_scout_extract_response_raises_for_failed_scout_response() -> None:
    target = ProductSurfaceTarget(
        tenant_id=1,
        company_id=20,
        company_name="Constructor",
        surface_family="docs",
        url="https://docs.constructor.com/",
    )

    with pytest.raises(ScoutSurfaceExtractionError, match="blocked"):
        scout_extract_response_to_product_records(
            {"success": False, "error": "blocked by robots"},
            target,
        )
