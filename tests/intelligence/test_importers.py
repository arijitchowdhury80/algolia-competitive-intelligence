"""Tests for file-based product-market payload imports."""

from __future__ import annotations

import json

from cios.intelligence.importers import (
    build_payload_from_exports,
    diagnose_looker_rows,
    load_export_records,
)


def test_load_export_records_reads_json_list(tmp_path) -> None:
    path = tmp_path / "scout.json"
    path.write_text(json.dumps([{"company_name": "Constructor"}]), encoding="utf-8")

    rows = load_export_records(path)

    assert rows == [{"company_name": "Constructor"}]


def test_load_export_records_reads_jsonl(tmp_path) -> None:
    path = tmp_path / "conversation.jsonl"
    path.write_text('{"company_name":"Constructor"}\n\n{"company_name":"Elastic"}\n', encoding="utf-8")

    rows = load_export_records(path)

    assert [row["company_name"] for row in rows] == ["Constructor", "Elastic"]


def test_load_export_records_reads_csv(tmp_path) -> None:
    path = tmp_path / "looker.csv"
    path.write_text(
        "topic,metric,value,change_pct,period_start,period_end,source_label,source_url\n"
        "agentic product discovery,engaged_sessions,1234,0.23,2026-07-03T00:00:00+00:00,2026-07-10T00:00:00+00:00,Looker Studio GA4 export,looker://algolia/ga4/topics\n",
        encoding="utf-8",
    )

    rows = load_export_records(path)

    assert rows[0]["topic"] == "agentic product discovery"
    assert rows[0]["value"] == "1234"


def test_build_payload_from_exports_combines_scout_conversation_and_looker_files(tmp_path) -> None:
    scout = tmp_path / "scout.json"
    scout.write_text(
        json.dumps([
            {
                "company_id": 20,
                "company_name": "Constructor",
                "company_role": "competitor",
                "capability": "agentic product discovery",
                "change_type": "release",
                "summary": "Constructor documented AI Shopping Agent.",
                "source_url": "https://constructor.com/changelog/ai-shopping-agent",
                "captured_at": "2026-07-10T19:00:00+00:00",
            }
        ]),
        encoding="utf-8",
    )
    conversation = tmp_path / "conversation.jsonl"
    conversation.write_text(
        '{"company_id":20,"company_name":"Constructor","theme":"agentic product discovery",'
        '"summary":"Constructor is positioning around AI shopping agents.","intensity":0.82,'
        '"source_url":"https://constructor.com/blog/ai-shopping-agent",'
        '"captured_at":"2026-07-10T19:00:00+00:00"}\n',
        encoding="utf-8",
    )
    looker = tmp_path / "looker.csv"
    looker.write_text(
        "topic,metric,value,change_pct,period_start,period_end,source_label,source_url\n"
        "agentic product discovery,engaged_sessions,1234,0.23,2026-07-03T00:00:00+00:00,2026-07-10T00:00:00+00:00,Looker Studio GA4 export,looker://algolia/ga4/topics\n",
        encoding="utf-8",
    )

    payload = build_payload_from_exports(
        own_company_name="Algolia",
        tenant_id=1,
        scout_path=scout,
        conversation_path=conversation,
        looker_path=looker,
    )

    assert payload.tenant_id == 1
    assert payload.own_company_name == "Algolia"
    assert payload.scout_records[0]["company_name"] == "Constructor"
    assert payload.conversation_records[0]["theme"] == "agentic product discovery"
    assert payload.looker_rows[0]["source_label"] == "Looker Studio GA4 export"
    assert payload.looker_rows[0]["source_file"] == "looker.csv"
    assert payload.looker_rows[0]["source_row_number"] == 1
    assert len(payload.looker_rows[0]["source_fingerprint"]) == 64


def test_build_payload_from_exports_merges_scout_command_records_with_file_records(tmp_path) -> None:
    scout = tmp_path / "scout.json"
    scout.write_text(json.dumps([{"company_name": "Constructor"}]), encoding="utf-8")

    payload = build_payload_from_exports(
        own_company_name="Algolia",
        tenant_id=1,
        scout_path=scout,
        scout_records=[{"company_name": "Elastic"}],
    )

    assert [row["company_name"] for row in payload.scout_records] == [
        "Constructor",
        "Elastic",
    ]


def test_build_payload_from_exports_merges_multiple_looker_paths(tmp_path) -> None:
    header = "topic,metric,value,change_pct,period_start,period_end,source_label,source_url\n"
    looker_a = tmp_path / "a.csv"
    looker_b = tmp_path / "b.csv"
    looker_a.write_text(
        header
        + "agentic product discovery,engaged_sessions,100,0.10,2026-07-01T00:00:00+00:00,2026-07-08T00:00:00+00:00,GA4,looker://algolia/a\n",
        encoding="utf-8",
    )
    looker_b.write_text(
        header
        + "context engineering,engaged_sessions,200,0.20,2026-07-01T00:00:00+00:00,2026-07-08T00:00:00+00:00,GA4,looker://algolia/b\n",
        encoding="utf-8",
    )

    payload = build_payload_from_exports(
        own_company_name="Algolia",
        tenant_id=1,
        looker_paths=[looker_a, looker_b],
    )

    assert [row["topic"] for row in payload.looker_rows] == [
        "agentic product discovery",
        "context engineering",
    ]


def test_build_payload_from_exports_normalizes_raw_ga_looker_page_rows(tmp_path) -> None:
    looker = tmp_path / "ga-pages.csv"
    looker.write_text(
        "Page title,Page path,Engaged sessions,Engaged sessions previous period,Period start,Period end,Looker Studio URL\n"
        "AI Shopping Agent guide,/solutions/ai-shopping-agent,240,160,2026-07-01,2026-07-08,https://lookerstudio.google.com/reporting/abc\n",
        encoding="utf-8",
    )

    payload = build_payload_from_exports(
        own_company_name="Algolia",
        tenant_id=1,
        looker_path=looker,
    )

    row = payload.looker_rows[0]
    assert row == {
        "topic": "AI Shopping Agent",
        "metric": "engaged_sessions",
        "value": 240.0,
        "change_pct": 0.5,
        "period_start": "2026-07-01T00:00:00+00:00",
        "period_end": "2026-07-08T00:00:00+00:00",
        "source_label": "Looker Studio GA4 export",
        "source_url": "https://lookerstudio.google.com/reporting/abc",
        "excerpt": "Page title: AI Shopping Agent guide; Page path: /solutions/ai-shopping-agent",
        "source_file": "ga-pages.csv",
        "source_row_number": 1,
        "source_fingerprint": row["source_fingerprint"],
    }
    assert len(row["source_fingerprint"]) == 64


def test_build_payload_from_argus_plan_template_rows_uses_argus_topic(tmp_path) -> None:
    looker = tmp_path / "argus-demand-plan-template.csv"
    looker.write_text(
        "Page title,Page path,Engaged sessions,Engaged sessions previous period,Period start,Period end,Looker Studio URL,"
        "Argus topic,Capability key,Assessment,Suggested filters,Related competitors,Why collect,Evidence URLs\n"
        ",,240,160,2026-07-01,2026-07-08,https://lookerstudio.google.com/reporting/abc,"
        "AI Assistant,ai assistant,own_product_gap,AI Assistant | assistant,Constructor | Elastic,"
        "Decide whether Algolia needs product proof for AI Assistant.,https://constructor.com/changelog/ai-assistant\n",
        encoding="utf-8",
    )

    payload = build_payload_from_exports(
        own_company_name="Algolia",
        tenant_id=1,
        looker_path=looker,
    )

    row = payload.looker_rows[0]
    assert row["topic"] == "AI Assistant"
    assert row["metric"] == "engaged_sessions"
    assert row["value"] == 240.0
    assert row["change_pct"] == 0.5
    assert row["period_start"] == "2026-07-01T00:00:00+00:00"
    assert row["period_end"] == "2026-07-08T00:00:00+00:00"
    assert row["source_label"] == "Looker Studio GA4 export"
    assert row["source_url"] == "https://lookerstudio.google.com/reporting/abc"
    assert row["source_file"] == "argus-demand-plan-template.csv"
    assert row["source_row_number"] == 1
    assert row["argus_capability_key"] == "ai assistant"
    assert row["argus_assessment"] == "own_product_gap"
    assert row["argus_suggested_filters"] == ["AI Assistant", "assistant"]
    assert row["argus_related_competitors"] == ["Constructor", "Elastic"]
    assert row["argus_why_collect"].startswith("Decide whether Algolia needs")
    assert row["argus_evidence_urls"] == ["https://constructor.com/changelog/ai-assistant"]


def test_build_payload_preserves_json_list_argus_plan_metadata(tmp_path) -> None:
    looker = tmp_path / "ga4-demand.json"
    looker.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "topic": "AI Shopping Agent guide",
                        "metric": "engaged_sessions",
                        "value": 240,
                        "change_pct": 0.5,
                        "period_start": "2026-07-01T00:00:00+00:00",
                        "period_end": "2026-07-08T00:00:00+00:00",
                        "source_label": "GA4 Data API export",
                        "source_url": "ga4://properties/123456/runReport",
                        "argus_capability_key": "ai assistant",
                        "argus_assessment": "own_product_gap",
                        "argus_suggested_filters": ["AI Shopping Agent", "shopping agent"],
                        "argus_related_competitors": ["Constructor", "Elastic"],
                        "argus_why_collect": "Collect tenant demand for AI Assistant.",
                        "argus_evidence_urls": ["https://constructor.com/changelog/ai-assistant"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    payload = build_payload_from_exports(
        own_company_name="Algolia",
        tenant_id=1,
        looker_path=looker,
    )

    row = payload.looker_rows[0]
    assert row["argus_capability_key"] == "ai assistant"
    assert row["argus_assessment"] == "own_product_gap"
    assert row["argus_suggested_filters"] == ["AI Shopping Agent", "shopping agent"]
    assert row["argus_related_competitors"] == ["Constructor", "Elastic"]
    assert row["argus_why_collect"] == "Collect tenant demand for AI Assistant."
    assert row["argus_evidence_urls"] == ["https://constructor.com/changelog/ai-assistant"]


def test_normalized_looker_rows_are_deduped_by_source_fingerprint(tmp_path) -> None:
    looker = tmp_path / "ga-pages.csv"
    looker.write_text(
        "Page title,Page path,Engaged sessions,Engaged sessions previous period,Period start,Period end,Looker Studio URL\n"
        "AI Shopping Agent guide,/solutions/ai-shopping-agent,240,160,2026-07-01,2026-07-08,https://lookerstudio.google.com/reporting/abc\n"
        "AI Shopping Agent guide,/solutions/ai-shopping-agent,240,160,2026-07-01,2026-07-08,https://lookerstudio.google.com/reporting/abc\n",
        encoding="utf-8",
    )

    payload = build_payload_from_exports(
        own_company_name="Algolia",
        tenant_id=1,
        looker_path=looker,
    )

    assert len(payload.looker_rows) == 1
    assert payload.looker_rows[0]["source_row_number"] == 1


def test_normalizes_real_ga4_looker_page_export_with_date_range(tmp_path) -> None:
    looker = tmp_path / "looker-pages.csv"
    looker.write_text(
        "Page title and screen name,Landing page + query string,Engaged sessions,Engaged sessions (previous period),Date range,Looker Studio URL\n"
        "AI shopping assistants for ecommerce,/solutions/ecommerce/ai-shopping-assistant?utm_source=report,\"1,240\",930,\"Jul 1, 2026 - Jul 8, 2026\",https://lookerstudio.google.com/reporting/ga4\n",
        encoding="utf-8",
    )

    payload = build_payload_from_exports(
        own_company_name="Algolia",
        tenant_id=1,
        looker_path=looker,
    )

    row = payload.looker_rows[0]
    assert row["topic"] == "AI Shopping Agent"
    assert row["metric"] == "engaged_sessions"
    assert row["value"] == 1240.0
    assert row["change_pct"] == round((1240 - 930) / 930, 4)
    assert row["period_start"] == "2026-07-01T00:00:00+00:00"
    assert row["period_end"] == "2026-07-08T00:00:00+00:00"
    assert "Page title: AI shopping assistants for ecommerce" in row["excerpt"]
    assert "Page path: /solutions/ecommerce/ai-shopping-assistant?utm_source=report" in row["excerpt"]


def test_already_normalized_looker_rows_get_stable_default_provenance(tmp_path) -> None:
    source = tmp_path / "manual-normalized.json"
    rows = [
        {
            "topic": "AI Shopping Agent",
            "metric": "engaged_sessions",
            "value": "240",
            "period_start": "2026-07-01",
            "period_end": "2026-07-08",
        }
    ]

    diagnosis = diagnose_looker_rows(rows, source_path=source)

    assert diagnosis["skipped_row_count"] == 0
    row = diagnosis["normalized"][0]
    assert row["source_label"] == "Looker Studio GA4 export"
    assert row["source_url"] == "looker://manual-normalized.json#row-1"
    assert row["period_start"] == "2026-07-01T00:00:00+00:00"
    assert row["period_end"] == "2026-07-08T00:00:00+00:00"
    assert len(row["source_fingerprint"]) == 64


def test_already_normalized_looker_rows_skip_when_required_period_is_missing(tmp_path) -> None:
    source = tmp_path / "bad-normalized.json"
    rows = [
        {
            "topic": "AI Shopping Agent",
            "metric": "engaged_sessions",
            "value": "240",
        }
    ]

    diagnosis = diagnose_looker_rows(rows, source_path=source)

    assert diagnosis["normalized"] == []
    assert diagnosis["skipped_row_count"] == 1
    assert diagnosis["skipped_rows"] == [
        {
            "row_number": 1,
            "reason": "missing_period",
            "missing_fields": ["period"],
            "source_file": "bad-normalized.json",
            "available_columns": ["metric", "topic", "value"],
        }
    ]


def test_already_normalized_looker_rows_skip_when_value_is_zero(tmp_path) -> None:
    source = tmp_path / "zero-normalized.json"
    rows = [
        {
            "topic": "AI Shopping Agent",
            "metric": "engaged_sessions",
            "value": "0",
            "period_start": "2026-07-01",
            "period_end": "2026-07-08",
        }
    ]

    diagnosis = diagnose_looker_rows(rows, source_path=source)

    assert diagnosis["normalized"] == []
    assert diagnosis["skipped_row_count"] == 1
    assert diagnosis["skipped_rows"] == [
        {
            "row_number": 1,
            "reason": "non_positive_metric",
            "missing_fields": ["value"],
            "source_file": "zero-normalized.json",
            "available_columns": ["metric", "period_end", "period_start", "topic", "value"],
        }
    ]


def test_raw_looker_page_rows_skip_when_metric_is_zero(tmp_path) -> None:
    source = tmp_path / "zero-ga-pages.csv"
    rows = [
        {
            "Page title": "AI Shopping Agent guide",
            "Page path": "/solutions/ai-shopping-agent",
            "Engaged sessions": "0",
            "Engaged sessions previous period": "0",
            "Period start": "2026-07-01",
            "Period end": "2026-07-08",
            "Looker Studio URL": "https://lookerstudio.google.com/reporting/abc",
        }
    ]

    diagnosis = diagnose_looker_rows(rows, source_path=source)

    assert diagnosis["normalized"] == []
    assert diagnosis["skipped_row_count"] == 1
    assert diagnosis["skipped_rows"] == [
        {
            "row_number": 1,
            "reason": "non_positive_metric",
            "missing_fields": ["value"],
            "source_file": "zero-ga-pages.csv",
            "available_columns": [
                "Engaged sessions",
                "Engaged sessions previous period",
                "Looker Studio URL",
                "Page path",
                "Page title",
                "Period end",
                "Period start",
            ],
        }
    ]


def test_diagnose_looker_rows_reports_skipped_row_reasons(tmp_path) -> None:
    source = tmp_path / "bad-export.csv"
    rows = [
        {
            "Page title and screen name": "Generic blog post",
            "Landing page + query string": "/blog/company-news",
            "Engaged sessions": "120",
            "Date range": "Jul 1, 2026 - Jul 8, 2026",
        },
        {
            "Page title and screen name": "AI shopping assistants for ecommerce",
            "Landing page + query string": "/solutions/ecommerce/ai-shopping-assistant",
            "Date range": "Jul 1, 2026 - Jul 8, 2026",
        },
    ]

    diagnosis = diagnose_looker_rows(rows, source_path=source)

    assert diagnosis["normalized"] == []
    assert diagnosis["skipped_row_count"] == 2
    assert diagnosis["skipped_rows"] == [
        {
            "row_number": 1,
            "reason": "missing_topic",
            "missing_fields": ["topic"],
            "source_file": "bad-export.csv",
            "available_columns": [
                "Date range",
                "Engaged sessions",
                "Landing page + query string",
                "Page title and screen name",
            ],
        },
        {
            "row_number": 2,
            "reason": "missing_metric",
            "missing_fields": ["metric"],
            "source_file": "bad-export.csv",
            "available_columns": [
                "Date range",
                "Landing page + query string",
                "Page title and screen name",
            ],
        },
    ]
