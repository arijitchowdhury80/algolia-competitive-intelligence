import importlib
import json
import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_ROOT / "scripts"


def load_ci_core(monkeypatch, tmp_path):
    monkeypatch.setenv("COMPETITIVE_RESEARCH_OUTPUT_ROOT", str(tmp_path))
    sys.path.insert(0, str(SCRIPTS_DIR))
    sys.modules.pop("ci_core", None)
    return importlib.import_module("ci_core")


def weekly_packet():
    return {
        "cadence": "weekly",
        "date_start": "2026-06-20",
        "date_end": "2026-06-26",
        "counts": {
            "total": 1,
            "by_owner": {"Product Marketing": 1},
            "by_category": {"ai_visibility": 1},
        },
        "source_coverage": {
            "totals": {
                "enabled_sources": 2,
                "checked_sources": 2,
                "successful_sources": 1,
                "failed_sources": 1,
                "missing_sources": 0,
                "changed_signal_sources": 1,
            },
            "sources": [
                {
                    "competitor": "OpenAI / ChatGPT",
                    "source_type": "blog",
                    "url": "https://openai.com/blog/",
                    "status": "error",
                    "error": "HTTP 403 Forbidden",
                }
            ],
        },
        "signals": [
            {
                "id": 101,
                "competitor": "AWS OpenSearch / CloudSearch",
                "category": "ai_visibility",
                "source_url": "https://aws.amazon.com/about-aws/whats-new/example",
                "source_type": "blog",
                "event_date": "2026-06-24",
                "detected_date": "2026-06-26",
                "title": "OpenSearch agent integration expands",
                "summary": "AWS positioned OpenSearch for agentic retrieval workflows.",
                "confidence": 0.9,
                "novelty": 0.8,
                "impact": 0.85,
                "score": 0.86,
                "action_owner": "Product Marketing",
            }
        ],
        "source_ledger": [
            {
                "id": "101",
                "url": "https://aws.amazon.com/about-aws/whats-new/example",
                "title": "OpenSearch agent integration expands",
                "competitor": "AWS OpenSearch / CloudSearch",
                "category": "ai_visibility",
            }
        ],
    }


WEEKLY_MARKDOWN = """**Weekly competitive synthesis - 2026-06-20 to 2026-06-26**

**What changed**

AWS expanded its agentic search positioning through [OpenSearch](https://aws.amazon.com/about-aws/whats-new/example).

**Strategic pattern**

Confirmed fact: the public signal supports a Product Marketing response.

**Recommended actions by owner**

- **Product Marketing:** Review the agentic retrieval positioning and update comparison messaging.

**Battlecard updates**

Add an objection note for agentic OpenSearch positioning.

**Coverage gaps**

- **OpenAI / ChatGPT:** [blog](https://openai.com/blog/) returned collection failure.
"""


def test_weekly_html_renderer_returns_valid_report(monkeypatch, tmp_path):
    ci_core = load_ci_core(monkeypatch, tmp_path)

    html = ci_core.render_html_report(WEEKLY_MARKDOWN, weekly_packet(), cadence="weekly")

    assert "<!doctype html>" in html
    assert "Weekly competitive synthesis" in html
    assert "Product Marketing" in html
    assert "OpenAI / ChatGPT" in html


def test_llm_synthesis_prompts_use_argus_not_athena(monkeypatch, tmp_path):
    ci_core = load_ci_core(monkeypatch, tmp_path)
    packet = weekly_packet()
    packet["date_start"] = "2026-06-26"
    packet["date_end"] = "2026-06-26"

    daily_prompt = ci_core.build_daily_prompt(packet)
    weekly_prompt = ci_core.build_weekly_prompt(packet)

    assert daily_prompt.startswith("You are Argus")
    assert weekly_prompt.startswith("You are Argus")
    assert "Athena supervises" in daily_prompt
    assert "Athena supervises" in weekly_prompt
    assert "You are Athena" not in daily_prompt
    assert "You are Athena" not in weekly_prompt


def test_weekly_artifacts_save_with_weekly_suffix(monkeypatch, tmp_path):
    ci_core = load_ci_core(monkeypatch, tmp_path)
    html = "<!doctype html><title>Weekly</title>"

    markdown_path = ci_core.save_markdown(WEEKLY_MARKDOWN, "2026-06-26", cadence="weekly")
    html_path = ci_core.save_html(html, "2026-06-26", cadence="weekly")

    assert markdown_path == tmp_path / "briefs" / "2026-06-26-weekly.md"
    assert html_path == tmp_path / "reports" / "2026-06-26-weekly.html"
    assert markdown_path.read_text().startswith("**Weekly competitive synthesis")
    assert html_path.read_text() == html


def test_daily_material_filter_rejects_direct_baseline_capture(monkeypatch, tmp_path):
    ci_core = load_ci_core(monkeypatch, tmp_path)

    signal = {
        "competitor": "Constructor",
        "category": "customer_proof",
        "source_url": "https://constructor.com/customers",
        "source_type": "case_study",
        "title": "Constructor baseline captured case_study",
        "score": 0.72,
        "novelty": 0.35,
        "raw_json": json.dumps({"collector": "direct_fetch", "baseline": True}),
    }

    assert ci_core.signal_is_daily_material(signal) is False


def test_daily_material_filter_accepts_changed_direct_signal(monkeypatch, tmp_path):
    ci_core = load_ci_core(monkeypatch, tmp_path)

    signal = {
        "competitor": "Constructor",
        "category": "customer_proof",
        "source_url": "https://constructor.com/customers",
        "source_type": "case_study",
        "title": "Constructor customers changed",
        "score": 0.72,
        "novelty": 0.85,
        "raw_json": json.dumps({"collector": "direct_fetch", "baseline": False}),
    }

    assert ci_core.signal_is_daily_material(signal) is True


def test_daily_quiet_day_with_full_coverage_does_not_invent_repair_action(monkeypatch, tmp_path):
    ci_core = load_ci_core(monkeypatch, tmp_path)

    packet = {
        "cadence": "daily",
        "date_start": "2026-06-29",
        "date_end": "2026-06-29",
        "signals": [],
        "source_ledger": [],
        "source_coverage": {
            "totals": {
                "enabled_sources": 39,
                "checked_sources": 39,
                "successful_sources": 39,
                "failed_sources": 0,
                "missing_sources": 0,
            },
            "sources": [],
        },
    }

    markdown = ci_core.synthesize_local(packet, cadence="daily")

    assert "39 succeeded, 0 failed, and 0 were missing" in markdown
    assert "No immediate competitive action is recommended today" in markdown
    assert "repair or replace" not in markdown
    assert "because some source coverage needs repair" not in markdown
    assert "missing_links" not in ci_core.validate_output(markdown)
    assert ci_core.quality_score(markdown) >= 0.9


def test_material_report_without_links_still_fails_link_gate(monkeypatch, tmp_path):
    ci_core = load_ci_core(monkeypatch, tmp_path)

    markdown = """**Competitive pulse - 2026-06-29**

**Bottom line**

Constructor launched a new customer proof campaign.

**Recommended action**

Sales Enablement should review the playbook.
"""

    assert "missing_links" in ci_core.validate_output(markdown)
    assert ci_core.quality_score(markdown) < 0.9


def test_hermes_empty_reply_is_treated_as_synthesis_failure(monkeypatch, tmp_path):
    ci_core = load_ci_core(monkeypatch, tmp_path)

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="⚠️ No reply: the model returned empty content after retries and any fallback providers.\n",
            stderr="",
        )

    monkeypatch.setattr(ci_core.subprocess, "run", fake_run)

    try:
        ci_core.synthesize_with_hermes("weekly prompt")
    except RuntimeError as exc:
        assert "empty/provider-failure" in str(exc)
    else:
        raise AssertionError("provider failure marker should raise RuntimeError")


def test_daily_quiet_day_with_failed_sources_routes_ci_ops_repair(monkeypatch, tmp_path):
    ci_core = load_ci_core(monkeypatch, tmp_path)

    packet = {
        "cadence": "daily",
        "date_start": "2026-06-29",
        "date_end": "2026-06-29",
        "signals": [],
        "source_ledger": [],
        "source_coverage": {
            "totals": {
                "enabled_sources": 39,
                "checked_sources": 39,
                "successful_sources": 38,
                "failed_sources": 1,
                "missing_sources": 0,
            },
            "sources": [
                {
                    "competitor": "Constructor",
                    "source_type": "customer proof",
                    "url": "https://constructor.com/customers",
                    "status": "error",
                    "error": "HTTP 403 Forbidden",
                }
            ],
        },
    }

    markdown = ci_core.synthesize_local(packet, cadence="daily")

    assert "38 succeeded, 1 failed, and 0 were missing" in markdown
    assert "repair or replace failed and missing sources" in markdown
    assert "low-medium confidence" in markdown


def test_v1_dashboard_tables_exist(monkeypatch, tmp_path):
    ci_core = load_ci_core(monkeypatch, tmp_path)
    conn = ci_core.connect_db()

    tables = {
        row["name"]
        for row in conn.execute(
            "select name from sqlite_master where type = 'table'"
        ).fetchall()
    }

    assert "source_health_events" in tables
    assert "report_index" in tables
    assert "action_items" in tables
    assert "bot_deliveries" in tables

    source_columns = {row["name"] for row in conn.execute("pragma table_info(sources)").fetchall()}
    snapshot_columns = {row["name"] for row in conn.execute("pragma table_info(snapshots)").fetchall()}
    health_columns = {row["name"] for row in conn.execute("pragma table_info(source_health_events)").fetchall()}

    assert {"collector", "fallback_collectors", "expected_content_markers", "requires_js"}.issubset(source_columns)
    assert {
        "collector",
        "duration_ms",
        "quality_score",
        "quality_reasons",
        "recommended_collector",
        "recommended_collector_reason",
        "content_markers_found",
        "content_markers_missing",
        "acquisition_json",
    }.issubset(snapshot_columns)
    assert {"collector", "duration_ms", "quality_score"}.issubset(health_columns)
    action_columns = {row["name"] for row in conn.execute("pragma table_info(action_items)").fetchall()}
    delivery_columns = {row["name"] for row in conn.execute("pragma table_info(bot_deliveries)").fetchall()}
    assert {"source_delta_ids", "due_window", "confidence"}.issubset(action_columns)
    assert {
        "cadence",
        "message_kind",
        "markdown_path",
        "html_path",
        "dashboard_url",
        "artifact_paths",
        "delivery_metadata",
        "updated_at",
    }.issubset(delivery_columns)


def test_source_registry_adds_collector_strategy(monkeypatch, tmp_path):
    ci_core = load_ci_core(monkeypatch, tmp_path)

    config = {
        "sources": {
            "constructor": {
                "company": "Constructor",
                "tier": 1,
                "urls": [
                    {
                        "url": "https://constructor.com/product",
                        "type": "product",
                        "signal_type": "positioning_messaging",
                    },
                    {
                        "url": "https://ir.coveo.com/en/news-events/press-releases",
                        "type": "press",
                        "signal_type": "product_release",
                    }
                ],
            },
            "openai": {
                "company": "OpenAI / ChatGPT",
                "tier": 4,
                "urls": [
                    {
                        "url": "https://openai.com/news/rss.xml",
                        "type": "rss",
                        "signal_type": "ai_visibility",
                    }
                ],
            },
        }
    }

    records = ci_core.flatten_sources(config)

    by_url = {record["url"]: record for record in records}
    assert by_url["https://constructor.com/product"]["collector"] == "scout_scrape"
    assert by_url["https://constructor.com/product"]["requires_js"] == 1
    assert by_url["https://ir.coveo.com/en/news-events/press-releases"]["collector"] == "scout_scrape"
    assert by_url["https://openai.com/news/rss.xml"]["collector"] == "rss_feed"
    assert "direct_http" in by_url["https://openai.com/news/rss.xml"]["fallback_collectors"]


def test_fetch_source_routes_scout_collector(monkeypatch, tmp_path):
    ci_core = load_ci_core(monkeypatch, tmp_path)
    conn = ci_core.connect_db()
    ci_core.upsert_sources(conn, [
        {
            "competitor": "Constructor",
            "tier": 1,
            "url": "https://constructor.com/product",
            "source_type": "product",
            "signal_type": "positioning_messaging",
            "cadence": "weekly",
            "priority": 2,
            "enabled": 1,
            "notes": "",
            "collector": "scout_scrape",
            "fallback_collectors": "direct_http",
            "expected_content_markers": "[]",
            "requires_js": 1,
            "gated": 0,
            "criticality": "important",
        }
    ])
    row = conn.execute("select * from sources where url = ?", ("https://constructor.com/product",)).fetchone()

    called = {}

    def fake_scout(url, timeout=60, use_js=True, expected_markers=None, source_id=None):
        called["url"] = url
        called["use_js"] = use_js
        called["expected_markers"] = expected_markers
        called["source_id"] = source_id
        return {
            "status": "ok",
            "http_status": 200,
            "text": "clean scout markdown",
            "error": None,
            "collector": "scout_scrape",
            "duration_ms": 12,
        }

    monkeypatch.setattr(ci_core, "fetch_scout_url", fake_scout)

    result = ci_core.fetch_source(row)

    assert result["collector"] == "scout_scrape"
    assert result["text"] == "clean scout markdown"
    assert called == {
        "url": "https://constructor.com/product",
        "use_js": True,
        "expected_markers": [],
        "source_id": "https://constructor.com/product",
    }


def test_fetch_scout_url_uses_acquisition_metadata_and_clean_markdown(monkeypatch, tmp_path):
    monkeypatch.setenv("SCOUT_API_KEY", "test-token")
    ci_core = load_ci_core(monkeypatch, tmp_path)
    captured = {}

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({
                "success": True,
                "markdown": "raw markdown",
                "clean_markdown": "clean markdown",
                "acquisition": {
                    "quality_score": 0.82,
                    "quality_reasons": ["expected_marker_found"],
                    "recommended_collector": "scout_scrape",
                    "recommended_collector_reason": "browser_rendered_product_page",
                    "content_markers_found": ["AI Search"],
                    "content_markers_missing": [],
                    "content_hash": "abc123",
                },
            }).encode("utf-8")

    def fake_urlopen(req, timeout):
        captured["timeout"] = timeout
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        captured["api_key"] = req.get_header("X-api-key")
        return FakeResponse()

    monkeypatch.setattr(ci_core, "urlopen", fake_urlopen)

    result = ci_core.fetch_scout_url(
        "https://www.algolia.com",
        use_js=True,
        expected_markers=["AI Search"],
        source_id="algolia-docs",
    )

    assert result["status"] == "ok"
    assert result["text"] == "clean markdown"
    assert result["raw_text"] == "raw markdown"
    assert result["quality_score"] == 0.82
    assert result["recommended_collector"] == "scout_scrape"
    assert captured["payload"]["quality_analysis"] is True
    assert captured["payload"]["cleanup"] is True
    assert captured["payload"]["recommend_collector"] is True
    assert captured["payload"]["expected_markers"] == ["AI Search"]
    assert captured["payload"]["source_id"] == "algolia-docs"


def test_fetch_source_routes_rss_feed_collector(monkeypatch, tmp_path):
    ci_core = load_ci_core(monkeypatch, tmp_path)
    conn = ci_core.connect_db()
    ci_core.upsert_sources(conn, [
        {
            "competitor": "OpenAI / ChatGPT",
            "tier": 4,
            "url": "https://openai.com/news/rss.xml",
            "source_type": "rss",
            "signal_type": "ai_visibility",
            "cadence": "daily",
            "priority": 2,
            "enabled": 1,
            "notes": "",
            "collector": "rss_feed",
            "fallback_collectors": "direct_http,scout_scrape",
            "expected_content_markers": "[]",
            "requires_js": 0,
            "gated": 0,
            "criticality": "important",
        }
    ])
    row = conn.execute("select * from sources where url = ?", ("https://openai.com/news/rss.xml",)).fetchone()

    def fake_rss(url, timeout=25):
        return {
            "status": "ok",
            "http_status": 200,
            "text": "Feed: OpenAI News\n- GPT update\n  Link: https://openai.com/news/example",
            "error": None,
            "collector": "rss_feed",
            "duration_ms": 9,
            "quality_score": 0.9,
        }

    monkeypatch.setattr(ci_core, "fetch_rss_url", fake_rss)

    result = ci_core.fetch_source(row)

    assert result["collector"] == "rss_feed"
    assert "GPT update" in result["text"]


def test_fetch_source_uses_fallback_collector_after_primary_error(monkeypatch, tmp_path):
    ci_core = load_ci_core(monkeypatch, tmp_path)
    conn = ci_core.connect_db()
    ci_core.upsert_sources(conn, [
        {
            "competitor": "Coveo",
            "tier": 1,
            "url": "https://www.coveo.com/en/platform",
            "source_type": "product",
            "signal_type": "positioning_messaging",
            "cadence": "daily",
            "priority": 1,
            "enabled": 1,
            "notes": "",
            "collector": "scout_scrape",
            "fallback_collectors": "direct_http",
            "expected_content_markers": "[]",
            "requires_js": 1,
            "gated": 0,
            "criticality": "important",
        }
    ])
    row = conn.execute("select * from sources where url = ?", ("https://www.coveo.com/en/platform",)).fetchone()

    monkeypatch.setattr(ci_core, "fetch_scout_url", lambda *args, **kwargs: {
        "status": "error",
        "http_status": None,
        "text": "",
        "error": "Blocked by anti-bot protection",
        "collector": "scout_scrape",
        "duration_ms": 20,
    })
    monkeypatch.setattr(ci_core, "fetch_url", lambda url: {
        "status": "ok",
        "http_status": 200,
        "text": "Coveo platform page direct fallback",
        "error": None,
        "collector": "direct_http",
        "duration_ms": 11,
    })

    result = ci_core.fetch_source(row)

    assert result["status"] == "ok"
    assert result["collector"] == "direct_http"
    assert result["primary_collector"] == "scout_scrape"
    assert result["fallback_used"] == "direct_http"
    assert result["attempts"][0]["collector"] == "scout_scrape"
    assert result["attempts"][1]["collector"] == "direct_http"


def test_fetch_rss_url_parses_feed_items(monkeypatch, tmp_path):
    ci_core = load_ci_core(monkeypatch, tmp_path)
    feed_xml = """<?xml version="1.0"?>
    <rss version="2.0">
      <channel>
        <title>OpenAI News</title>
        <item>
          <title>GPT update</title>
          <link>https://openai.com/news/example</link>
          <pubDate>Sat, 27 Jun 2026 10:00:00 GMT</pubDate>
          <description>New model update for developers.</description>
        </item>
      </channel>
    </rss>
    """

    class FakeHeaders:
        def get_content_charset(self):
            return "utf-8"

    class FakeResponse:
        status = 200
        headers = FakeHeaders()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self, *_args):
            return feed_xml.encode("utf-8")

    monkeypatch.setattr(ci_core, "urlopen", lambda req, timeout: FakeResponse())

    result = ci_core.fetch_rss_url("https://openai.com/news/rss.xml")

    assert result["collector"] == "rss_feed"
    assert result["status"] == "ok"
    assert "Feed: OpenAI News" in result["text"]
    assert "GPT update" in result["text"]
    assert "https://openai.com/news/example" in result["text"]
    assert result["quality_score"] >= 0.8


def test_save_snapshot_persists_quality_metadata(monkeypatch, tmp_path):
    ci_core = load_ci_core(monkeypatch, tmp_path)
    conn = ci_core.connect_db()

    snapshot_id = ci_core.save_snapshot(conn, "https://example.com", {
        "status": "ok",
        "http_status": 200,
        "text": "clean markdown",
        "error": None,
        "collector": "scout_scrape",
        "duration_ms": 123,
        "quality_score": 0.82,
        "quality_reasons": ["expected_marker_found"],
        "recommended_collector": "scout_scrape",
        "recommended_collector_reason": "browser_rendered_product_page",
        "content_markers_found": ["AI Search"],
        "content_markers_missing": [],
        "acquisition": {"content_hash": "abc123"},
    })

    row = conn.execute("select * from snapshots where id = ?", (snapshot_id,)).fetchone()

    assert row["collector"] == "scout_scrape"
    assert row["duration_ms"] == 123
    assert row["quality_score"] == 0.82
    assert json.loads(row["quality_reasons"]) == ["expected_marker_found"]
    assert row["recommended_collector"] == "scout_scrape"
    assert json.loads(row["content_markers_found"]) == ["AI Search"]
    assert json.loads(row["acquisition_json"]) == {"content_hash": "abc123"}


def test_collect_direct_sources_writes_source_health_events(monkeypatch, tmp_path):
    ci_core = load_ci_core(monkeypatch, tmp_path)
    conn = ci_core.connect_db()
    ci_core.upsert_sources(conn, [
        {
            "competitor": "Constructor",
            "tier": 1,
            "url": "https://constructor.com/product",
            "source_type": "product",
            "signal_type": "positioning_messaging",
            "cadence": "daily",
            "priority": 1,
            "enabled": 1,
            "notes": "",
            "collector": "scout_scrape",
            "fallback_collectors": "direct_http",
            "expected_content_markers": "[]",
            "requires_js": 1,
            "gated": 0,
            "criticality": "important",
        }
    ])

    monkeypatch.setattr(ci_core, "fetch_source", lambda row: {
        "status": "ok",
        "http_status": 200,
        "text": "Constructor AI Search product positioning",
        "error": None,
        "collector": "scout_scrape",
        "duration_ms": 321,
        "quality_score": 0.88,
        "recommended_collector": "scout_scrape",
    })

    result = ci_core.collect_direct_sources(conn, limit=1)
    event = conn.execute("select * from source_health_events").fetchone()

    assert result["snapshots"] == 1
    assert event["source_url"] == "https://constructor.com/product"
    assert event["collector"] == "scout_scrape"
    assert event["status"] == "ok"
    assert event["duration_ms"] == 321
    assert event["quality_score"] == 0.88


def test_record_synthesis_run_updates_report_index(monkeypatch, tmp_path):
    ci_core = load_ci_core(monkeypatch, tmp_path)
    conn = ci_core.connect_db()

    markdown_path = tmp_path / "briefs" / "2026-06-26-weekly.md"
    html_path = tmp_path / "reports" / "2026-06-26-weekly.html"
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(WEEKLY_MARKDOWN)
    html_path.write_text("<!doctype html><title>Weekly</title>")

    report_id = ci_core.record_synthesis_run(
        conn,
        "weekly",
        "2026-06-20",
        "2026-06-26",
        [101],
        markdown_path,
        html_path,
        0.91,
    )

    row = conn.execute("select * from report_index where cadence = 'weekly'").fetchone()
    assert row["id"] == report_id
    assert row["date_start"] == "2026-06-20"
    assert row["date_end"] == "2026-06-26"
    assert row["markdown_path"].endswith("2026-06-26-weekly.md")
    assert row["html_path"].endswith("2026-06-26-weekly.html")
    assert row["quality_score"] == 0.91


def test_report_archive_and_action_queue_helpers(monkeypatch, tmp_path):
    ci_core = load_ci_core(monkeypatch, tmp_path)
    conn = ci_core.connect_db()
    markdown_path = tmp_path / "briefs" / "2026-06-26.md"
    html_path = tmp_path / "reports" / "2026-06-26.html"

    ci_core.record_synthesis_run(
        conn,
        "daily",
        "2026-06-26",
        "2026-06-26",
        [101],
        markdown_path,
        html_path,
        0.88,
    )

    archive = ci_core.list_report_archive(conn)
    assert archive[0]["cadence"] == "daily"
    assert archive[0]["quality_score"] == 0.88

    action_id = ci_core.create_action_item(
        conn,
        title="Repair blocked OpenAI source",
        owner="Competitive Intelligence",
        recommendation="Replace direct blog fetch with a public search/RSS fallback.",
        evidence_signal_ids=[101],
        report_id=archive[0]["id"],
        priority=2,
    )
    actions = ci_core.list_action_items(conn)
    assert actions[0]["id"] == action_id
    assert actions[0]["status"] == "proposed"
    assert actions[0]["owner"] == "Competitive Intelligence"


def test_delivery_record_written_for_report(monkeypatch, tmp_path):
    ci_core = load_ci_core(monkeypatch, tmp_path)
    conn = ci_core.connect_db()
    report_id = ci_core.record_synthesis_run(
        conn,
        "daily",
        "2026-06-29",
        "2026-06-29",
        [],
        tmp_path / "briefs" / "2026-06-29.md",
        tmp_path / "reports" / "2026-06-29.html",
        1.0,
    )

    delivery_id = ci_core.record_bot_delivery(
        conn,
        report_id=report_id,
        cadence="daily",
        bot_profile="argus",
        channel="telegram",
        recipient="6789423537",
        status="queued_for_telegram",
        markdown_path="/briefs/2026-06-29.md",
        html_path="/reports/2026-06-29.html",
        dashboard_url="https://ci.chowmes.com/",
        artifact_paths=["/briefs/2026-06-29.md", "/reports/2026-06-29.html"],
        delivery_metadata={"source": "cron_stdout"},
    )

    rows = ci_core.list_bot_deliveries(conn, cadence="daily")
    assert rows[0]["id"] == delivery_id
    assert rows[0]["report_id"] == report_id
    assert rows[0]["bot_profile"] == "argus"
    assert rows[0]["channel"] == "telegram"
    assert rows[0]["status"] == "queued_for_telegram"
    assert rows[0]["dashboard_url"] == "https://ci.chowmes.com/"
    assert json.loads(rows[0]["artifact_paths"]) == ["/briefs/2026-06-29.md", "/reports/2026-06-29.html"]


def test_action_items_created_only_from_publishable_semantic_deltas(monkeypatch, tmp_path):
    ci_core = load_ci_core(monkeypatch, tmp_path)
    conn = ci_core.connect_db()
    report_id = ci_core.record_synthesis_run(
        conn,
        "weekly",
        "2026-06-23",
        "2026-06-29",
        [],
        tmp_path / "briefs" / "2026-06-29-weekly.md",
        tmp_path / "reports" / "2026-06-29-weekly.html",
        0.94,
    )

    created = ci_core.create_action_items_from_semantic_deltas(conn, report_id, [
        {
            "id": 17,
            "quality_status": "publish",
            "action_owner": "Sales Enablement",
            "recommended_action": "Validate Constructor customer proof against active objection handling.",
            "delta_summary": "Constructor added Petco proof.",
            "materiality_score": 0.82,
            "evidence_urls": ["https://constructor.com/customers"],
        },
        {
            "id": 18,
            "quality_status": "suppressed",
            "action_owner": "Product Marketing",
            "recommended_action": "Ignore cookie-banner movement.",
            "delta_summary": "Cookie copy changed.",
            "materiality_score": 0.0,
            "evidence_urls": ["https://example.com"],
        },
    ])

    assert len(created) == 1
    action = ci_core.list_action_items(conn)[0]
    assert action["owner"] == "Sales Enablement"
    assert action["source_delta_ids"] == "[17]"
    assert action["due_window"] == "next business day"
    assert action["confidence"] == 0.82


def test_weekly_semantic_report_uses_workflow_backed_action_candidates(monkeypatch, tmp_path):
    ci_core = load_ci_core(monkeypatch, tmp_path)
    packet = weekly_packet()
    packet["semantic_deltas"] = [
        {
            "id": 17,
            "competitor": "Constructor",
            "delta_type": "new_customer_proof",
            "delta_summary": "Constructor added Petco proof.",
            "algolia_implication": "Sales should validate whether this changes proof pressure.",
            "action_owner": "Sales Enablement",
            "recommended_action": "Validate the proof against active objection handling.",
            "evidence_urls": ["https://constructor.com/customers"],
            "quality_status": "publish",
            "materiality_score": 0.82,
        }
    ]
    packet["suppressed_deltas"] = []

    markdown = ci_core.synthesize_local(packet, cadence="weekly")

    assert "Workflow action candidates" in markdown
    assert "Recommended actions by owner" not in markdown
    assert "Sales Enablement" in markdown
    assert "Action records should be created from these material semantic deltas" in markdown


def test_source_health_summary_uses_coverage(monkeypatch, tmp_path):
    ci_core = load_ci_core(monkeypatch, tmp_path)
    conn = ci_core.connect_db()
    conn.execute(
        """
        insert into sources (competitor, tier, url, source_type, signal_type, cadence, priority, collector)
        values ('OpenAI / ChatGPT', 4, 'https://openai.com/blog', 'blog', 'ai_visibility', 'daily', 2, 'rss_feed')
        """
    )
    conn.execute(
        """
        insert into snapshots (source_url, fetched_at, status, http_status, error)
        values ('https://openai.com/blog', '2026-06-26T19:00:00', 'error', null, 'HTTP Error 403: Forbidden')
        """
    )
    conn.commit()

    rows = ci_core.list_source_health(conn, "2026-06-26", "2026-06-26")

    assert rows[0]["competitor"] == "OpenAI / ChatGPT"
    assert rows[0]["status"] == "error"
    assert rows[0]["error"] == "HTTP Error 403: Forbidden"


def test_static_dashboard_renders_six_views(monkeypatch, tmp_path):
    ci_core = load_ci_core(monkeypatch, tmp_path)
    conn = ci_core.connect_db()
    markdown_path = tmp_path / "briefs" / "2026-06-26-weekly.md"
    html_path = tmp_path / "reports" / "2026-06-26-weekly.html"
    ci_core.record_synthesis_run(
        conn,
        "weekly",
        "2026-06-20",
        "2026-06-26",
        [101],
        markdown_path,
        html_path,
        0.91,
    )
    conn.execute(
        """
        insert into sources (competitor, tier, url, source_type, signal_type, cadence, priority, collector)
        values ('OpenAI / ChatGPT', 4, 'https://openai.com/blog', 'blog', 'ai_visibility', 'daily', 2, 'rss_feed')
        """
    )
    conn.execute(
        """
        insert into snapshots (source_url, fetched_at, status, error)
        values ('https://openai.com/blog', '2026-06-26T19:00:00', 'error', 'HTTP Error 403: Forbidden')
        """
    )
    ci_core.create_action_item(
        conn,
        title="Repair OpenAI source",
        owner="Competitive Intelligence",
        recommendation="Replace blocked direct fetch.",
        evidence_signal_ids=[101],
        report_id=1,
    )

    html = ci_core.render_dashboard_html(conn, "2026-06-26", "2026-06-26")

    assert "CI Command Center" in html
    assert "Today" in html
    assert "Weekly" in html
    assert "Sources" in html
    assert "Collectors:" in html
    assert "rss_feed" in html
    assert "Signals" in html
    assert "Actions" in html
    assert "Archive" in html
    assert "Repair OpenAI source" in html


def test_collector_benchmark_writes_artifacts(monkeypatch, tmp_path):
    ci_core = load_ci_core(monkeypatch, tmp_path)

    monkeypatch.setattr(ci_core, "fetch_url", lambda url, timeout=25: {
        "status": "ok",
        "collector": "direct_http",
        "duration_ms": 10,
        "text": "direct text for %s" % url,
    })
    monkeypatch.setattr(ci_core, "fetch_scout_url", lambda url, timeout=60, use_js=True, expected_markers=None, source_id=None: {
        "status": "ok",
        "collector": "scout_scrape",
        "duration_ms": 20,
        "text": "scout text for %s" % url,
        "quality_score": 0.8,
        "recommended_collector": "scout_scrape",
    })
    monkeypatch.setattr(ci_core, "fetch_rss_url", lambda url, timeout=25: {
        "status": "ok",
        "collector": "rss_feed",
        "duration_ms": 5,
        "text": "feed text for %s" % url,
        "quality_score": 0.9,
    })

    out_dir = ci_core.run_collector_benchmark(
        targets=[
            {"id": "static", "label": "Static", "url": "https://example.com", "expected_collector": "direct_http"},
            {"id": "feed", "label": "Feed", "url": "https://openai.com/news/rss.xml", "expected_collector": "rss_feed"},
        ],
        date_str="2026-06-27",
    )

    benchmark = json.loads((out_dir / "benchmark.json").read_text())
    comparison = (out_dir / "comparison.md").read_text()

    assert benchmark["targets"][0]["results"]["direct_http"]["status"] == "ok"
    assert benchmark["targets"][0]["selected_collector"] == "direct_http"
    assert benchmark["targets"][1]["results"]["rss_feed"]["status"] == "ok"
    assert benchmark["targets"][1]["selected_collector"] == "rss_feed"
    assert (out_dir / "samples" / "static-direct_http.txt").exists()
    assert (out_dir / "samples" / "feed-rss_feed.txt").exists()
    assert "| Static |" in comparison
    assert "direct_http" in comparison
    assert "scout_scrape" in comparison
