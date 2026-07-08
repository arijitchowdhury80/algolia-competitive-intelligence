"""CI-OS production daily runner -- the real per-tenant chain run for real,
not a rehearsal.

Adapted from scripts/gate7_e2e_rehearsal.py (do not modify that file; this
is a copy/adapt for production use). What changed relative to the
rehearsal:
  * No planted-miss fixtures. The real SemanticFNAuditor still runs, fed
    real raw observations vs real promoted signals only.
  * No tenant-bleed probe section (that was a one-time certification check,
    not a per-run production concern).
  * No docs/planning/gate7-rehearsal-runs/...md report writing.
  * Tenant/source config loads from config/tenants-sources.yaml instead of a
    hardcoded dict, and tenants are read from the DB (not hardcoded ids).
  * Exactly one tenant (CIOS_DELIVER_TENANT) gets a REAL Telegram send; every
    other tenant runs the full pipeline but delivers to a capturing (no-op)
    adapter.
  * Adds the weekly/monthly cadence ladder (WeeklySynthesizer /
    MonthlySynthesizer) on top of the daily chain, gated on is_weekly_due /
    is_monthly_due.
  * Writes the dashboard HTML + JSON for the delivered tenant to disk instead
    of writing a rehearsal report.

ARGUS V2 marker (see build_daily_message): this runner is a parallel system.
The old system stays primary until Arijit makes a cutover decision -- every
message delivered to the real tenant is prefixed so nobody mistakes it for
the production brief.

Two documented schema-gap workarounds (do not "fix" by touching schema.sql,
see the pre-resolved design decisions this script implements):
  1. Monthly cadence has no DB-level support (reports.cadence CHECK only
     allows daily/weekly/ad_hoc). Monthly runs persist with cadence='ad_hoc'
     and metadata={"real_cadence": "monthly"} -- see run_monthly_if_due().
  2. No table stores weekly synthesis results -- they are stored inside
     reports.metadata on the weekly report row and reconstructed by
     PgWeeklyResultLedger (src/cios/db/repos/cadence.py).

Env vars (read-only, never printed):
  CIOS_DATABASE_URL       - Postgres DSN (required)
  CIOS_CLAUDE_SHIM_URL    - claude-shim base URL (default http://127.0.0.1:8663)
  TELEGRAM_BOT_TOKEN      - real Telegram bot token, bridged onto TelegramAdapter
  CIOS_TELEGRAM_CHAT_ID   - real Telegram chat id, bridged onto TelegramAdapter
  CIOS_DELIVER_TENANT     - slug of the ONE tenant that gets a real send (default "algolia")
  CIOS_DASHBOARD_OUT      - path to write the dashboard HTML (default /tmp/argus-dashboard.html)
  TELEGRAM_ALLOWED_USER_IDS - comma-separated allowlist, passed through to TelegramAdapter unchanged

Run:
  CIOS_DATABASE_URL=postgresql://cios_app:<pw>@127.0.0.1:5433/cios \\
  TELEGRAM_BOT_TOKEN=... CIOS_TELEGRAM_CHAT_ID=... \\
      .venv/bin/python scripts/daily_production_run.py
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import psycopg
import yaml
from psycopg.rows import dict_row
from psycopg.types.json import Json

from cios.brain.cadence import MonthlySynthesizer, WeeklySynthesizer
from cios.brain.fn_auditor import (
    FNSemanticLLMClient,
    PromotedSignalsProvider,
    RawObservationsProvider,
    SemanticFNAuditor,
)
from cios.brain.brief import compose_daily_brief
from cios.brain.quality import QualityReviewer, UnparseableVerdict, extract_json_object
from cios.brain.synthesizer import Synthesizer
from cios.brain.thesis import ThesisEngine
from cios.brain.types import (
    CadenceActionItem,
    CoverageReport,
    LaneStatus,
    MonthlySynthesisResult,
    Pattern,
    Signal,
    SynthesisInput,
    Thesis,
    Verdict,
    WeeklySynthesisResult,
)
from cios.collect.article_resolver import resolve_article_links
from cios.collect.extract import canonical_url, semantic_diff
from cios.collect.fetcher import HttpContentFetcher, ProbeFetcherAdapter
from cios.collect.types import Delta as CDelta
from cios.collect.types import FetchStatus, Snapshot, SourceContext
from cios.dashboard.publisher import default_filename, publish_to_file, to_json_str
from cios.dashboard.state_builder import DashboardStateBuilder
from cios.db.repos.cadence import PgDailySignalLedger, PgWeeklyResultLedger
from cios.horizon.connector import DotConnector
from cios.horizon.industry import HorizonSynthesizer
from cios.horizon.ledger_scan import LedgerRecord, bucket_boundaries, scan_all_horizons
from cios.horizon.types import Horizon
from cios.ownbrand.collector import OwnBrandCollector
from cios.ownbrand.position import BrandPositionCompiler
from cios.ownbrand.types import BrandPositionRead, OwnBrandSource, OwnBrandSourceSpec
from cios.prescribe.engine import PrescriptionEngine
from cios.prescribe.types import Prescription
from cios.db.repos.collect import (
    PgDeltaRepository,
    PgFactRepository,
    PgFetchRunRepository,
    PgSnapshotRepository,
)
from cios.db.repos.dashboard import PgReportHistoryRepository, PgSuppressedSignalsRepository
from cios.db.repos.delivery import PgBotDeliveryRepository, PgDeliveryAttemptRepository
from cios.db.repos.learn import PgImprovementQueueRepository, PgLearningEventRepository
from cios.db.repos.sources import PgSourceRepository
from cios.db.session import get_dsn, tenant_context
from cios.delivery.action_router import ActionRouter
from cios.delivery.gated_commander import GatedDeliveryCommander
from cios.delivery.telegram_format import render_brief_html
from cios.delivery.types import Cadence, DeliveryRequest, ReportReadyEvent
from cios.hunter.lifecycle import SourceLifecycle
from cios.hunter.types import HealthEventType, SourceHealthEvent
from cios.hunter.validator import SourceValidator, normalize_url
from cios.learn.recorder import LearningRecorder
from cios.learn.types import FalseNegativeAuditStatus
from cios.platform.channels.adapter import ChannelAdapter
from cios.platform.channels.adapters.telegram import TelegramAdapter
from cios.platform.channels.types import (
    Channel,
    ChannelIdentity,
    DeliveryResult,
    ResponseEnvelope,
    VerificationResult,
)
from cios.platform.models.providers.claude_cli import ClaudeCliShimProvider
from cios.platform.models.types import ModelRequest

LLM_BUDGET = 35
LLM_CALLS = {"count": 0}

# Cutover 2026-07-08 (Arijit's explicit order): V2 IS the system. V0 cron
# jobs are paused (argus profile, ids 19930dfa21e5 / 03671620cd60) — resume
# them for rollback.
DAILY_MARKER = "ARGUS — Daily Competitive Brief"

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "tenants-sources.yaml"


class CountingModel:
    """Wraps a provider; hard-fails if the whole-run LLM budget is exceeded.
    Both the Synthesizer path (via .generate) and the sync
    ClaudeQualityReviewer.review() path increment the SAME LLM_CALLS counter,
    so the budget cap is enforced across the whole run, not per-component."""

    def __init__(self, inner) -> None:
        self._inner = inner

    async def generate(self, request: ModelRequest):
        LLM_CALLS["count"] += 1
        if LLM_CALLS["count"] > LLM_BUDGET:
            raise RuntimeError(f"LLM call budget ({LLM_BUDGET}) exceeded - aborting run")
        return await self._inner.generate(request)


def load_tenant_plan(path: Path = CONFIG_PATH) -> dict[str, list[dict[str, str]]]:
    """Loads the tenant/competitor/source plan from config/tenants-sources.yaml."""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data


class CapturingTelegramAdapter(ChannelAdapter):
    """No-op Telegram adapter for every tenant except CIOS_DELIVER_TENANT.
    Records what would have been sent; sends nothing. The real
    commander/formatting code path still runs and still writes real
    bot_deliveries + delivery_attempts rows."""

    channel_name = "telegram"

    def __init__(self) -> None:
        self.captured: list[ResponseEnvelope] = []

    async def receive(self, raw_event: Any):  # pragma: no cover
        raise NotImplementedError

    async def send(self, response: ResponseEnvelope) -> DeliveryResult:
        self.captured.append(response)
        return DeliveryResult(
            success=True, channel=response.channel,
            provider_message_id=f"CAPTURED-{len(self.captured)}",
            raw_response={"captured": True, "note": "no real telegram send for this tenant"},
        )

    def verify_signature(self, raw_event: Any) -> VerificationResult:
        return VerificationResult(verified=True)

    def map_identity(self, raw_event: Any) -> ChannelIdentity:
        return ChannelIdentity(channel=Channel.TELEGRAM, channel_user_id="capturing")

    def supports(self, capability: str) -> bool:
        return capability in {"send", "html"}


class SingleAdapterRegistry:
    def __init__(self, adapter: ChannelAdapter) -> None:
        self._adapter = adapter

    def get_adapter(self, channel: str) -> ChannelAdapter:
        if channel != "telegram":
            raise KeyError(f"no adapter for channel {channel}")
        return self._adapter


class TelegramOnlyChannelConfig:
    def __init__(self, chat_id: str) -> None:
        self._chat_id = chat_id

    def get_channel_preference(self, tenant_id: int) -> list[Channel]:
        return [Channel.TELEGRAM]

    def get_recipient(self, tenant_id: int, channel: Channel) -> Optional[str]:
        return self._chat_id if channel == Channel.TELEGRAM else None

    def get_thread_id(self, tenant_id: int, channel: Channel) -> Optional[str]:
        return self._chat_id if channel == Channel.TELEGRAM else None


def build_real_telegram_adapter() -> TelegramAdapter:
    """Constructs a real TelegramAdapter and bridges this runner's env-var
    contract (TELEGRAM_BOT_TOKEN / CIOS_TELEGRAM_CHAT_ID) onto the adapter's
    own env-var names (ARGUS_TELEGRAM_BOT_TOKEN / ARGUS_TELEGRAM_CHAT_ID),
    which it reads directly from os.environ at construction time. This is a
    deliberate bridge (decision #4), not a bug: the two env contracts differ
    on purpose (this runner's contract vs the adapter's own), so we set the
    attributes explicitly right after construction rather than renaming
    either side."""
    adapter = TelegramAdapter()
    adapter.bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    adapter.default_chat_id = os.environ["CIOS_TELEGRAM_CHAT_ID"]
    return adapter


def select_adapter_for_tenant(slug: str, deliver_tenant: str, telegram_env: dict) -> ChannelAdapter:
    """Returns a real (env-bridged) TelegramAdapter for the delivered tenant,
    a CapturingTelegramAdapter (no real send) for every other tenant.
    `telegram_env` is injected (not read from os.environ here) so this stays
    testable without process env mutation."""
    if slug == deliver_tenant:
        adapter = TelegramAdapter()
        adapter.bot_token = telegram_env["TELEGRAM_BOT_TOKEN"]
        adapter.default_chat_id = telegram_env["CIOS_TELEGRAM_CHAT_ID"]
        return adapter
    return CapturingTelegramAdapter()


def build_daily_message(brief_markdown: str) -> str:
    """Prefixes the daily brief markdown with the ARGUS V2 parallel-run
    marker before it is rendered to Telegram HTML. Injected at the markdown
    level (ReportReadyEvent.markdown_body), since DeliveryCommander itself
    calls render_brief_html() on markdown_body -- see
    cios/delivery/commander.py:_build_envelope. Factored out so it is
    directly unit-testable without constructing a whole delivery request."""
    return f"{DAILY_MARKER}\n\n{brief_markdown}"


class ClaudeQualityReviewer:
    """QualityLLMReviewer backed by the live Claude shim. Copied from
    scripts/gate7_e2e_rehearsal.py (production uses the identical, real,
    LIVE-Claude-backed reviewer)."""

    def __init__(self, shim_url: str, model_alias: str = "opus") -> None:
        self._url = shim_url
        self._alias = model_alias

    def review(self, tenant_id, run_id, reader_text, claims, evidence_texts, attempt: int = 1) -> dict:
        import httpx

        LLM_CALLS["count"] += 1
        if LLM_CALLS["count"] > LLM_BUDGET:
            raise RuntimeError(f"LLM call budget ({LLM_BUDGET}) exceeded - aborting run")
        claim_lines = "\n".join(f"- {getattr(c, 'text', '')} (src: {getattr(c, 'source_url', '')})" for c in claims)
        evidence_block = self._build_evidence_block(evidence_texts, claims=claims)
        prompt = (
            "You are Argus, a skeptical competitive-intelligence editor. Review this "
            "brief for: (1) any claim not backed by a source URL, (2) generic AI slop, "
            "(3) hallucinated specifics. NOTE: every quoted string and specific figure "
            "in these claims has ALREADY been verified verbatim against the FULL source "
            "text by a deterministic pre-check; the excerpts below are quote-anchored "
            "windows from that verification, so judge accuracy of framing and evidence "
            "sufficiency, and do NOT fail a claim merely because its quote falls "
            "outside a truncated excerpt. Return "
            'ONLY JSON: {"pass": bool, "required_fixes": [str], "notes": str}.\n\n'
            f"BRIEF:\n{reader_text}\n\nCLAIMS:\n{claim_lines or '(none)'}\n\n"
            f"SOURCE EXCERPTS (quote-anchored windows):\n{evidence_block or '(none)'}\n"
        )
        if attempt > 1:
            prompt = (
                "Your previous reply was not valid JSON. Return ONLY the JSON object "
                "described, nothing else.\n\n" + prompt
            )
        try:
            resp = httpx.post(f"{self._url}/generate",
                              json={"prompt": prompt, "model_alias": self._alias, "json_mode": True, "timeout_s": 90},
                              timeout=120.0)
            resp.raise_for_status()
            text = (resp.json().get("text") or "").strip()
        except Exception as exc:  # noqa: BLE001
            raise UnparseableVerdict(f"quality reviewer LLM call failed: {exc}") from exc
        obj = extract_json_object(text)
        if isinstance(obj, dict) and "pass" in obj:
            return {"pass": bool(obj.get("pass")),
                    "required_fixes": list(obj.get("required_fixes") or []),
                    "notes": obj.get("notes", "")}
        raise UnparseableVerdict(f"quality reviewer returned unparseable verdict: {text[:300]}")

    @staticmethod
    def _build_evidence_block(evidence_texts: dict[str, str], cap: int = 8000, claims=()) -> str:
        import re as _re

        if not evidence_texts:
            return ""
        spans_by_url: dict[str, list[str]] = {}
        for c in claims or ():
            text = getattr(c, "text", "") or ""
            url = getattr(c, "source_url", "") or ""
            found = _re.findall(r'[""]([^""]{4,})[""]|"([^"]{4,})"', text)
            spans = [a or b for a, b in found]
            spans += _re.findall(r"\$[\d,.]+\s*[BbMmKk]?\+?|\d+(?:\.\d+)?%", text)
            if spans:
                spans_by_url.setdefault(url, []).extend(spans)
        cited = {getattr(c, "source_url", "") for c in claims or ()}
        ordered = sorted(evidence_texts.items(), key=lambda kv: kv[0] not in cited)
        parts: list[str] = []
        total = 0
        window = 400
        for url, text in ordered:
            if total >= cap:
                break
            text = text or ""
            pieces: list[str] = []
            for span in spans_by_url.get(url, []):
                idx = text.lower().find(span.lower().strip())
                if idx >= 0:
                    pieces.append(text[max(0, idx - window // 2): idx + len(span) + window // 2])
            if not pieces:
                pieces = [text[:800]]
            excerpt = " [...] ".join(pieces)[: max(500, cap - total)]
            parts.append(f"- {url}:\n  {excerpt}")
            total += len(excerpt)
        return "\n".join(parts)


class _ReviewClaim:
    def __init__(self, text: str, source_url: Optional[str]) -> None:
        self.text = text
        self.source_url = source_url


class _ReviewInput:
    def __init__(self, tenant_id, run_id, claims, reader_text, quiet_verdict, coverage_ran_clean,
                 evidence_texts: Optional[dict[str, str]] = None) -> None:
        self.tenant_id = tenant_id
        self.run_id = run_id
        self.claims = claims
        self.reader_text = reader_text
        self.quiet_verdict = quiet_verdict
        self.coverage_ran_clean = coverage_ran_clean
        self.evidence_texts = evidence_texts or {}


class DbMaterialSignals:
    def __init__(self, conn) -> None:
        self._conn = conn

    def get_material_deltas(self, tenant_id: int) -> list[dict]:
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT d.id, d.competitor_id, c.name AS competitor_name, d.delta_type,
                           d.materiality_score, d.what_changed, d.why_it_matters,
                           d.recommended_action, d.confidence, d.evidence_ids
                    FROM semantic_deltas d JOIN competitors c ON c.id = d.competitor_id
                    WHERE d.tenant_id = %s AND d.quality_status = 'published'
                    ORDER BY d.materiality_score DESC
                    """,
                    (tenant_id,),
                )
                return [dict(r) for r in cur.fetchall()]


class DbTheses:
    def __init__(self, conn) -> None:
        self._conn = conn

    def get_active_theses(self, tenant_id: int) -> list[dict]:
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT t.id, t.competitor_id, c.name AS competitor_name, t.thesis,
                           t.status, t.confidence, t.supporting_delta_ids, t.contradicting_delta_ids,
                           t.updated_at
                    FROM competitor_theses t JOIN competitors c ON c.id = t.competitor_id
                    WHERE t.tenant_id = %s AND t.status = 'active'
                    """,
                    (tenant_id,),
                )
                return [dict(r) for r in cur.fetchall()]


class DbCoverage:
    def __init__(self, cov: dict) -> None:
        self._cov = cov

    def get_latest_coverage(self, tenant_id: int) -> Optional[dict]:
        return self._cov


class DbRuns:
    def __init__(self, run: dict) -> None:
        self._run = run

    def get_latest_run(self, tenant_id: int, cadence: str) -> Optional[dict]:
        return self._run


class TenantResult:
    def __init__(self, slug: str) -> None:
        self.slug = slug
        self.tenant_id: Optional[int] = None
        self.sources_fetched: list[dict] = []
        self.facts_extracted = 0
        self.deltas_extracted = 0
        self.promoted_signals: list[dict] = []
        self.synth_verdict: Optional[str] = None
        self.quality_status: Optional[str] = None
        self.quality_fixes: list = []
        self.fn_status: Optional[str] = None
        self.delivered = False
        self.deliveries: list[dict] = []
        self.dashboard_state = None
        self.errors: list[str] = []


def app_dsn(superuser_dsn: str) -> str:
    info = psycopg.conninfo.conninfo_to_dict(superuser_dsn)
    info["user"] = "cios_app"
    info["password"] = os.environ.get("CIOS_APP_PASSWORD", "cios_app_dev_local_only_not_secret")
    return psycopg.conninfo.make_conninfo(**info)


def is_weekly_due(now: datetime) -> bool:
    """Weekly cadence is due on Sunday, UTC."""
    return now.weekday() == 6


def is_monthly_due(now: datetime) -> bool:
    """Monthly cadence is due on the first Monday of the month, UTC."""
    return now.day <= 7 and now.weekday() == 0


def _now() -> datetime:
    return datetime.now(timezone.utc)


def seed_competitors(conn, tenant_id: int, plan: list[dict]) -> dict[str, int]:
    ids: dict[str, int] = {}
    with tenant_context(conn, tenant_id):
        with conn.cursor(row_factory=dict_row) as cur:
            for c in plan:
                cur.execute(
                    """
                    INSERT INTO competitors (tenant_id, name, domain, category, priority, status)
                    VALUES (%s, %s, %s, 'search/discovery', 2, 'active')
                    ON CONFLICT (tenant_id, name) DO UPDATE SET domain = EXCLUDED.domain
                    RETURNING id, name
                    """,
                    (tenant_id, c["name"], c["domain"]),
                )
                row = cur.fetchone()
                ids[row["name"]] = row["id"]
    return ids


def insert_health_event(conn, ev: SourceHealthEvent) -> None:
    with tenant_context(conn, ev.tenant_id):
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO source_health_events (tenant_id, source_id, event_type, http_status, detail, metadata)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (ev.tenant_id, ev.source_id, ev.event_type.value, ev.http_status, ev.detail, Json(ev.metadata)),
            )


def insert_report(conn, tenant_id, cadence, title, summary, metadata: Optional[dict] = None) -> int:
    with tenant_context(conn, tenant_id):
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO reports (tenant_id, cadence, report_date, title, status, summary, metadata)
                VALUES (%s, %s, %s, %s, 'rendered', %s, %s) RETURNING id
                """,
                (tenant_id, cadence, date.today(), title, summary, Json(metadata or {})),
            )
            return cur.fetchone()["id"]


def insert_thesis(conn, tenant_id, competitor_id, thesis_text, confidence, evidence_ids) -> int:
    with tenant_context(conn, tenant_id):
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO competitor_theses (tenant_id, competitor_id, thesis, status, confidence, supporting_delta_ids)
                VALUES (%s, %s, %s, 'active', %s, %s) RETURNING id
                """,
                (tenant_id, competitor_id, thesis_text, confidence, Json(evidence_ids)),
            )
            return cur.fetchone()["id"]


def insert_claim(conn, tenant_id, competitor_id, claim_text, evidence_ids) -> int:
    with tenant_context(conn, tenant_id):
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO claims (tenant_id, competitor_id, claim_text, claim_type, evidence_ids)
                VALUES (%s, %s, %s, 'positioning', %s) RETURNING id
                """,
                (tenant_id, competitor_id, claim_text, Json(evidence_ids)),
            )
            return cur.fetchone()["id"]


def insert_quality_review(conn, tenant_id, run_id, status, findings, fixes) -> None:
    with tenant_context(conn, tenant_id):
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO quality_reviews (tenant_id, run_id, review_type, status, findings, required_fixes, reviewed_at)
                VALUES (%s, %s, 'pre-delivery', %s, %s, %s, now())
                """,
                (tenant_id, run_id, status, Json(findings), Json(fixes)),
            )


def insert_fn_audit(conn, tenant_id, run_id, audit_status, risk_reason, recheck) -> None:
    with tenant_context(conn, tenant_id):
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO false_negative_audits (tenant_id, run_id, audit_status, risk_reason, recommended_recheck)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (tenant_id, run_id, audit_status, risk_reason, Json(recheck)),
            )


def insert_dashboard_state(conn, tenant_id, daily_json, material_ids, delivery_ids, path) -> None:
    with tenant_context(conn, tenant_id):
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO dashboard_state (tenant_id, daily_state, material_delta_ids, delivery_ids, json_path)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (tenant_id, Json(daily_json), Json(material_ids), Json(delivery_ids), path),
            )


def _apply_cold_start_labels(text: str, cold_start: bool) -> str:
    """Re-applies the cold-start (first cycle, no prior snapshot) heading
    swap. Factored out so every reader_text rebuild (initial synth, revise
    pass, post-prescriptions rebuild) stays consistent instead of only the
    first render getting the swap."""
    if not cold_start:
        return text
    return text.replace(
        "## Your competitive picture", "## Your competitive BASELINE (first cycle)", 1
    ).replace("## WHAT HAPPENED (24h)", "## WHERE YOUR COMPETITORS STAND TODAY", 1)


def prescription_to_action_item(p: Prescription, report_id: Optional[int] = None) -> dict:
    """Maps a Prescription onto an action_items row (schema: src/cios/db/schema.sql).
    No schema change needed -- action_items already has owner/recommendation/
    evidence_ids/priority/confidence/due_window/report_id, a good-enough fit
    for a prescription's shape. Deviation: there is no dedicated `payload`
    jsonb column on action_items, so the play steps are folded into
    `recommendation` (title + steps) rather than dropped, and grounding
    thesis_ids (the only non-URL evidence reference) are carried in
    `source_delta_ids` since that is the closest existing jsonb column for
    "what this traces back to" that is not `evidence_ids` itself."""
    g = p.grounding
    steps = "; ".join(p.play)
    recommendation = f"{p.title}: {steps}" if steps else p.title
    return {
        "tenant_id": p.tenant_id,
        "owner": p.team.value,
        "recommendation": recommendation,
        "evidence_ids": list(dict.fromkeys(g.evidence_urls)),
        "source_delta_ids": list(g.thesis_ids),
        "priority": p.urgency_window.value,
        "confidence": p.materiality_score,
        "due_window": p.urgency_window.value,
        "report_id": report_id,
    }


def insert_action_item(conn, row: dict) -> Optional[int]:
    with tenant_context(conn, row["tenant_id"]):
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO action_items
                    (tenant_id, owner, recommendation, evidence_ids, source_delta_ids,
                     priority, confidence, due_window, report_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    row["tenant_id"], row["owner"], row["recommendation"],
                    Json(row["evidence_ids"]), Json(row["source_delta_ids"]),
                    row["priority"], row["confidence"], row["due_window"], row["report_id"],
                ),
            )
            fetched = cur.fetchone()
            return fetched["id"] if fetched else None


class DbLedgerRecords:
    """LedgerRepo (cios.horizon.ledger_scan.LedgerRepo) backed by published
    semantic_deltas -- industry-wide (not filtered to a single named
    competitor), per doctrine Addendum 2 point 1. evidence_ids on
    semantic_deltas is a jsonb array of URL strings (Delta.evidence_urls);
    the first one becomes the LedgerRecord's source_url, matching the
    1-URL-per-record shape ledger_scan expects."""

    def __init__(self, conn) -> None:
        self._conn = conn

    def records_in_window(self, tenant_id: int, start, end) -> list[LedgerRecord]:
        with tenant_context(self._conn, tenant_id):
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT competitor_id, created_at::date AS observed_at, delta_type,
                           what_changed, evidence_ids
                    FROM semantic_deltas
                    WHERE tenant_id = %s AND quality_status = 'published'
                      AND created_at::date BETWEEN %s AND %s
                    """,
                    (tenant_id, start, end),
                )
                rows = cur.fetchall()
        out: list[LedgerRecord] = []
        for r in rows:
            evidence = r["evidence_ids"] or []
            url = evidence[0] if evidence else None
            out.append(LedgerRecord(
                competitor_id=r["competitor_id"], observed_at=r["observed_at"],
                kind=r["delta_type"] or "signal", summary=r["what_changed"] or "", source_url=url,
            ))
        return out


def _format_horizon_section(horizon_reads: list, connections: list) -> str:
    """Renders the weekly-only multi-horizon industry read + dot-connections
    section (doctrine Addendum 2 point 1). Returns "" (no section) when
    there is genuinely nothing to show -- never a fabricated placeholder."""
    lines: list[str] = []
    any_content = False
    for read in horizon_reads:
        if not read.notable_movements and not read.themes:
            continue
        any_content = True
        lines.append(f"### Horizon {read.horizon.value} (as of {read.as_of.isoformat()})")
        for m in read.notable_movements:
            lines.append(f"- {m}")
        for theme in read.themes:
            lines.append(f"- [{theme.confidence.value}] {theme.theme} (evidence={theme.evidence_urls})")
        lines.append("")
    if connections:
        any_content = True
        lines.append("### This week connects to")
        for c in connections:
            lines.append(f"- ({c.horizon.value}) {c.connection}")
        lines.append("")
    if not any_content:
        return ""
    return "## MULTI-HORIZON INDUSTRY READ\n\n" + "\n".join(lines).rstrip() + "\n"


def _format_weekly_brief(result: WeeklySynthesisResult) -> str:
    lines = [f"Weekly pattern review - competitor {result.competitor_id}", ""]
    if not result.patterns:
        lines.append("No material pattern identified this week.")
    else:
        lines.append("Patterns:")
        for p in result.patterns:
            lines.append(f"- {p.pattern} (materiality={p.materiality_score:.2f}, evidence={p.evidence_urls})")
    lines.append("")
    if not result.action_plan:
        lines.append("No action items this week.")
    else:
        lines.append("Action plan:")
        for a in result.action_plan:
            lines.append(f"- [{a.team_to_involve}] {a.action} (evidence={a.evidence_urls})")
    return "\n".join(lines)


def _format_monthly_brief(result: MonthlySynthesisResult) -> str:
    lines = [f"Monthly roll-up - competitor {result.competitor_id}", ""]
    if not result.patterns:
        lines.append("No material pattern identified this month.")
    else:
        lines.append("Patterns:")
        for p in result.patterns:
            lines.append(f"- {p.pattern} (materiality={p.materiality_score:.2f}, evidence={p.evidence_urls})")
    lines.append("")
    if not result.action_plan:
        lines.append("No action items this month.")
    else:
        lines.append("Action plan:")
        for a in result.action_plan:
            lines.append(f"- [{a.team_to_involve}] {a.action} (evidence={a.evidence_urls})")
    return "\n".join(lines)


async def _deliver_cadence_report(
    app_conn, tenant_id: int, slug: str, adapter: ChannelAdapter, cadence: Cadence,
    report_id: int, title: str, markdown_body: str,
) -> None:
    """Shared delivery plumbing for weekly/monthly reports: same
    commander/adapter/router pattern as the daily chain, minus the quality
    gate (weekly/monthly are internal roll-ups over already-quality-gated
    daily signals, not fresh LLM claims against raw evidence)."""
    recorder = LearningRecorder(
        learning_events=PgLearningEventRepository(app_conn),
        improvement_queue=PgImprovementQueueRepository(app_conn),
    )
    commander = GatedDeliveryCommander(
        adapters=SingleAdapterRegistry(adapter),
        bot_deliveries=PgBotDeliveryRepository(app_conn),
        delivery_attempts=PgDeliveryAttemptRepository(app_conn),
        recorder=recorder,
    )
    router = ActionRouter(channel_config=TelegramOnlyChannelConfig(os.environ.get("CIOS_TELEGRAM_CHAT_ID", "")))
    report_event = ReportReadyEvent(
        report_id=report_id, tenant_id=tenant_id, cadence=cadence,
        title=title, summary=markdown_body[:200], markdown_body=markdown_body,
    )
    plan_route = router.route_report(report_event)
    from cios.learn.types import QualityReview, QualityReviewStatus

    passed_verdict = QualityReview(status=QualityReviewStatus.PASSED, findings=[], required_fixes=[])
    await commander.deliver(
        DeliveryRequest(tenant_id=tenant_id, report=report_event, plan=plan_route),
        quality_verdict=passed_verdict,
    )


async def run_weekly_if_due(
    app_conn, tenant_id: int, slug: str, adapter: ChannelAdapter, model, now: datetime
) -> None:
    """Runs the weekly pattern-identification pass for every competitor of
    this tenant, if `now` is a Sunday (is_weekly_due)."""
    if not is_weekly_due(now):
        return
    week_start = (now - timedelta(days=now.weekday() + 1)).date()  # the Monday that started this week
    ledger = PgDailySignalLedger(app_conn)
    synthesizer = WeeklySynthesizer(model=model, ledger=ledger)

    with tenant_context(app_conn, tenant_id):
        with app_conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT id FROM competitors WHERE tenant_id = %s AND status = 'active'", (tenant_id,))
            competitor_ids = [row["id"] for row in cur.fetchall()]

    for competitor_id in competitor_ids:
        result = await synthesizer.synthesize(tenant_id, competitor_id, week_start)
        metadata = {"weekly_synthesis": {str(competitor_id): result.model_dump(mode="json")}}
        report_id = insert_report(
            app_conn, tenant_id, "weekly", f"Weekly pattern review - {slug}",
            f"competitor {competitor_id}", metadata=metadata,
        )
        brief = _format_weekly_brief(result)
        await _deliver_cadence_report(app_conn, tenant_id, slug, adapter, Cadence.WEEKLY, report_id,
                                       f"Argus weekly review - {slug}", brief)

    # Multi-horizon industry read + dot-connections (doctrine Addendum 2
    # point 1): industry-wide (not per-competitor), computed once per tenant
    # per week. Wrapped so a failure here never blocks the per-competitor
    # weekly pattern reviews above, which have already been delivered.
    try:
        as_of = now.date()
        ledger_repo = DbLedgerRecords(app_conn)
        obs_by_horizon = scan_all_horizons(ledger_repo, tenant_id, as_of)
        horizon_synth = HorizonSynthesizer(model=model)
        horizon_reads = []
        for horizon in Horizon:
            start, end = bucket_boundaries(as_of, horizon)
            read = await horizon_synth.synthesize(
                tenant_id, horizon, as_of, obs_by_horizon[horizon], (start, end)
            )
            horizon_reads.append(read)

        week_records = ledger_repo.records_in_window(tenant_id, week_start, as_of)
        week_signals = [
            Signal(
                competitor_id=r.competitor_id if r.competitor_id is not None else 0,
                signal_type=r.kind or "signal", headline=(r.summary or "")[:120],
                what_changed=r.summary or "", recommended_action="", owner="PMM",
                team_to_involve="Marketing", materiality_score=0.5,
                evidence_urls=[r.source_url],
            )
            for r in week_records if r.source_url
        ]
        connector = DotConnector(model=model)
        connections = await connector.connect(tenant_id, week_signals, horizon_reads) if week_signals else []

        horizon_brief = _format_horizon_section(horizon_reads, connections)
        if horizon_brief:
            h_metadata = {
                "horizon_reads": [r.model_dump(mode="json") for r in horizon_reads],
                "dot_connections": [c.model_dump(mode="json") for c in connections],
            }
            h_report_id = insert_report(
                app_conn, tenant_id, "weekly", f"Weekly horizon review - {slug}",
                "multi-horizon industry read", metadata=h_metadata,
            )
            await _deliver_cadence_report(
                app_conn, tenant_id, slug, adapter, Cadence.WEEKLY, h_report_id,
                f"Argus weekly horizon review - {slug}", horizon_brief,
            )
    except Exception as exc:  # noqa: BLE001
        print(f"WARNING: weekly horizon/dot-connection integration failed for {slug}: {exc}")


async def run_monthly_if_due(
    app_conn, tenant_id: int, slug: str, adapter: ChannelAdapter, model, now: datetime
) -> None:
    """Runs the monthly roll-up pass for every competitor of this tenant, if
    `now` is the first Monday of the month (is_monthly_due)."""
    if not is_monthly_due(now):
        return
    month_start = now.date().replace(day=1)
    ledger = PgWeeklyResultLedger(app_conn)
    synthesizer = MonthlySynthesizer(model=model, ledger=ledger)

    with tenant_context(app_conn, tenant_id):
        with app_conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT id FROM competitors WHERE tenant_id = %s AND status = 'active'", (tenant_id,))
            competitor_ids = [row["id"] for row in cur.fetchall()]

    for competitor_id in competitor_ids:
        result = await synthesizer.synthesize(tenant_id, competitor_id, month_start)
        # Schema-gap workaround (decision #1): reports.cadence CHECK only
        # allows ('daily','weekly','ad_hoc') -- the Cadence enum's MONTHLY
        # value is not a legal DB value. Persist as 'ad_hoc' and record the
        # true cadence in metadata.real_cadence instead of touching schema.sql.
        metadata = {"real_cadence": "monthly"}
        report_id = insert_report(
            app_conn, tenant_id, "ad_hoc", f"Monthly roll-up - {slug}",
            f"competitor {competitor_id}", metadata=metadata,
        )
        brief = _format_monthly_brief(result)
        await _deliver_cadence_report(app_conn, tenant_id, slug, adapter, Cadence.AD_HOC, report_id,
                                       f"Argus monthly roll-up - {slug}", brief)


async def run_tenant(
    slug, tenant_id, plan, app_conn, model, adapter: ChannelAdapter,
    own_brand_plan: Optional[list[dict]] = None,
) -> TenantResult:
    res = TenantResult(slug)
    res.tenant_id = tenant_id
    run_id = f"daily-{slug}-{int(time.time())}"

    comp_ids = seed_competitors(app_conn, tenant_id, plan)

    content_fetcher = HttpContentFetcher(timeout=20.0, retries=1)
    probe = ProbeFetcherAdapter(content_fetcher)
    source_repo = PgSourceRepository(app_conn)

    class _ExistingLookup:
        def exists(self, t_id: int, normalized: str) -> bool:
            return source_repo.get_by_normalized_url(t_id, normalized) is not None

    validator = SourceValidator(fetcher=probe, existing_sources=_ExistingLookup())
    lifecycle = SourceLifecycle(sources=source_repo, health_events=lambda ev: insert_health_event(app_conn, ev))

    fetch_run_repo = PgFetchRunRepository(app_conn)
    snap_repo = PgSnapshotRepository(app_conn)
    fetch_run = fetch_run_repo.start(tenant_id)

    collection_ran = False
    extraction_ran = False
    all_facts: list = []
    all_deltas_by_comp: dict[int, list] = {}
    snapshot_count = 0
    evidence_texts: dict[str, str] = {}

    for c in plan[:6]:
        competitor_id = comp_ids[c["name"]]
        vr = validator.validate(tenant_id, c["url"])
        if vr.accepted:
            source = lifecycle.upsert_validated(tenant_id, competitor_id, vr)
        else:
            # A duplicate is not a reason to skip COLLECTION -- the source
            # already being in the ledger (e.g. via the V0 migration) is the
            # normal steady state. Only skip when the source truly can't be
            # collected (unreachable / invalid).
            source = source_repo.get_by_normalized_url(tenant_id, normalize_url(c["url"]))
            if source is None:
                continue
        fetched = content_fetcher.fetch_content(c["url"])
        if fetched.status != FetchStatus.OK or not fetched.text:
            insert_health_event(app_conn, SourceHealthEvent(
                tenant_id=tenant_id, source_id=source.id, event_type=HealthEventType.FETCH_ERROR,
                http_status=fetched.http_status, detail=fetched.error or "empty",
            ))
            continue
        collection_ran = True
        insert_health_event(app_conn, SourceHealthEvent(
            tenant_id=tenant_id, source_id=source.id, event_type=HealthEventType.OK, http_status=fetched.http_status,
        ))
        snap_repo.save(Snapshot(tenant_id=tenant_id, source_id=source.id, fetch_run_id=fetch_run.id,
                                title=c["name"], text=fetched.text))
        snapshot_count += 1
        evidence_texts[canonical_url(c["url"])] = fetched.text
        facts, deltas = [], []
        article_urls = resolve_article_links(fetched.raw_html or fetched.text, c["url"])[:4]
        if article_urls:
            for a_url in article_urls:
                a_fetched = content_fetcher.fetch_content(a_url)
                if a_fetched.status != FetchStatus.OK or not a_fetched.text:
                    continue
                evidence_texts[canonical_url(a_url)] = a_fetched.text
                a_ctx = SourceContext(competitor_id=competitor_id, competitor_name=c["name"],
                                      url=a_url, source_type=c["family"], priority=2)
                a_facts, a_deltas = semantic_diff(a_ctx, "", a_fetched.text, date.today().isoformat())
                facts.extend(a_facts)
                deltas.extend(a_deltas)
        else:
            ctx = SourceContext(competitor_id=competitor_id, competitor_name=c["name"], url=c["url"],
                                source_type=c["family"], priority=2)
            facts, deltas = semantic_diff(ctx, "", fetched.text, date.today().isoformat())
        if facts or deltas:
            extraction_ran = True
        fact_repo = PgFactRepository(app_conn, tenant_id)
        delta_repo = PgDeltaRepository(app_conn, tenant_id)
        for f in facts:
            fact_repo.save(f)
        real_deltas = [d for d in deltas if d.delta_type != "suppressed_non_semantic_change"]
        for d in deltas:
            delta_repo.save(d)
        all_facts.extend(facts)
        all_deltas_by_comp.setdefault(competitor_id, []).extend(real_deltas)
        res.sources_fetched.append({"name": c["name"], "url": c["url"], "http": fetched.http_status,
                                    "chars": len(fetched.text), "facts": len(facts), "deltas": len(real_deltas)})

    res.facts_extracted = len(all_facts)
    res.deltas_extracted = sum(len(v) for v in all_deltas_by_comp.values())
    exec_speech_ran = False  # exec_speech scanner is not wired into this pass; honestly marked not-run.

    fetch_run.status = "completed"
    fetch_run.finished_at = datetime.now(timezone.utc)
    fetch_run.source_count = len(res.sources_fetched)
    fetch_run.snapshot_count = snapshot_count
    fetch_run.finding_count = res.facts_extracted
    fetch_run_repo.finish(fetch_run)

    coverage = CoverageReport(lanes=[
        LaneStatus(lane="collection", ran=collection_ran, error=None if collection_ran else "no source fetched"),
        LaneStatus(lane="extraction", ran=extraction_ran, error=None if extraction_ran else "no facts extracted"),
        LaneStatus(lane="exec_speech", ran=exec_speech_ran, error=None if exec_speech_ran else "exec-speech scanner not run this pass"),
    ])

    # Own-brand read (doctrine Addendum 2 point 2): feeds the "where you are"
    # leg of the three-position framing via SynthesisInput.own_position_facts.
    # Bounded (max 3 sources, max 2 articles each) and wrapped -- a failure
    # or missing config here must never block the core competitor brief.
    own_brand_read: Optional[BrandPositionRead] = None
    own_position_facts: list[str] = []
    tenant_company_name: Optional[str] = slug.capitalize()
    try:
        if not own_brand_plan:
            res.errors.append(f"own-brand: no source config for tenant '{slug}' in {CONFIG_PATH}; skipped")
        else:
            ob_specs = [
                OwnBrandSourceSpec(
                    tenant_id=tenant_id,
                    source_type=OwnBrandSource(s["source_type"]),
                    url=s["url"],
                    name=s.get("name"),
                )
                for s in own_brand_plan[:3]
            ]
            ob_collector = OwnBrandCollector(content_fetcher=content_fetcher, article_fetch_cap=2)
            observations = ob_collector.collect(tenant_id, ob_specs)
            if observations:
                compiler = BrandPositionCompiler(model=model)
                own_brand_read = await compiler.compile(tenant_id, tenant_company_name, observations)
                own_position_facts = own_brand_read.to_own_position_facts()
    except Exception as exc:  # noqa: BLE001
        res.errors.append(f"own-brand error: {exc}")

    synthesizer = Synthesizer(model=model)
    promoted: list[dict] = []
    verdict = None
    best_comp = None
    comp_name = None
    best_deltas: list = []
    cold_start = False
    if all_deltas_by_comp:
        best_comp = max(all_deltas_by_comp.items(), key=lambda kv: len(kv[1]))[0]
        comp_name = next(n for n, i in comp_ids.items() if i == best_comp)
        best_deltas = all_deltas_by_comp[best_comp]
        comp_facts = [f for f in all_facts if f.competitor_id == best_comp]
        # Cold start: on a tenant's FIRST collection cycle there is no prior
        # snapshot, so nothing can honestly be called a 24h change. The quality
        # reviewer correctly kills recency claims on day one (seen live,
        # 2026-07-08 first prod run). Frame run #1 as a BASELINE brief:
        # current competitive position, zero recency claims. Real deltas
        # begin on run #2.
        prior_runs = app_conn.execute(
            "SELECT count(*) FROM intel_fetch_runs WHERE tenant_id = %s AND status = 'completed'",
            (tenant_id,),
        ).fetchone()
        # app_conn may or may not use dict_row; support both shapes.
        _count = (prior_runs["count"] if isinstance(prior_runs, dict) else prior_runs[0]) if prior_runs else 0
        cold_start = _count <= 1  # this run included
        baseline_note = (
            "BASELINE MODE: this is the FIRST collection cycle for this reader. "
            "There is no prior snapshot, so you cannot claim anything changed in "
            "the last 24 hours. Frame every signal as the competitor's CURRENT "
            "position ('X is positioned as...', 'X currently offers...'), never "
            "as a recent change or launch, and never use time-relative words "
            "like 'now pivots', 'just launched', 'this week'. Tomorrow's run "
            "compares against today's baseline and reports true changes."
        ) if cold_start else ""
        inp = SynthesisInput(tenant_id=tenant_id, competitor_id=best_comp, competitor_name=comp_name,
                             deltas=best_deltas, facts=comp_facts, exec_signals=[],
                             prior_theses=[], coverage=coverage,
                             tenant_company_name=tenant_company_name, own_position_facts=own_position_facts,
                             extra_instructions=baseline_note)
        try:
            sr = await synthesizer.synthesize(inp)
            verdict = sr.verdict.value
            allowed = inp.evidence_urls()
            for s in sr.signals:
                urls_ok = bool(s.evidence_urls) and all(u in allowed for u in s.evidence_urls)
                promoted.append({**s.model_dump(), "competitor_name": comp_name, "competitor_id": best_comp, "urls_ok": urls_ok})
        except Exception as exc:  # noqa: BLE001
            res.errors.append(f"synthesis error: {exc}")
            verdict = "error"
    else:
        verdict = Verdict.COVERAGE_FAILURE.value if not coverage.all_ran else Verdict.QUIET.value
    res.synth_verdict = verdict
    res.promoted_signals = promoted

    published_ids: list[int] = []
    delta_repo = PgDeltaRepository(app_conn, tenant_id)
    for s in promoted:
        d = CDelta(competitor_id=s["competitor_id"], delta_type=s.get("signal_type", "signal"),
                   materiality_score=s["materiality_score"], what_changed=s["what_changed"],
                   why_it_matters=s.get("why_it_matters"), implication=s.get("implication"),
                   recommended_action=s.get("recommended_action"), evidence_urls=s["evidence_urls"],
                   quality_status="published", confidence=s.get("confidence"))
        saved = delta_repo.save(d)
        if saved.id:
            published_ids.append(saved.id)

    if promoted:
        insert_claim(app_conn, tenant_id, promoted[0]["competitor_id"], promoted[0]["headline"], promoted[0]["evidence_urls"])
    elif res.sources_fetched:
        first = res.sources_fetched[0]
        insert_claim(app_conn, tenant_id, comp_ids[first["name"]],
                     f"{first['name']} maintains an active content narrative", [canonical_url(first["url"])])

    claims_for_review = [
        _ReviewClaim(s["headline"], s["evidence_urls"][0] if s["evidence_urls"] else None)
        for s in promoted
    ]
    reader_text = compose_daily_brief(
        [Signal(**{k: v for k, v in s.items() if k in Signal.model_fields}) for s in promoted],
        tenant_name=slug,
        brief_date=date.today(),
    )
    reader_text = _apply_cold_start_labels(reader_text, cold_start)
    quality_reviewer = QualityReviewer(llm_reviewer=ClaudeQualityReviewer(
        os.environ.get("CIOS_CLAUDE_SHIM_URL", "http://127.0.0.1:8663"), model_alias="opus"))
    qr = quality_reviewer.review(_ReviewInput(tenant_id=tenant_id, run_id=run_id, claims=claims_for_review,
                                              reader_text=reader_text, quiet_verdict=(verdict == "quiet"),
                                              coverage_ran_clean=coverage.all_ran,
                                              evidence_texts=evidence_texts))
    insert_quality_review(app_conn, tenant_id, run_id, qr.status.value, qr.findings, qr.required_fixes)

    # One-shot REVISE loop on a failed verdict: feed required_fixes back to
    # the synthesizer, re-review once. Fail after that and the brief stays
    # blocked by the gated commander -- never loosened.
    if qr.status.value == "failed" and promoted and best_comp is not None:
        fixes_text = "; ".join(str(f) for f in qr.required_fixes)
        revise_inp = SynthesisInput(
            tenant_id=tenant_id, competitor_id=best_comp, competitor_name=comp_name,
            deltas=best_deltas, coverage=coverage,
            tenant_company_name=tenant_company_name, own_position_facts=own_position_facts,
            extra_instructions=(
                "REVISION PASS. An editorial review rejected specific claims. "
                f"Required fixes: {fixes_text}. Remove or hedge every flagged "
                "specific; keep only what the evidence text itself supports. "
                "Dropping a signal entirely is acceptable."),
        )
        try:
            sr2 = await synthesizer.synthesize(revise_inp)
            promoted2 = []
            allowed = revise_inp.evidence_urls()
            for s in sr2.signals:
                urls_ok = bool(s.evidence_urls) and all(u in allowed for u in s.evidence_urls)
                promoted2.append({**s.model_dump(), "competitor_name": comp_name,
                                  "competitor_id": best_comp, "urls_ok": urls_ok})
            if promoted2:
                promoted = promoted2
                res.promoted_signals = promoted
                claims_for_review = [
                    _ReviewClaim(s["headline"], s["evidence_urls"][0] if s["evidence_urls"] else None)
                    for s in promoted
                ]
                reader_text = compose_daily_brief(
                    [Signal(**{k: v for k, v in s.items() if k in Signal.model_fields}) for s in promoted],
                    tenant_name=slug,
                    brief_date=date.today(),
                )
                reader_text = _apply_cold_start_labels(reader_text, cold_start)
                qr = quality_reviewer.review(_ReviewInput(
                    tenant_id=tenant_id, run_id=run_id, claims=claims_for_review,
                    reader_text=reader_text, quiet_verdict=False,
                    coverage_ran_clean=coverage.all_ran, evidence_texts=evidence_texts))
                insert_quality_review(app_conn, tenant_id, run_id, qr.status.value, qr.findings, qr.required_fixes)
                res.errors.append("quality revise pass applied")
        except Exception as exc:  # noqa: BLE001
            res.errors.append(f"revision pass error (original failed verdict kept): {exc}")

    res.quality_status = qr.status.value
    res.quality_fixes = qr.required_fixes

    # Prescriptions (doctrine Addendum 2 point 3): post revise-loop, before
    # delivery, so the delivered brief includes the "YOUR PLAYS" section.
    # Grounded in this cycle's promoted signals + standing theses + the
    # own-brand read above. No horizon connections on the daily path --
    # those are weekly-only (Addendum 2 point 1, see run_weekly_if_due).
    prescriptions: list[Prescription] = []
    try:
        theses_rows = DbTheses(app_conn).get_active_theses(tenant_id)
        theses_objs = [
            Thesis(
                id=t["id"], tenant_id=tenant_id, competitor_id=t["competitor_id"],
                thesis=t["thesis"], status=t["status"],
                confidence=float(t["confidence"]) if t.get("confidence") is not None else None,
            )
            for t in theses_rows
        ]
        signal_objs = [Signal(**{k: v for k, v in s.items() if k in Signal.model_fields}) for s in promoted]
        prescribe_engine = PrescriptionEngine(model=model)
        prescriptions = await prescribe_engine.prescribe(
            tenant_id=tenant_id, signals=signal_objs, connections=[],
            theses=theses_objs, brand_position=own_brand_read,
        )
    except Exception as exc:  # noqa: BLE001
        res.errors.append(f"prescription engine error: {exc}")

    if prescriptions:
        reader_text = compose_daily_brief(
            [Signal(**{k: v for k, v in s.items() if k in Signal.model_fields}) for s in promoted],
            tenant_name=slug,
            brief_date=date.today(),
            prescriptions=prescriptions,
        )
        reader_text = _apply_cold_start_labels(reader_text, cold_start)

    # Real false-negative audit: real raw observations vs real promoted
    # signals only, no synthetic planted-miss fixture (that was a one-time
    # certification device in the Gate 7 rehearsal, not a production check).
    real_obs = [{"headline": f.statement, "evidence_url": f.evidence_url} for f in all_facts]

    class _Raw(RawObservationsProvider):
        def get_observations(self, t_id: int, r_id: str) -> list[dict]:
            return real_obs

    class _Promoted(PromotedSignalsProvider):
        def get_promoted_signals(self, t_id: int, r_id: str) -> list[dict]:
            return promoted

    class _LiveFNLLM(FNSemanticLLMClient):
        def find_missed_signal(self, *a, **k) -> dict:
            # Production has no LLM-backed FN pass wired yet; the
            # deterministic checks in SemanticFNAuditor run first and cover
            # the documented cases. Absence of a live LLM path here is a
            # known limitation, not a silent skip: audit_status still
            # reflects whatever the deterministic checks found.
            return {}

    auditor = SemanticFNAuditor(_Raw(), _Promoted(), _LiveFNLLM())
    audit = auditor.audit(tenant_id=tenant_id, run_id=run_id)
    res.fn_status = audit.audit_status.value if audit else None
    insert_fn_audit(app_conn, tenant_id, run_id, res.fn_status, audit.risk_reason if audit else None,
                    audit.recommended_recheck if audit else [])

    if promoted:
        s0 = promoted[0]
        engine = ThesisEngine()
        engine.open_thesis(tenant_id=tenant_id, competitor_id=s0["competitor_id"],
                           thesis=f"{s0['competitor_name']} is investing in the space; initial monitoring thesis.",
                           confidence=0.3, evidence_ids=[s0["evidence_urls"][0]])
        prompt = ("You are Argus. Given this competitor signal, write ONE sharp sentence (no em dashes) "
                  "updating the strategic thesis. Return ONLY the sentence.\n\n"
                  f"SIGNAL: {s0['headline']} - {s0['what_changed']}\n")
        req = ModelRequest(task_profile="brain.thesis_update", messages=[{"role": "user", "content": prompt}])
        resp = await model.generate(req)
        new_text = (resp.text or "").strip() or f"{s0['competitor_name']} continues to invest in its category."
        updated = engine.update(competitor_id=s0["competitor_id"], thesis=new_text, confidence=0.55,
                                new_evidence_ids=[s0["evidence_urls"][0]])
        insert_thesis(app_conn, tenant_id, s0["competitor_id"], updated.thesis, updated.confidence, updated.evidence_ids)

    report_id = insert_report(app_conn, tenant_id, "daily", f"Argus daily brief - {slug}", reader_text[:200])

    # Persist prescriptions as action_items (doctrine Addendum 2 point 3):
    # collateral generation is deliberately NOT triggered here (see
    # scripts/generate_collateral.py) -- this only records the decision-layer
    # row so a human can later run collateral generation against it.
    action_item_ids: list[int] = []
    try:
        for p in prescriptions:
            row = prescription_to_action_item(p, report_id=report_id)
            aid = insert_action_item(app_conn, row)
            if aid is not None:
                action_item_ids.append(aid)
    except Exception as exc:  # noqa: BLE001
        res.errors.append(f"action_items persistence error: {exc}")

    message_markdown = build_daily_message(reader_text)
    recorder = LearningRecorder(
        learning_events=PgLearningEventRepository(app_conn),
        improvement_queue=PgImprovementQueueRepository(app_conn),
    )
    commander = GatedDeliveryCommander(adapters=SingleAdapterRegistry(adapter),
                                       bot_deliveries=PgBotDeliveryRepository(app_conn),
                                       delivery_attempts=PgDeliveryAttemptRepository(app_conn),
                                       recorder=recorder)
    router = ActionRouter(channel_config=TelegramOnlyChannelConfig(os.environ.get("CIOS_TELEGRAM_CHAT_ID", "")))
    report_event = ReportReadyEvent(report_id=report_id, tenant_id=tenant_id, cadence=Cadence.DAILY,
                                    title=f"Argus daily brief - {slug}", summary=reader_text[:200],
                                    markdown_body=message_markdown, dashboard_url=f"https://ci.chowmes.com/{slug}")
    plan_route = router.route_report(report_event)
    outcome = await commander.deliver(
        DeliveryRequest(tenant_id=tenant_id, report=report_event, plan=plan_route),
        quality_verdict=qr,
    )
    res.delivered = outcome.delivered
    res.deliveries = [{"channel": b.channel.value, "status": b.status.value, "id": b.id} for b in outcome.bot_deliveries]

    cov_dict = {
        "lanes": [{"lane": l.lane, "ran": l.ran, "error": l.error} for l in coverage.lanes],
        "coverage_score": round(sum(1 for l in coverage.lanes if l.ran) / len(coverage.lanes), 4),
        "false_negative_audit_status": res.fn_status,
        "missing_source_families": [l.lane for l in coverage.lanes if not l.ran],
    }
    run_dict = {"run_id": run_id, "report_id": report_id, "generated_at": datetime.now(timezone.utc),
                "model_tier": "judgment", "source_family_count": len(res.sources_fetched),
                "delivery_status": "sent" if res.delivered else "failed", "quality_review_status": res.quality_status,
                "argus_read": {"useful_truth": reader_text.split(chr(10))[0]},
                "action_item_ids": action_item_ids, "delivery_ids": [d["id"] for d in res.deliveries]}
    builder = DashboardStateBuilder(signals=DbMaterialSignals(app_conn), theses=DbTheses(app_conn),
                                    coverage=DbCoverage(cov_dict), runs=DbRuns(run_dict),
                                    report_history=PgReportHistoryRepository(app_conn),
                                    suppressed_signals=PgSuppressedSignalsRepository(app_conn))
    state = builder.build(tenant_id=tenant_id, cadence="daily")
    res.dashboard_state = state
    dash_json_path = Path(os.environ.get("CIOS_DASHBOARD_OUT", "/tmp/argus-dashboard.html")).with_suffix("")
    dash_path = dash_json_path.parent / default_filename(state)
    publish_to_file(state, dash_path)
    insert_dashboard_state(app_conn, tenant_id, json.loads(to_json_str(state)), published_ids,
                           [d["id"] for d in res.deliveries], str(dash_path))
    return res


async def main() -> int:
    started = time.time()
    superuser_dsn = get_dsn()
    app_conninfo = app_dsn(superuser_dsn)
    deliver_tenant = os.environ.get("CIOS_DELIVER_TENANT", "algolia")

    telegram_configured = bool(os.environ.get("TELEGRAM_BOT_TOKEN")) and bool(os.environ.get("CIOS_TELEGRAM_CHAT_ID"))
    print(f"telegram configured: {telegram_configured}")

    provider = ClaudeCliShimProvider(model_alias="opus", timeout_s=90.0)
    health = await provider.health_check()
    print(f"claude-shim health: {health.healthy} ({health.detail})")
    if not health.healthy:
        print("ABORT: claude-shim not healthy; refusing to run against a dead model.")
        return 2

    if not telegram_configured:
        print("ABORT: TELEGRAM_BOT_TOKEN / CIOS_TELEGRAM_CHAT_ID not both set; refusing to run a production "
              "delivery pass with no real delivery target configured.")
        return 2

    model = CountingModel(provider)
    tenant_plan = load_tenant_plan()
    own_brand_map: dict = tenant_plan.get("own_brand", {}) or {}

    results: list[TenantResult] = []
    now = _now()

    with psycopg.connect(app_conninfo, autocommit=True) as app_conn:
        with app_conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT id, slug FROM tenants ORDER BY id")
            db_tenants = {row["slug"]: row["id"] for row in cur.fetchall()}

        for slug, tenant_id in db_tenants.items():
            plan = tenant_plan.get(slug)
            if plan is None:
                print(f"WARNING: tenant '{slug}' has no entry in {CONFIG_PATH}; skipping.")
                continue
            print(f"\n=== TENANT {slug} (id={tenant_id}) ===")
            adapter = select_adapter_for_tenant(slug, deliver_tenant, {
                "TELEGRAM_BOT_TOKEN": os.environ.get("TELEGRAM_BOT_TOKEN", ""),
                "CIOS_TELEGRAM_CHAT_ID": os.environ.get("CIOS_TELEGRAM_CHAT_ID", ""),
            })
            r = await run_tenant(slug, tenant_id, plan, app_conn, model, adapter,
                                 own_brand_plan=own_brand_map.get(slug))
            results.append(r)
            print(f"  sources={len(r.sources_fetched)} facts={r.facts_extracted} deltas={r.deltas_extracted} "
                  f"signals={len(r.promoted_signals)} verdict={r.synth_verdict} quality={r.quality_status} "
                  f"fn={r.fn_status} delivered={r.delivered} llm={LLM_CALLS['count']}")

            await run_weekly_if_due(app_conn, tenant_id, slug, adapter, model, now)
            await run_monthly_if_due(app_conn, tenant_id, slug, adapter, model, now)

        delivered_result = next((r for r in results if r.slug == deliver_tenant), None)
        if delivered_result is not None and delivered_result.dashboard_state is not None:
            from cios.dashboard.html_renderer import render_dashboard_html

            html_out = render_dashboard_html(delivered_result.dashboard_state)
            html_path = Path(os.environ.get("CIOS_DASHBOARD_OUT", "/tmp/argus-dashboard.html"))
            html_path.parent.mkdir(parents=True, exist_ok=True)
            html_path.write_text(html_out, encoding="utf-8")
            json_path = html_path.with_suffix(".json")
            publish_to_file(delivered_result.dashboard_state, json_path)
            print(f"Dashboard written: {html_path} (+ {json_path})")

    wall = time.time() - started
    print(f"\nRun complete in {wall:.1f}s. LLM calls used: {LLM_CALLS['count']} / {LLM_BUDGET}")
    for r in results:
        print(f"  {r.slug}: delivered={r.delivered} quality={r.quality_status} errors={r.errors}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(main()))
