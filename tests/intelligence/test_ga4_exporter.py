"""Tests for GA4 demand export normalization."""

from __future__ import annotations

from cios.intelligence.ga4_exporter import (
    Ga4DemandExportConfig,
    Ga4ReportRow,
    build_ga4_demand_records,
    export_ga4_demand_records,
    resolve_ga4_date_windows,
    summarize_ga4_demand_plan_coverage,
)


class FakeGa4Client:
    def run_report(self, *, property_id, dimensions, metric, start_date, end_date, limit):
        assert property_id == "123456"
        assert dimensions == ["pageTitle", "pagePath"]
        assert metric == "engagedSessions"
        assert limit == 5000
        if start_date == "2026-07-01":
            return [
                Ga4ReportRow(topic="AI Shopping Agent guide", url="/solutions/ai-shopping-agent", value=240.0),
                Ga4ReportRow(topic="Context engineering guide", url="/docs/context-engineering", value=180.0),
            ]
        return [
            Ga4ReportRow(topic="AI Shopping Agent guide", url="/solutions/ai-shopping-agent", value=160.0),
            Ga4ReportRow(topic="Context engineering guide", url="/docs/context-engineering", value=200.0),
        ]


def test_build_ga4_demand_records_calculates_change_and_provenance() -> None:
    config = Ga4DemandExportConfig(
        property_id="123456",
        current_start="2026-07-01",
        current_end="2026-07-08",
        previous_start="2026-06-24",
        previous_end="2026-06-30",
        source_url="https://lookerstudio.google.com/reporting/algolia-demand",
    )

    records = build_ga4_demand_records(
        config=config,
        current_rows=[
            Ga4ReportRow(topic="AI Shopping Agent guide", url="/solutions/ai-shopping-agent", value=240.0),
            Ga4ReportRow(topic="Context engineering guide", url="/docs/context-engineering", value=180.0),
        ],
        previous_rows=[
            Ga4ReportRow(topic="AI Shopping Agent guide", url="/solutions/ai-shopping-agent", value=160.0),
            Ga4ReportRow(topic="Context engineering guide", url="/docs/context-engineering", value=200.0),
        ],
    )

    assert records == [
        {
            "topic": "AI Shopping Agent guide",
            "metric": "engaged_sessions",
            "value": 240.0,
            "change_pct": 0.5,
            "period_start": "2026-07-01T00:00:00+00:00",
            "period_end": "2026-07-08T00:00:00+00:00",
            "source_label": "GA4 Data API export",
            "source_url": "https://lookerstudio.google.com/reporting/algolia-demand",
            "excerpt": (
                "pageTitle: AI Shopping Agent guide; pagePath: /solutions/ai-shopping-agent; "
                "engagedSessions: 240.0; previous: 160.0"
            ),
        },
        {
            "topic": "Context engineering guide",
            "metric": "engaged_sessions",
            "value": 180.0,
            "change_pct": -0.1,
            "period_start": "2026-07-01T00:00:00+00:00",
            "period_end": "2026-07-08T00:00:00+00:00",
            "source_label": "GA4 Data API export",
            "source_url": "https://lookerstudio.google.com/reporting/algolia-demand",
            "excerpt": (
                "pageTitle: Context engineering guide; pagePath: /docs/context-engineering; "
                "engagedSessions: 180.0; previous: 200.0"
            ),
        },
    ]


def test_export_ga4_demand_records_uses_client_and_sorts_by_current_value() -> None:
    config = Ga4DemandExportConfig(
        property_id="123456",
        current_start="2026-07-01",
        current_end="2026-07-08",
        previous_start="2026-06-24",
        previous_end="2026-06-30",
        source_url="https://lookerstudio.google.com/reporting/algolia-demand",
    )

    records = export_ga4_demand_records(config=config, client=FakeGa4Client())

    assert [row["topic"] for row in records] == [
        "AI Shopping Agent guide",
        "Context engineering guide",
    ]
    assert records[0]["change_pct"] == 0.5


def test_build_ga4_demand_records_tags_rows_that_match_argus_demand_plan() -> None:
    config = Ga4DemandExportConfig(
        property_id="123456",
        current_start="2026-07-01",
        current_end="2026-07-08",
        previous_start="2026-06-24",
        previous_end="2026-06-30",
        planned_topics=[
            {
                "topic": "AI Assistant",
                "capability_key": "ai assistant",
                "assessment": "own_product_gap",
                "why_collect": "Collect tenant demand for AI Assistant.",
                "suggested_filter_terms": ["AI Shopping Agent", "shopping agent"],
                "related_competitors": ["Constructor", "Elastic"],
                "evidence_urls": ["https://constructor.com/changelog/ai-assistant"],
            }
        ],
    )

    records = build_ga4_demand_records(
        config=config,
        current_rows=[
            Ga4ReportRow(topic="AI Shopping Agent guide", url="/solutions/ai-shopping-agent", value=240.0),
            Ga4ReportRow(topic="Pricing page", url="/pricing", value=190.0),
        ],
        previous_rows=[
            Ga4ReportRow(topic="AI Shopping Agent guide", url="/solutions/ai-shopping-agent", value=160.0),
            Ga4ReportRow(topic="Pricing page", url="/pricing", value=180.0),
        ],
    )

    matched = next(row for row in records if row["topic"] == "AI Shopping Agent guide")
    off_plan = next(row for row in records if row["topic"] == "Pricing page")
    assert matched["argus_capability_key"] == "ai assistant"
    assert matched["argus_assessment"] == "own_product_gap"
    assert matched["argus_suggested_filters"] == ["AI Shopping Agent", "shopping agent"]
    assert matched["argus_related_competitors"] == ["Constructor", "Elastic"]
    assert matched["argus_why_collect"] == "Collect tenant demand for AI Assistant."
    assert matched["argus_evidence_urls"] == ["https://constructor.com/changelog/ai-assistant"]
    assert matched["argus_plan_matched"] is True
    assert "argus_capability_key" not in off_plan

    assert summarize_ga4_demand_plan_coverage(config.planned_topics, records) == {
        "status": "partial_coverage",
        "planned_topic_count": 1,
        "matched_plan_topic_count": 1,
        "off_plan_record_count": 1,
        "matched_topics": ["ai assistant"],
        "missing_topics": [],
    }


def test_resolve_ga4_date_windows_uses_explicit_dates_when_present() -> None:
    window = resolve_ga4_date_windows(
        {
            "CIOS_GA4_CURRENT_START": "2026-07-01",
            "CIOS_GA4_CURRENT_END": "2026-07-08",
            "CIOS_GA4_PREVIOUS_START": "2026-06-24",
            "CIOS_GA4_PREVIOUS_END": "2026-06-30",
            "CIOS_GA4_ROLLING_DAYS": "14",
            "CIOS_GA4_TODAY": "2026-07-12",
        }
    )

    assert window.current_start == "2026-07-01"
    assert window.current_end == "2026-07-08"
    assert window.previous_start == "2026-06-24"
    assert window.previous_end == "2026-06-30"
    assert window.source == "explicit"


def test_resolve_ga4_date_windows_defaults_to_last_complete_rolling_week() -> None:
    window = resolve_ga4_date_windows({"CIOS_GA4_TODAY": "2026-07-12"})

    assert window.current_start == "2026-07-05"
    assert window.current_end == "2026-07-11"
    assert window.previous_start == "2026-06-28"
    assert window.previous_end == "2026-07-04"
    assert window.source == "rolling"
    assert window.rolling_days == 7
