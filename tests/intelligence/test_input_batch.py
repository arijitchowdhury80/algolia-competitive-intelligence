"""Tests for normalizing collector outputs into product-market workflow inputs."""

from __future__ import annotations

from datetime import datetime, timezone

from cios.intelligence.inputs import build_product_market_input_batch


NOW = datetime(2026, 7, 10, 17, 0, tzinfo=timezone.utc)


def test_build_product_market_input_batch_from_scout_conversation_and_looker_rows() -> None:
    batch = build_product_market_input_batch(
        tenant_id=1,
        scout_records=[
            {
                "company_id": 20,
                "company_name": "Constructor",
                "company_role": "competitor",
                "capability": "agentic product discovery",
                "change_type": "release",
                "summary": "Constructor documented AI Shopping Agent.",
                "source_url": "https://constructor.com/changelog/ai-shopping-agent",
                "captured_at": NOW.isoformat(),
            }
        ],
        conversation_records=[
            {
                "company_id": 20,
                "company_name": "Constructor",
                "theme": "agentic product discovery",
                "summary": "Constructor is positioning around AI shopping agents.",
                "intensity": 0.82,
                "source_url": "https://constructor.com/blog/ai-shopping-agent",
                "captured_at": NOW.isoformat(),
            }
        ],
        looker_rows=[
            {
                "topic": "agentic product discovery",
                "metric": "engaged_sessions",
                "value": 1234,
                "change_pct": 0.23,
                "period_start": NOW.isoformat(),
                "period_end": NOW.isoformat(),
                "source_label": "Looker Studio GA4 export",
                "source_url": "looker://algolia/ga4/topics",
            }
        ],
    )

    assert batch.product_events[0].company_name == "Constructor"
    assert batch.conversation_themes[0].theme == "agentic product discovery"
    assert batch.demand_signals[0].source_label == "Looker Studio GA4 export"
