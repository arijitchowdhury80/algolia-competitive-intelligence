#!/usr/bin/env python3
"""Shared competitive intelligence engine for the Algolia CI skill.

The daily and weekly runners should stay thin. This module owns the source
registry, SQLite ledger, public-source fetching, signal normalization, scoring,
and report rendering so fixture runs can test output quality without live
collection or model calls.
"""

import difflib
import hashlib
import html
import json
import os
import re
import sqlite3
import subprocess
import textwrap
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

import yaml


SKILL_DIR = Path(__file__).resolve().parent.parent
LOCAL_KNOWLEDGE_ROOT = Path("/Volumes/Data/Dropbox/AI-Development/Personal/Obsidian-Vault/MyOS/Projects/Competitive Intelligence/artifacts/competitive-research")
DEFAULT_RUNTIME_KNOWLEDGE_ROOT = Path("/opt/data/knowledge/obsidian/MyOS/Projects/Competitive Intelligence/artifacts/competitive-research")
DEFAULT_KNOWLEDGE_ROOT = DEFAULT_RUNTIME_KNOWLEDGE_ROOT if DEFAULT_RUNTIME_KNOWLEDGE_ROOT.exists() else LOCAL_KNOWLEDGE_ROOT
KNOWLEDGE_ROOT = Path(os.environ.get("COMPETITIVE_RESEARCH_OUTPUT_ROOT", str(DEFAULT_KNOWLEDGE_ROOT)))
SOURCES_FILE = SKILL_DIR / "references" / "sources.yaml"
RAW_DIR = KNOWLEDGE_ROOT / "raw"
BRIEFS_DIR = KNOWLEDGE_ROOT / "briefs"
REPORTS_DIR = KNOWLEDGE_ROOT / "reports"
DASHBOARD_DIR = KNOWLEDGE_ROOT / "dashboard"
BENCHMARKS_DIR = KNOWLEDGE_ROOT / "benchmarks"
DB_PATH = Path(os.environ.get("COMPETITIVE_RESEARCH_DB", str(KNOWLEDGE_ROOT / "ci.sqlite")))
SCOUT_BASE_URL = os.environ.get("SCOUT_BASE_URL", "http://127.0.0.1:8421").rstrip("/")
SCOUT_API_KEY = os.environ.get("SCOUT_API_KEY", "")
ALGOLIA_DESIGN_SYSTEM_PATH = Path(os.environ.get(
    "ALGOLIA_DESIGN_SYSTEM_PATH",
    "/Volumes/Data/Dropbox/AI-Projects/Algolia-Design-System",
))
ALGOLIA_DESIGN_SYSTEM_FALLBACKS = [
    ALGOLIA_DESIGN_SYSTEM_PATH,
    Path("/Volumes/Data/Dropbox/AI-Development/Algolia-Design-System"),
    Path("/Users/arijitchowdhury/Library/CloudStorage/GoogleDrive-arijit.chowdhury@gmail.com/My Drive/AI-Projects/Algolia-Design-System"),
]
HERMES_BIN = os.environ.get("HERMES_BIN", "/opt/hermes/.venv/bin/hermes")
SYNTHESIS_MODEL = os.environ.get("COMPETITIVE_RESEARCH_MODEL", "gemini-2.5-flash")
SYNTHESIS_PROVIDER = os.environ.get("COMPETITIVE_RESEARCH_PROVIDER", "").strip()

ACTION_OWNERS = [
    "Product",
    "Product Marketing",
    "Sales Enablement",
    "Partner Enablement",
    "Competitive Intelligence",
    "Executive Review",
]

SIGNAL_CATEGORIES = [
    "product_release",
    "changelog_docs_change",
    "pricing_packaging",
    "positioning_messaging",
    "customer_proof",
    "partnership_marketplace",
    "hiring_org_signal",
    "analyst_review_signal",
    "customer_community_voice",
    "seo_content_movement",
    "ai_visibility",
    "sales_relevant_objection",
    "algolia_baseline_comparison",
]

ALGOLIA_BASELINE = [
    {
        "competitor": "Algolia",
        "category": "algolia_baseline_comparison",
        "title": "Algolia MCP baseline",
        "summary": "Algolia has MCP offerings, including Productivity MCP and Public MCP.",
        "source_url": "https://www.algolia.com/doc/guides/model-context-protocol",
        "evidence": "Official Algolia MCP documentation describes Productivity MCP and Public MCP.",
        "action_owner": "Product Marketing",
        "confidence": 0.95,
        "impact": 0.65,
        "novelty": 0.2,
    },
    {
        "competitor": "Algolia",
        "category": "algolia_baseline_comparison",
        "title": "Algolia Public MCP server baseline",
        "summary": "Algolia documents a remote MCP server endpoint at mcp.algolia.com.",
        "source_url": "https://www.algolia.com/doc/guides/model-context-protocol/public-mcp",
        "evidence": "Official Algolia docs list the Public MCP server endpoint.",
        "action_owner": "Product Marketing",
        "confidence": 0.95,
        "impact": 0.6,
        "novelty": 0.2,
    },
]

CI_COLLECTOR_BENCHMARK_TARGETS = [
    {
        "id": "google-ai-blog",
        "label": "Google AI blog",
        "url": "https://cloud.google.com/blog/products/ai-machine-learning",
        "expected_collector": "scout_scrape",
        "expected_markers": ["AI", "Google Cloud"],
    },
    {
        "id": "constructor-product",
        "label": "Constructor product",
        "url": "https://constructor.com/product",
        "expected_collector": "scout_scrape",
        "expected_markers": ["Product", "AI"],
    },
    {
        "id": "coveo-press-blog",
        "label": "Coveo press/blog",
        "url": "https://ir.coveo.com/en/news-events/press-releases",
        "expected_collector": "scout_scrape",
        "expected_markers": ["Coveo", "press"],
    },
    {
        "id": "bloomreach-updates",
        "label": "Bloomreach updates",
        "url": "https://www.bloomreach.com/en/products/updates",
        "expected_collector": "direct_http",
        "expected_markers": ["Bloomreach", "updates"],
    },
    {
        "id": "openai-rss",
        "label": "OpenAI RSS",
        "url": "https://openai.com/news/rss.xml",
        "expected_collector": "rss_feed",
        "expected_markers": ["OpenAI"],
    },
    {
        "id": "static-example",
        "label": "Simple static source",
        "url": "https://example.com",
        "expected_collector": "direct_http",
        "expected_markers": ["Example Domain"],
    },
]


class TextExtractor(HTMLParser):
    """Small HTML-to-text extractor that avoids adding heavy dependencies."""

    def __init__(self) -> None:
        super().__init__()
        self._skip = 0
        self.parts: List[str] = []

    def handle_starttag(self, tag: str, attrs: Sequence[Tuple[str, Optional[str]]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip += 1
        if tag in {"p", "li", "h1", "h2", "h3", "h4", "tr", "br", "section", "article"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._skip:
            self._skip -= 1
        if tag in {"p", "li", "h1", "h2", "h3", "h4", "tr", "section", "article"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)

    def text(self) -> str:
        return normalize_text(" ".join(self.parts))


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def date_today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def ensure_dirs() -> None:
    for path in [RAW_DIR, BRIEFS_DIR, REPORTS_DIR, DASHBOARD_DIR, BENCHMARKS_DIR, DB_PATH.parent]:
        path.mkdir(parents=True, exist_ok=True)


def normalize_text(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return clean_generated_text(text).strip()


def clean_generated_text(text: str) -> str:
    return (
        (text or "")
        .replace("\u2014", "-")
        .replace("\u2013", "-")
        .replace("\u2192", "->")
        .replace("\u00a0", " ")
    )


def clean_synthesis_markdown(text: str) -> str:
    text = clean_generated_text(text)
    for marker in ["**Weekly competitive synthesis", "**Competitive pulse", "**Bottom line**"]:
        idx = text.find(marker)
        if idx > 0:
            return text[idx:].strip()
    return text.strip()


def content_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def connect_db(db_path: Path = DB_PATH) -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        create table if not exists sources (
          id integer primary key autoincrement,
          competitor text not null,
          tier integer,
          url text not null unique,
          source_type text,
          signal_type text,
          cadence text,
          priority integer default 3,
          enabled integer default 1,
          notes text,
          created_at text default current_timestamp,
          updated_at text default current_timestamp
        );

        create table if not exists snapshots (
          id integer primary key autoincrement,
          source_url text not null,
          fetched_at text not null,
          status text not null,
          http_status integer,
          content_hash text,
          content_text text,
          error text,
          foreign key(source_url) references sources(url)
        );

        create table if not exists signals (
          id integer primary key autoincrement,
          competitor text not null,
          category text not null,
          source_url text not null,
          source_type text,
          event_date text,
          detected_date text not null,
          title text not null,
          evidence_snippet text,
          summary text,
          confidence real default 0.6,
          novelty real default 0.5,
          impact real default 0.5,
          score real default 0.5,
          action_owner text default 'Competitive Intelligence',
          status text default 'new',
          raw_json text,
          created_at text default current_timestamp
        );

        create table if not exists semantic_facts (
          id integer primary key autoincrement,
          source_url text not null,
          competitor text not null,
          source_type text,
          detected_date text not null,
          fact_type text not null,
          fact_json text not null,
          evidence_text text,
          evidence_url text,
          confidence real default 0.6,
          created_at text default current_timestamp
        );

        create table if not exists semantic_deltas (
          id integer primary key autoincrement,
          source_url text not null,
          competitor text not null,
          source_type text,
          detected_date text not null,
          delta_type text not null,
          before_json text,
          after_json text,
          delta_summary text not null,
          materiality_score real default 0,
          materiality_reason text,
          algolia_implication text,
          action_owner text,
          recommended_action text,
          evidence_urls text,
          quality_status text default 'suppressed',
          created_at text default current_timestamp
        );

        create table if not exists synthesis_runs (
          id integer primary key autoincrement,
          cadence text not null,
          date_start text,
          date_end text,
          input_signal_ids text,
          markdown_path text,
          html_path text,
          quality_score real,
          created_at text default current_timestamp
        );

        create table if not exists source_health_events (
          id integer primary key autoincrement,
          source_url text not null,
          status text not null,
          failure_reason text,
          http_status integer,
          last_success_at text,
          last_failure_at text,
          failure_streak integer default 0,
          replacement_recommendation text,
          created_at text default current_timestamp,
          foreign key(source_url) references sources(url)
        );

        create table if not exists report_index (
          id integer primary key autoincrement,
          cadence text not null,
          date_start text,
          date_end text,
          markdown_path text,
          html_path text,
          pdf_path text,
          quality_score real,
          top_signal_ids text,
          top_action_owners text,
          source_health_summary text,
          status text default 'generated',
          created_at text default current_timestamp
        );

        create table if not exists action_items (
          id integer primary key autoincrement,
          report_id integer,
          title text not null,
          owner text default 'Competitive Intelligence',
          recommendation text,
          evidence_signal_ids text,
          status text default 'proposed',
          priority integer default 3,
          due_date text,
          athena_review_status text default 'pending',
          created_at text default current_timestamp,
          updated_at text default current_timestamp,
          foreign key(report_id) references report_index(id)
        );

        create table if not exists bot_deliveries (
          id integer primary key autoincrement,
          report_id integer,
          bot_profile text not null,
          channel text not null,
          recipient text,
          status text not null,
          delivered_at text,
          error text,
          created_at text default current_timestamp,
          foreign key(report_id) references report_index(id)
        );

        create index if not exists idx_snapshots_url_time on snapshots(source_url, fetched_at);
        create index if not exists idx_signals_detected on signals(detected_date);
        create index if not exists idx_signals_competitor on signals(competitor);
        create index if not exists idx_signals_score on signals(score);
        create index if not exists idx_semantic_facts_source_date on semantic_facts(source_url, detected_date);
        create index if not exists idx_semantic_deltas_date_status on semantic_deltas(detected_date, quality_status);
        create index if not exists idx_semantic_deltas_competitor on semantic_deltas(competitor, delta_type);
        create index if not exists idx_report_index_period on report_index(cadence, date_end);
        create index if not exists idx_action_items_status on action_items(status, owner);
        create index if not exists idx_source_health_url_time on source_health_events(source_url, created_at);
        """
    )
    ensure_column(conn, "sources", "collector", "text")
    ensure_column(conn, "sources", "fallback_collectors", "text")
    ensure_column(conn, "sources", "expected_content_markers", "text")
    ensure_column(conn, "sources", "requires_js", "integer default 0")
    ensure_column(conn, "sources", "gated", "integer default 0")
    ensure_column(conn, "sources", "criticality", "text default 'important'")
    ensure_column(conn, "snapshots", "collector", "text")
    ensure_column(conn, "snapshots", "duration_ms", "integer")
    ensure_column(conn, "snapshots", "quality_score", "real")
    ensure_column(conn, "snapshots", "quality_reasons", "text")
    ensure_column(conn, "snapshots", "recommended_collector", "text")
    ensure_column(conn, "snapshots", "recommended_collector_reason", "text")
    ensure_column(conn, "snapshots", "content_markers_found", "text")
    ensure_column(conn, "snapshots", "content_markers_missing", "text")
    ensure_column(conn, "snapshots", "acquisition_json", "text")
    ensure_column(conn, "source_health_events", "collector", "text")
    ensure_column(conn, "source_health_events", "duration_ms", "integer")
    ensure_column(conn, "source_health_events", "quality_score", "real")
    ensure_column(conn, "source_health_events", "recommended_collector", "text")
    conn.commit()


def ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in conn.execute("pragma table_info(%s)" % table).fetchall()}
    if column not in columns:
        conn.execute("alter table %s add column %s %s" % (table, column, definition))


def load_sources(path: Path = SOURCES_FILE) -> Dict[str, Any]:
    with open(path) as f:
        return yaml.safe_load(f.read())


def source_type_to_signal(source_type: str, url: str = "") -> str:
    st = (source_type or "").lower()
    target = f"{st} {url.lower()}"
    if any(k in target for k in ["changelog", "release", "updates", "docs", "help", "github.com"]):
        return "changelog_docs_change"
    if "pricing" in target or "package" in target:
        return "pricing_packaging"
    if any(k in target for k in ["case", "customer", "story"]):
        return "customer_proof"
    if any(k in target for k in ["partner", "marketplace", "integration"]):
        return "partnership_marketplace"
    if any(k in target for k in ["press", "news-release", "prnewswire", "ir."]):
        return "product_release"
    if any(k in target for k in ["reddit", "hacker", "forum", "community"]):
        return "customer_community_voice"
    if any(k in target for k in ["analyst", "gartner", "forrester"]):
        return "analyst_review_signal"
    if any(k in target for k in ["blog", "content"]):
        return "seo_content_movement"
    if any(k in target for k in ["ai", "mcp", "agent", "chatgpt", "perplexity"]):
        return "ai_visibility"
    return "positioning_messaging"


def default_collector_for_source(source_type: str, url: str = "") -> str:
    source_type = (source_type or "").lower()
    url = (url or "").lower()
    if source_type in {"rss", "feed"} or url.endswith((".rss", ".xml")):
        return "rss_feed"
    if source_type in {"product", "roadmap", "case_study", "blog", "news", "press", "protocol"}:
        return "scout_scrape"
    if source_type in {"analyst"}:
        return "manual_only"
    if source_type in {"forum"} and ("rss" in url or url.endswith(".rss")):
        return "rss_feed"
    return "direct_http"


def default_fallback_collectors(primary: str) -> str:
    if primary == "scout_scrape":
        return "direct_http"
    if primary == "direct_http":
        return "scout_scrape"
    if primary == "rss_feed":
        return "direct_http,scout_scrape"
    return ""


def bool_int(value: Any, default: bool = False) -> int:
    if value is None:
        return int(default)
    return int(bool(value))


def flatten_sources(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for key, value in (config.get("sources") or {}).items():
        if key in {"industry", "community"}:
            for item in value or []:
                url = item.get("url")
                if not url:
                    continue
                competitor = item.get("name") or key.title()
                source_type = item.get("type", key)
                collector = item.get("collector") or default_collector_for_source(source_type, url)
                records.append({
                    "competitor": competitor,
                    "tier": 5 if key == "community" else 4,
                    "url": canonical_url(url),
                    "source_type": source_type,
                    "signal_type": item.get("signal_type") or source_type_to_signal(source_type, url),
                    "cadence": item.get("cadence", "weekly"),
                    "priority": int(item.get("priority", 4)),
                    "enabled": int(item.get("enabled", True)),
                    "notes": item.get("notes", ""),
                    "collector": collector,
                    "fallback_collectors": item.get("fallback_collectors") or default_fallback_collectors(collector),
                    "expected_content_markers": json.dumps(item.get("expected_content_markers") or []),
                    "requires_js": bool_int(item.get("requires_js"), collector == "scout_scrape"),
                    "gated": bool_int(item.get("gated"), collector == "manual_only"),
                    "criticality": item.get("criticality", "important"),
                })
            continue

        if not isinstance(value, dict):
            continue
        competitor = value.get("company", key)
        tier = int(value.get("tier", 5))
        for item in value.get("urls", []) or []:
            url = item.get("url")
            if not url:
                continue
            source_type = item.get("type", "unknown")
            collector = item.get("collector") or default_collector_for_source(source_type, url)
            records.append({
                "competitor": competitor,
                "tier": tier,
                "url": canonical_url(url),
                "source_type": source_type,
                "signal_type": item.get("signal_type") or source_type_to_signal(source_type, url),
                "cadence": item.get("cadence", "weekly"),
                "priority": int(item.get("priority", 3)),
                "enabled": int(item.get("enabled", True)),
                "notes": item.get("notes", ""),
                "collector": collector,
                "fallback_collectors": item.get("fallback_collectors") or default_fallback_collectors(collector),
                "expected_content_markers": json.dumps(item.get("expected_content_markers") or []),
                "requires_js": bool_int(item.get("requires_js"), collector == "scout_scrape"),
                "gated": bool_int(item.get("gated"), collector == "manual_only"),
                "criticality": item.get("criticality", "important" if tier <= 2 else "watchlist"),
            })
    return records


def canonical_url(url: str) -> str:
    url = (url or "").strip()
    if url and not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.rstrip("/")


def upsert_sources(conn: sqlite3.Connection, records: Sequence[Dict[str, Any]]) -> None:
    active_urls = [record["url"] for record in records]
    for record in records:
        conn.execute(
            """
            insert into sources (
              competitor, tier, url, source_type, signal_type, cadence, priority,
              enabled, notes, collector, fallback_collectors, expected_content_markers,
              requires_js, gated, criticality
            )
            values (
              :competitor, :tier, :url, :source_type, :signal_type, :cadence, :priority,
              :enabled, :notes, :collector, :fallback_collectors, :expected_content_markers,
              :requires_js, :gated, :criticality
            )
            on conflict(url) do update set
              competitor=excluded.competitor,
              tier=excluded.tier,
              source_type=excluded.source_type,
              signal_type=excluded.signal_type,
              cadence=excluded.cadence,
              priority=excluded.priority,
              enabled=excluded.enabled,
              notes=excluded.notes,
              collector=excluded.collector,
              fallback_collectors=excluded.fallback_collectors,
              expected_content_markers=excluded.expected_content_markers,
              requires_js=excluded.requires_js,
              gated=excluded.gated,
              criticality=excluded.criticality,
              updated_at=current_timestamp
            """,
            record,
        )
    if active_urls:
        placeholders = ",".join("?" for _ in active_urls)
        conn.execute("update sources set enabled = 0, updated_at = current_timestamp where url not in (%s)" % placeholders, active_urls)
    conn.commit()


def get_sources(conn: sqlite3.Connection, limit: Optional[int] = None, types: Optional[Sequence[str]] = None) -> List[sqlite3.Row]:
    clauses = ["enabled = 1"]
    params: List[Any] = []
    if types:
        clauses.append("source_type in (%s)" % ",".join("?" for _ in types))
        params.extend(types)
    sql = "select * from sources where %s order by priority asc, tier asc, competitor asc" % " and ".join(clauses)
    if limit:
        sql += " limit ?"
        params.append(limit)
    return list(conn.execute(sql, params))


def fetch_url(url: str, timeout: int = 25) -> Dict[str, Any]:
    started = time.time()
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; ChowmesCompetitiveResearch/2.0)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,text/plain;q=0.8,*/*;q=0.7",
        },
    )
    try:
        with urlopen(req, timeout=timeout) as response:
            raw = response.read(1_500_000)
            charset = response.headers.get_content_charset() or "utf-8"
            body = raw.decode(charset, errors="replace")
            if "<html" in body[:1000].lower() or "<body" in body[:5000].lower():
                parser = TextExtractor()
                parser.feed(body)
                text = parser.text()
            else:
                text = normalize_text(body)
            return {
                "status": "ok",
                "http_status": getattr(response, "status", 200),
                "text": text[:120000],
                "error": None,
                "collector": "direct_http",
                "duration_ms": int((time.time() - started) * 1000),
            }
    except Exception as exc:
        return {
            "status": "error",
            "http_status": None,
            "text": "",
            "error": str(exc)[:500],
            "collector": "direct_http",
            "duration_ms": int((time.time() - started) * 1000),
        }


def parse_json_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, list) else [parsed]
        except json.JSONDecodeError:
            return [part.strip() for part in text.split(",") if part.strip()]
    return [value]


def json_dumps_compact(value: Any) -> str:
    return json.dumps(value if value is not None else [], ensure_ascii=True, default=str)


def fetch_scout_url(
    url: str,
    timeout: int = 60,
    use_js: bool = True,
    expected_markers: Optional[Sequence[str]] = None,
    source_id: Optional[str] = None,
) -> Dict[str, Any]:
    started = time.time()
    if not SCOUT_API_KEY:
        return {
            "status": "error",
            "http_status": None,
            "text": "",
            "error": "SCOUT_API_KEY is not configured",
            "collector": "scout_scrape",
            "duration_ms": int((time.time() - started) * 1000),
        }
    payload = json.dumps({
        "url": url,
        "formats": ["markdown"],
        "use_js": use_js,
        "timeout_ms": timeout * 1000,
        "stealth": False,
        "quality_analysis": True,
        "cleanup": True,
        "expected_markers": list(expected_markers or []),
        "recommend_collector": True,
        "source_id": source_id or url,
    }).encode("utf-8")
    req = Request(
        f"{SCOUT_BASE_URL}/scrape",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": SCOUT_API_KEY,
        },
    )
    try:
        with urlopen(req, timeout=timeout + 10) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
            acquisition = data.get("acquisition") or {}
            raw_text = normalize_text(data.get("markdown", ""))
            text = normalize_text(data.get("clean_markdown") or data.get("markdown", ""))
            status = "ok" if data.get("success") and text else "error"
            return {
                "status": status,
                "http_status": getattr(response, "status", 200),
                "text": text[:120000],
                "raw_text": raw_text[:120000],
                "error": (data.get("error") or None) if status == "error" else None,
                "collector": "scout_scrape",
                "duration_ms": int(data.get("duration_ms") or ((time.time() - started) * 1000)),
                "quality_score": acquisition.get("quality_score"),
                "quality_reasons": acquisition.get("quality_reasons") or [],
                "recommended_collector": acquisition.get("recommended_collector"),
                "recommended_collector_reason": acquisition.get("recommended_collector_reason"),
                "content_markers_found": acquisition.get("content_markers_found") or [],
                "content_markers_missing": acquisition.get("content_markers_missing") or [],
                "acquisition": acquisition,
            }
    except Exception as exc:
        return {
            "status": "error",
            "http_status": None,
            "text": "",
            "error": str(exc)[:500],
            "collector": "scout_scrape",
            "duration_ms": int((time.time() - started) * 1000),
        }


def strip_xml_namespace(tag: str) -> str:
    return tag.split("}", 1)[-1].lower()


def child_text(element: ET.Element, names: Sequence[str]) -> str:
    wanted = {name.lower() for name in names}
    for child in list(element):
        if strip_xml_namespace(child.tag) in wanted:
            return normalize_text("".join(child.itertext()))
    return ""


def child_link(element: ET.Element) -> str:
    explicit = child_text(element, ["link"])
    if explicit:
        return explicit
    for child in list(element):
        if strip_xml_namespace(child.tag) == "link":
            href = child.attrib.get("href")
            if href:
                return href.strip()
    return ""


def parse_feed_text(body: str) -> Tuple[str, int]:
    root = ET.fromstring(body)
    channel = root.find("channel")
    container = channel if channel is not None else root
    feed_title = child_text(container, ["title"]) or "Untitled feed"
    items = [
        element
        for element in root.iter()
        if strip_xml_namespace(element.tag) in {"item", "entry"}
    ]
    lines = ["Feed: %s" % feed_title]
    for item in items[:40]:
        title = child_text(item, ["title"]) or "Untitled item"
        link = child_link(item)
        published = child_text(item, ["pubDate", "published", "updated", "date"])
        summary = child_text(item, ["description", "summary", "content", "encoded"])
        lines.append("- %s" % title)
        if link:
            lines.append("  Link: %s" % link)
        if published:
            lines.append("  Published: %s" % published)
        if summary:
            lines.append("  Summary: %s" % compact(summary, 500))
    return "\n".join(lines), len(items)


def fetch_rss_url(url: str, timeout: int = 25) -> Dict[str, Any]:
    started = time.time()
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; ChowmesCompetitiveResearch/2.0)",
            "Accept": "application/rss+xml,application/atom+xml,application/xml,text/xml;q=0.9,*/*;q=0.5",
        },
    )
    try:
        with urlopen(req, timeout=timeout) as response:
            raw = response.read(1_500_000)
            charset = response.headers.get_content_charset() or "utf-8"
            body = raw.decode(charset, errors="replace")
            text, item_count = parse_feed_text(body)
            status = "ok" if item_count else "error"
            return {
                "status": status,
                "http_status": getattr(response, "status", 200),
                "text": text[:120000],
                "error": None if item_count else "feed contained no items",
                "collector": "rss_feed",
                "duration_ms": int((time.time() - started) * 1000),
                "quality_score": 0.9 if item_count else 0.2,
                "quality_reasons": ["feed_items:%d" % item_count],
                "recommended_collector": "rss_feed",
            }
    except Exception as exc:
        return {
            "status": "error",
            "http_status": None,
            "text": "",
            "error": str(exc)[:500],
            "collector": "rss_feed",
            "duration_ms": int((time.time() - started) * 1000),
            "quality_score": 0.0,
            "quality_reasons": ["feed_fetch_failed"],
            "recommended_collector": "rss_feed",
        }


def fetch_with_collector(row: sqlite3.Row, collector: str) -> Dict[str, Any]:
    url = row["url"]
    if collector == "manual_only":
        return {
            "status": "skipped",
            "http_status": None,
            "text": "",
            "error": "manual_only source",
            "collector": collector,
            "duration_ms": 0,
        }
    if collector == "scout_scrape":
        return fetch_scout_url(
            url,
            use_js=bool(row["requires_js"]),
            expected_markers=parse_json_list(row["expected_content_markers"]),
            source_id=url,
        )
    if collector == "rss_feed":
        return fetch_rss_url(url)
    return fetch_url(url)


def fetch_source(row: sqlite3.Row) -> Dict[str, Any]:
    url = row["url"]
    primary = row["collector"] or default_collector_for_source(row["source_type"], url)
    collectors = [primary]
    for fallback in parse_json_list(row["fallback_collectors"]):
        fallback = str(fallback).strip()
        if fallback and fallback not in collectors:
            collectors.append(fallback)

    attempts: List[Dict[str, Any]] = []
    first_result: Optional[Dict[str, Any]] = None
    last_result: Optional[Dict[str, Any]] = None
    for collector in collectors:
        result = fetch_with_collector(row, collector)
        result["primary_collector"] = primary
        result.setdefault("fallback_used", None if collector == primary else collector)
        attempt_summary = {
            "collector": collector,
            "status": result.get("status"),
            "http_status": result.get("http_status"),
            "duration_ms": result.get("duration_ms"),
            "error": result.get("error"),
        }
        attempts.append(attempt_summary)
        result["attempts"] = list(attempts)
        if first_result is None:
            first_result = result
        last_result = result
        if result.get("status") == "ok":
            if collector != primary:
                result["fallback_used"] = collector
                acquisition = dict(result.get("acquisition") or {})
                acquisition["collector_attempts"] = attempts
                result["acquisition"] = acquisition
            return result
        if collector == "manual_only":
            break

    result = last_result or first_result or {
        "status": "error",
        "http_status": None,
        "text": "",
        "error": "no collector attempted",
        "collector": primary,
        "duration_ms": 0,
    }
    result["attempts"] = attempts
    acquisition = dict(result.get("acquisition") or {})
    acquisition["collector_attempts"] = attempts
    result["acquisition"] = acquisition
    return result


def benchmark_result_summary(result: Dict[str, Any]) -> Dict[str, Any]:
    text = result.get("text") or ""
    return {
        "status": result.get("status"),
        "http_status": result.get("http_status"),
        "collector": result.get("collector"),
        "duration_ms": result.get("duration_ms"),
        "text_chars": len(text),
        "quality_score": result.get("quality_score"),
        "quality_reasons": result.get("quality_reasons") or [],
        "recommended_collector": result.get("recommended_collector"),
        "recommended_collector_reason": result.get("recommended_collector_reason"),
        "error": result.get("error"),
    }


def write_benchmark_sample(samples_dir: Path, target_id: str, collector: str, text: str) -> None:
    samples_dir.mkdir(parents=True, exist_ok=True)
    safe_id = re.sub(r"[^a-zA-Z0-9_.-]+", "-", target_id).strip("-") or "target"
    path = samples_dir / ("%s-%s.txt" % (safe_id, collector))
    path.write_text((text or "")[:120000])


def render_benchmark_comparison(benchmark: Dict[str, Any]) -> str:
    lines = [
        "# CI collector benchmark",
        "",
        "Date: %s" % benchmark["date"],
        "",
        "| Source | Expected | direct_http | scout_scrape | rss_feed | Recommendation |",
        "|---|---|---:|---:|---:|---|",
    ]
    for target in benchmark["targets"]:
        results = target["results"]

        def cell(name: str) -> str:
            result = results.get(name) or {}
            status = result.get("status") or "skipped"
            duration = result.get("duration_ms")
            chars = result.get("text_chars")
            if status == "skipped":
                return "skipped"
            return "%s / %sms / %s chars" % (status, duration if duration is not None else "", chars if chars is not None else 0)

        recommendation = target.get("selected_collector") or target.get("expected_collector") or ""
        lines.append(
            "| {label} | {expected} | {direct} | {scout} | {rss} | {recommendation} |".format(
                label=target["label"],
                expected=target.get("expected_collector") or "",
                direct=cell("direct_http"),
                scout=cell("scout_scrape"),
                rss=cell("rss_feed"),
                recommendation=recommendation,
            )
        )
    lines.append("")
    lines.append("Raw and clean samples are saved under `samples/` for audit.")
    return "\n".join(lines)


def choose_benchmark_collector(target: Dict[str, Any], results: Dict[str, Dict[str, Any]]) -> str:
    expected = target.get("expected_collector") or "direct_http"
    direct = results.get("direct_http") or {}
    scout = results.get("scout_scrape") or {}
    rss = results.get("rss_feed") or {}
    if rss.get("status") == "ok" and (expected == "rss_feed" or scout.get("recommended_collector") == "rss_feed"):
        return "rss_feed"
    if expected == "direct_http" and direct.get("status") == "ok":
        return "direct_http"
    if expected == "scout_scrape" and scout.get("status") == "ok":
        return "scout_scrape"
    if scout.get("status") == "ok" and direct.get("status") == "ok":
        scout_chars = int(scout.get("text_chars") or 0)
        direct_chars = int(direct.get("text_chars") or 0)
        if scout_chars > direct_chars * 1.5:
            return "scout_scrape"
    if direct.get("status") == "ok":
        return "direct_http"
    if scout.get("status") == "ok":
        return "scout_scrape"
    return expected


def run_collector_benchmark(
    targets: Optional[Sequence[Dict[str, Any]]] = None,
    date_str: Optional[str] = None,
) -> Path:
    ensure_dirs()
    date_str = date_str or date_today()
    targets = list(targets or CI_COLLECTOR_BENCHMARK_TARGETS)
    out_dir = BENCHMARKS_DIR / ("%s-ci-collector-benchmark" % date_str)
    samples_dir = out_dir / "samples"
    out_dir.mkdir(parents=True, exist_ok=True)
    benchmark = {
        "date": date_str,
        "created_at": now_iso(),
        "targets": [],
    }
    for target in targets:
        url = target["url"]
        markers = target.get("expected_markers") or []
        result_set: Dict[str, Dict[str, Any]] = {}

        direct = fetch_url(url)
        result_set["direct_http"] = benchmark_result_summary(direct)
        write_benchmark_sample(samples_dir, target["id"], "direct_http", direct.get("text") or "")

        scout = fetch_scout_url(
            url,
            use_js=True,
            expected_markers=markers,
            source_id=target.get("id") or url,
        )
        result_set["scout_scrape"] = benchmark_result_summary(scout)
        write_benchmark_sample(samples_dir, target["id"], "scout_scrape", scout.get("text") or "")

        feed_like = url.lower().endswith((".rss", ".xml")) or "rss" in url.lower()
        if target.get("expected_collector") == "rss_feed" or feed_like:
            rss = fetch_rss_url(url)
            result_set["rss_feed"] = benchmark_result_summary(rss)
            write_benchmark_sample(samples_dir, target["id"], "rss_feed", rss.get("text") or "")
        else:
            result_set["rss_feed"] = {"status": "skipped", "collector": "rss_feed", "error": "not a feed target"}

        selected_collector = choose_benchmark_collector(target, result_set)
        benchmark["targets"].append({
            "id": target["id"],
            "label": target["label"],
            "url": url,
            "expected_collector": target.get("expected_collector"),
            "selected_collector": selected_collector,
            "results": result_set,
        })

    (out_dir / "benchmark.json").write_text(json.dumps(benchmark, indent=2, default=str))
    (out_dir / "comparison.md").write_text(render_benchmark_comparison(benchmark))
    return out_dir


def latest_snapshot(conn: sqlite3.Connection, url: str) -> Optional[sqlite3.Row]:
    return conn.execute(
        "select * from snapshots where source_url = ? order by fetched_at desc, id desc limit 1",
        (url,),
    ).fetchone()


def save_snapshot(conn: sqlite3.Connection, source_url: str, fetch: Dict[str, Any]) -> int:
    text = fetch.get("text") or ""
    cur = conn.execute(
        """
        insert into snapshots (
          source_url, fetched_at, status, http_status, content_hash, content_text, error,
          collector, duration_ms, quality_score, quality_reasons, recommended_collector,
          recommended_collector_reason, content_markers_found, content_markers_missing,
          acquisition_json
        )
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source_url,
            now_iso(),
            fetch.get("status", "unknown"),
            fetch.get("http_status"),
            content_hash(text) if text else None,
            text,
            fetch.get("error"),
            fetch.get("collector"),
            fetch.get("duration_ms"),
            fetch.get("quality_score"),
            json_dumps_compact(fetch.get("quality_reasons")),
            fetch.get("recommended_collector"),
            fetch.get("recommended_collector_reason"),
            json_dumps_compact(fetch.get("content_markers_found")),
            json_dumps_compact(fetch.get("content_markers_missing")),
            json.dumps(fetch.get("acquisition") or {}, ensure_ascii=True, default=str),
        ),
    )
    conn.commit()
    conn.commit()
    return int(cur.lastrowid)


def record_source_health_event(conn: sqlite3.Connection, source: sqlite3.Row, fetch: Dict[str, Any]) -> None:
    status = fetch.get("status") or "unknown"
    now = now_iso()
    conn.execute(
        """
        insert into source_health_events (
          source_url, status, failure_reason, http_status, last_success_at, last_failure_at,
          failure_streak, replacement_recommendation, collector, duration_ms, quality_score,
          recommended_collector, created_at
        )
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source["url"],
            status,
            fetch.get("error") if status != "ok" else None,
            fetch.get("http_status"),
            now if status == "ok" else None,
            now if status != "ok" else None,
            0 if status == "ok" else 1,
            fetch.get("recommended_collector_reason"),
            fetch.get("collector") or source["collector"],
            fetch.get("duration_ms"),
            fetch.get("quality_score"),
            fetch.get("recommended_collector"),
            now,
        ),
    )


def diff_summary(old_text: str, new_text: str, max_lines: int = 14) -> str:
    old_lines = split_signal_lines(old_text)
    new_lines = split_signal_lines(new_text)
    diff = []
    for line in difflib.unified_diff(old_lines, new_lines, n=1, lineterm=""):
        if line.startswith("+") and not line.startswith("+++"):
            cleaned = line[1:].strip()
            if is_boilerplate_diff(cleaned):
                continue
            if cleaned and len(cleaned) > 20:
                diff.append(cleaned)
        if len(diff) >= max_lines:
            break
    return " | ".join(diff)[:1200]


def is_boilerplate_diff(text: str) -> bool:
    lower = normalize_text(text).lower()
    if not lower:
        return True
    nav_markers = [
        "contact us login",
        "login apac eu us uk canada",
        "partners rfp/rfi company",
        "facebook instagram linkedin",
        "privacy at",
        "schedule a demo",
        "product tours",
        "toggle navigation",
        "sign in appearance settings",
    ]
    marker_count = sum(1 for marker in nav_markers if marker in lower)
    if marker_count >= 2:
        return True
    if re.search(r"\bcareers?\s+\d+\b", lower) and marker_count >= 1:
        return True
    if len(lower) > 500 and marker_count >= 1:
        return True
    return False


def is_relevant_community_signal(text: str) -> bool:
    lower = normalize_text(text).lower()
    keywords = [
        "algolia", "coveo", "bloomreach", "constructor", "vertex ai search",
        "elastic enterprise search", "meilisearch", "typesense", "lucidworks",
        "perplexity", "chatgpt search", "site search", "ecommerce search",
        "product discovery", "search relevance", "mcp", "agentic search",
    ]
    return any(keyword in lower for keyword in keywords)


def split_signal_lines(text: str) -> List[str]:
    chunks = re.split(r"(?<=[.!?])\s+|\s{2,}", normalize_text(text))
    return [c.strip() for c in chunks if len(c.strip()) > 20][:800]


def source_value(source: Any, key: str, default: Any = None) -> Any:
    try:
        value = source[key]
    except (KeyError, IndexError, TypeError):
        value = default
    return default if value is None else value


def semantic_lines(text: str) -> List[str]:
    lines: List[str] = []
    for raw in (text or "").splitlines():
        line = normalize_text(raw).strip(" -*\t")
        if not line or is_boilerplate_diff(line):
            continue
        lower = line.lower()
        if any(marker in lower for marker in [
            "cookie preferences",
            "accept all",
            "decline all",
            "privacy policy",
            "terms of use",
            "navigation products",
            "subscribe to newsletter",
        ]):
            continue
        if len(line) >= 4:
            lines.append(line)
    return lines[:500]


def normalize_identity(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def is_customer_source(source: Any) -> bool:
    source_type = (source_value(source, "source_type", "") or "").lower()
    url = (source_value(source, "url", "") or "").lower()
    return any(marker in f"{source_type} {url}" for marker in ["case", "customer", "story"])


def is_content_source(source: Any) -> bool:
    source_type = (source_value(source, "source_type", "") or "").lower()
    url = (source_value(source, "url", "") or "").lower()
    return any(marker in f"{source_type} {url}" for marker in ["blog", "press", "news", "ai", "rss", "content"])


def infer_product_area(text: str) -> str:
    lower = text.lower()
    if "ai search" in lower or ("ai" in lower and "search" in lower):
        return "AI search"
    if "product discovery" in lower:
        return "product discovery"
    if "personalization" in lower or "personalized" in lower:
        return "personalization"
    if "recommendation" in lower:
        return "recommendations"
    if "commerce search" in lower or "ecommerce search" in lower:
        return "commerce search"
    if "search" in lower:
        return "search"
    return "unknown"


def infer_industry(text: str) -> str:
    lower = text.lower()
    if any(k in lower for k in ["ecommerce", "commerce", "retail", "shopper", "product discovery"]):
        return "retail/ecommerce"
    if any(k in lower for k in ["health", "pharma", "clinic"]):
        return "healthcare"
    if any(k in lower for k in ["bank", "finance", "insurance"]):
        return "financial services"
    if any(k in lower for k in ["media", "publisher", "content"]):
        return "media"
    return "unknown"


def extract_metric(text: str) -> str:
    match = re.search(r"\b\d+(?:\.\d+)?\s?%|\b\d+(?:\.\d+)?x\b|\$\s?\d+(?:\.\d+)?[mMkK]?", text)
    return normalize_text(match.group(0)).replace(" ", "") if match else ""


def customer_candidate_name(line: str) -> str:
    candidate = re.sub(r"^#+\s*", "", line).strip()
    candidate = re.split(r"\s+(?:uses|selected|chooses|is using|announced|launches)\s+", candidate, maxsplit=1, flags=re.I)[0]
    if " - " in candidate:
        candidate = candidate.split(" - ", 1)[0]
    elif ": " in candidate:
        candidate = candidate.split(": ", 1)[0]
    words = candidate.split()
    if len(words) > 4:
        candidate = " ".join(words[:3])
    if not re.match(r"^[A-Z][A-Za-z0-9&.' -]{1,60}$", candidate):
        return ""
    if candidate.lower() in {"customers", "customer stories", "case studies", "constructor customers"}:
        return ""
    return candidate.strip()


def surrounding_evidence(lines: Sequence[str], idx: int) -> str:
    window = " ".join(lines[idx: idx + 5])
    return normalize_text(window)[:900]


def extract_customer_proof_facts(text: str, source: Any, detected_date: str) -> List[Dict[str, Any]]:
    lines = semantic_lines(text)
    facts: List[Dict[str, Any]] = []
    competitor = source_value(source, "competitor", infer_competitor_from_url(source_value(source, "url", "")))
    source_url = canonical_url(source_value(source, "url", ""))
    seen = set()
    for idx, line in enumerate(lines):
        name = customer_candidate_name(line)
        evidence = surrounding_evidence(lines, idx)
        if not name and any(k in line.lower() for k in ["uses", "selected", "chooses", "customer", "case study"]):
            name = customer_candidate_name(line)
        if not name or normalize_identity(name) in seen:
            continue
        target = evidence or line
        metric = extract_metric(target)
        product_area = infer_product_area(target)
        proof_strength = "high" if metric else ("medium" if any(k in target.lower() for k in ["uses", "selected", "case study", "customer"]) else "low")
        fact_json = {
            "customer_name": name,
            "industry": infer_industry(target),
            "use_case": product_area if product_area != "unknown" else "unknown",
            "product_area": product_area,
            "claimed_outcome": target if any(k in target.lower() for k in ["increase", "improve", "conversion", "revenue", "personalized", "uses"]) else "",
            "metric": metric,
            "quote": "",
            "asset_title": line,
            "asset_url": source_url,
            "proof_strength": proof_strength,
        }
        facts.append({
            "source_url": source_url,
            "competitor": competitor,
            "source_type": source_value(source, "source_type", "case_study"),
            "detected_date": detected_date,
            "fact_type": "customer_proof",
            "fact_json": fact_json,
            "evidence_text": target,
            "evidence_url": source_url,
            "confidence": 0.82 if proof_strength == "high" else 0.7,
        })
        seen.add(normalize_identity(name))
    return facts


def infer_content_topic(text: str) -> str:
    lower = text.lower()
    if ("agent" in lower or "agentic" in lower) and "search" in lower:
        return "agentic_search"
    if "ai search" in lower or ("ai" in lower and "retrieval" in lower):
        return "ai_search"
    if "product discovery" in lower:
        return "product_discovery"
    if "personalization" in lower:
        return "personalization"
    if "customer" in lower or "case study" in lower:
        return "customer_proof"
    return "market_narrative"


def infer_narrative_angle(text: str) -> str:
    topic = infer_content_topic(text)
    if topic == "agentic_search":
        return "Agentic search and retrieval are being packaged as enterprise workflow infrastructure."
    if topic == "ai_search":
        return "AI search is being positioned as a platform-level capability."
    if topic == "product_discovery":
        return "Product discovery is being framed around commerce outcomes and personalization."
    if topic == "customer_proof":
        return "Customer proof is being used to validate competitive claims."
    return "Competitor narrative movement needs classification."


def infer_target_audience(text: str) -> str:
    lower = text.lower()
    if any(k in lower for k in ["developer", "api", "build", "workflow"]):
        return "developers"
    if any(k in lower for k in ["commerce", "merchandising", "shopper", "retail"]):
        return "commerce teams"
    if any(k in lower for k in ["enterprise", "leader", "cto", "cio"]):
        return "enterprise AI leaders"
    return "go-to-market teams"


def infer_content_opportunity(topic: str, competitor: str) -> str:
    if topic == "agentic_search":
        return "Algolia should explain where its AI search and MCP story fits into agentic discovery workflows."
    if topic == "ai_search":
        return "Algolia should produce evidence-backed AI search comparison content for buyers evaluating retrieval quality."
    if topic == "product_discovery":
        return "Algolia should connect product discovery content to measurable ecommerce outcomes and proof."
    if topic == "customer_proof":
        return "Algolia should counter with comparable customer proof and vertical-specific stories."
    return "Algolia should decide whether this narrative deserves a response or only monitoring."


def content_candidate_title(line: str) -> str:
    title = re.sub(r"^#+\s*", "", line).strip()
    title = re.sub(r"\s+", " ", title)
    lower = title.lower()
    if not title or len(title) < 12:
        return ""
    if any(k in lower for k in ["cookie", "privacy", "navigation", "contact", "subscribe"]):
        return ""
    if len(title.split()) > 18:
        title = " ".join(title.split()[:18])
    return title


def extract_content_narrative_facts(text: str, source: Any, detected_date: str) -> List[Dict[str, Any]]:
    lines = semantic_lines(text)
    facts: List[Dict[str, Any]] = []
    competitor = source_value(source, "competitor", infer_competitor_from_url(source_value(source, "url", "")))
    source_url = canonical_url(source_value(source, "url", ""))
    source_type = source_value(source, "source_type", "blog")
    for idx, line in enumerate(lines):
        target = surrounding_evidence(lines, idx)
        title = content_candidate_title(line)
        lower_target = target.lower()
        if not title or not any(k in lower_target for k in ["ai", "agent", "search", "retrieval", "product discovery", "launch", "announce", "introducing"]):
            continue
        topic = infer_content_topic(target)
        publish_match = re.search(r"\b20\d{2}-\d{2}-\d{2}\b|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},\s+20\d{2}\b|\bJune\s+\d{1,2},\s+20\d{2}\b", target)
        fact_json = {
            "title": title,
            "publish_date": publish_match.group(0) if publish_match else "",
            "asset_type": "press" if source_type in {"press", "news"} else "blog",
            "topic": topic,
            "narrative_angle": infer_narrative_angle(target),
            "target_audience": infer_target_audience(target),
            "strategic_claim": target,
            "product_claims": [claim for claim in ["AI search", "agentic discovery", "retrieval workflows", "product discovery"] if claim.lower() in lower_target],
            "proof_points": [extract_metric(target)] if extract_metric(target) else [],
            "cta": "Learn more" if "learn more" in lower_target else "",
            "algolia_content_opportunity": infer_content_opportunity(topic, competitor),
        }
        facts.append({
            "source_url": source_url,
            "competitor": competitor,
            "source_type": source_type,
            "detected_date": detected_date,
            "fact_type": "content_narrative",
            "fact_json": fact_json,
            "evidence_text": target,
            "evidence_url": source_url,
            "confidence": 0.78 if topic in {"agentic_search", "ai_search", "product_discovery"} else 0.62,
        })
        break
    return facts


def extract_semantic_facts(text: str, source: Any, detected_date: str) -> List[Dict[str, Any]]:
    if is_customer_source(source):
        return extract_customer_proof_facts(text, source, detected_date)
    if is_content_source(source):
        return extract_content_narrative_facts(text, source, detected_date)
    return []


def semantic_fact_identity(fact: Dict[str, Any]) -> str:
    payload = fact.get("fact_json") or {}
    if fact.get("fact_type") == "customer_proof":
        return "customer:%s" % normalize_identity(payload.get("customer_name", ""))
    if fact.get("fact_type") == "content_narrative":
        return "content:%s" % normalize_identity(payload.get("title", ""))
    return normalize_identity(json.dumps(payload, sort_keys=True, default=str))


def mostly_boilerplate_delta(old_text: str, new_text: str) -> bool:
    summary = diff_summary(old_text, new_text)
    if not summary:
        return True
    useful_keywords = ["customer", "case study", "ai", "search", "agent", "launch", "announce", "product discovery", "conversion", "revenue"]
    return not any(keyword in summary.lower() for keyword in useful_keywords)


def materiality_for_delta(delta: Dict[str, Any], source: Any, collector_changed: bool = False) -> Dict[str, Any]:
    after = delta.get("after_json") or {}
    score = 0.0
    reasons: List[str] = []
    if delta["delta_type"] == "new_customer_proof":
        score = 0.42
        reasons.append("named customer proof")
        if after.get("customer_name"):
            score += 0.15
        if after.get("metric") or after.get("claimed_outcome"):
            score += 0.16
            reasons.append("outcome evidence")
        if after.get("product_area") in {"AI search", "product discovery", "commerce search", "search"}:
            score += 0.12
            reasons.append("Algolia-relevant product area")
        if int(source_value(source, "priority", 3) or 3) <= 2:
            score += 0.08
            reasons.append("priority source")
        if after.get("proof_strength") == "high":
            score += 0.08
        delta["algolia_implication"] = (
            "%s is adding customer proof in %s. Algolia should check whether the proof weakens current sales claims or battlecards."
            % (delta["competitor"], after.get("product_area") or "search/product discovery")
        )
        delta["action_owner"] = "Sales Enablement"
        delta["recommended_action"] = "Validate the customer proof, compare it against Algolia proof points, and decide whether the competitive playbook needs an update."
    elif delta["delta_type"] == "new_content_narrative":
        score = 0.35
        reasons.append("new content narrative")
        if after.get("topic") in {"agentic_search", "ai_search", "product_discovery"}:
            score += 0.2
            reasons.append("Algolia-relevant topic")
        if after.get("strategic_claim"):
            score += 0.1
        if after.get("product_claims"):
            score += 0.1
            reasons.append("product claim present")
        if int(source_value(source, "priority", 3) or 3) <= 2:
            score += 0.06
        delta["algolia_implication"] = after.get("algolia_content_opportunity") or "Algolia should decide whether this narrative requires a response."
        delta["action_owner"] = "Product Marketing"
        delta["recommended_action"] = "Review the narrative, compare it with Algolia messaging, and decide whether to create or update content."
    else:
        reasons.append("no semantic delta")

    if collector_changed:
        score -= 0.25
        reasons.append("collector method changed, so confidence is penalized")
    if not delta.get("evidence_urls"):
        score -= 0.2
        reasons.append("missing evidence URL")

    score = max(0.0, min(0.98, round(score, 3)))
    delta["materiality_score"] = score
    delta["materiality_reason"] = "; ".join(reasons)
    delta["quality_status"] = "publish" if score >= 0.65 and delta["delta_type"] in {"new_customer_proof", "new_content_narrative"} else "suppressed"
    return delta


def make_suppressed_delta(source: Any, detected_date: str, reason: str, old_text: str, new_text: str) -> Dict[str, Any]:
    source_url = canonical_url(source_value(source, "url", ""))
    return {
        "source_url": source_url,
        "competitor": source_value(source, "competitor", infer_competitor_from_url(source_url)),
        "source_type": source_value(source, "source_type", "source"),
        "detected_date": detected_date,
        "delta_type": "suppressed_non_semantic_change",
        "before_json": {},
        "after_json": {},
        "delta_summary": "Suppressed source change: %s." % reason,
        "materiality_score": 0.0,
        "materiality_reason": reason,
        "algolia_implication": "No Algolia action. The change did not produce a validated semantic delta.",
        "action_owner": "Competitive Intelligence",
        "recommended_action": "Keep for diagnostics only.",
        "evidence_urls": [source_url] if source_url else [],
        "quality_status": "suppressed",
    }


def semantic_diff(
    source: Any,
    old_text: str,
    new_text: str,
    detected_date: str,
    collector_changed: bool = False,
) -> Dict[str, Any]:
    old_facts = extract_semantic_facts(old_text, source, detected_date) if old_text else []
    new_facts = extract_semantic_facts(new_text, source, detected_date)
    old_by_identity = {semantic_fact_identity(fact): fact for fact in old_facts}
    deltas: List[Dict[str, Any]] = []
    for fact in new_facts:
        identity = semantic_fact_identity(fact)
        if not identity or identity in old_by_identity:
            continue
        after = fact["fact_json"]
        if fact["fact_type"] == "customer_proof":
            delta_type = "new_customer_proof"
            summary = "%s added customer proof for %s." % (fact["competitor"], after.get("customer_name", "a named customer"))
        elif fact["fact_type"] == "content_narrative":
            delta_type = "new_content_narrative"
            summary = "%s published or surfaced a narrative asset: %s." % (fact["competitor"], after.get("title", "Untitled asset"))
        else:
            continue
        delta = {
            "source_url": fact["source_url"],
            "competitor": fact["competitor"],
            "source_type": fact["source_type"],
            "detected_date": detected_date,
            "delta_type": delta_type,
            "before_json": {},
            "after_json": after,
            "delta_summary": summary,
            "materiality_score": 0.0,
            "materiality_reason": "",
            "algolia_implication": "",
            "action_owner": "Competitive Intelligence",
            "recommended_action": "",
            "evidence_urls": [fact["evidence_url"]],
            "quality_status": "suppressed",
        }
        deltas.append(materiality_for_delta(delta, source, collector_changed=collector_changed))
    if not deltas and (old_text or new_text):
        reason = "only boilerplate, collector, or hash-level movement detected"
        if not mostly_boilerplate_delta(old_text, new_text):
            reason = "changed text did not map to a supported semantic schema"
        deltas.append(make_suppressed_delta(source, detected_date, reason, old_text, new_text))
    return {"facts": new_facts, "deltas": deltas}


def json_dumps_record(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=True, sort_keys=True, default=str)


def insert_semantic_facts(conn: sqlite3.Connection, facts: Sequence[Dict[str, Any]]) -> List[int]:
    ids: List[int] = []
    for fact in facts:
        cur = conn.execute(
            """
            insert into semantic_facts (
              source_url, competitor, source_type, detected_date, fact_type,
              fact_json, evidence_text, evidence_url, confidence
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fact["source_url"],
                fact["competitor"],
                fact.get("source_type"),
                fact["detected_date"],
                fact["fact_type"],
                json_dumps_record(fact.get("fact_json")),
                fact.get("evidence_text"),
                fact.get("evidence_url"),
                fact.get("confidence", 0.6),
            ),
        )
        ids.append(int(cur.lastrowid))
    conn.commit()
    return ids


def insert_semantic_deltas(conn: sqlite3.Connection, deltas: Sequence[Dict[str, Any]]) -> List[int]:
    ids: List[int] = []
    for delta in deltas:
        cur = conn.execute(
            """
            insert into semantic_deltas (
              source_url, competitor, source_type, detected_date, delta_type,
              before_json, after_json, delta_summary, materiality_score,
              materiality_reason, algolia_implication, action_owner,
              recommended_action, evidence_urls, quality_status
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                delta["source_url"],
                delta["competitor"],
                delta.get("source_type"),
                delta["detected_date"],
                delta["delta_type"],
                json_dumps_record(delta.get("before_json")),
                json_dumps_record(delta.get("after_json")),
                delta["delta_summary"],
                delta.get("materiality_score", 0.0),
                delta.get("materiality_reason"),
                delta.get("algolia_implication"),
                delta.get("action_owner"),
                delta.get("recommended_action"),
                json_dumps_record(delta.get("evidence_urls") or []),
                delta.get("quality_status", "suppressed"),
            ),
        )
        ids.append(int(cur.lastrowid))
    conn.commit()
    return ids


def semantic_delta_to_signal(delta: Dict[str, Any]) -> Dict[str, Any]:
    after = delta.get("after_json") or {}
    category = "customer_proof" if delta["delta_type"] == "new_customer_proof" else source_type_to_signal(delta.get("source_type", ""), delta["source_url"])
    if delta["delta_type"] == "new_content_narrative":
        category = "ai_visibility" if after.get("topic") in {"agentic_search", "ai_search"} else "seo_content_movement"
    confidence = 0.84 if delta.get("materiality_score", 0) >= 0.75 else 0.72
    return build_signal(
        competitor=delta["competitor"],
        category=category,
        source_url=delta["source_url"],
        source_type=delta.get("source_type", ""),
        title=delta["delta_summary"],
        evidence=delta["delta_summary"],
        summary="%s Why it matters to Algolia: %s Recommended action: %s" % (
            delta["delta_summary"],
            delta.get("algolia_implication") or "",
            delta.get("recommended_action") or "",
        ),
        detected_date=delta["detected_date"],
        event_date=delta["detected_date"],
        novelty=0.82,
        confidence=confidence,
        impact=max(0.55, float(delta.get("materiality_score", 0.0))),
        raw={"semantic_delta": delta},
    )


def build_signal(
    competitor: str,
    category: str,
    source_url: str,
    source_type: str,
    title: str,
    evidence: str,
    summary: str,
    detected_date: str,
    event_date: Optional[str] = None,
    novelty: float = 0.5,
    confidence: float = 0.65,
    impact: float = 0.5,
    raw: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    category = category if category in SIGNAL_CATEGORIES else source_type_to_signal(category, source_url)
    action_owner = infer_action_owner(category, title + " " + summary)
    score = round((confidence * 0.25) + (novelty * 0.3) + (impact * 0.45), 3)
    return {
        "competitor": competitor or infer_competitor_from_url(source_url),
        "category": category,
        "source_url": canonical_url(source_url),
        "source_type": source_type,
        "event_date": event_date,
        "detected_date": detected_date,
        "title": clean_title(title),
        "evidence_snippet": normalize_text(evidence)[:900],
        "summary": normalize_text(summary)[:900],
        "confidence": round(float(confidence), 3),
        "novelty": round(float(novelty), 3),
        "impact": round(float(impact), 3),
        "score": score,
        "action_owner": action_owner,
        "status": "new",
        "raw_json": json.dumps(raw or {}, default=str)[:8000],
    }


def clean_title(title: str) -> str:
    title = normalize_text(title)
    if not title:
        return "Untitled competitive signal"
    return title[:180]


def infer_competitor_from_url(url: str) -> str:
    host = urlparse(url).netloc.lower().replace("www.", "")
    labels = {
        "coveo": "Coveo",
        "bloomreach": "Bloomreach",
        "constructor": "Constructor",
        "google": "Google Vertex AI Search",
        "elastic": "Elastic",
        "meilisearch": "Meilisearch",
        "typesense": "Typesense",
        "perplexity": "Perplexity AI",
        "openai": "OpenAI / ChatGPT",
        "algolia": "Algolia",
    }
    for key, label in labels.items():
        if key in host:
            return label
    return host or "Unknown"


def infer_category(text: str, source_type: str = "", url: str = "") -> str:
    target = f"{text} {source_type} {url}".lower()
    if any(k in target for k in ["review", "best alternative", "alternatives", " vs "]) and "pricing" not in url.lower():
        return "seo_content_movement"
    if any(k in target for k in ["pricing", "package", "tier", "cost", "quote"]):
        return "pricing_packaging"
    if any(k in target for k in ["mcp", "agent", "chatgpt", "claude", "perplexity", "gemini", "ai search"]):
        return "ai_visibility"
    if any(k in target for k in ["partner", "marketplace", "co-sell", "integration", "salesforce", "adobe", "aws", "azure"]):
        return "partnership_marketplace"
    if any(k in target for k in ["case study", "customer", "selected", "chooses", "win", "logo"]):
        return "customer_proof"
    if any(k in target for k in ["release", "launch", "announced", "generally available", "feature", "product"]):
        return "product_release"
    if any(k in target for k in ["docs", "documentation", "changelog", "github", "release notes"]):
        return "changelog_docs_change"
    if any(k in target for k in ["reddit", "hacker news", "forum", "complaint", "review"]):
        return "customer_community_voice"
    if any(k in target for k in ["gartner", "forrester", "analyst", "peer insights", "g2", "trustradius"]):
        return "analyst_review_signal"
    if any(k in target for k in ["seo", "keyword", "content", "blog", "rank"]):
        return "seo_content_movement"
    return source_type_to_signal(source_type, url)


def infer_action_owner(category: str, text: str) -> str:
    target = f"{category} {text}".lower()
    if category in {"product_release", "changelog_docs_change"}:
        return "Product"
    if category in {"positioning_messaging", "seo_content_movement", "ai_visibility", "algolia_baseline_comparison"}:
        return "Product Marketing"
    if category in {"pricing_packaging", "sales_relevant_objection", "customer_proof", "analyst_review_signal"}:
        return "Sales Enablement"
    if category == "partnership_marketplace":
        return "Partner Enablement"
    if any(k in target for k in ["funding", "acquired", "market share", "category", "gartner"]):
        return "Executive Review"
    return "Competitive Intelligence"


def infer_event_date(item: Dict[str, Any], fallback: str) -> str:
    for key in ["date", "published_date", "published", "event_date"]:
        val = item.get(key)
        if val:
            return str(val)[:10]
    text = json.dumps(item, default=str)
    match = re.search(r"(20\d{2}-\d{2}-\d{2})", text)
    if match:
        return match.group(1)
    match = re.search(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},\s+20\d{2}", text)
    if match:
        return match.group(0)
    return fallback


def score_impact(category: str, source_type: str, priority: int, title: str) -> float:
    base = 0.45
    if priority <= 1:
        base += 0.18
    elif priority == 2:
        base += 0.1
    if category in {"pricing_packaging", "customer_proof", "partnership_marketplace", "ai_visibility"}:
        base += 0.15
    if source_type in {"press", "changelog", "product", "pricing", "case_study"}:
        base += 0.08
    if any(k in title.lower() for k in ["launch", "selected", "announces", "generally available", "pricing", "mcp"]):
        base += 0.08
    if any(k in title.lower() for k in ["review", "best alternative", "alternatives", " vs "]):
        base -= 0.16
    return min(base, 0.95)


def competitor_priority_boost(competitor: str) -> float:
    if competitor in {"Coveo", "Bloomreach", "Constructor", "Google Vertex AI Search"}:
        return 0.09
    if competitor in {"Elastic", "Lucidworks", "Yext", "Algonomy"}:
        return 0.04
    if competitor in {"Meilisearch", "Typesense"}:
        return -0.02
    if competitor == "Algolia":
        return -0.08
    return 0.0


def source_authority_boost(url: str) -> float:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    if "ir.coveo.com" in host or "prnewswire.com" in host:
        return 0.1
    if any(k in path for k in ["/news", "/press", "/releases", "/customers", "/case"]):
        return 0.07
    if "github.com" in host and "releases" in path:
        return 0.05
    if "/blog" in path and any(k in path for k in ["review", "alternative", "vs"]):
        return -0.14
    return 0.0


def insert_signal(conn: sqlite3.Connection, signal: Dict[str, Any]) -> int:
    cur = conn.execute(
        """
        insert into signals (
          competitor, category, source_url, source_type, event_date, detected_date,
          title, evidence_snippet, summary, confidence, novelty, impact, score,
          action_owner, status, raw_json
        ) values (
          :competitor, :category, :source_url, :source_type, :event_date, :detected_date,
          :title, :evidence_snippet, :summary, :confidence, :novelty, :impact, :score,
          :action_owner, :status, :raw_json
        )
        """,
        signal,
    )
    conn.commit()
    return int(cur.lastrowid)


def insert_signals(conn: sqlite3.Connection, signals: Sequence[Dict[str, Any]]) -> List[int]:
    ids = []
    for signal in signals:
        ids.append(insert_signal(conn, signal))
    return ids


def collect_direct_sources(conn: sqlite3.Connection, limit: Optional[int] = None) -> Dict[str, Any]:
    rows = get_sources(conn, limit=limit)
    created_signals = []
    errors = []
    snapshots = 0
    semantic_fact_count = 0
    semantic_delta_count = 0
    for row in rows:
        url = row["url"]
        previous = latest_snapshot(conn, url)
        fetch = fetch_source(row)
        save_snapshot(conn, url, fetch)
        record_source_health_event(conn, row, fetch)
        snapshots += 1
        if fetch["status"] != "ok":
            errors.append({"url": url, "collector": fetch.get("collector"), "error": fetch.get("error")})
            continue
        new_text = fetch.get("text", "")
        old_text = previous["content_text"] if previous and previous["status"] == "ok" else ""
        new_hash = content_hash(new_text)
        old_hash = previous["content_hash"] if previous else None
        if previous and old_hash == new_hash:
            continue
        if not old_text:
            baseline_facts = extract_semantic_facts(new_text, row, date_today())
            if baseline_facts:
                semantic_fact_count += len(insert_semantic_facts(conn, baseline_facts))
            continue

        collector_changed = bool(previous and (previous["collector"] or "") != (fetch.get("collector") or ""))
        semantic = semantic_diff(
            row,
            old_text=old_text,
            new_text=new_text,
            detected_date=date_today(),
            collector_changed=collector_changed,
        )
        if semantic.get("facts"):
            semantic_fact_count += len(insert_semantic_facts(conn, semantic["facts"]))
        if semantic.get("deltas"):
            semantic_delta_count += len(insert_semantic_deltas(conn, semantic["deltas"]))

        for delta in semantic.get("deltas", []):
            if delta.get("quality_status") == "publish":
                created_signals.append(semantic_delta_to_signal(delta))
    ids = insert_signals(conn, created_signals)
    return {
        "snapshots": snapshots,
        "signals": len(ids),
        "errors": errors,
        "signal_ids": ids,
        "semantic_facts": semantic_fact_count,
        "semantic_deltas": semantic_delta_count,
    }


def first_evidence(text: str) -> str:
    lines = split_signal_lines(text)
    return " | ".join(lines[:4])[:1200]


def run_parallel_search(query: str, max_results: int = 5, timeout: int = 60) -> List[Dict[str, Any]]:
    try:
        result = subprocess.run(
            [
                "parallel-cli", "search", query,
                "--json", "--max-results", str(max_results),
                "--mode", "one-shot",
            ],
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode != 0:
            return []
        data = json.loads(result.stdout)
        return data.get("results", []) if isinstance(data, dict) else []
    except Exception:
        return []


def check_parallel_cli() -> bool:
    try:
        result = subprocess.run(["parallel-cli", "auth"], capture_output=True, text=True, timeout=10)
        return result.returncode == 0
    except Exception:
        return False


def check_monitors() -> List[Dict[str, Any]]:
    try:
        result = subprocess.run(["parallel-cli", "monitor", "list", "--json"], capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            return []
        monitors = json.loads(result.stdout)
        alerts: List[Dict[str, Any]] = []
        for monitor in monitors if isinstance(monitors, list) else monitors.get("monitors", []):
            monitor_id = monitor.get("id") or monitor.get("monitor_id")
            if not monitor_id:
                continue
            events_result = subprocess.run(
                ["parallel-cli", "monitor", "events", monitor_id, "--json"],
                capture_output=True, text=True, timeout=15,
            )
            if events_result.returncode != 0:
                continue
            events = json.loads(events_result.stdout)
            if isinstance(events, list):
                alerts.extend(events)
            elif isinstance(events, dict):
                alerts.extend(events.get("events", []))
        return alerts
    except Exception:
        return []


def fixture_to_signals(fixture_path: Path, detected_date: Optional[str] = None) -> List[Dict[str, Any]]:
    data = json.loads(Path(fixture_path).read_text())
    detected = detected_date or data.get("date") or date_today()
    signals: List[Dict[str, Any]] = []
    for key, source_type in [
        ("competitor_moves", "search_competitor_move"),
        ("industry_signals", "search_industry_signal"),
        ("ai_threats", "search_ai_threat"),
    ]:
        for item in data.get(key, []) or []:
            url = canonical_url(item.get("url") or item.get("link") or "")
            if not url:
                continue
            title = item.get("title") or url
            excerpts = item.get("excerpts") or []
            evidence = excerpts[0] if excerpts else item.get("snippet", "")
            query = item.get("query", "")
            category = infer_category(f"{title} {evidence} {query}", source_type, url)
            competitor = infer_competitor_from_url(url)
            impact = score_impact(category, source_type, 2 if key == "competitor_moves" else 3, title)
            impact = max(0.1, min(0.95, impact + competitor_priority_boost(competitor) + source_authority_boost(url)))
            signals.append(build_signal(
                competitor=competitor,
                category=category,
                source_url=url,
                source_type=source_type,
                title=title,
                evidence=evidence,
                summary=summarize_search_item(title, evidence, query),
                detected_date=detected,
                event_date=infer_event_date(item, detected),
                novelty=0.7 if key == "competitor_moves" else 0.55,
                confidence=0.68 if url else 0.4,
                impact=impact,
                raw={"collector": "fixture_replay", "query": query, "item": item},
            ))
    for baseline in ALGOLIA_BASELINE:
        signals.append(build_signal(
            competitor=baseline["competitor"],
            category=baseline["category"],
            source_url=baseline["source_url"],
            source_type="official_algolia_baseline",
            title=baseline["title"],
            evidence=baseline["evidence"],
            summary=baseline["summary"],
            detected_date=detected,
            event_date=detected,
            novelty=baseline["novelty"],
            confidence=baseline["confidence"],
            impact=baseline["impact"],
            raw={"collector": "algolia_baseline"},
        ))
    return signals


def summarize_search_item(title: str, evidence: str, query: str) -> str:
    evidence = clean_evidence(evidence)
    if evidence:
        return "Search query '%s' surfaced this source: %s" % (query, evidence[:260])
    return "%s surfaced from query '%s'." % (clean_title(title), query)


def clean_evidence(text: str) -> str:
    text = normalize_text(text)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1", text)
    text = re.sub(r"^.*?(Coveo Announces Hosted MCP Server)", r"\1", text, flags=re.I)
    text = re.sub(r"Press Releases Banner.*?Email Alerts\s*", "", text, flags=re.I)
    text = re.sub(r"Home\s+-\s+[^-]+-\s+", "", text, flags=re.I)
    text = re.sub(r"Download as PDF\s*", "", text, flags=re.I)
    text = re.sub(r"\s[#*_`\\]+", " ", text)
    text = re.sub(r"#+\s*", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[.!?])\s+", text)
    clean_parts = [p for p in parts if len(p) > 30 and not p.lower().startswith(("home ", "overview ", "news & events"))]
    return " ".join(clean_parts[:2])[:420] if clean_parts else text[:420]


def collect_parallel_searches(conn: sqlite3.Connection, config: Dict[str, Any], max_results: int = 5) -> Dict[str, Any]:
    created = []
    errors = []
    for group, queries in (config.get("daily_queries") or {}).items():
        for query in queries or []:
            results = run_parallel_search(query, max_results=max_results)
            if not results:
                errors.append({"query": query, "error": "no_results_or_parallel_failure"})
                continue
            fixture_like = {"date": date_today(), group: results}
            temp_path = RAW_DIR / ("parallel_%s_%s.json" % (group, int(time.time() * 1000)))
            temp_path.write_text(json.dumps(fixture_like, indent=2, default=str))
            signals = fixture_to_signals(temp_path, detected_date=date_today())
            temp_path.unlink(missing_ok=True)
            for signal in signals:
                if signal["source_type"] == "official_algolia_baseline":
                    continue
                signal["raw_json"] = json.dumps({"collector": "parallel_search", "query": query, "group": group}, default=str)
                created.append(signal)
    ids = insert_signals(conn, created)
    return {"signals": len(ids), "errors": errors, "signal_ids": ids}


def monitor_events_to_signals(conn: sqlite3.Connection, events: Sequence[Dict[str, Any]], detected_date: Optional[str] = None) -> Dict[str, Any]:
    detected = detected_date or date_today()
    signals = []
    for event in events:
        url = canonical_url(event.get("url") or event.get("source_url") or event.get("link") or "")
        if not url:
            continue
        title = event.get("title") or event.get("name") or "Monitor alert"
        text = normalize_text(event.get("summary") or event.get("content") or json.dumps(event, default=str))
        category = infer_category(f"{title} {text}", "monitor_alert", url)
        signals.append(build_signal(
            competitor=infer_competitor_from_url(url),
            category=category,
            source_url=url,
            source_type="monitor_alert",
            title=title,
            evidence=text[:900],
            summary="Monitor alert detected a public source change.",
            detected_date=detected,
            event_date=detected,
            novelty=0.9,
            confidence=0.62,
            impact=score_impact(category, "monitor_alert", 2, title),
            raw={"collector": "parallel_monitor", "event": event},
        ))
    ids = insert_signals(conn, signals)
    return {"signals": len(ids), "signal_ids": ids}


def get_signals(
    conn: sqlite3.Connection,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    limit: int = 40,
    min_score: float = 0.0,
) -> List[sqlite3.Row]:
    clauses = ["score >= ?", "coalesce(status, 'new') != 'ignored'"]
    params: List[Any] = [min_score]
    if date_start:
        clauses.append("detected_date >= ?")
        params.append(date_start)
    if date_end:
        clauses.append("detected_date <= ?")
        params.append(date_end)
    sql = """
        select * from signals
        where %s
        order by score desc, novelty desc, impact desc, id desc
        limit ?
    """ % " and ".join(clauses)
    params.append(limit)
    return list(conn.execute(sql, params))


def get_signal_counts(conn: sqlite3.Connection, date_start: Optional[str], date_end: Optional[str]) -> Dict[str, Any]:
    where = ["coalesce(status, 'new') != 'ignored'"]
    params: List[Any] = []
    if date_start:
        where.append("detected_date >= ?")
        params.append(date_start)
    if date_end:
        where.append("detected_date <= ?")
        params.append(date_end)
    suffix = "where " + " and ".join(where) if where else ""
    rows = conn.execute(
        "select action_owner, count(*) c from signals %s group by action_owner order by c desc" % suffix,
        params,
    ).fetchall()
    category_rows = conn.execute(
        "select category, count(*) c from signals %s group by category order by c desc" % suffix,
        params,
    ).fetchall()
    total = conn.execute("select count(*) c from signals %s" % suffix, params).fetchone()["c"]
    return {
        "total": total,
        "by_owner": {row["action_owner"]: row["c"] for row in rows},
        "by_category": {row["category"]: row["c"] for row in category_rows},
    }


def get_semantic_deltas(
    conn: sqlite3.Connection,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    quality_status: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    clauses: List[str] = []
    params: List[Any] = []
    if date_start:
        clauses.append("detected_date >= ?")
        params.append(date_start)
    if date_end:
        clauses.append("detected_date <= ?")
        params.append(date_end)
    if quality_status:
        clauses.append("quality_status = ?")
        params.append(quality_status)
    suffix = "where " + " and ".join(clauses) if clauses else ""
    rows = conn.execute(
        """
        select * from semantic_deltas
        %s
        order by materiality_score desc, id desc
        limit ?
        """ % suffix,
        params + [limit],
    ).fetchall()
    parsed: List[Dict[str, Any]] = []
    for row in rows:
        record = dict(row)
        for key in ["before_json", "after_json", "evidence_urls"]:
            value = record.get(key)
            try:
                record[key] = json.loads(value) if value else ([] if key == "evidence_urls" else {})
            except json.JSONDecodeError:
                record[key] = [] if key == "evidence_urls" else {}
        parsed.append(record)
    return parsed


def get_source_inventory(conn: sqlite3.Connection) -> Dict[str, Any]:
    rows = conn.execute(
        """
        select competitor, source_type, count(*) c
        from sources
        where enabled = 1
        group by competitor, source_type
        order by competitor, source_type
        """
    ).fetchall()
    by_competitor: Dict[str, int] = {}
    by_type: Dict[str, int] = {}
    for row in rows:
        by_competitor[row["competitor"]] = by_competitor.get(row["competitor"], 0) + int(row["c"])
        by_type[row["source_type"]] = by_type.get(row["source_type"], 0) + int(row["c"])
    return {
        "enabled_sources": sum(by_competitor.values()),
        "by_competitor": by_competitor,
        "by_source_type": by_type,
    }


def get_source_coverage(conn: sqlite3.Connection, date_start: str, date_end: str) -> Dict[str, Any]:
    sources = conn.execute(
        """
        select competitor, tier, url, source_type, signal_type, cadence, priority, enabled,
               collector, fallback_collectors, expected_content_markers, requires_js
        from sources
        where enabled = 1
        order by priority asc, tier asc, competitor asc, source_type asc
        """
    ).fetchall()
    rows: List[Dict[str, Any]] = []
    by_competitor: Dict[str, Dict[str, int]] = {}
    by_type: Dict[str, Dict[str, int]] = {}
    totals = {
        "enabled_sources": len(sources),
        "checked_sources": 0,
        "successful_sources": 0,
        "failed_sources": 0,
        "missing_sources": 0,
        "signal_sources": 0,
        "baseline_signal_sources": 0,
        "changed_signal_sources": 0,
        "material_signal_sources": 0,
        "snapshots_in_window": 0,
        "signals_in_window": 0,
    }

    def bump(bucket: Dict[str, Dict[str, int]], key: str, status: str) -> None:
        label = key or "Unknown"
        if label not in bucket:
            bucket[label] = {"enabled": 0, "checked": 0, "ok": 0, "error": 0, "missing": 0, "signals": 0, "changed": 0}
        bucket[label]["enabled"] += 1
        if status != "missing":
            bucket[label]["checked"] += 1
        if status == "ok":
            bucket[label]["ok"] += 1
        elif status == "error":
            bucket[label]["error"] += 1
        else:
            bucket[label]["missing"] += 1

    for source in sources:
        url = source["url"]
        window_snapshot = conn.execute(
            """
            select *
            from snapshots
            where source_url = ?
              and date(fetched_at) between date(?) and date(?)
            order by fetched_at desc, id desc
            limit 1
            """,
            (url, date_start, date_end),
        ).fetchone()
        latest = window_snapshot or latest_snapshot(conn, url)
        snapshot_count = conn.execute(
            """
            select count(*) c
            from snapshots
            where source_url = ?
              and date(fetched_at) between date(?) and date(?)
            """,
            (url, date_start, date_end),
        ).fetchone()["c"]
        signal_rows = conn.execute(
            """
            select *
            from signals
            where source_url = ?
              and date(detected_date) between date(?) and date(?)
              and coalesce(status, 'new') != 'ignored'
            order by score desc, id desc
            """,
            (url, date_start, date_end),
        ).fetchall()
        signal_count = len(signal_rows)
        baseline_count = sum(1 for signal in signal_rows if signal_is_baseline(dict(signal)))
        changed_count = signal_count - baseline_count
        material_count = sum(
            1 for signal in signal_rows
            if not signal_is_baseline(dict(signal)) and float(signal["score"] or 0) >= 0.3
        )
        if window_snapshot:
            status = window_snapshot["status"] or "unknown"
            totals["checked_sources"] += 1
            totals["snapshots_in_window"] += int(snapshot_count)
            if status == "ok":
                totals["successful_sources"] += 1
            else:
                totals["failed_sources"] += 1
        else:
            status = "missing"
            totals["missing_sources"] += 1
        if signal_count:
            totals["signal_sources"] += 1
            totals["signals_in_window"] += signal_count
        if baseline_count:
            totals["baseline_signal_sources"] += 1
        if changed_count:
            totals["changed_signal_sources"] += 1
        if material_count:
            totals["material_signal_sources"] += 1
        bump(by_competitor, source["competitor"], status if status == "ok" else ("error" if status != "missing" else "missing"))
        bump(by_type, source["source_type"], status if status == "ok" else ("error" if status != "missing" else "missing"))
        if signal_count:
            by_competitor[source["competitor"]]["signals"] += signal_count
            by_type[source["source_type"]]["signals"] += signal_count
        if changed_count:
            by_competitor[source["competitor"]]["changed"] += changed_count
            by_type[source["source_type"]]["changed"] += changed_count
        rows.append({
            "competitor": source["competitor"],
            "tier": source["tier"],
            "url": url,
            "source_type": source["source_type"],
            "signal_type": source["signal_type"],
            "cadence": source["cadence"],
            "priority": source["priority"],
            "collector": source["collector"],
            "fallback_collectors": source["fallback_collectors"],
            "requires_js": source["requires_js"],
            "status": status,
            "checked_in_window": bool(window_snapshot),
            "snapshots_in_window": int(snapshot_count),
            "last_fetched_at": latest["fetched_at"] if latest else None,
            "http_status": latest["http_status"] if latest else None,
            "error": latest["error"] if latest else None,
            "duration_ms": latest["duration_ms"] if latest and "duration_ms" in latest.keys() else None,
            "quality_score": latest["quality_score"] if latest and "quality_score" in latest.keys() else None,
            "recommended_collector": latest["recommended_collector"] if latest and "recommended_collector" in latest.keys() else None,
            "signal_count": signal_count,
            "baseline_signal_count": baseline_count,
            "changed_signal_count": changed_count,
            "material_signal_count": material_count,
        })
    return {
        "date_start": date_start,
        "date_end": date_end,
        "totals": totals,
        "by_competitor": by_competitor,
        "by_source_type": by_type,
        "sources": rows,
    }


def source_ledger(signals: Sequence[sqlite3.Row], limit: int = 20) -> List[Dict[str, str]]:
    rows = []
    seen = set()
    for signal in signals:
        url = signal["source_url"]
        if not url or url in seen:
            continue
        seen.add(url)
        rows.append({
            "id": "S%d" % (len(rows) + 1),
            "competitor": signal["competitor"],
            "category": signal["category"],
            "title": signal["title"],
            "url": url,
            "evidence": signal["evidence_snippet"] or "",
        })
        if len(rows) >= limit:
            break
    return rows


def signal_is_daily_material(signal: Dict[str, Any]) -> bool:
    if not signal.get("source_url") or not signal.get("title"):
        return False
    if signal_is_baseline(signal):
        return False
    if signal_is_legacy_raw_change(signal):
        return False
    try:
        return float(signal.get("score", 0)) >= 0.3
    except (TypeError, ValueError):
        return False


def signal_raw_json(signal: Dict[str, Any]) -> Dict[str, Any]:
    raw = signal.get("raw_json")
    if not raw:
        return {}
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def signal_has_semantic_delta(signal: Dict[str, Any]) -> bool:
    raw_data = signal_raw_json(signal)
    return isinstance(raw_data.get("semantic_delta"), dict)


def signal_is_legacy_raw_change(signal: Dict[str, Any]) -> bool:
    if signal_has_semantic_delta(signal):
        return False
    raw_data = signal_raw_json(signal)
    collector = str(raw_data.get("collector", "")).lower()
    text = " ".join([
        str(signal.get("title", "")),
        str(signal.get("summary", "")),
        str(signal.get("evidence_snippet", "")),
    ]).lower()
    acquisition_collectors = {"direct_fetch", "direct_http", "scout_scrape", "rss_feed"}
    raw_change_patterns = [
        "changed since the previous snapshot",
        "changed case_study",
        "changed blog",
        "changed press",
        "public case_study source changed",
        "public blog source changed",
        "public press source changed",
        "baseline captured",
    ]
    if collector in acquisition_collectors and any(pattern in text for pattern in raw_change_patterns):
        return True
    return bool(any(pattern in text for pattern in raw_change_patterns))


def signal_is_baseline(signal: Dict[str, Any]) -> bool:
    raw_data = signal_raw_json(signal)
    if raw_data.get("baseline") is True:
        return True
    return (
        signal.get("category") == "algolia_baseline_comparison"
        or signal.get("source_type") == "official_algolia_baseline"
        or str(signal.get("competitor", "")).lower() == "algolia"
    )


def build_synthesis_packet(conn: sqlite3.Connection, cadence: str, date_start: str, date_end: str, limit: int = 18) -> Dict[str, Any]:
    signals = get_signals(conn, date_start=date_start, date_end=date_end, limit=limit, min_score=0.3)
    all_signals = get_signals(conn, date_start=date_start, date_end=date_end, limit=5000, min_score=0.0)
    semantic_deltas = get_semantic_deltas(conn, date_start=date_start, date_end=date_end, quality_status="publish", limit=limit)
    suppressed_deltas = get_semantic_deltas(conn, date_start=date_start, date_end=date_end, quality_status="suppressed", limit=50)
    signals = [row for row in signals if not signal_is_legacy_raw_change(dict(row))]
    all_signals_for_prompt = [row for row in all_signals if not signal_is_legacy_raw_change(dict(row))]
    if cadence == "daily":
        signals = [row for row in signals if signal_is_daily_material(dict(row))]
    counts = get_signal_counts(conn, date_start, date_end)
    return {
        "cadence": cadence,
        "date_start": date_start,
        "date_end": date_end,
        "counts": counts,
        "source_inventory": get_source_inventory(conn),
        "source_coverage": get_source_coverage(conn, date_start, date_end),
        "signals": [dict(row) for row in signals],
        "all_signals": [dict(row) for row in all_signals],
        "semantic_deltas": semantic_deltas,
        "suppressed_deltas": suppressed_deltas,
        "source_ledger": source_ledger(all_signals_for_prompt),
    }


def build_daily_prompt(packet: Dict[str, Any]) -> str:
    prompt_packet = {k: v for k, v in packet.items() if k != "all_signals"}
    return """You are Argus, the dedicated male Competitive Intelligence analyst for Algolia CI. Athena supervises quality and escalation, but she is not the daily CI operator.

Write a concise, source-backed decision brief from the structured signal ledger below. Do not write a research dump.

Use exactly these Markdown sections:
**Competitive pulse - {date_end}**
**Bottom line**
**Recommended action**
**Evidence**
**Watch trigger**
**Research coverage**

Rules:
- 450 words maximum.
- Use semantic_deltas as the primary intelligence input. Do not infer strategic meaning from raw hash changes or generic page changes.
- Never write "changed case_study", "page changed", or "changed since the previous snapshot" as the finding. Publish only the semantic change and evidence.
- Every material claim must link to a source URL from the signal ledger.
- Pick one action owner from Product, Product Marketing, Sales Enablement, Partner Enablement, Competitive Intelligence, or Executive Review.
- Be explicit about confidence.
- Do not say Algolia lacks MCP. Algolia has MCP; compare packaging, adoption, positioning, distribution, or proof.
- No tables. No emoji. Use ASCII hyphens only.
- If evidence is weak, say what is unknown and what internal validation is needed.

Signal ledger:
{packet}
""".format(date_end=packet["date_end"], packet=json.dumps(prompt_packet, indent=2, default=str)[:18000])


def build_weekly_prompt(packet: Dict[str, Any]) -> str:
    prompt_packet = {k: v for k, v in packet.items() if k != "all_signals"}
    return """You are Argus, the dedicated male Competitive Intelligence analyst for Algolia CI. Athena supervises quality and escalation, but she is not the weekly CI operator.

Write pattern-first analysis from the signal ledger. Do not recap day by day.

Use exactly these Markdown sections:
**Weekly competitive synthesis - {date_start} to {date_end}**
**What changed**
**Strategic pattern**
**Recommended actions by owner**
**Battlecard updates**
**Coverage gaps**

Rules:
- 900 words maximum.
- Use semantic_deltas as the primary intelligence input. Suppressed deltas are diagnostics only.
- Never recommend battlecard updates from baseline captures, collector changes, hash-only movement, or generic page-change signals.
- Return only the final Markdown report. Do not include reasoning notes, preambles, or statements about what you are about to do.
- Every material claim must link to a source URL from the signal ledger.
- Group recommendations by owner.
- Separate confirmed fact, public-evidence inference, and unknown.
- Coverage gaps must be supported by the packet. Do not say a competitor or source type is not configured if it appears in source_inventory. If it has no stored signal in this window, say "no stored signal this week" instead.
- Use source_coverage to distinguish collection health from market quiet. If a source was checked successfully and produced no changed signal, call it quiet. If it was not checked, call it missing coverage. If it failed, call it collection failure.
- Baseline captures are not competitive moves. If all signals are baselines, say this is a setup report and do not recommend battlecard changes.
- No tables. No emoji. Use ASCII hyphens only.

Signal ledger:
{packet}
""".format(
        date_start=packet["date_start"],
        date_end=packet["date_end"],
        packet=json.dumps(prompt_packet, indent=2, default=str)[:22000],
    )


def synthesize_with_hermes(prompt: str, timeout: int = 600) -> str:
    command = [HERMES_BIN, "chat", "-q", prompt, "-m", SYNTHESIS_MODEL, "--quiet"]
    if SYNTHESIS_PROVIDER:
        command.extend(["--provider", SYNTHESIS_PROVIDER])
    result = subprocess.run(
        command,
        capture_output=True, text=True, timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr[:800])
    lines = [line for line in result.stdout.splitlines() if not line.startswith("session_id:")]
    return clean_synthesis_markdown("\n".join(lines).strip())


def quiet_day_evidence(packet: Dict[str, Any]) -> str:
    coverage = packet.get("source_coverage") or {}
    failed = [
        source for source in coverage.get("sources", [])
        if source.get("status") != "ok"
    ][:3]
    if failed:
        return "\n".join(
            "- **{competitor}:** [{source_type}]({url}) returned `{status}`; {reason}".format(
                competitor=source.get("competitor", "Unknown"),
                source_type=source.get("source_type", "source"),
                url=source.get("url", ""),
                status=source.get("status", "error"),
                reason=(source.get("error") or "collection failed")[:180],
            )
            for source in failed
        )
    ledger = packet.get("source_ledger", [])[:3]
    if ledger:
        return "\n".join(
            "- **{competitor}:** [{title}]({url}) was checked with no material changed signal.".format(
                competitor=row.get("competitor", "Unknown"),
                title=row.get("title", "Source"),
                url=row.get("url", ""),
            )
            for row in ledger
        )
    return "- No material changed signal was available in the current ledger window."


def synthesize_local(packet: Dict[str, Any], cadence: str = "daily") -> str:
    signals = packet.get("signals", [])
    semantic_deltas = packet.get("semantic_deltas", [])
    suppressed_deltas = packet.get("suppressed_deltas", [])
    if semantic_deltas:
        top_delta = semantic_deltas[0]
        evidence_url = (top_delta.get("evidence_urls") or [top_delta.get("source_url", "")])[0]
        if cadence == "weekly":
            customer = [d for d in semantic_deltas if d.get("delta_type") == "new_customer_proof"]
            narrative = [d for d in semantic_deltas if d.get("delta_type") == "new_content_narrative"]
            customer_lines = "\n".join(
                "- **{competitor}:** [{summary}]({url}) - {implication}".format(
                    competitor=d.get("competitor", "Unknown"),
                    summary=d.get("delta_summary", "Customer proof movement"),
                    url=(d.get("evidence_urls") or [d.get("source_url", "")])[0],
                    implication=d.get("algolia_implication", "Review for sales impact."),
                )
                for d in customer[:5]
            ) or "- No material customer proof movement passed the semantic gate."
            narrative_lines = "\n".join(
                "- **{competitor}:** [{summary}]({url}) - {implication}".format(
                    competitor=d.get("competitor", "Unknown"),
                    summary=d.get("delta_summary", "Narrative movement"),
                    url=(d.get("evidence_urls") or [d.get("source_url", "")])[0],
                    implication=d.get("algolia_implication", "Review for messaging impact."),
                )
                for d in narrative[:5]
            ) or "- No material content or narrative movement passed the semantic gate."
            action_lines = "\n".join(
                "- **{owner}:** {action} Evidence: [{summary}]({url}).".format(
                    owner=d.get("action_owner", "Competitive Intelligence"),
                    action=d.get("recommended_action", "Review and validate."),
                    summary=d.get("delta_summary", "semantic delta"),
                    url=(d.get("evidence_urls") or [d.get("source_url", "")])[0],
                )
                for d in semantic_deltas[:6]
            )
            battlecard_lines = "\n".join(
                "- Candidate: {summary} Only update the playbook after validation confirms this changes the objection, proof gap, or talk track.".format(
                    summary=d.get("delta_summary", "customer proof movement")
                )
                for d in customer[:4]
            ) or "- No battlecard update recommended from this week of semantic deltas."
            suppressed_count = len(suppressed_deltas)
            return """**Weekly competitive synthesis - {date_start} to {date_end}**

**What changed**

{top_summary}

**Customer proof movement**

{customer_lines}

**Content/narrative movement**

{narrative_lines}

**Campaign opportunities**

- Product Marketing should turn the strongest narrative deltas into content hypotheses only where the evidence shows a clear AI/search/product-discovery claim.

**Recommended actions by owner**

{action_lines}

**Battlecard updates**

{battlecard_lines}

**Suppressed weak signals**

{suppressed_count} weak or ambiguous source changes were kept out of the executive brief because they did not pass semantic materiality gates.

**Coverage gaps**

This run remains public-source only. Internal win/loss, CRM, Gong, Slack, paid review exports, and paid traffic data are not included.
""".format(
                date_start=packet["date_start"],
                date_end=packet["date_end"],
                top_summary=top_delta.get("delta_summary", "Semantic movement detected."),
                customer_lines=customer_lines,
                narrative_lines=narrative_lines,
                action_lines=action_lines,
                battlecard_lines=battlecard_lines,
                suppressed_count=suppressed_count,
            )

        return """**Competitive pulse - {date_end}**

**What changed**

{summary} Evidence: [{source}]({url}).

**Why it matters to Algolia**

{implication}

**Recommended action**

{owner} should {action}

**Evidence**

- [{source}]({url}) - {reason}. Confidence is {confidence}; materiality score is {score:.0%}.

**Validation needed**

- Confirm whether this semantic delta changes an Algolia sales claim, content angle, or product narrative before changing public messaging.

**Research coverage**

The report uses semantic deltas from public-source snapshots. Hash-only page changes, collector changes, and boilerplate movement are suppressed.
""".format(
            date_end=packet["date_end"],
            summary=top_delta.get("delta_summary", "Semantic movement detected."),
            source=top_delta.get("competitor", "source"),
            url=evidence_url,
            implication=top_delta.get("algolia_implication", "Review for Algolia impact."),
            owner=top_delta.get("action_owner", "Competitive Intelligence"),
            action=(top_delta.get("recommended_action") or "review and validate this delta.").rstrip(".") + ".",
            reason=top_delta.get("materiality_reason", "semantic gate passed"),
            confidence=confidence_label(0.8 if top_delta.get("materiality_score", 0) >= 0.75 else 0.65),
            score=float(top_delta.get("materiality_score", 0.0)),
        )

    if not signals:
        if cadence == "weekly":
            return """**Weekly competitive synthesis - {date_start} to {date_end}**

**What changed**

No material public signals were stored in the ledger for this period.

**Strategic pattern**

No pattern is strong enough to act on.

**Recommended actions by owner**

- **Competitive Intelligence:** Review source coverage and confirm collectors are running.

**Battlecard updates**

No battlecard update recommended.

**Coverage gaps**

No source-backed signals available for this period.
""".format(**packet)
        coverage_totals = (packet.get("source_coverage") or {}).get("totals", {})
        failed_sources = int(coverage_totals.get("failed_sources", 0) or 0)
        missing_sources = int(coverage_totals.get("missing_sources", 0) or 0)
        has_coverage_gap = failed_sources > 0 or missing_sources > 0
        if has_coverage_gap:
            confidence = "low-medium"
            confidence_clause = "Treat this as a quiet day with low-medium confidence because some source coverage needs repair."
            action = "Competitive Intelligence should repair or replace failed and missing sources before treating quiet days as confirmed market quiet."
            trigger = "- If a failed or missing tier 1 or AI-native source returns on the next run and produces a changed signal, treat it as time-delayed and review the source same day."
        else:
            confidence = "medium"
            confidence_clause = "Treat this as a quiet day with medium confidence: collection completed, but public-source CI can still miss gated or delayed market movement."
            action = "No immediate competitive action is recommended today. Maintain the watchlist and wait for a material semantic delta before changing sales, PMM, or product guidance."
            trigger = "- If tomorrow's run produces a material semantic delta from a tier 1, customer-proof, AI/search, or pricing source, review it same day and route it to the relevant owner."
        return """**Competitive pulse - {date_end}**

**Bottom line**

No material public competitive signal was stored in the ledger today. Direct source collection checked {checked} of {enabled} enabled sources; {ok} succeeded, {failed} failed, and {missing} were missing from the collection window. {confidence_clause}

**Recommended action**

{action}

**Evidence**

{evidence}

**Watch trigger**

{trigger}

**Research coverage**

Daily synthesis uses direct public-source diffs only. Broad search discovery and monitor ingestion are disabled in the production wrapper until their noise and runtime behavior are validated separately.
""".format(
            date_end=packet["date_end"],
            enabled=coverage_totals.get("enabled_sources", 0),
            checked=coverage_totals.get("checked_sources", 0),
            ok=coverage_totals.get("successful_sources", 0),
            failed=failed_sources,
            missing=missing_sources,
            confidence=confidence,
            confidence_clause=confidence_clause,
            action=action,
            evidence=quiet_day_evidence(packet),
            trigger=trigger,
        )

    top = signals[0]
    evidence_items = signals[:4]
    owner = top["action_owner"]
    confidence = confidence_label(float(top["confidence"]))
    if cadence == "weekly":
        grouped = group_by_owner(signals)
        action_lines = []
        for group_owner, items in grouped.items():
            sample = items[0]
            action_lines.append(
                "- **%s:** Act on %s by validating whether [%s](%s) changes positioning, battlecards, roadmap questions, or partner enablement. Evidence summary: %s."
                % (group_owner, display_label(sample["category"]), sample["title"], sample["source_url"], sample["summary"])
            )
        evidence_links = "\n".join(
            "- **%s:** [%s](%s) - %s"
            % (s["competitor"], s["title"], s["source_url"], s["summary"])
            for s in evidence_items
        )
        ai_count = packet["counts"]["by_category"].get("ai_visibility", 0)
        content_count = packet["counts"]["by_category"].get("seo_content_movement", 0)
        pricing_count = packet["counts"]["by_category"].get("pricing_packaging", 0)
        return """**Weekly competitive synthesis - {date_start} to {date_end}**

**What changed**

The ledger captured {total} public signals. AI visibility is the dominant movement with {ai_count} signals, followed by SEO/content movement ({content_count}) and pricing/packaging ({pricing_count}). The strongest source-backed signal is from {competitor}: [{title}]({url}).

**Strategic pattern**

The pattern is named AI search packaging. Competitors are not just describing features; they are giving AI search and retrieval a marketable wrapper across MCP, agent, commerce reasoning, personalization, and product-discovery narratives. Treat this as a Product Marketing-led positioning problem first, then escalate to Product only where internal validation shows a real capability delta.

**Recommended actions by owner**

{actions}

**Battlecard updates**

{evidence}

**Coverage gaps**

This v1 run uses public sources only. It does not include Gong, Salesforce, Slack, G2 paid exports, Semrush API, or internal win/loss data.
""".format(
            date_start=packet["date_start"],
            date_end=packet["date_end"],
            total=packet["counts"]["total"],
            competitor=top["competitor"],
            title=top["title"],
            url=top["source_url"],
            ai_count=ai_count,
            content_count=content_count,
            pricing_count=pricing_count,
            category=display_label(top["category"]),
            confidence=confidence,
            actions="\n".join(action_lines),
            evidence=evidence_links,
        )

    evidence = "\n".join(
        "- **%s, %s:** [%s](%s) - %s"
        % (s["competitor"], s.get("event_date") or s["detected_date"], s["title"], s["source_url"], s["summary"])
        for s in evidence_items
    )
    return """**Competitive pulse - {date_end}**

**Bottom line**

{competitor} produced the highest-scored public signal: [{title}]({url}). The signal category is {category}, with {confidence} confidence and a {impact:.0%} impact score. Treat this as actionable only after checking whether the same theme appears in sales conversations or customer proof.

**Recommended action**

{owner} owns the first move. Review the source evidence today, decide whether it changes positioning, battlecards, or product response, and log the validation result in the next weekly synthesis.

**Evidence**

{evidence}

**Watch trigger**

- If a tier 1 competitor adds named customers, pricing changes, marketplace distribution, or documentation that supports this theme, escalate from watch to response planning.

**Research coverage**

The ledger used public sources only: direct source snapshots, monitor/search inputs, fixture replay, and Algolia baseline checks. Internal field intel and paid SaaS APIs are out of scope for v1.
""".format(
        date_end=packet["date_end"],
        competitor=top["competitor"],
        title=top["title"],
        url=top["source_url"],
        category=display_label(top["category"]),
        confidence=confidence,
        impact=float(top["impact"]),
        owner=owner,
        evidence=evidence,
    )


def group_by_owner(signals: Sequence[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for signal in signals:
        grouped.setdefault(signal["action_owner"], []).append(signal)
    return grouped


def confidence_label(value: float) -> str:
    if value >= 0.8:
        return "high"
    if value >= 0.6:
        return "medium"
    return "low"


def display_label(value: str) -> str:
    label = (value or "").replace("_", " ").strip().title()
    return label.replace("Ai ", "AI ")


def is_link_exempt_quiet_day(markdown: str) -> bool:
    return (
        "No material public competitive signal was stored in the ledger today" in markdown
        and "Direct source collection checked" in markdown
        and "No immediate competitive action is recommended today" in markdown
    )


def quality_score(markdown: str) -> float:
    score = 1.0
    if "|" in markdown and re.search(r"^\|", markdown, re.M):
        score -= 0.2
    if "http" not in markdown and not is_link_exempt_quiet_day(markdown):
        score -= 0.25
    if "Recommended action" not in markdown and "Recommended actions by owner" not in markdown:
        score -= 0.2
    if "lacks MCP" in markdown or "Algolia does not have MCP" in markdown:
        score -= 0.4
    if "\u2014" in markdown or "\u2013" in markdown:
        score -= 0.1
    return max(round(score, 2), 0.0)


def validate_output(markdown: str, surface: str = "telegram") -> List[str]:
    errors = []
    if re.search(r"^\|", markdown, re.M):
        errors.append("tables_not_allowed")
    if "lacks MCP" in markdown or "Algolia does not have MCP" in markdown:
        errors.append("unsupported_algolia_gap")
    if surface == "telegram" and len(markdown.split()) > 520:
        errors.append("telegram_too_long")
    if "Recommended action" not in markdown and "Recommended actions by owner" not in markdown:
        errors.append("missing_action")
    if "http" not in markdown and not is_link_exempt_quiet_day(markdown):
        errors.append("missing_links")
    return errors


def save_markdown(markdown: str, date_str: str, cadence: str = "daily") -> Path:
    BRIEFS_DIR.mkdir(parents=True, exist_ok=True)
    suffix = "" if cadence == "daily" else "-%s" % cadence
    path = BRIEFS_DIR / ("%s%s.md" % (date_str, suffix))
    path.write_text(clean_generated_text(markdown))
    return path


def save_html(html_text: str, date_str: str, cadence: str = "daily") -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    suffix = "" if cadence == "daily" else "-%s" % cadence
    path = REPORTS_DIR / ("%s%s.html" % (date_str, suffix))
    path.write_text(html_text)
    return path


def record_synthesis_run(
    conn: sqlite3.Connection,
    cadence: str,
    date_start: str,
    date_end: str,
    signal_ids: Sequence[int],
    markdown_path: Path,
    html_path: Path,
    score: float,
) -> None:
    conn.execute(
        """
        insert into synthesis_runs (cadence, date_start, date_end, input_signal_ids, markdown_path, html_path, quality_score)
        values (?, ?, ?, ?, ?, ?, ?)
        """,
        (cadence, date_start, date_end, json.dumps(list(signal_ids)), str(markdown_path), str(html_path), score),
    )
    conn.execute(
        """
        insert into report_index (cadence, date_start, date_end, markdown_path, html_path, quality_score, top_signal_ids, status)
        values (?, ?, ?, ?, ?, ?, ?, 'generated')
        """,
        (cadence, date_start, date_end, str(markdown_path), str(html_path), score, json.dumps(list(signal_ids))),
    )
    conn.commit()


def list_report_archive(conn: sqlite3.Connection, limit: int = 50) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        select *
        from report_index
        order by date(date_end) desc, id desc
        limit ?
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def list_source_health(conn: sqlite3.Connection, date_start: str, date_end: str) -> List[Dict[str, Any]]:
    coverage = get_source_coverage(conn, date_start, date_end)
    status_rank = {"error": 0, "missing": 1, "ok": 2}
    rows = coverage.get("sources", [])
    return sorted(
        rows,
        key=lambda row: (
            status_rank.get(str(row.get("status")), 3),
            int(row.get("priority") or 99),
            str(row.get("competitor") or ""),
            str(row.get("url") or ""),
        ),
    )


def create_action_item(
    conn: sqlite3.Connection,
    title: str,
    owner: str,
    recommendation: str,
    evidence_signal_ids: Sequence[int],
    report_id: Optional[int] = None,
    priority: int = 3,
    due_date: Optional[str] = None,
) -> int:
    cur = conn.execute(
        """
        insert into action_items
          (report_id, title, owner, recommendation, evidence_signal_ids, status, priority, due_date)
        values (?, ?, ?, ?, ?, 'proposed', ?, ?)
        """,
        (
            report_id,
            title,
            owner,
            recommendation,
            json.dumps(list(evidence_signal_ids)),
            priority,
            due_date,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def list_action_items(conn: sqlite3.Connection, status: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    params: List[Any] = []
    where = ""
    if status:
        where = "where status = ?"
        params.append(status)
    params.append(limit)
    rows = conn.execute(
        """
        select *
        from action_items
        {where}
        order by
          case status
            when 'proposed' then 0
            when 'accepted' then 1
            when 'assigned' then 2
            when 'completed' then 3
            when 'rejected' then 4
            else 5
          end,
          priority asc,
          id desc
        limit ?
        """.format(where=where),
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def render_dashboard_html(conn: sqlite3.Connection, date_start: str, date_end: str) -> str:
    archive = list_report_archive(conn, limit=20)
    health = list_source_health(conn, date_start, date_end)
    actions = list_action_items(conn, limit=20)
    signals = [dict(row) for row in get_signals(conn, date_start=date_start, date_end=date_end, limit=30, min_score=0.0)]
    latest_daily = next((row for row in archive if row.get("cadence") == "daily"), None)
    latest_weekly = next((row for row in archive if row.get("cadence") == "weekly"), None)
    failed_sources = [row for row in health if row.get("status") != "ok"]
    material_signals = [row for row in signals if not signal_is_baseline(row)]
    top_action = actions[0] if actions else None
    collector_counts: Dict[str, int] = {}
    for row in health:
        collector = row.get("collector") or "unassigned"
        collector_counts[collector] = collector_counts.get(collector, 0) + 1
    collector_summary = ", ".join(
        "%s: %d" % (html.escape(name), count)
        for name, count in sorted(collector_counts.items())
    ) or "No collector strategy rows yet."

    def pill(status: str) -> str:
        label = html.escape(status or "unknown")
        klass = "ok" if status == "ok" else "warn" if status == "missing" else "bad"
        return '<span class="pill %s">%s</span>' % (klass, label)

    def report_card(title: str, row: Optional[Dict[str, Any]]) -> str:
        if not row:
            return '<div class="empty">No %s report indexed yet.</div>' % html.escape(title.lower())
        return """
        <div class="report-line">
          <strong>{title}</strong>
          <span>{period}</span>
          <span>Quality {quality:.2f}</span>
          <a href="{html_path}">HTML</a>
          <a href="{markdown_path}">Markdown</a>
        </div>
        """.format(
            title=html.escape(title),
            period=html.escape("%s to %s" % (row.get("date_start") or "", row.get("date_end") or "")),
            quality=float(row.get("quality_score") or 0),
            html_path=html.escape(row.get("html_path") or "#"),
            markdown_path=html.escape(row.get("markdown_path") or "#"),
        )

    source_rows = "\n".join(
        """
        <tr>
          <td>{competitor}</td>
          <td>{source_type}</td>
          <td>{collector}</td>
          <td>{quality}</td>
          <td>{priority}</td>
          <td>{status}</td>
          <td>{reason}</td>
        </tr>
        """.format(
            competitor=html.escape(row.get("competitor") or ""),
            source_type=html.escape(row.get("source_type") or ""),
            collector=html.escape(row.get("collector") or ""),
            quality=html.escape("%.2f" % float(row.get("quality_score")) if row.get("quality_score") is not None else ""),
            priority=html.escape(str(row.get("priority") or "")),
            status=pill(row.get("status") or "unknown"),
            reason=html.escape(compact(row.get("error") or row.get("url") or "", 100)),
        )
        for row in health[:18]
    )
    signal_rows = "\n".join(
        """
        <tr>
          <td>{competitor}</td>
          <td>{category}</td>
          <td>{owner}</td>
          <td>{score:.2f}</td>
          <td><a href="{url}">{title}</a></td>
        </tr>
        """.format(
            competitor=html.escape(row.get("competitor") or ""),
            category=html.escape(row.get("category") or ""),
            owner=html.escape(row.get("action_owner") or ""),
            score=float(row.get("score") or 0),
            url=html.escape(row.get("source_url") or "#"),
            title=html.escape(compact(row.get("title") or "", 90)),
        )
        for row in signals[:18]
    ) or '<tr><td colspan="5">No signals in this window.</td></tr>'
    action_rows = "\n".join(
        """
        <tr>
          <td>{title}</td>
          <td>{owner}</td>
          <td>{status}</td>
          <td>{priority}</td>
          <td>{recommendation}</td>
        </tr>
        """.format(
            title=html.escape(row.get("title") or ""),
            owner=html.escape(row.get("owner") or ""),
            status=html.escape(row.get("status") or ""),
            priority=html.escape(str(row.get("priority") or "")),
            recommendation=html.escape(compact(row.get("recommendation") or "", 120)),
        )
        for row in actions[:12]
    ) or '<tr><td colspan="5">No action items yet.</td></tr>'
    archive_rows = "\n".join(
        """
        <tr>
          <td>{cadence}</td>
          <td>{period}</td>
          <td>{quality:.2f}</td>
          <td><a href="{html_path}">HTML</a></td>
          <td><a href="{markdown_path}">Markdown</a></td>
        </tr>
        """.format(
            cadence=html.escape(row.get("cadence") or ""),
            period=html.escape("%s to %s" % (row.get("date_start") or "", row.get("date_end") or "")),
            quality=float(row.get("quality_score") or 0),
            html_path=html.escape(row.get("html_path") or "#"),
            markdown_path=html.escape(row.get("markdown_path") or "#"),
        )
        for row in archive
    ) or '<tr><td colspan="5">No reports indexed yet.</td></tr>'

    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>CI Command Center</title>
  <style>
    :root {{
      --blue: #003DFF;
      --cyan: #00B6FF;
      --ink: #021046;
      --body: #30364a;
      --muted: #667085;
      --line: #dfe4ee;
      --paper: #ffffff;
      --canvas: #f6f8fc;
      --ok: #087f5b;
      --warn: #b45309;
      --bad: #c2410c;
      --shadow: 0 10px 26px rgba(2, 16, 70, .08);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: var(--canvas); color: var(--body); }}
    a {{ color: var(--blue); text-decoration: none; font-weight: 650; }}
    .shell {{ max-width: 1440px; margin: 0 auto; padding: 24px; }}
    header {{ display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; margin-bottom: 20px; }}
    h1 {{ margin: 0; color: var(--ink); font-size: 34px; line-height: 1.1; letter-spacing: 0; }}
    h2 {{ margin: 0 0 12px; color: var(--ink); font-size: 18px; letter-spacing: 0; }}
    .eyebrow {{ color: var(--blue); font-weight: 800; font-size: 12px; text-transform: uppercase; }}
    .updated {{ color: var(--muted); font-size: 13px; }}
    nav {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 16px 0 22px; }}
    nav a {{ min-height: 40px; display: inline-flex; align-items: center; padding: 0 12px; border: 1px solid var(--line); border-radius: 8px; background: var(--paper); }}
    .metrics {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 14px; }}
    .metric, section {{ background: var(--paper); border: 1px solid var(--line); border-radius: 8px; box-shadow: var(--shadow); }}
    .metric {{ padding: 16px; min-height: 92px; }}
    .metric b {{ display: block; color: var(--ink); font-size: 28px; line-height: 1; }}
    .metric span {{ display: block; margin-top: 8px; color: var(--muted); font-size: 13px; }}
    .grid {{ display: grid; grid-template-columns: minmax(0, 1fr) minmax(320px, .45fr); gap: 14px; }}
    section {{ padding: 18px; margin-bottom: 14px; overflow: hidden; }}
    .report-line {{ display: grid; grid-template-columns: 1fr 1.3fr .7fr auto auto; gap: 10px; align-items: center; padding: 12px; border: 1px solid var(--line); border-radius: 8px; margin-bottom: 10px; }}
    .callout {{ border-left: 4px solid var(--blue); padding-left: 12px; color: var(--ink); font-weight: 650; }}
    .collector-line {{ margin: 0 0 10px; color: var(--muted); font-size: 13px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ text-align: left; padding: 10px 8px; border-bottom: 1px solid var(--line); vertical-align: top; }}
    th {{ color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .04em; }}
    .pill {{ display: inline-flex; min-height: 24px; align-items: center; border-radius: 999px; padding: 0 8px; font-size: 12px; font-weight: 750; }}
    .pill.ok {{ color: var(--ok); background: #ecfdf5; }}
    .pill.warn {{ color: var(--warn); background: #fff7ed; }}
    .pill.bad {{ color: var(--bad); background: #fff1f2; }}
    .empty {{ color: var(--muted); border: 1px dashed var(--line); border-radius: 8px; padding: 14px; }}
    @media (max-width: 900px) {{
      .shell {{ padding: 14px; }}
      header, .grid {{ display: block; }}
      .metrics {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .report-line {{ grid-template-columns: 1fr; }}
      table {{ display: block; overflow-x: auto; white-space: nowrap; }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <header>
      <div>
        <div class="eyebrow">Algolia competitive intelligence</div>
        <h1>CI Command Center</h1>
      </div>
      <div class="updated">Window: {date_start} to {date_end}</div>
    </header>
    <nav aria-label="Dashboard views">
      <a href="#today">Today</a>
      <a href="#weekly">Weekly</a>
      <a href="#sources">Sources</a>
      <a href="#signals">Signals</a>
      <a href="#actions">Actions</a>
      <a href="#archive">Archive</a>
    </nav>
    <div class="metrics">
      <div class="metric"><b>{material_count}</b><span>Material signals</span></div>
      <div class="metric"><b>{failed_count}</b><span>Sources needing attention</span></div>
      <div class="metric"><b>{action_count}</b><span>Open action items</span></div>
      <div class="metric"><b>{archive_count}</b><span>Indexed reports</span></div>
    </div>
    <div class="grid">
      <div>
        <section id="today">
          <h2>Today</h2>
          {daily_report}
          <p class="callout">{today_line}</p>
        </section>
        <section id="weekly">
          <h2>Weekly</h2>
          {weekly_report}
        </section>
        <section id="signals">
          <h2>Signals</h2>
          <table><thead><tr><th>Competitor</th><th>Category</th><th>Owner</th><th>Score</th><th>Evidence</th></tr></thead><tbody>{signal_rows}</tbody></table>
        </section>
        <section id="archive">
          <h2>Archive</h2>
          <table><thead><tr><th>Cadence</th><th>Period</th><th>Quality</th><th>HTML</th><th>Markdown</th></tr></thead><tbody>{archive_rows}</tbody></table>
        </section>
      </div>
      <aside>
        <section id="sources">
          <h2>Source health and collector strategy</h2>
          <p class="collector-line">Collectors: {collector_summary}</p>
          <table><thead><tr><th>Source</th><th>Type</th><th>Collector</th><th>Quality</th><th>Priority</th><th>Status</th><th>Reason</th></tr></thead><tbody>{source_rows}</tbody></table>
        </section>
        <section id="actions">
          <h2>Actions</h2>
          <table><thead><tr><th>Title</th><th>Owner</th><th>Status</th><th>Priority</th><th>Recommendation</th></tr></thead><tbody>{action_rows}</tbody></table>
        </section>
      </aside>
    </div>
  </main>
</body>
</html>
""".format(
        date_start=html.escape(date_start),
        date_end=html.escape(date_end),
        material_count=len(material_signals),
        failed_count=len(failed_sources),
        action_count=len([row for row in actions if row.get("status") != "completed"]),
        archive_count=len(archive),
        daily_report=report_card("Latest daily", latest_daily),
        weekly_report=report_card("Latest weekly", latest_weekly),
        today_line=html.escape(top_action.get("recommendation") if top_action else "No open action item is currently queued."),
        collector_summary=collector_summary,
        source_rows=source_rows or '<tr><td colspan="7">No source health rows.</td></tr>',
        signal_rows=signal_rows,
        action_rows=action_rows,
        archive_rows=archive_rows,
    )


def save_dashboard_html(html_text: str) -> Path:
    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)
    path = DASHBOARD_DIR / "index.html"
    path.write_text(html_text)
    return path


def extract_section(markdown: str, heading: str) -> str:
    wanted = heading.strip().lower()
    lines = markdown.splitlines()
    start = None
    for i, line in enumerate(lines):
        label = line.strip().strip("*").strip().lower()
        if label == wanted:
            start = i + 1
            break
    if start is None:
        return ""
    end = len(lines)
    for j in range(start, len(lines)):
        stripped = lines[j].strip()
        if re.fullmatch(r"-{3,}", stripped):
            continue
        if stripped.startswith("**") and stripped.endswith("**") and stripped.strip("*").strip():
            end = j
            break
    return "\n".join(lines[start:end]).strip()


def render_telegram(markdown: str, date_str: str, markdown_path: Path, html_path: Path) -> str:
    sections = {
        "Bottom line": extract_section(markdown, "Bottom line"),
        "Recommended action": extract_section(markdown, "Recommended action"),
        "Evidence": extract_section(markdown, "Evidence"),
        "Watch trigger": extract_section(markdown, "Watch trigger"),
    }
    evidence_lines = [line.strip() for line in sections["Evidence"].splitlines() if line.strip().startswith("- ")][:3]
    lines = [
        "Competitive pulse - %s" % date_str,
        "",
        "Bottom line",
        compact(sections["Bottom line"], 650),
        "",
        "Recommended action",
        compact(sections["Recommended action"], 600),
        "",
        "Evidence",
    ]
    lines.extend(evidence_lines or ["- No source-backed evidence section generated."])
    if sections["Watch trigger"]:
        lines.extend(["", "Watch trigger", compact(sections["Watch trigger"], 360)])
    lines.extend(["", "Artifacts", "Markdown: %s" % markdown_path, "HTML: %s" % html_path, "MEDIA:%s" % html_path])
    return "\n".join(lines)


def compact(text: str, max_chars: int) -> str:
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1", clean_generated_text(text or ""))
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"(^|\s)-{3,}(\s|$)", " ", text).strip()
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return "Not generated."
    if len(text) > max_chars:
        window = text[:max_chars - 3].rstrip()
        sentence_end = max(window.rfind(". "), window.rfind("? "), window.rfind("! "))
        if sentence_end >= int(max_chars * 0.55):
            return window[:sentence_end + 1].strip()
        word_end = window.rfind(" ")
        if word_end >= int(max_chars * 0.55):
            return window[:word_end].rstrip() + "..."
        return window + "..."
    return text


def plain_markdown_text(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1", text or "")
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    return clean_generated_text(text)


def markdown_inline(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(
        r"\[([^\]]+)\]\((https?://[^)]+)\)",
        lambda m: '<a href="%s">%s</a>' % (m.group(2), m.group(1)),
        escaped,
    )
    escaped = re.sub(
        r'(?<!["=])(https?://[^\s<]+)',
        lambda m: '<a href="%s">%s</a>' % (m.group(1).rstrip(".,);"), m.group(1).rstrip(".,);")),
        escaped,
    )
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    return escaped


def heading_id(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", plain_markdown_text(text).lower()).strip("-")
    return slug or "section"


def markdown_block(markdown: str) -> str:
    parts = []
    in_list = False
    for raw in markdown.splitlines():
        line = raw.strip()
        if not line:
            if in_list:
                parts.append("</ul>")
                in_list = False
            continue
        if line.startswith("- "):
            if not in_list:
                parts.append("<ul>")
                in_list = True
            parts.append("<li>%s</li>" % markdown_inline(line[2:]))
            continue
        if in_list:
            parts.append("</ul>")
            in_list = False
        if line.startswith("**") and line.endswith("**"):
            heading = line.strip("*").strip()
            if re.match(r"competitive pulse\s*-", heading, flags=re.IGNORECASE):
                continue
            parts.append('<h2 id="%s">%s</h2>' % (html.escape(heading_id(heading)), markdown_inline(heading)))
        elif line.startswith("# "):
            heading = line[2:].strip()
            if re.match(r"competitive pulse\s*-", heading, flags=re.IGNORECASE):
                continue
            parts.append('<h1 id="%s">%s</h1>' % (html.escape(heading_id(heading)), markdown_inline(heading)))
        else:
            parts.append("<p>%s</p>" % markdown_inline(line))
    if in_list:
        parts.append("</ul>")
    return "\n".join(parts)


def algolia_logo_html() -> str:
    for design_root in ALGOLIA_DESIGN_SYSTEM_FALLBACKS:
        logo_path = design_root / "assets" / "Algolia-logo-blue.svg"
        try:
            if logo_path.exists():
                svg = logo_path.read_text()
                data_uri = "data:image/svg+xml," + quote(svg)
                return '<img class="brand-logo" src="%s" alt="Algolia">' % data_uri
        except OSError:
            continue
    return '<span class="brand-text">Algolia</span>'


def human_date(value: str) -> str:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
        return parsed.strftime("%b ") + str(parsed.day) + parsed.strftime(", %Y")
    except Exception:
        return value


def report_period_label(packet: Dict[str, Any], cadence: str) -> str:
    start = packet.get("date_start", "")
    end = packet.get("date_end", "")
    label = "%s pulse" % cadence.title()
    if start and end and start != end:
        try:
            start_dt = datetime.strptime(start, "%Y-%m-%d")
            end_dt = datetime.strptime(end, "%Y-%m-%d")
            if start_dt.year == end_dt.year and start_dt.month == end_dt.month:
                return "%s - %s %s-%s, %s" % (
                    label,
                    start_dt.strftime("%b"),
                    start_dt.day,
                    end_dt.day,
                    end_dt.year,
                )
            if start_dt.year == end_dt.year:
                return "%s - %s %s-%s %s, %s" % (
                    label,
                    start_dt.strftime("%b"),
                    start_dt.day,
                    end_dt.strftime("%b"),
                    end_dt.day,
                    end_dt.year,
                )
        except Exception:
            pass
        return "%s - %s to %s" % (label, human_date(start), human_date(end))
    if end:
        return "%s - %s" % (label, human_date(end))
    return label


def render_weekly_html_report(markdown: str, packet: Dict[str, Any], cadence: str = "weekly") -> str:
    signals = packet.get("signals", [])
    coverage_totals = (packet.get("source_coverage") or {}).get("totals", {})
    failed_sources = [
        source for source in (packet.get("source_coverage") or {}).get("sources", [])
        if source.get("status") != "ok"
    ][:6]
    owner_count = len((packet.get("counts") or {}).get("by_owner", {}))
    changed_sources = coverage_totals.get("changed_signal_sources", 0)
    failed_count = coverage_totals.get("failed_sources", 0)
    signal_count = len(signals)
    body = markdown_block(markdown)
    logo = algolia_logo_html()
    period_label = report_period_label(packet, cadence)
    strategic_pattern = compact(
        plain_markdown_text(extract_section(markdown, "Strategic pattern") or extract_section(markdown, "What changed")),
        320,
    )
    failed_rows = []
    for source in failed_sources:
        failed_rows.append(
            '<div class="source-row"><a href="{url}">{competitor}</a><span>{source_type}</span><strong>{status}</strong></div>'.format(
                url=html.escape(source.get("url", "")),
                competitor=html.escape(source.get("competitor", "Unknown")),
                source_type=html.escape(display_label(source.get("source_type", "source"))),
                status=html.escape(source.get("status", "error")),
            )
        )
    if not failed_rows:
        failed_rows.append('<p class="meta">No source failures in this weekly window.</p>')
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Weekly competitive synthesis - {date_start} to {date_end}</title>
  <style>
    :root {{
      --algolia-blue: #003DFF;
      --algolia-blue-050: #f2f5ff;
      --ink: #021046;
      --fg2: #2f3447;
      --muted: #6b7280;
      --line: #e1e4ec;
      --paper: #ffffff;
      --canvas: #f7f8fb;
      --warning: #d97706;
      --shadow-sm: 0 2px 4px rgba(2, 16, 70, 0.06), 0 1px 2px rgba(2, 16, 70, 0.04);
      --font-body: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      --font-mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
    }}
    * {{ box-sizing: border-box; }}
    html {{ -webkit-text-size-adjust: 100%; text-size-adjust: 100%; }}
    body {{ margin: 0; background: #fff; color: var(--fg2); font-family: var(--font-body); font-size: 16px; line-height: 1.55; -webkit-font-smoothing: antialiased; }}
    a {{ color: var(--algolia-blue); text-decoration: none; overflow-wrap: anywhere; }}
    a:hover {{ text-decoration: underline; text-underline-offset: 3px; }}
    .page {{ max-width: 1040px; margin: 0 auto; padding: 28px; }}
    .brand {{ display: flex; align-items: center; gap: 10px; margin-bottom: 14px; color: var(--algolia-blue); font-weight: 700; font-size: 13px; }}
    .brand-logo {{ width: 128px; height: auto; display: block; }}
    .brand-text {{ font-weight: 800; }}
    .hero {{ padding: 26px; border: 1px solid var(--line); border-radius: 14px; background: linear-gradient(180deg, #ffffff 0%, #f8faff 100%); box-shadow: var(--shadow-sm); }}
    .eyebrow {{ color: var(--algolia-blue); font-size: 12px; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; }}
    h1 {{ margin: 9px 0 10px; color: var(--ink); font-size: 38px; line-height: 1.08; letter-spacing: 0; font-weight: 760; }}
    .lede {{ max-width: 820px; margin: 0; font-size: 16px; line-height: 1.5; }}
    .stats {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-top: 18px; }}
    .stat {{ min-height: 66px; padding: 12px 13px; border: 1px solid var(--line); border-radius: 10px; background: var(--paper); box-shadow: var(--shadow-sm); }}
    .stat b {{ display: block; color: var(--ink); font-size: 20px; line-height: 1.15; }}
    .stat span {{ display: block; margin-top: 4px; color: var(--muted); font-size: 11px; line-height: 1.25; }}
    .grid {{ display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(280px, .65fr); gap: 20px; margin-top: 22px; align-items: start; }}
    .card {{ background: var(--paper); border: 1px solid var(--line); border-radius: 14px; padding: 24px; box-shadow: var(--shadow-sm); }}
    .brief h2, .card h2 {{ margin: 24px 0 10px; color: var(--ink); font-size: 22px; line-height: 1.2; letter-spacing: 0; }}
    .brief h2:first-child, .card h2:first-child {{ margin-top: 0; }}
    .brief p {{ margin: 0 0 13px; font-size: 16px; line-height: 1.62; }}
    ul {{ margin: 10px 0 0; padding-left: 20px; }}
    li {{ margin: 8px 0; font-size: 16px; line-height: 1.55; }}
    code {{ font-family: var(--font-mono); font-size: 13px; background: var(--algolia-blue-050); border-radius: 6px; padding: 1px 5px; }}
    .source-list {{ display: grid; border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }}
    .source-row {{ display: grid; grid-template-columns: minmax(0, 1fr) 88px 64px; gap: 10px; align-items: center; padding: 10px 12px; border-top: 1px solid var(--line); }}
    .source-row:first-child {{ border-top: 0; }}
    .source-row span, .source-row strong, .meta {{ color: var(--muted); font-size: 12px; }}
    .source-row strong {{ color: var(--warning); text-align: right; }}
    @media (max-width: 820px) {{
      .page {{ padding: 14px 12px 24px; }}
      .brand-logo {{ width: 108px; }}
      .hero {{ padding: 16px 14px; border-radius: 12px; }}
      h1 {{ font-size: 25px; }}
      .lede {{ display: -webkit-box; -webkit-line-clamp: 4; -webkit-box-orient: vertical; overflow: hidden; }}
      .stats {{ grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }}
      .grid {{ grid-template-columns: 1fr; gap: 12px; margin-top: 12px; }}
      .card {{ padding: 16px; border-radius: 12px; }}
      .brief h2, .card h2 {{ font-size: 19px; margin: 18px 0 8px; }}
      .source-row {{ grid-template-columns: 1fr; gap: 4px; }}
      .source-row strong {{ text-align: left; }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <div class="brand">{logo}<span>Weekly competitive intelligence</span></div>
    <section class="hero">
      <div class="eyebrow">{period_label}</div>
      <h1>Weekly competitive synthesis</h1>
      <p class="lede">{strategic_pattern}</p>
      <div class="stats">
        <div class="stat"><b>{signal_count}</b><span>Material signals</span></div>
        <div class="stat"><b>{owner_count}</b><span>Action owners</span></div>
        <div class="stat"><b>{changed_sources}</b><span>Changed sources</span></div>
        <div class="stat"><b>{failed_count}</b><span>Source failures</span></div>
      </div>
    </section>
    <section class="grid">
      <article class="card brief">{body}</article>
      <aside class="card">
        <h2>Source health</h2>
        <div class="source-list">{failed_sources}</div>
      </aside>
    </section>
  </main>
</body>
</html>
""".format(
        date_start=html.escape(packet.get("date_start", "")),
        date_end=html.escape(packet.get("date_end", "")),
        logo=logo,
        period_label=html.escape(period_label),
        strategic_pattern=html.escape(strategic_pattern),
        signal_count=signal_count,
        owner_count=owner_count,
        changed_sources=changed_sources,
        failed_count=failed_count,
        body=body,
        failed_sources="\n".join(failed_rows),
    )


def render_html_report(markdown: str, packet: Dict[str, Any], cadence: str = "daily") -> str:
    if cadence == "weekly":
        return render_weekly_html_report(markdown, packet, cadence)
    signals = packet.get("signals", [])
    top = signals[0] if signals else {}
    owner = top.get("action_owner", "Competitive Intelligence") if top else "Competitive Intelligence"
    action_section = extract_section(markdown, "Recommended action")
    owner_match = re.search(r"(?:^|\n)\s*Owner:\s*([^\n]+)", action_section, flags=re.IGNORECASE)
    if owner_match:
        owner = plain_markdown_text(owner_match.group(1)).strip() or owner
    competitor = top.get("competitor", "No material signal") if top else "No material signal"
    confidence = confidence_label(float(top.get("confidence", 0))) if top else "none"
    evidence_count = len(packet.get("source_ledger", []))
    body = markdown_block(markdown)
    logo = algolia_logo_html()
    period_label = report_period_label(packet, cadence)
    bottom_line = compact(
        plain_markdown_text(extract_section(markdown, "Bottom line") or extract_section(markdown, "What changed")),
        280,
    )
    hero_headline = "Decision-ready competitive signal" if top else "No material competitive signal"
    top_signal = competitor if top else "Quiet"
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Competitive intelligence - {date_end}</title>
  <style>
    :root {{
      --algolia-blue: #003DFF;
      --algolia-blue-700: #0031cc;
      --algolia-blue-100: #e6ecff;
      --algolia-blue-050: #f2f5ff;
      --accent-cyan: #00B6FF;
      --accent-purple: #8A4FFF;
      --accent-pink: #FF4F81;
      --ink: #021046;
      --fg2: #2f3447;
      --muted: #6b7280;
      --line: #e1e4ec;
      --paper: #ffffff;
      --canvas: #f7f8fb;
      --navy: #0e1224;
      --success: #1f9d55;
      --warning: #d97706;
      --radius-md: 8px;
      --radius-xl: 16px;
      --shadow-sm: 0 2px 4px rgba(2, 16, 70, 0.06), 0 1px 2px rgba(2, 16, 70, 0.04);
      --shadow-lg: 0 18px 40px rgba(2, 16, 70, 0.10), 0 4px 12px rgba(2, 16, 70, 0.06);
      --font-display: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      --font-body: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      --font-mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
    }}
    * {{ box-sizing: border-box; }}
    html {{ -webkit-text-size-adjust: 100%; text-size-adjust: 100%; }}
    body {{
      margin: 0;
      overflow-x: hidden;
      background: #ffffff;
      color: var(--fg2);
      font-family: var(--font-body);
      font-size: 16px;
      line-height: 1.5;
      -webkit-font-smoothing: antialiased;
    }}
    a {{ color: var(--algolia-blue); text-decoration: none; }}
    a:hover {{ text-decoration: underline; text-underline-offset: 3px; }}
    .page {{ max-width: 920px; margin: 0 auto; padding: 28px; }}
    .brand {{ display: flex; align-items: center; gap: 10px; margin-bottom: 14px; color: var(--algolia-blue); font-weight: 700; font-size: 13px; }}
    .brand-logo {{ width: 128px; height: auto; display: block; }}
    .brand-text {{ font-weight: 800; }}
    .hero {{
      padding: 24px 26px 22px;
      border: 1px solid var(--line);
      border-radius: 14px;
      background:
        radial-gradient(circle at 12% 18%, rgba(0, 182, 255, 0.18), transparent 32%),
        radial-gradient(circle at 80% 8%, rgba(138, 79, 255, 0.14), transparent 30%),
        var(--paper);
      box-shadow: var(--shadow-sm);
    }}
    .eyebrow {{ color: var(--algolia-blue); font-size: 12px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; }}
    h1 {{ margin: 9px 0 10px; color: var(--ink); font-family: var(--font-display); font-size: clamp(28px, 4vw, 44px); line-height: 1.08; letter-spacing: 0; font-weight: 750; }}
    .lede {{ max-width: 760px; margin: 0; font-size: 16px; line-height: 1.5; color: var(--fg2); }}
    .stats {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-top: 18px; }}
    .stat {{ position: relative; min-height: 64px; padding: 11px 13px; border: 1px solid var(--line); border-radius: 10px; background: linear-gradient(180deg, #ffffff 0%, #f8faff 100%); box-shadow: 0 6px 14px rgba(2, 16, 70, 0.08), 0 1px 3px rgba(2, 16, 70, 0.05), inset 0 1px 0 rgba(255,255,255,.95); }}
    .stat b {{ display: block; color: var(--ink); font-size: 17px; line-height: 1.15; overflow-wrap: anywhere; }}
    .stat span {{ display: block; margin-top: 4px; color: var(--muted); font-size: 11px; line-height: 1.25; }}
    a.stat {{ display: block; color: inherit; text-decoration: none; transition: border-color 160ms ease, box-shadow 160ms ease, transform 160ms ease; }}
    a.stat::after {{ content: ""; position: absolute; inset: 0; border-radius: inherit; pointer-events: none; box-shadow: inset 0 -1px 0 rgba(2,16,70,.08); }}
    a.stat:hover {{ border-color: var(--algolia-blue); box-shadow: 0 16px 32px rgba(0, 61, 255, 0.16), 0 5px 12px rgba(2, 16, 70, 0.10), inset 0 1px 0 rgba(255,255,255,.95); transform: translateY(-2px); }}
    a.stat:active {{ box-shadow: 0 6px 12px rgba(2,16,70,.10), inset 0 2px 4px rgba(2,16,70,.10); transform: translateY(0); }}
    a.stat:focus-visible {{ outline: 3px solid var(--algolia-blue-100); outline-offset: 2px; border-color: var(--algolia-blue); }}
    .grid {{ display: grid; grid-template-columns: minmax(0, .9fr) minmax(0, 1.1fr); gap: 22px; margin-top: 22px; }}
    .section {{ margin-top: 14px; }}
    .card {{ background: var(--paper); border: 1px solid var(--line); border-radius: 14px; padding: 24px; box-shadow: var(--shadow-sm); }}
    .brief h2, .card h2 {{ margin: 24px 0 10px; color: var(--ink); font-size: 23px; line-height: 1.2; letter-spacing: 0; }}
    .brief h2:first-child {{ margin-top: 0; }}
    .brief p {{ margin: 0 0 13px; font-size: 16px; line-height: 1.62; }}
    ul {{ margin: 10px 0 0; padding-left: 20px; }}
    li {{ margin: 8px 0; font-size: 16px; line-height: 1.55; }}
    .brief a {{ overflow-wrap: anywhere; word-break: break-word; }}
    code {{ font-family: var(--font-mono); font-size: 13px; background: var(--algolia-blue-050); border-radius: 6px; padding: 1px 5px; }}
    .signal-list {{ display: grid; gap: 12px; }}
    .signal {{ padding: 16px; border: 1px solid var(--line); border-radius: 12px; background: #fff; }}
    .signal-top {{ display: flex; justify-content: space-between; gap: 12px; margin-bottom: 10px; }}
    .signal-title {{ color: var(--ink); font-weight: 600; overflow-wrap: anywhere; }}
    .badge {{ display: inline-flex; align-items: center; border-radius: 999px; padding: 4px 9px; background: var(--algolia-blue-050); color: var(--algolia-blue); font-size: 12px; white-space: nowrap; }}
    .meta {{ color: var(--muted); font-size: 13px; }}
    .source-ledger-card {{ margin-top: 22px; }}
    .ledger {{ display: grid; gap: 0; border: 1px solid var(--line); border-radius: 12px; overflow: hidden; background: #fff; }}
    .ledger-row {{ display: grid; grid-template-columns: 58px minmax(0, 1fr) 220px; gap: 14px; align-items: center; padding: 12px 14px; border-top: 1px solid var(--line); }}
    .ledger-row:first-child {{ border-top: 0; }}
    .ledger-row .badge {{ justify-self: start; }}
    .ledger a {{ overflow-wrap: anywhere; }}
    @media (max-width: 860px) {{
      .page {{ padding: 14px 12px 24px; }}
      .brand {{ margin-bottom: 10px; gap: 8px; font-size: 12px; }}
      .brand-logo {{ width: 108px; }}
      .grid {{ grid-template-columns: 1fr; gap: 14px; margin-top: 14px; }}
      .hero {{ padding: 15px 14px 13px; border-radius: 12px; background: #f8faff; }}
      .hero h1 {{ margin: 7px 0 8px; font-size: 24px; line-height: 1.1; }}
      .hero .lede {{ font-size: 15px; line-height: 1.45; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }}
      .stats {{ grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-top: 12px; }}
      .stat {{ min-height: 54px; padding: 9px 10px; border-radius: 8px; }}
      .stat b {{ font-size: 15px; }}
      .stat span {{ font-size: 10.5px; }}
      .card {{ padding: 16px; border-radius: 12px; }}
      .brief h2, .card h2 {{ font-size: 19px; margin: 18px 0 8px; }}
      .brief p, .brief li {{ font-size: 16px; line-height: 1.58; }}
      .signal-list {{ gap: 8px; }}
      .signal {{ padding: 12px; }}
      .ledger-row {{ grid-template-columns: 1fr; gap: 6px; }}
      .source-ledger-card {{ margin-top: 14px; }}
    }}
    @media (max-width: 560px) {{
      .page {{ padding: 10px 8px 22px; }}
      .brand {{ margin: 0 0 8px 2px; font-size: 11px; }}
      .brand-logo {{ width: 96px; }}
      .hero {{ padding: 13px 12px 12px; }}
      .eyebrow {{ font-size: 10.5px; }}
      .hero h1 {{ margin: 6px 0 7px; font-size: 22px; }}
      .hero .lede {{ font-size: 14.5px; line-height: 1.42; }}
      .stats {{ gap: 7px; margin-top: 11px; }}
      .stat {{ padding: 8px 9px; min-height: 50px; }}
      .stat b {{ font-size: 14px; }}
      .stat span {{ font-size: 10px; }}
      .grid {{ gap: 10px; margin-top: 10px; }}
      .section {{ margin-top: 12px; }}
      .card {{ padding: 14px; }}
      .brief h2, .card h2 {{ font-size: 18px; margin: 16px 0 7px; }}
      .brief p, .brief li {{ font-size: 15.5px; line-height: 1.56; }}
      ul {{ padding-left: 18px; }}
      .signal {{ padding: 10px; }}
      .signal-list {{ gap: 6px; }}
      .source-ledger-card {{ margin-top: 10px; }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <div class="brand">{logo}<span>Competitive intelligence</span></div>
    <section class="hero">
      <div>
        <div class="eyebrow">{cadence_label}</div>
        <h1>{hero_headline}</h1>
        <p class="lede">{bottom_line}</p>
      </div>
      <div class="stats">
        <a class="stat" href="#recommended-action"><b>{owner}</b><span>Recommended owner</span></a>
        <a class="stat" href="#evidence"><b>{top_signal}</b><span>Top signal</span></a>
        <a class="stat" href="#evidence"><b>{evidence_count}</b><span>Linked sources</span></a>
        <a class="stat" href="#watch-trigger"><b>{confidence}</b><span>Confidence</span></a>
      </div>
    </section>
    <section class="section">
      <article class="card brief">{body}</article>
    </section>
  </main>
</body>
</html>
""".format(
        date_end=html.escape(packet.get("date_end", "")),
        period_label=html.escape(period_label),
        cadence_label=html.escape("%s competitive pulse" % cadence.title()),
        logo=logo,
        hero_headline=html.escape(hero_headline),
        owner=html.escape(owner),
        top_signal=html.escape(top_signal),
        evidence_count=evidence_count,
        confidence=html.escape(confidence),
        bottom_line=html.escape(bottom_line),
        body=body,
    )

def render_signal_cards(signals: Sequence[Dict[str, Any]], limit: int = 5) -> str:
    if not signals:
        return '<p class="meta">No material signals in this window.</p>'
    cards = []
    for signal in signals[:limit]:
        cards.append(
            """<div class="signal">
  <div class="signal-top"><div class="signal-title">{title}</div><span class="badge">{owner}</span></div>
  <div class="meta">{competitor} - {category} - score {score:.2f}</div>
  <p>{summary}</p>
  <p><a href="{url}">Open source</a></p>
</div>""".format(
                title=html.escape(signal.get("title", "")),
                owner=html.escape(signal.get("action_owner", "")),
                competitor=html.escape(signal.get("competitor", "")),
                category=html.escape(display_label(signal.get("category", ""))),
                score=float(signal.get("score", 0)),
                summary=html.escape(compact(signal.get("summary", ""), 220)),
                url=html.escape(signal.get("source_url", "")),
            )
        )
    return '<div class="signal-list">%s</div>' % "\n".join(cards)


def render_source_ledger(ledger: Sequence[Dict[str, str]]) -> str:
    if not ledger:
        return '<p class="meta">No source ledger entries.</p>'
    rows = []
    for row in ledger[:12]:
        rows.append(
            '<div class="ledger-row"><span class="badge">{id}</span><a href="{url}">{title}</a><span class="meta">{competitor} - {category}</span></div>'.format(
                id=html.escape(row["id"]),
                url=html.escape(row["url"]),
                title=html.escape(row["title"]),
                competitor=html.escape(row["competitor"]),
                category=html.escape(display_label(row["category"])),
            )
        )
    return '<div class="ledger">%s</div>' % "\n".join(rows)


def write_collection_raw(payload: Dict[str, Any], date_str: str) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / ("%s-v2-collection.json" % date_str)
    path.write_text(json.dumps(payload, indent=2, default=str))
    return path


def seed_fixture(conn: sqlite3.Connection, fixture_path: Path, detected_date: Optional[str] = None) -> List[int]:
    signals = fixture_to_signals(fixture_path, detected_date=detected_date)
    return insert_signals(conn, signals)


def date_window(end_date: str, days: int) -> Tuple[str, str]:
    end = datetime.strptime(end_date, "%Y-%m-%d")
    start = end - timedelta(days=days - 1)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
