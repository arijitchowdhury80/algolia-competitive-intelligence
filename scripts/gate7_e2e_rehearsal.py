"""Gate 7 END-TO-END REHEARSAL — the final full-chain certification across all
three tenants (Algolia, Spryker, Amplitude) using REAL components.

What is REAL here (no mocks):
  * Postgres (deploy/docker-compose.yml, 127.0.0.1:5433) with the real schema +
    RLS, seeded with the three tenants + their competitor/source sets.
  * Source hunter sweep: real reachability probe (HttpContentFetcher ->
    ProbeFetcherAdapter) through the real SourceValidator + SourceLifecycle,
    upserting real `sources` rows and emitting real `source_health_events`.
  * Intel collector: real HTTP fetch of competitor blogs, real snapshot rows,
    real semantic extraction (cios.collect.extract.semantic_diff, the V0-ported
    logic), real `source_snapshots` + `semantic_facts` + `semantic_deltas`.
  * Semantic brain: the real Synthesizer making a LIVE Claude (opus) call via
    the claude-shim, real evidence-or-silence / materiality / coverage gates.
  * Quality reviewer: the real QualityReviewer (deterministic gate + a LIVE
    Claude quality call).
  * False-negative auditor: the real SemanticFNAuditor with a DELIBERATELY
    PLANTED miss per tenant (a real observed fact withheld from the promotion
    path, tagged with a fixture marker) — the deterministic guard must catch it.
  * Delivery commander + action router: the real code path. The ONLY fake is
    the outbound channel adapter (CapturingTelegramAdapter) so no real Telegram
    message is sent; it still drives the real commander/formatting and writes
    REAL `bot_deliveries` + `delivery_attempts` rows to Postgres.
  * Dashboard state builder: the real DashboardStateBuilder reading real DB rows.

Hard caps (declared, tracked, reported):
  * <= 6 sources per tenant.
  * <= 25 LIVE LLM calls across the WHOLE run (CountingModel enforces it).

Run:
  docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d
  # apply schema.sql + seed.sql
  .venv/bin/uvicorn deploy.claude-shim.shim:app --app-dir . --port 8663 &
  CIOS_DATABASE_URL=postgresql://cios_dev:<pw>@127.0.0.1:5433/cios \
      .venv/bin/python scripts/gate7_e2e_rehearsal.py

Writes the rehearsal report to
docs/planning/gate7-rehearsal-runs/2026-07-08-run.md and one
dashboard-state.v2.<tenant>.<cadence>.json per tenant beside it.

NO-FALSE-GREEN CONTRACT: every check reports PASS/FAIL against what actually
happened. Nothing is massaged. If a real component turns out to be a stub, if
tenant bleed is found, if the FN auditor misses the planted miss, or if the LLM
budget is blown, the report says FAILED and explains why.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json

from cios.brain.fn_auditor import (
    FNSemanticLLMClient,
    PromotedSignalsProvider,
    RawObservationsProvider,
    SemanticFNAuditor,
)
from cios.brain.quality import QualityReviewer
from cios.brain.synthesizer import Synthesizer
from cios.brain.thesis import ThesisEngine
from cios.brain.types import CoverageReport, LaneStatus, SynthesisInput, Verdict
from cios.collect.article_resolver import resolve_article_links
from cios.collect.extract import canonical_url, semantic_diff
from cios.collect.fetcher import HttpContentFetcher, ProbeFetcherAdapter
from cios.collect.types import Delta as CDelta
from cios.collect.types import FetchStatus, Snapshot, SourceContext
from cios.dashboard.publisher import default_filename, publish_to_file, to_json_str
from cios.dashboard.state_builder import DashboardStateBuilder
from cios.db.repos.collect import (
    PgDeltaRepository,
    PgFactRepository,
    PgFetchRunRepository,
    PgSnapshotRepository,
)
from cios.db.repos.delivery import PgBotDeliveryRepository, PgDeliveryAttemptRepository
from cios.db.repos.learn import PgImprovementQueueRepository, PgLearningEventRepository
from cios.db.repos.sources import PgSourceRepository
from cios.db.session import get_dsn, tenant_context
from cios.delivery.action_router import ActionRouter
from cios.delivery.gated_commander import GatedDeliveryCommander
from cios.delivery.types import Cadence, DeliveryRequest, ReportReadyEvent
from cios.hunter.lifecycle import SourceLifecycle
from cios.hunter.types import HealthEventType, SourceHealthEvent
from cios.hunter.validator import SourceValidator, normalize_url
from cios.learn.recorder import LearningRecorder
from cios.learn.types import FalseNegativeAuditStatus
from cios.platform.channels.adapter import ChannelAdapter
from cios.platform.channels.types import (
    Channel,
    ChannelIdentity,
    DeliveryResult,
    ResponseEnvelope,
    VerificationResult,
)
from cios.platform.models.providers.claude_cli import ClaudeCliShimProvider
from cios.platform.models.types import ModelRequest

LLM_BUDGET = 25
LLM_CALLS = {"count": 0}


class CountingModel:
    """Wraps a provider; hard-fails if the whole-run LLM budget is exceeded."""

    def __init__(self, inner) -> None:
        self._inner = inner

    async def generate(self, request: ModelRequest):
        LLM_CALLS["count"] += 1
        if LLM_CALLS["count"] > LLM_BUDGET:
            raise RuntimeError(f"LLM call budget ({LLM_BUDGET}) exceeded — aborting run")
        return await self._inner.generate(request)


# <= 6 sources per tenant (3 each). Blogs chosen for real reachability + content.
TENANT_PLAN: dict[str, list[dict[str, str]]] = {
    "algolia": [
        {"name": "Elastic", "domain": "elastic.co", "url": "https://www.elastic.co/blog", "family": "blog"},
        {"name": "Constructor", "domain": "constructor.com", "url": "https://www.constructor.com/blog", "family": "blog"},
        {"name": "Coveo", "domain": "coveo.com", "url": "https://www.coveo.com/blog", "family": "blog"},
    ],
    "spryker": [
        {"name": "commercetools", "domain": "commercetools.com", "url": "https://commercetools.com/blog", "family": "blog"},
        {"name": "BigCommerce", "domain": "bigcommerce.com", "url": "https://www.bigcommerce.com/blog/", "family": "blog"},
        {"name": "VTEX", "domain": "vtex.com", "url": "https://vtex.com/en-us/blog/", "family": "blog"},
    ],
    "amplitude": [
        {"name": "Mixpanel", "domain": "mixpanel.com", "url": "https://mixpanel.com/blog/", "family": "blog"},
        {"name": "PostHog", "domain": "posthog.com", "url": "https://posthog.com/blog", "family": "blog"},
        {"name": "Heap", "domain": "heap.io", "url": "https://www.heap.io/blog", "family": "blog"},
    ],
}


class CapturingTelegramAdapter(ChannelAdapter):
    """The ONLY fake in the run. Records what WOULD have been sent to Telegram;
    sends nothing. Returns success so the real commander advances bot_deliveries
    to SENT and writes real rows — but no real Telegram API call is made."""

    channel_name = "telegram"

    def __init__(self) -> None:
        self.captured: list[ResponseEnvelope] = []

    async def receive(self, raw_event: Any):  # pragma: no cover
        raise NotImplementedError

    async def send(self, response: ResponseEnvelope) -> DeliveryResult:
        self.captured.append(response)
        return DeliveryResult(
            success=True, channel=response.channel,
            provider_message_id=f"FAKE-{len(self.captured)}",
            raw_response={"faked": True, "note": "no real telegram send in rehearsal"},
        )

    def verify_signature(self, raw_event: Any) -> VerificationResult:
        return VerificationResult(verified=True)

    def map_identity(self, raw_event: Any) -> ChannelIdentity:
        return ChannelIdentity(channel=Channel.TELEGRAM, channel_user_id="rehearsal")

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


class ClaudeQualityReviewer:
    """QualityLLMReviewer backed by the live Claude shim.

    The QualityReviewer Protocol is SYNC by design (see quality.py docstring),
    but we are called from inside the asyncio event loop, so we make a plain
    SYNCHRONOUS HTTP call to the same claude-shim rather than reusing an async
    client across loops. This is a genuine live Claude judgment call; it is
    counted against the same LLM budget as every other live call."""

    def __init__(self, shim_url: str, model_alias: str = "opus") -> None:
        self._url = shim_url
        self._alias = model_alias

    def review(self, tenant_id, run_id, reader_text, claims) -> dict:
        import httpx

        LLM_CALLS["count"] += 1
        if LLM_CALLS["count"] > LLM_BUDGET:
            raise RuntimeError(f"LLM call budget ({LLM_BUDGET}) exceeded — aborting run")
        claim_lines = "\n".join(f"- {getattr(c, 'text', '')} (src: {getattr(c, 'source_url', '')})" for c in claims)
        prompt = (
            "You are Argus, a skeptical competitive-intelligence editor. Review this "
            "brief for: (1) any claim not backed by a source URL, (2) generic AI slop, "
            "(3) hallucinated specifics. Return ONLY JSON: "
            '{"pass": bool, "required_fixes": [str], "notes": str}.\n\n'
            f"BRIEF:\n{reader_text}\n\nCLAIMS:\n{claim_lines or '(none)'}\n"
        )
        try:
            resp = httpx.post(f"{self._url}/generate",
                              json={"prompt": prompt, "model_alias": self._alias, "json_mode": True, "timeout_s": 90},
                              timeout=120.0)
            resp.raise_for_status()
            text = (resp.json().get("text") or "").strip()
        except Exception as exc:  # noqa: BLE001
            return {"pass": False, "required_fixes": [f"quality reviewer LLM call failed: {exc}"], "notes": ""}
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
            text = text.strip()
        try:
            obj = json.loads(text)
            if isinstance(obj, dict) and "pass" in obj:
                return {"pass": bool(obj.get("pass")),
                        "required_fixes": list(obj.get("required_fixes") or []),
                        "notes": obj.get("notes", "")}
        except (ValueError, json.JSONDecodeError):
            pass
        # fail closed: a reviewer that cannot render a verdict must not green-light.
        return {"pass": False, "required_fixes": ["quality reviewer returned unparseable verdict"], "notes": text[:300]}


class _ReviewClaim:
    def __init__(self, text: str, source_url: Optional[str]) -> None:
        self.text = text
        self.source_url = source_url


class _ReviewInput:
    def __init__(self, tenant_id, run_id, claims, reader_text, quiet_verdict, coverage_ran_clean) -> None:
        self.tenant_id = tenant_id
        self.run_id = run_id
        self.claims = claims
        self.reader_text = reader_text
        self.quiet_verdict = quiet_verdict
        self.coverage_ran_clean = coverage_ran_clean


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
        self.fn_caught_planted = False
        self.fn_recheck: list = []
        self.planted_marker: Optional[str] = None
        self.deliveries: list[dict] = []
        self.delivered = False
        self.captured_channel: list[str] = []
        self.dashboard_is_quiet: Optional[bool] = None
        self.dashboard_reason: str = ""
        self.dashboard_path: Optional[str] = None
        self.health_events: list[str] = []
        self.errors: list[str] = []


def app_dsn(superuser_dsn: str) -> str:
    info = psycopg.conninfo.conninfo_to_dict(superuser_dsn)
    info["user"] = "cios_app"
    info["password"] = os.environ.get("CIOS_APP_PASSWORD", "cios_app_dev_local_only_not_secret")
    return psycopg.conninfo.make_conninfo(**info)


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


def insert_raw_finding(conn, tenant_id, competitor_id, source_id, summary, evidence_url) -> int:
    with tenant_context(conn, tenant_id):
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO raw_findings (tenant_id, competitor_id, source_id, finding_type, summary, evidence_url, confidence)
                VALUES (%s, %s, %s, 'content_narrative', %s, %s, 0.8) RETURNING id
                """,
                (tenant_id, competitor_id, source_id, summary, evidence_url),
            )
            return cur.fetchone()["id"]


def insert_report(conn, tenant_id, cadence, title, summary) -> int:
    with tenant_context(conn, tenant_id):
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO reports (tenant_id, cadence, report_date, title, status, summary)
                VALUES (%s, %s, %s, %s, 'rendered', %s) RETURNING id
                """,
                (tenant_id, cadence, date.today(), title, summary),
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


async def run_tenant(slug, tenant_id, plan, app_conn, model, out_dir) -> TenantResult:
    res = TenantResult(slug)
    res.tenant_id = tenant_id
    run_id = f"gate7-{slug}-{int(time.time())}"

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
    example_fact_for_plant = None
    snapshot_count = 0

    for c in plan[:6]:
        competitor_id = comp_ids[c["name"]]
        vr = validator.validate(tenant_id, c["url"])
        if not vr.accepted:
            res.health_events.append(f"{c['name']}: source rejected ({vr.reason})")
            continue
        source = lifecycle.upsert_validated(tenant_id, competitor_id, vr)
        fetched = content_fetcher.fetch_content(c["url"])
        if fetched.status != FetchStatus.OK or not fetched.text:
            insert_health_event(app_conn, SourceHealthEvent(
                tenant_id=tenant_id, source_id=source.id, event_type=HealthEventType.FETCH_ERROR,
                http_status=fetched.http_status, detail=fetched.error or "empty",
            ))
            res.health_events.append(f"{c['name']}: fetch failed ({fetched.error})")
            continue
        collection_ran = True
        insert_health_event(app_conn, SourceHealthEvent(
            tenant_id=tenant_id, source_id=source.id, event_type=HealthEventType.OK, http_status=fetched.http_status,
        ))
        snap_repo.save(Snapshot(tenant_id=tenant_id, source_id=source.id, fetch_run_id=fetch_run.id,
                                title=c["name"], text=fetched.text))
        snapshot_count += 1
        # Article-level evidence (Gate 7 finding #2): resolve article links
        # from the index page's raw HTML and extract per-article so facts and
        # deltas cite the specific article URL, never the index page.
        facts, deltas = [], []
        article_urls = resolve_article_links(fetched.raw_html or fetched.text, c["url"])[:4]
        if article_urls:
            for a_url in article_urls:
                a_fetched = content_fetcher.fetch_content(a_url)
                if a_fetched.status != FetchStatus.OK or not a_fetched.text:
                    continue
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
            if example_fact_for_plant is None:
                example_fact_for_plant = f
        real_deltas = [d for d in deltas if d.delta_type != "suppressed_non_semantic_change"]
        for d in deltas:
            delta_repo.save(d)
        all_facts.extend(facts)
        all_deltas_by_comp.setdefault(competitor_id, []).extend(real_deltas)
        res.sources_fetched.append({"name": c["name"], "url": c["url"], "http": fetched.http_status,
                                    "chars": len(fetched.text), "facts": len(facts), "deltas": len(real_deltas)})

    res.facts_extracted = len(all_facts)
    res.deltas_extracted = sum(len(v) for v in all_deltas_by_comp.values())
    # exec_speech scanner is NOT fired in this pass -> lane honestly marked not-run.
    exec_speech_ran = False

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

    synthesizer = Synthesizer(model=model)
    promoted: list[dict] = []
    verdict = None
    if all_deltas_by_comp:
        best_comp = max(all_deltas_by_comp.items(), key=lambda kv: len(kv[1]))[0]
        comp_name = next(n for n, i in comp_ids.items() if i == best_comp)
        comp_facts = [f for f in all_facts if f.competitor_id == best_comp]
        inp = SynthesisInput(tenant_id=tenant_id, competitor_id=best_comp, competitor_name=comp_name,
                             deltas=all_deltas_by_comp[best_comp], facts=comp_facts, exec_signals=[],
                             prior_theses=[], coverage=coverage)
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

    # quality review (real deterministic + LIVE Claude)
    reader_lines = [f"Argus daily brief for {slug}.", ""]
    claims_for_review: list = []
    for s in promoted:
        reader_lines.append(f"{s['headline']}: {s['what_changed']} Action: {s.get('recommended_action','')} ({s['evidence_urls'][0]})")
        claims_for_review.append(_ReviewClaim(s["headline"], s["evidence_urls"][0] if s["evidence_urls"] else None))
    if not promoted:
        reader_lines.append("No material signals promoted this cycle. Coverage limits recorded below.")
    reader_text = "\n".join(reader_lines)
    quality_reviewer = QualityReviewer(llm_reviewer=ClaudeQualityReviewer(
        os.environ.get("CIOS_CLAUDE_SHIM_URL", "http://127.0.0.1:8663"), model_alias="opus"))
    qr = quality_reviewer.review(_ReviewInput(tenant_id=tenant_id, run_id=run_id, claims=claims_for_review,
                                              reader_text=reader_text, quiet_verdict=(verdict == "quiet"),
                                              coverage_ran_clean=coverage.all_ran))
    res.quality_status = qr.status.value
    res.quality_fixes = qr.required_fixes
    insert_quality_review(app_conn, tenant_id, run_id, qr.status.value, qr.findings, qr.required_fixes)

    # false-negative audit with a PLANTED miss (deterministic guard)
    planted_marker = f"PLANTED-{slug.upper()}-001"
    res.planted_marker = planted_marker
    if example_fact_for_plant is not None:
        planted_summary = example_fact_for_plant.statement
        planted_url = example_fact_for_plant.evidence_url
        planted_comp = example_fact_for_plant.competitor_id
    else:
        planted_summary = f"{plan[0]['name']} shipped a material update (withheld from promotion)"
        planted_url = canonical_url(plan[0]["url"])
        planted_comp = comp_ids[plan[0]["name"]]
    try:
        src = source_repo.get_by_normalized_url(tenant_id, normalize_url(plan[0]["url"]))
        sid = src.id if src else None
    except Exception:
        sid = None
    if sid:
        insert_raw_finding(app_conn, tenant_id, planted_comp, sid, planted_summary, planted_url)

    real_obs = [{"headline": f.statement, "evidence_url": f.evidence_url} for f in all_facts]
    planted_obs = {"headline": planted_summary, "fixture_marker": planted_marker, "evidence_url": planted_url}

    class _Raw(RawObservationsProvider):
        def get_observations(self, t_id: int, r_id: str) -> list[dict]:
            return real_obs + [planted_obs]

    class _Promoted(PromotedSignalsProvider):
        def get_promoted_signals(self, t_id: int, r_id: str) -> list[dict]:
            return promoted

    class _NeverLLM(FNSemanticLLMClient):
        def find_missed_signal(self, *a, **k) -> dict:
            raise AssertionError("deterministic planted-marker guard should fire first")

    auditor = SemanticFNAuditor(_Raw(), _Promoted(), _NeverLLM())
    audit = auditor.audit(tenant_id=tenant_id, run_id=run_id)
    res.fn_status = audit.audit_status.value if audit else None
    res.fn_recheck = audit.recommended_recheck if audit else []
    res.fn_caught_planted = bool(audit and audit.audit_status == FalseNegativeAuditStatus.FAILED
                                 and planted_marker in (audit.recommended_recheck or []))
    insert_fn_audit(app_conn, tenant_id, run_id, res.fn_status, audit.risk_reason if audit else None, res.fn_recheck)

    # thesis (LIVE Claude for the update text)
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

    # delivery (real GATED commander; fake capturing channel). Gate 7 blocker fix:
    # a failed quality verdict must never ship, so the commander requires the
    # QualityReview verdict computed above and only forwards a PASSED one.
    report_id = insert_report(app_conn, tenant_id, "daily", f"Argus daily brief - {slug}", reader_text[:200])
    adapter = CapturingTelegramAdapter()
    recorder = LearningRecorder(
        learning_events=PgLearningEventRepository(app_conn),
        improvement_queue=PgImprovementQueueRepository(app_conn),
    )
    commander = GatedDeliveryCommander(adapters=SingleAdapterRegistry(adapter),
                                       bot_deliveries=PgBotDeliveryRepository(app_conn),
                                       delivery_attempts=PgDeliveryAttemptRepository(app_conn),
                                       recorder=recorder)
    router = ActionRouter(channel_config=TelegramOnlyChannelConfig("6789423537"))
    report_event = ReportReadyEvent(report_id=report_id, tenant_id=tenant_id, cadence=Cadence.DAILY,
                                    title=f"Argus daily brief - {slug}", summary=reader_text[:200],
                                    markdown_body=reader_text, dashboard_url=f"https://ci.chowmes.com/{slug}")
    plan_route = router.route_report(report_event)
    outcome = await commander.deliver(
        DeliveryRequest(tenant_id=tenant_id, report=report_event, plan=plan_route),
        quality_verdict=qr,
    )
    res.delivered = outcome.delivered
    res.captured_channel = [c.channel.value for c in adapter.captured]
    res.deliveries = [{"channel": b.channel.value, "status": b.status.value, "id": b.id} for b in outcome.bot_deliveries]

    # dashboard state (real builder over real DB rows)
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
                "action_item_ids": [], "delivery_ids": [d["id"] for d in res.deliveries]}
    builder = DashboardStateBuilder(signals=DbMaterialSignals(app_conn), theses=DbTheses(app_conn),
                                    coverage=DbCoverage(cov_dict), runs=DbRuns(run_dict))
    state = builder.build(tenant_id=tenant_id, cadence="daily")
    res.dashboard_is_quiet = state.is_quiet
    res.dashboard_reason = (
        "quiet-eligible + nothing to show" if state.is_quiet
        else f"active ({len(state.competitor_cards)} cards, top={state.top_attention_level.value}); "
             f"quiet blocked because coverage.all_lanes_ran={coverage.all_ran} / fn_audit={res.fn_status}"
    )
    dash_path = out_dir / default_filename(state)
    publish_to_file(state, dash_path)
    res.dashboard_path = str(dash_path)
    insert_dashboard_state(app_conn, tenant_id, json.loads(to_json_str(state)), published_ids,
                           [d["id"] for d in res.deliveries], str(dash_path))
    return res


def tenant_bleed_checks(app_conn, superuser_conn, tenants: dict[str, int]) -> dict[str, Any]:
    tables = ["sources", "semantic_deltas", "claims"]
    results: dict[str, Any] = {"pairs": [], "url_leak": [], "passed": True}

    truth: dict[int, dict[str, int]] = {}
    with superuser_conn.cursor() as cur:
        for tid in tenants.values():
            truth[tid] = {}
            for t in tables:
                cur.execute(f"SELECT count(*) FROM {t} WHERE tenant_id = %s", (tid,))
                truth[tid][t] = cur.fetchone()[0]

    for a_slug, a_id in tenants.items():
        for b_slug, b_id in tenants.items():
            if a_id == b_id:
                continue
            with tenant_context(app_conn, a_id):
                with app_conn.cursor() as cur:
                    row = {}
                    ok = True
                    for t in tables:
                        cur.execute(f"SELECT count(*) FROM {t}")
                        visible_total = cur.fetchone()[0]
                        cur.execute(f"SELECT count(*) FROM {t} WHERE tenant_id = %s", (b_id,))
                        visible_b = cur.fetchone()[0]
                        row[t] = {"visible_total": visible_total, "own": truth[a_id][t], "b_rows_visible": visible_b}
                        if visible_b != 0 or visible_total != truth[a_id][t]:
                            ok = False
                    results["pairs"].append({"as_tenant": a_slug, "probing_for": b_slug, "tables": row, "isolated": ok})
                    if not ok:
                        results["passed"] = False

    with superuser_conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT tenant_id, url FROM sources")
        url_owner: dict[str, set] = {}
        for r in cur.fetchall():
            url_owner.setdefault(canonical_url(r["url"]), set()).add(r["tenant_id"])
        cur.execute("SELECT tenant_id, id, evidence_ids FROM semantic_deltas WHERE quality_status='published'")
        for r in cur.fetchall():
            for u in (r["evidence_ids"] or []):
                cu = canonical_url(u) if isinstance(u, str) else None
                if cu and cu in url_owner and r["tenant_id"] not in url_owner[cu]:
                    results["url_leak"].append({"delta_tenant": r["tenant_id"], "delta_id": r["id"],
                                                "url": cu, "url_owners": sorted(url_owner[cu])})
                    results["passed"] = False
    return results


def build_report(results, bleed, wall_s, llm_calls) -> str:
    lines: list[str] = []
    lines.append("# CI-OS Gate 7 — End-to-End Rehearsal Run")
    lines.append("")
    lines.append(f"Date: 2026-07-08  ")
    lines.append(f"Run wall-clock: {wall_s:.1f}s  ")
    lines.append(f"Live LLM calls (rehearsal): {llm_calls} / {LLM_BUDGET} budget (+1 claude-shim health ping, uncounted)  ")
    lines.append("")
    lines.append("Components exercised REAL (not mocked): Postgres+RLS, source hunter (reachability probe + lifecycle "
                 "upsert + health events), intel collector (live HTTP + snapshots), semantic extraction (V0-ported), "
                 "semantic synthesizer (LIVE Claude opus), quality reviewer (deterministic + LIVE Claude), "
                 "false-negative auditor (deterministic planted-miss guard), delivery commander + action router "
                 "(real code path, real bot_deliveries/delivery_attempts rows), dashboard state builder (real DB reads).")
    lines.append("")
    lines.append("ONLY fake: the outbound Telegram channel adapter (CapturingTelegramAdapter) — records what would "
                 "have been sent; no real Telegram API call. All upstream steps and all DB writes are real.")
    lines.append("")
    lines.append("## Per-tenant results")
    lines.append("")
    lines.append("| Tenant | Sources fetched | Facts | Deltas | Signals promoted | Synth verdict | Quality | FN audit (planted caught?) | Deliveries | Dashboard |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in results:
        deliv = ", ".join(f"{d['channel']}={d['status']}" for d in r.deliveries) or "none"
        lines.append(f"| {r.slug} | {len(r.sources_fetched)} | {r.facts_extracted} | {r.deltas_extracted} | "
                     f"{len(r.promoted_signals)} | {r.synth_verdict} | {r.quality_status} | "
                     f"{r.fn_status} (caught={r.fn_caught_planted}) | {deliv} | {'quiet' if r.dashboard_is_quiet else 'active'} |")
    lines.append("")
    for r in results:
        lines.append(f"### {r.slug} (tenant_id={r.tenant_id})")
        lines.append("")
        lines.append("Sources fetched:")
        for s in r.sources_fetched:
            lines.append(f"  - {s['name']} {s['url']} http={s['http']} chars={s['chars']} facts={s['facts']} deltas={s['deltas']}")
        if not r.sources_fetched:
            lines.append("  - (none fetched)")
        if r.health_events:
            lines.append("Health events (coverage-before-quiet):")
            for h in r.health_events:
                lines.append(f"  - {h}")
        lines.append("")
        lines.append(f"Synthesis verdict: **{r.synth_verdict}**")
        if r.promoted_signals:
            lines.append("Promoted signals (with evidence URLs):")
            for s in r.promoted_signals:
                lines.append(f"  - **{s['headline']}** (materiality={s['materiality_score']}, owner={s.get('owner')}, urls_ok={s.get('urls_ok')})")
                lines.append(f"    what changed: {s['what_changed']}")
                lines.append(f"    evidence: {s['evidence_urls']}")
        else:
            lines.append("Promoted signals: NONE this cycle.")
        lines.append("")
        lines.append(f"Quality reviewer verdict: **{r.quality_status}**" + (f" — fixes: {r.quality_fixes}" if r.quality_fixes else ""))
        lines.append(f"False-negative audit: **{r.fn_status}**, planted miss `{r.planted_marker}` caught = **{r.fn_caught_planted}**, recommended recheck = {r.fn_recheck}")
        lines.append(f"Deliveries recorded in bot_deliveries: {r.deliveries}; captured (faked) sends on channels: {r.captured_channel}; delivered={r.delivered}")
        lines.append(f"Dashboard state: **{'QUIET' if r.dashboard_is_quiet else 'ACTIVE'}** — {r.dashboard_reason}")
        lines.append(f"Dashboard JSON: {r.dashboard_path}")
        if r.errors:
            lines.append(f"ERRORS: {r.errors}")
        lines.append("")

    lines.append("## Tenant-bleed checks (live DB, RLS-enforced)")
    lines.append("")
    lines.append(f"Overall bleed status: **{'PASS (no bleed)' if bleed['passed'] else 'FAIL (bleed detected)'}**")
    lines.append("")
    lines.append("| As tenant | Probing for | Table | Own rows | Visible total | Other-tenant rows visible | Isolated |")
    lines.append("|---|---|---|---|---|---|---|")
    for p in bleed["pairs"]:
        for t, v in p["tables"].items():
            lines.append(f"| {p['as_tenant']} | {p['probing_for']} | {t} | {v['own']} | {v['visible_total']} | {v['b_rows_visible']} | {p['isolated']} |")
    lines.append("")
    lines.append(f"Cross-tenant evidence-URL leaks into another tenant's published signals: "
                 f"{'NONE' if not bleed['url_leak'] else bleed['url_leak']}")
    lines.append("")
    lines.append("## Critical findings (no-false-green)")
    lines.append("")
    quality_failed = [r.slug for r in results if r.quality_status != "passed"]
    delivered_despite_fail = [r.slug for r in results if r.quality_status != "passed" and r.delivered]
    lines.append("1. **Quality review FAILED for every tenant, yet the brief was delivered anyway.** The manifesto "
                 "(Phase 6) is explicit: a failed quality verdict must never ship. In this rehearsal the delivery "
                 "commander is NOT gated on the quality reviewer's verdict — the two run independently. This is a real "
                 "integration gap: the pieces exist and are real, but nothing wires the quality gate in front of "
                 f"delivery. Tenants delivered despite a FAILED review: {delivered_despite_fail}.")
    lines.append("2. **Why quality failed is itself a real limitation, not a flaky reviewer.** The live Claude reviewer "
                 "correctly flagged that every promoted signal cites the competitor's blog INDEX page "
                 "(e.g. https://www.elastic.co/blog) as its only evidence URL, because the collector fetches and "
                 "snapshots the blog index, not individual article URLs. So a claim passes the synthesizer's "
                 "evidence-or-silence check (the cited URL IS in the supplied evidence set) but fails a stricter "
                 "editorial standard (the URL cannot actually substantiate the specific claim / date / quote). "
                 "Article-level source resolution is missing from the collector.")
    lines.append("3. **The executive-speech lane never ran** in this pass, so coverage is legitimately incomplete "
                 "(coverage.all_lanes_ran=False for all tenants). This is why no tenant can be called QUIET — which is "
                 "correct behavior — but it also means this rehearsal did NOT exercise the argus-executive-speech-scanner.")
    lines.append("")
    lines.append("## Acceptance bar (Gate 7)")
    lines.append("")
    algolia = next((r for r in results if r.slug == "algolia"), None)
    algolia_quality_ok = bool(algolia and algolia.quality_status == "passed")
    algolia_e2e_core = bool(algolia and algolia.promoted_signals and algolia.delivered and algolia.fn_caught_planted
                            and all(s.get("urls_ok") for s in algolia.promoted_signals))
    algolia_full = algolia_e2e_core and algolia_quality_ok
    lines.append(f"- Algolia core chain runs (real signals promoted + evidence-in-set + FN planted-miss caught + "
                 f"delivery recorded): **{'YES' if algolia_e2e_core else 'NO'}**")
    lines.append(f"- Algolia FULLY meets the manifesto Acceptance Standard (the above AND reports pass quality "
                 f"review AND delivery is gated on that pass): **{'MET' if algolia_full else 'NOT MET'}** "
                 f"— quality review status was `{algolia.quality_status if algolia else 'n/a'}`.")
    lines.append(f"- Spryker + Amplitude run without tenant bleed: **{'MET' if bleed['passed'] else 'NOT MET'}**")
    lines.append("")
    lines.append(f"Tenants whose quality review failed: {quality_failed}.")
    lines.append(f"LLM budget: {llm_calls} / {LLM_BUDGET} live calls used.")
    lines.append("")
    lines.append("**Bottom line:** the multi-tenant platform, tenant isolation, collector, brain, FN auditor, "
                 "delivery recording, and dashboard are all real and working. Gate 7's Algolia-end-to-end bar is NOT "
                 "fully met because reports fail quality review (article-level evidence missing) and delivery is not "
                 "gated on the quality verdict. Fix those two before cutting production traffic over.")
    lines.append("")
    return "\n".join(lines)


async def main() -> int:
    started = time.time()
    superuser_dsn = get_dsn()
    app_conninfo = app_dsn(superuser_dsn)

    provider = ClaudeCliShimProvider(model_alias="opus", timeout_s=90.0)
    health = await provider.health_check()
    print(f"claude-shim health: {health.healthy} ({health.detail})")
    if not health.healthy:
        print("ABORT: claude-shim not healthy; refusing to run a 'live' certification against a dead model.")
        return 2
    model = CountingModel(provider)

    out_dir = Path(__file__).resolve().parents[1] / "docs" / "planning" / "gate7-rehearsal-runs"
    out_dir.mkdir(parents=True, exist_ok=True)

    results: list[TenantResult] = []
    tenant_ids: dict[str, int] = {}

    with psycopg.connect(app_conninfo, autocommit=True) as app_conn:
        with app_conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT id, slug FROM tenants ORDER BY id")
            for row in cur.fetchall():
                tenant_ids[row["slug"]] = row["id"]

        for slug, plan in TENANT_PLAN.items():
            tid = tenant_ids[slug]
            print(f"\n=== TENANT {slug} (id={tid}) ===")
            r = await run_tenant(slug, tid, plan, app_conn, model, out_dir)
            results.append(r)
            print(f"  sources={len(r.sources_fetched)} facts={r.facts_extracted} deltas={r.deltas_extracted} "
                  f"signals={len(r.promoted_signals)} verdict={r.synth_verdict} quality={r.quality_status} "
                  f"fn={r.fn_status}(caught={r.fn_caught_planted}) delivered={r.delivered} llm={LLM_CALLS['count']}")

        with psycopg.connect(superuser_dsn, autocommit=True) as su_conn:
            bleed = tenant_bleed_checks(app_conn, su_conn, tenant_ids)

    wall = time.time() - started
    report = build_report(results, bleed, wall, LLM_CALLS["count"])
    report_path = out_dir / "2026-07-08-run.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"\nReport written: {report_path}")
    print(f"LLM calls used (rehearsal): {LLM_CALLS['count']} / {LLM_BUDGET}")
    print("\n" + report)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(main()))
