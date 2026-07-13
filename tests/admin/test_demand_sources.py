from __future__ import annotations

import json

from cios.admin.demand_sources import build_demand_source_contract


def test_demand_source_contract_carries_public_safe_demand_plan_summary(tmp_path) -> None:
    contract = build_demand_source_contract(
        tenant_slug="algolia",
        work_root=tmp_path / "work",
        demand_plane={"status": "missing", "demand_signal_count": 0},
        manual_import={
            "drop_folder": str(tmp_path / "app" / "data" / "looker" / "algolia"),
            "manifest_path": str(tmp_path / "app" / "data" / "looker" / "algolia" / "manifest.json"),
            "accepted_suffixes": [".csv", ".json"],
            "template_fields": ["Page title", "Page path"],
        },
        ga4_connector={"enabled": False, "ready": False},
        generated_at="2026-07-12T02:00:00Z",
        demand_collection_plan={
            "status": "needs_demand_source",
            "summary": "Collect GA / Looker demand for 2 Argus-prioritized capability topics.",
            "source_dashboard_field": "product_market_run.product_feature_comparison_read.rows",
            "topic_count": 2,
            "drop_folder": "/root/.hermes/apps/cios/data/looker/algolia",
            "topics": [
                {
                    "topic": "AI Assistant",
                    "capability_key": "ai assistant",
                    "assessment": "own_product_gap",
                    "why_collect": "Internal operator rationale that should stay out of the compact contract.",
                    "related_competitors": ["Constructor", "Elastic"],
                    "suggested_filter_terms": ["AI Assistant", "AI agent"],
                    "evidence_urls": [
                        "https://constructor.com/changelog/ai-assistant",
                        "https://elastic.co/blog/ai-assistant",
                    ],
                },
                {
                    "topic": "Context engineering",
                    "capability_key": "context engineering",
                    "assessment": "own_narrative_gap",
                    "related_competitors": ["Elastic"],
                    "suggested_filter_terms": ["Context engineering"],
                    "evidence_urls": ["https://elastic.co/blog/context-engineering"],
                },
            ],
            "coverage": {
                "status": "off_plan",
                "planned_topic_count": 2,
                "covered_topic_count": 0,
                "missing_topic_count": 2,
                "off_plan_topic_count": 0,
                "coverage_ratio": 0,
            },
        },
    )

    assert contract["demand_plan"] == {
        "status": "needs_demand_source",
        "summary": "Collect GA / Looker demand for 2 Argus-prioritized capability topics.",
        "source_dashboard_field": "product_market_run.product_feature_comparison_read.rows",
        "topic_count": 2,
        "template": {
            "format": "csv",
            "filename": "argus-demand-plan-template.csv",
        },
        "top_topics": [
            {
                "topic": "AI Assistant",
                "capability_key": "ai assistant",
                "assessment": "own_product_gap",
                "related_competitors": ["Constructor", "Elastic"],
                "suggested_filter_terms": ["AI Assistant", "AI agent"],
                "evidence_url_count": 2,
            },
            {
                "topic": "Context engineering",
                "capability_key": "context engineering",
                "assessment": "own_narrative_gap",
                "related_competitors": ["Elastic"],
                "suggested_filter_terms": ["Context engineering"],
                "evidence_url_count": 1,
            },
        ],
        "coverage": {
            "status": "off_plan",
            "planned_topic_count": 2,
            "covered_topic_count": 0,
            "missing_topic_count": 2,
            "off_plan_topic_count": 0,
            "coverage_ratio": 0,
        },
    }
    rendered = json.dumps(contract["demand_plan"], sort_keys=True)
    assert "/root/" not in rendered
    assert "/admin" not in rendered
    assert "href" not in rendered
    assert "credentials" not in rendered.lower()
    assert "why_collect" not in rendered

