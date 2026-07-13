"""Adapter tests for bringing Scout and Looker/GA data into Argus."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from cios.intelligence.adapters import (
    conversation_record_to_conversation_theme,
    looker_row_to_demand_signal,
    scout_record_to_product_change_event,
)
from cios.intelligence.types import SourceMethod


NOW = datetime(2026, 7, 10, 14, 0, tzinfo=timezone.utc)


def test_scout_record_maps_to_product_change_event() -> None:
    event = scout_record_to_product_change_event(
        tenant_id=1,
        company_id=20,
        company_name="Constructor",
        company_role="competitor",
        record={
            "capability": "agentic product discovery",
            "change_type": "release",
            "summary": "Constructor documents AI Shopping Agent",
            "source_url": "https://constructor.com/changelog/ai-shopping-agent",
            "captured_at": NOW.isoformat(),
            "excerpt": "AI Shopping Agent helps shoppers use natural language.",
            "method": "scout_changelog",
        },
    )

    assert event.company_name == "Constructor"
    assert event.capability == "agentic product discovery"
    assert event.evidence[0].source_url == "https://constructor.com/changelog/ai-shopping-agent"
    assert event.evidence[0].method == SourceMethod.SCOUT_CHANGELOG


def test_scout_record_requires_source_url() -> None:
    with pytest.raises(ValueError, match="source_url"):
        scout_record_to_product_change_event(
            tenant_id=1,
            company_id=20,
            company_name="Constructor",
            company_role="competitor",
            record={
                "capability": "agentic product discovery",
                "change_type": "release",
                "summary": "Constructor documents AI Shopping Agent",
                "captured_at": NOW.isoformat(),
            },
        )


def test_looker_row_maps_to_demand_signal() -> None:
    signal = looker_row_to_demand_signal(
        tenant_id=1,
        row={
            "topic": "agentic product discovery",
            "metric": "engaged_sessions",
            "value": "1234",
            "change_pct": "0.23",
            "period_start": "2026-07-03T00:00:00+00:00",
            "period_end": "2026-07-10T00:00:00+00:00",
            "source_label": "Looker Studio GA4 export",
            "source_url": "looker://algolia/ga4/topics",
            "excerpt": "Topic engagement increased week over week.",
            "source_file": "ga-pages.csv",
            "source_row_number": 4,
            "source_fingerprint": "a" * 64,
        },
    )

    assert signal.topic == "agentic product discovery"
    assert signal.value == pytest.approx(1234)
    assert signal.change_pct == pytest.approx(0.23)
    assert signal.evidence[0].method == SourceMethod.LOOKER_EXPORT
    assert signal.metadata == {
        "source_file": "ga-pages.csv",
        "source_row_number": 4,
        "source_fingerprint": "a" * 64,
    }


def test_looker_row_preserves_argus_plan_metadata() -> None:
    signal = looker_row_to_demand_signal(
        tenant_id=1,
        row={
            "topic": "AI Assistant",
            "metric": "engaged_sessions",
            "value": "240",
            "change_pct": "0.50",
            "period_start": "2026-07-01T00:00:00+00:00",
            "period_end": "2026-07-08T00:00:00+00:00",
            "source_label": "Looker Studio GA4 export",
            "source_url": "https://lookerstudio.google.com/reporting/abc",
            "source_file": "argus-demand-plan-template.csv",
            "source_row_number": 1,
            "source_fingerprint": "b" * 64,
            "argus_capability_key": "ai assistant",
            "argus_assessment": "own_product_gap",
            "argus_suggested_filters": ["AI Assistant", "assistant"],
            "argus_related_competitors": ["Constructor", "Elastic"],
            "argus_why_collect": "Decide whether Algolia needs product proof for AI Assistant.",
            "argus_evidence_urls": ["https://constructor.com/changelog/ai-assistant"],
        },
    )

    assert signal.metadata == {
        "source_file": "argus-demand-plan-template.csv",
        "source_row_number": 1,
        "source_fingerprint": "b" * 64,
        "argus_capability_key": "ai assistant",
        "argus_assessment": "own_product_gap",
        "argus_suggested_filters": ["AI Assistant", "assistant"],
        "argus_related_competitors": ["Constructor", "Elastic"],
        "argus_why_collect": "Decide whether Algolia needs product proof for AI Assistant.",
        "argus_evidence_urls": ["https://constructor.com/changelog/ai-assistant"],
    }


def test_looker_row_requires_evidence_url() -> None:
    with pytest.raises(ValueError, match="source_url"):
        looker_row_to_demand_signal(
            tenant_id=1,
            row={
                "topic": "agentic product discovery",
                "metric": "engaged_sessions",
                "value": "1234",
                "period_start": "2026-07-03T00:00:00+00:00",
                "period_end": "2026-07-10T00:00:00+00:00",
                "source_label": "Looker Studio GA4 export",
            },
        )


def test_conversation_record_maps_to_conversation_theme() -> None:
    theme = conversation_record_to_conversation_theme(
        tenant_id=1,
        record={
            "company_id": 20,
            "company_name": "Constructor",
            "theme": "agentic product discovery",
            "summary": "Constructor is positioning around AI shopping agents.",
            "intensity": "0.82",
            "source_url": "https://constructor.com/blog/ai-shopping-agent",
            "captured_at": NOW.isoformat(),
            "excerpt": "AI Shopping Agent helps shoppers use natural language.",
        },
    )

    assert theme.company_id == 20
    assert theme.company_name == "Constructor"
    assert theme.theme == "agentic product discovery"
    assert theme.intensity == pytest.approx(0.82)
    assert theme.evidence[0].source_url == "https://constructor.com/blog/ai-shopping-agent"
    assert theme.evidence[0].method == SourceMethod.WEB_SCAN


def test_conversation_record_requires_source_url() -> None:
    with pytest.raises(ValueError, match="source_url"):
        conversation_record_to_conversation_theme(
            tenant_id=1,
            record={
                "company_name": "Constructor",
                "theme": "agentic product discovery",
                "summary": "Constructor is positioning around AI shopping agents.",
                "captured_at": NOW.isoformat(),
            },
        )
