import importlib
import json
import sys
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_ROOT / "scripts"


def load_ci_core(monkeypatch, tmp_path):
    monkeypatch.setenv("COMPETITIVE_RESEARCH_OUTPUT_ROOT", str(tmp_path))
    sys.path.insert(0, str(SCRIPTS_DIR))
    sys.modules.pop("ci_core", None)
    return importlib.import_module("ci_core")


def source_row(**overrides):
    row = {
        "competitor": "Constructor",
        "tier": 1,
        "url": "https://constructor.com/customers",
        "source_type": "case_study",
        "signal_type": "customer_proof",
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
    row.update(overrides)
    return row


CUSTOMER_OLD = """
# Constructor customers

## Balsam Brands
Balsam Brands uses Constructor for ecommerce product discovery.

## Sephora
Sephora uses Constructor for personalized commerce search.
"""


CUSTOMER_NEW = CUSTOMER_OLD + """

## Petco
Petco uses Constructor AI Search for ecommerce product discovery and increased
conversion by 12%.
"""


CONTENT_TEXT = """
# Google Cloud AI blog

## Introducing Gemini Enterprise Agents for AI Search
June 24, 2026
Google Cloud is helping enterprise developers connect AI agents to search and
retrieval workflows. Learn more about building agentic discovery experiences.
"""


COOKIE_OLD = """
# Bloomreach customers
Cookie preferences Accept all Decline all
Navigation Products Customers Resources
"""


COOKIE_NEW = """
# Bloomreach customers
Cookie preferences Accept all Decline all Manage preferences
Navigation Products Customers Resources Careers Contact
"""


def test_customer_proof_extractor_identifies_named_customer_and_outcome(monkeypatch, tmp_path):
    ci_core = load_ci_core(monkeypatch, tmp_path)

    facts = ci_core.extract_semantic_facts(
        CUSTOMER_NEW,
        source_row(),
        detected_date="2026-06-28",
    )
    petco = [fact for fact in facts if fact["fact_json"].get("customer_name") == "Petco"][0]

    assert petco["fact_type"] == "customer_proof"
    assert petco["competitor"] == "Constructor"
    assert petco["evidence_url"] == "https://constructor.com/customers"
    assert petco["fact_json"]["metric"] == "12%"
    assert petco["fact_json"]["product_area"] == "AI search"
    assert petco["fact_json"]["proof_strength"] == "high"


def test_content_narrative_extractor_identifies_theme_and_content_opportunity(monkeypatch, tmp_path):
    ci_core = load_ci_core(monkeypatch, tmp_path)

    facts = ci_core.extract_semantic_facts(
        CONTENT_TEXT,
        source_row(
            competitor="Google Vertex AI Search",
            url="https://cloud.google.com/blog/products/ai-machine-learning",
            source_type="blog",
            signal_type="ai_visibility",
        ),
        detected_date="2026-06-28",
    )
    fact = facts[0]

    assert fact["fact_type"] == "content_narrative"
    assert fact["fact_json"]["topic"] == "agentic_search"
    assert fact["fact_json"]["target_audience"] == "developers"
    assert "agentic" in fact["fact_json"]["narrative_angle"].lower()
    assert "Algolia" in fact["fact_json"]["algolia_content_opportunity"]


def test_semantic_diff_detects_new_customer_proof(monkeypatch, tmp_path):
    ci_core = load_ci_core(monkeypatch, tmp_path)

    result = ci_core.semantic_diff(
        source_row(),
        old_text=CUSTOMER_OLD,
        new_text=CUSTOMER_NEW,
        detected_date="2026-06-28",
    )

    published = [delta for delta in result["deltas"] if delta["quality_status"] == "publish"]
    assert len(published) == 1
    assert published[0]["delta_type"] == "new_customer_proof"
    assert "Petco" in published[0]["delta_summary"]
    assert published[0]["action_owner"] == "Sales Enablement"
    assert published[0]["materiality_score"] >= 0.65


def test_semantic_diff_suppresses_cookie_only_change(monkeypatch, tmp_path):
    ci_core = load_ci_core(monkeypatch, tmp_path)

    result = ci_core.semantic_diff(
        source_row(competitor="Bloomreach", url="https://www.bloomreach.com/en/customers"),
        old_text=COOKIE_OLD,
        new_text=COOKIE_NEW,
        detected_date="2026-06-28",
    )

    assert result["deltas"]
    assert all(delta["quality_status"] == "suppressed" for delta in result["deltas"])
    assert all(delta["delta_type"] != "new_customer_proof" for delta in result["deltas"])


def test_collect_direct_sources_records_semantic_tables_and_suppresses_hash_only_signal(monkeypatch, tmp_path):
    ci_core = load_ci_core(monkeypatch, tmp_path)
    conn = ci_core.connect_db()
    ci_core.upsert_sources(conn, [source_row()])

    fetches = iter([
        {
            "status": "ok",
            "http_status": 200,
            "text": CUSTOMER_OLD,
            "error": None,
            "collector": "direct_http",
            "duration_ms": 20,
            "quality_score": 0.8,
        },
        {
            "status": "ok",
            "http_status": 200,
            "text": COOKIE_NEW,
            "error": None,
            "collector": "scout_scrape",
            "duration_ms": 25,
            "quality_score": 0.82,
        },
    ])
    monkeypatch.setattr(ci_core, "fetch_source", lambda row: next(fetches))

    first = ci_core.collect_direct_sources(conn, limit=1)
    second = ci_core.collect_direct_sources(conn, limit=1)

    assert first["signals"] == 0
    assert second["signals"] == 0
    assert conn.execute("select count(*) c from semantic_facts").fetchone()["c"] > 0
    suppressed = conn.execute("select * from semantic_deltas").fetchall()
    assert suppressed
    assert all(row["quality_status"] == "suppressed" for row in suppressed)
    assert conn.execute("select count(*) c from signals").fetchone()["c"] == 0


def test_synthesis_packet_prefers_semantic_deltas_over_raw_page_change(monkeypatch, tmp_path):
    ci_core = load_ci_core(monkeypatch, tmp_path)
    conn = ci_core.connect_db()
    ci_core.upsert_sources(conn, [source_row()])

    delta = ci_core.semantic_diff(
        source_row(),
        old_text=CUSTOMER_OLD,
        new_text=CUSTOMER_NEW,
        detected_date="2026-06-28",
    )["deltas"][0]
    ci_core.insert_semantic_deltas(conn, [delta])
    ci_core.insert_signals(conn, [ci_core.semantic_delta_to_signal(delta)])

    packet = ci_core.build_synthesis_packet(conn, "daily", "2026-06-28", "2026-06-28")
    markdown = ci_core.synthesize_local(packet, cadence="daily")

    assert packet["semantic_deltas"]
    assert "Petco" in markdown
    assert "Why it matters to Algolia" in markdown
    assert "changed case_study" not in markdown
    assert "changed since the previous snapshot" not in markdown
    raw = json.loads(packet["signals"][0]["raw_json"])
    assert raw["semantic_delta"]["delta_type"] == "new_customer_proof"


def test_synthesis_packet_filters_legacy_raw_change_signals(monkeypatch, tmp_path):
    ci_core = load_ci_core(monkeypatch, tmp_path)
    conn = ci_core.connect_db()
    ci_core.insert_signals(conn, [
        ci_core.build_signal(
            competitor="Constructor",
            category="customer_proof",
            source_url="https://constructor.com/customers",
            source_type="case_study",
            title="Constructor changed case_study",
            evidence="Constructor public case_study source changed since the previous snapshot.",
            summary="Constructor public case_study source changed since the previous snapshot.",
            detected_date="2026-06-28",
            event_date="2026-06-28",
            novelty=0.85,
            confidence=0.72,
            impact=0.8,
            raw={"collector": "direct_fetch", "baseline": False},
        )
    ])

    packet = ci_core.build_synthesis_packet(conn, "weekly", "2026-06-28", "2026-06-28")
    markdown = ci_core.synthesize_local(packet, cadence="weekly")

    assert packet["signals"] == []
    assert packet["source_ledger"] == []
    assert "changed case_study" not in markdown
    assert "changed since the previous snapshot" not in markdown
    assert "No material public signals" in markdown
