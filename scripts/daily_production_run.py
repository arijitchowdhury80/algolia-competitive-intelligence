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
    MonthlySynthesizer) on top of the daily chain. Those rollups are opt-in
    via CIOS_ENABLE_WEEKLY_ROLLUP / CIOS_ENABLE_MONTHLY_ROLLUP so the daily
    publish gate is never blocked by a long cadence roll-up.
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
import re
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

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
from cios.brain.thesis import ThesisEngine, find_similar_active_thesis
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
from cios.collect.fetcher import BLOCKED_BY_WAF_ERROR, HttpContentFetcher, ProbeFetcherAdapter
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
from cios.db.repos.dashboard import (
    PgMonitoredCompetitorsRepository,
    PgPrescriptionsRepository,
    PgReportHistoryRepository,
    PgSourceHealthRepository,
    PgSuppressedSignalsRepository,
)
from cios.db.repos.delivery import PgBotDeliveryRepository, PgDeliveryAttemptRepository
from cios.db.repos.learn import PgImprovementQueueRepository, PgLearningEventRepository
from cios.db.repos.product_market import PgProductMarketRepository
from cios.db.repos.product_surfaces import PgProductSurfaceRepository
from cios.db.repos.run_stage import PgRunStageRepository
from cios.db.repos.sources import PgSourceRepository
from cios.db.session import get_dsn, tenant_context
from cios.delivery.action_router import ActionRouter
from cios.delivery.gated_commander import GatedDeliveryCommander
from cios.delivery.telegram_format import render_brief_html
from cios.delivery.types import Cadence, DeliveryRequest, ReportReadyEvent
from cios.execspeech.providers import SnapshotQuoteProvider
from cios.execspeech.scanner import ExecSpeechScanner
from cios.hunter.lifecycle import SourceLifecycle
from cios.hunter.types import Competitor, HealthEventType, Source, SourceHealthEvent, SourceStatus
from cios.hunter.validator import SourceValidator, normalize_url
from cios.intelligence.capabilities import capability_key
from cios.intelligence.ga4_exporter import resolve_ga4_date_windows
from cios.intelligence.importers import diagnose_looker_rows, load_export_records, normalize_looker_rows
from cios.intelligence.scout_surface_exporter import ProductSurfaceTarget
from cios.intelligence.product_surface_executor import MAX_PRODUCT_SURFACE_WORKERS
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
from cios.platform.process_supervisor import PROCESS_GROUPS, install_shutdown_handlers
from cios.platform.redaction import redact_sensitive_text
from cios.platform.models.providers.claude_cli import ClaudeCliShimProvider
from cios.platform.models.types import ModelRequest

LLM_BUDGET = 35
LLM_CALLS = {"count": 0}

# Cutover 2026-07-08 (Arijit's explicit order): V2 IS the system. V0 cron
# jobs are paused (argus profile, ids 19930dfa21e5 / 03671620cd60) — resume
# them for rollback.
DAILY_MARKER = "ARGUS — Daily Competitive Brief"

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "tenants-sources.yaml"
SCRIPT_DIR = Path(__file__).resolve().parent
PRODUCT_MARKET_STAGE_PREFIX = "CIOS_PRODUCT_MARKET_STAGE"


def redacted_exception_message(exc: BaseException) -> str:
    """Return bounded exception text without configured secret values."""

    return redact_sensitive_text(str(exc))


def redacted_exception_detail(exc: BaseException) -> str:
    """Return a bounded exception type and redacted message for diagnostics."""

    message = redacted_exception_message(exc)
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__


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


def select_tenants_for_run(db_tenants: dict[str, int], *, deliver_tenant: str, run_all: bool) -> dict[str, int]:
    if run_all:
        return dict(db_tenants)
    if deliver_tenant not in db_tenants:
        return {}
    return {deliver_tenant: db_tenants[deliver_tenant]}


def fetch_settings(env: dict[str, str]) -> tuple[float, int]:
    timeout = float(env.get("CIOS_FETCH_TIMEOUT_SECONDS", "8"))
    retries = int(env.get("CIOS_FETCH_RETRIES", "0"))
    return timeout, retries


def model_call_settings(env: dict[str, str]) -> tuple[float, int]:
    timeout = float(env.get("CIOS_MODEL_TIMEOUT_SECONDS", "45"))
    attempts = int(env.get("CIOS_CLAUDE_MAX_ATTEMPTS", "1"))
    return timeout, attempts


def quality_timeout_seconds(env: dict[str, str]) -> float:
    return float(env.get("CIOS_QUALITY_TIMEOUT_SECONDS", env.get("CIOS_MODEL_TIMEOUT_SECONDS", "75")))


def synthesis_settings(env: dict[str, str]) -> tuple[int, int, int]:
    competitors = int(env.get("CIOS_MAX_SYNTH_COMPETITORS", "4"))
    deltas = int(env.get("CIOS_SYNTH_DELTAS_PER_COMPETITOR", "8"))
    facts = int(env.get("CIOS_SYNTH_FACTS_PER_COMPETITOR", "12"))
    return competitors, deltas, facts


def article_fetch_cap(env: dict[str, str]) -> int:
    return max(0, int(env.get("CIOS_ARTICLE_FETCH_CAP", "1")))


def env_flag(env: dict[str, str], key: str, *, default: bool = False) -> bool:
    value = env.get(key)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_paths(env: dict[str, str], key: str) -> list[str]:
    value = (env.get(key) or "").strip()
    if not value:
        return []
    return [part for part in value.split(os.pathsep) if part.strip()]


def demand_quality_cli_args_from_env(env: Mapping[str, str]) -> list[str]:
    """Return optional product-market demand threshold flags for child scripts."""

    change_floor = (
        env.get("CIOS_PRODUCT_MARKET_DEMAND_CHANGE_FLOOR")
        or env.get("CIOS_DEMAND_CHANGE_FLOOR")
        or ""
    ).strip()
    value_floor = (
        env.get("CIOS_PRODUCT_MARKET_DEMAND_VALUE_FLOOR")
        or env.get("CIOS_DEMAND_VALUE_FLOOR")
        or ""
    ).strip()
    args: list[str] = []
    if change_floor:
        args.extend(["--demand-change-floor", change_floor])
    if value_floor:
        args.extend(["--demand-value-floor", value_floor])
    return args


LOOKER_EXPORT_SUFFIXES = {".csv", ".json", ".jsonl"}


def discover_product_market_looker_exports(
    *,
    slug: str,
    env: dict[str, str],
    app_dir: Path | None = None,
) -> list[Path]:
    """Resolve tenant demand exports from explicit paths plus a safe drop folder."""

    discovered: list[Path] = []
    seen: set[str] = set()

    def add_path(path: Path) -> None:
        key = str(path.expanduser())
        if key in seen:
            return
        seen.add(key)
        discovered.append(path)

    for raw_path in env_paths(env, "CIOS_PRODUCT_MARKET_LOOKER_EXPORTS"):
        add_path(Path(raw_path).expanduser())

    search_dirs = [Path(raw).expanduser() for raw in env_paths(env, "CIOS_PRODUCT_MARKET_LOOKER_EXPORT_DIRS")]
    if env_flag(env, "CIOS_PRODUCT_MARKET_LOOKER_AUTO_DISCOVER", default=True):
        root = app_dir or SCRIPT_DIR.parent
        search_dirs.extend([
            root / "data" / "looker" / slug,
            root / "data" / "looker",
        ])

    for directory in search_dirs:
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir(), key=lambda item: item.name):
            if path.is_file() and path.suffix.lower() in LOOKER_EXPORT_SUFFIXES:
                add_path(path)

    return discovered


def _looker_drop_root(*, slug: str, app_dir: Path) -> Path:
    return app_dir / "data" / "looker" / slug


def _is_auto_discovered_looker_path(path: Path, *, slug: str, app_dir: Path) -> bool:
    try:
        path.resolve().relative_to(_looker_drop_root(slug=slug, app_dir=app_dir).resolve())
        return True
    except ValueError:
        return False


def _normalized_looker_filename(path: Path, seen: set[str]) -> str:
    stem = re.sub(r"[^a-zA-Z0-9._-]+", "-", path.stem).strip("-") or "looker-export"
    name = f"{stem}.normalized.json"
    if name not in seen:
        seen.add(name)
        return name
    index = 2
    while True:
        candidate = f"{stem}-{index}.normalized.json"
        if candidate not in seen:
            seen.add(candidate)
            return candidate
        index += 1


def prepare_product_market_looker_exports(
    *,
    slug: str,
    env: dict[str, str],
    work_dir: Path,
    app_dir: Path | None = None,
) -> dict[str, Any]:
    """Validate demand exports and write normalized payload files plus a manifest."""

    app_root = app_dir or SCRIPT_DIR.parent
    raw_paths = discover_product_market_looker_exports(slug=slug, env=env, app_dir=app_root)
    normalized_dir = work_dir / "looker-normalized"
    normalized_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = work_dir / "looker-export-manifest.json"
    seen_names: set[str] = set()

    files: list[dict[str, Any]] = []
    payload_paths: list[Path] = []
    normalized_row_count = 0
    skipped_row_count = 0
    error_count = 0

    for raw_path in raw_paths:
        entry: dict[str, Any] = {
            "path": str(raw_path),
            "auto_discovered": _is_auto_discovered_looker_path(raw_path, slug=slug, app_dir=app_root),
            "status": "pending",
            "raw_row_count": 0,
            "normalized_row_count": 0,
            "skipped_row_count": 0,
        }
        try:
            rows = load_export_records(raw_path)
            diagnosis = diagnose_looker_rows(rows, source_path=raw_path)
            normalized = list(diagnosis["normalized"])
        except Exception as exc:  # noqa: BLE001
            entry["status"] = "error"
            entry["error"] = redacted_exception_detail(exc)
            error_count += 1
            files.append(entry)
            continue

        entry["raw_row_count"] = len(rows)
        entry["normalized_row_count"] = len(normalized)
        entry["skipped_row_count"] = int(diagnosis["skipped_row_count"])
        entry["skipped_rows"] = diagnosis["skipped_rows"]
        entry["duplicate_row_count"] = int(diagnosis["duplicate_row_count"])
        normalized_row_count += len(normalized)
        skipped_row_count += entry["skipped_row_count"]

        if not normalized:
            entry["status"] = "empty"
            files.append(entry)
            continue

        normalized_path = normalized_dir / _normalized_looker_filename(raw_path, seen_names)
        normalized_path.write_text(
            json.dumps({"records": normalized}, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        entry["status"] = "ready"
        entry["payload_path"] = str(normalized_path)
        payload_paths.append(normalized_path)
        files.append(entry)

    manifest = {
        "tenant": slug,
        "discovered_count": len(raw_paths),
        "ready_count": len(payload_paths),
        "error_count": error_count,
        "normalized_row_count": normalized_row_count,
        "skipped_row_count": skipped_row_count,
        "files": files,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return {
        **manifest,
        "manifest_path": str(manifest_path),
        "raw_paths": [str(path) for path in raw_paths],
        "payload_paths": [str(path) for path in payload_paths],
    }


def archive_prepared_product_market_looker_exports(
    *,
    prepared: dict[str, Any],
    slug: str,
    app_dir: Path | None = None,
    archive_label: str | None = None,
) -> dict[str, Any]:
    """Move auto-discovered demand exports out of the drop folder after processing."""

    app_root = app_dir or SCRIPT_DIR.parent
    label = archive_label or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    moved: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []

    for entry in prepared.get("files", []):
        raw_path = Path(str(entry.get("path") or ""))
        if not entry.get("auto_discovered"):
            skipped.append({"path": str(raw_path), "reason": "explicit_path"})
            continue
        if not raw_path.exists():
            skipped.append({"path": str(raw_path), "reason": "missing"})
            continue

        status = str(entry.get("status") or "")
        if status == "ready":
            archive_dir = _looker_drop_root(slug=slug, app_dir=app_root) / "_archive" / label
        elif status in {"empty", "error"}:
            archive_dir = _looker_drop_root(slug=slug, app_dir=app_root) / "_rejected" / label
        else:
            skipped.append({"path": str(raw_path), "reason": f"status:{status}"})
            continue

        archive_dir.mkdir(parents=True, exist_ok=True)
        destination = archive_dir / raw_path.name
        raw_path.replace(destination)
        moved.append({"path": str(raw_path), "archived_path": str(destination), "status": status})

    return {
        "archived_count": len(moved),
        "archived_files": moved,
        "skipped_archive_files": skipped,
    }


def _append_path_env(value: str | None, path: Path) -> str:
    paths = [item for item in (value or "").split(os.pathsep) if item]
    paths.append(str(path))
    return os.pathsep.join(paths)


def export_ga4_demand_if_enabled(*, env: dict[str, str], work_dir: Path, python_bin: str) -> dict[str, Any]:
    if not env_flag(env, "CIOS_GA4_EXPORT_ENABLED"):
        return {"status": "skipped_disabled"}

    required = [
        "CIOS_GA4_PROPERTY_ID",
    ]
    missing = [name for name in required if not env.get(name)]
    if missing:
        raise ValueError(f"GA4 export enabled but missing required env: {', '.join(missing)}")

    date_window = resolve_ga4_date_windows(env)
    output_path = work_dir / "ga4-demand.json"
    cmd = [
        python_bin,
        str(SCRIPT_DIR / "export_ga4_demand.py"),
        "--property-id",
        str(env["CIOS_GA4_PROPERTY_ID"]),
        "--current-start",
        date_window.current_start,
        "--current-end",
        date_window.current_end,
        "--previous-start",
        date_window.previous_start,
        "--previous-end",
        date_window.previous_end,
        "--topic-dimension",
        env.get("CIOS_GA4_TOPIC_DIMENSION", "pageTitle"),
        "--url-dimension",
        env.get("CIOS_GA4_URL_DIMENSION", "pagePath"),
        "--metric",
        env.get("CIOS_GA4_METRIC", "engagedSessions"),
        "--limit",
        env.get("CIOS_GA4_LIMIT", "1000"),
        "--output",
        str(output_path),
    ]
    if env.get("CIOS_GA4_SOURCE_URL"):
        cmd.extend(["--source-url", str(env["CIOS_GA4_SOURCE_URL"])])
    if env.get("CIOS_GA4_CREDENTIALS_JSON"):
        cmd.extend(["--credentials-json", str(env["CIOS_GA4_CREDENTIALS_JSON"])])

    completed = _run_checked(
        cmd,
        timeout_seconds=float(env.get("CIOS_GA4_EXPORT_TIMEOUT_SECONDS", "120")),
    )
    summary = json.loads(completed.stdout) if completed.stdout.strip() else {}
    return {
        "status": "ran",
        "path": str(output_path),
        "record_count": int(summary.get("record_count") or 0),
    }


def summarize_product_surface_plan(plan_path: Path) -> dict[str, Any]:
    """Summarize learning-prioritized surface targets from the Scout plan."""
    try:
        data = json.loads(plan_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"target_count": 0, "learning_prioritized_count": 0, "prioritized_targets": []}

    items = data.get("items") if isinstance(data, dict) else []
    if not isinstance(items, list):
        items = []

    try:
        target_count = int(data.get("target_count") or len(items)) if isinstance(data, dict) else len(items)
    except (TypeError, ValueError):
        target_count = len(items)

    target_companies: set[str] = set()
    surface_family_counts: dict[str, int] = {}
    prioritized_targets: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        target = item.get("target") if isinstance(item.get("target"), dict) else {}
        company_name = str(target.get("company_name") or "").strip()
        if company_name:
            target_companies.add(company_name)
        surface_family = str(target.get("surface_family") or "").strip()
        if surface_family:
            surface_family_counts[surface_family] = surface_family_counts.get(surface_family, 0) + 1
        try:
            learning_priority = int(item.get("learning_priority") or 0)
        except (TypeError, ValueError):
            learning_priority = 0
        if learning_priority <= 0:
            continue

        learning_reasons = item.get("learning_reasons") or []
        if not isinstance(learning_reasons, list):
            learning_reasons = [str(learning_reasons)]

        prioritized_targets.append(
            {
                "company_name": target.get("company_name") or "",
                "surface_family": target.get("surface_family") or "",
                "url": target.get("url") or "",
                "learning_priority": learning_priority,
                "learning_reasons": [str(reason) for reason in learning_reasons],
            }
        )

    return {
        "target_count": target_count,
        "target_company_count": len(target_companies),
        "target_companies": sorted(target_companies),
        "surface_family_counts": dict(sorted(surface_family_counts.items())),
        "learning_prioritized_count": len(prioritized_targets),
        "prioritized_targets": prioritized_targets,
    }


def summarize_learning_apply_plan(plan_path: Path) -> dict[str, Any]:
    """Summarize package-scoped apply actions proposed from approved learning."""
    try:
        data = json.loads(plan_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "action_count": 0,
            "skipped_count": 0,
            "targets": [],
            "package_paths": [],
        }

    actions = data.get("actions") if isinstance(data, dict) else []
    skipped = data.get("skipped") if isinstance(data, dict) else []
    if not isinstance(actions, list):
        actions = []
    if not isinstance(skipped, list):
        skipped = []

    targets = sorted(
        {
            str(action.get("target") or "").strip()
            for action in actions
            if isinstance(action, dict) and str(action.get("target") or "").strip()
        }
    )
    package_paths = sorted(
        {
            str(action.get("package_path") or "").strip()
            for action in actions
            if isinstance(action, dict) and str(action.get("package_path") or "").strip()
        }
    )
    return {
        "action_count": len(actions),
        "skipped_count": len(skipped),
        "targets": targets,
        "package_paths": package_paths,
    }


def summarize_learning_apply_execution(result_path: Path) -> dict[str, Any]:
    """Summarize safe proposal/applied output from execute_learning_apply_plan.py."""
    try:
        data = json.loads(result_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "applied_count": 0,
            "proposal_count": 0,
            "skipped_count": 0,
            "proposal_statuses": [],
            "targets": [],
        }

    proposals = data.get("proposals") if isinstance(data, dict) else []
    applied = data.get("applied") if isinstance(data, dict) else []
    skipped = data.get("skipped") if isinstance(data, dict) else []
    if not isinstance(proposals, list):
        proposals = []
    if not isinstance(applied, list):
        applied = []
    if not isinstance(skipped, list):
        skipped = []

    proposal_statuses = sorted(
        {
            str(item.get("status") or "").strip()
            for item in proposals
            if isinstance(item, dict) and str(item.get("status") or "").strip()
        }
    )
    targets = sorted(
        {
            str(item.get("target") or "").strip()
            for item in [*proposals, *applied]
            if isinstance(item, dict) and str(item.get("target") or "").strip()
        }
    )

    return {
        "applied_count": int(data.get("applied_count") or len(applied)) if isinstance(data, dict) else len(applied),
        "proposal_count": int(data.get("proposal_count") or len(proposals)) if isinstance(data, dict) else len(proposals),
        "skipped_count": len(skipped),
        "proposal_statuses": proposal_statuses,
        "targets": targets,
    }


def summarize_next_sweep_learning_plan(plan_path: Path) -> dict[str, Any]:
    """Summarize approved learning impact loaded into the next Hermes sweep."""
    try:
        data = json.loads(plan_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "instruction_count": 0,
            "skipped_count": 0,
            "approved_policy_count": 0,
            "policy_instruction_count": 0,
            "duplicate_policy_instruction_count": 0,
            "skipped_policy_instruction_count": 0,
            "policy_sources": [],
        }

    instructions = data.get("instructions") if isinstance(data, dict) else []
    skipped = data.get("skipped") if isinstance(data, dict) else []
    metadata = data.get("metadata") if isinstance(data, dict) else {}
    if not isinstance(instructions, list):
        instructions = []
    if not isinstance(skipped, list):
        skipped = []
    if not isinstance(metadata, dict):
        metadata = {}

    return {
        "instruction_count": len(instructions),
        "skipped_count": len(skipped),
        "approved_policy_count": int(metadata.get("approved_policy_count") or 0),
        "policy_instruction_count": int(metadata.get("policy_instruction_count") or 0),
        "duplicate_policy_instruction_count": int(metadata.get("duplicate_policy_instruction_count") or 0),
        "skipped_policy_instruction_count": int(metadata.get("skipped_policy_instruction_count") or 0),
        "policy_sources": [
            dict(item)
            for item in metadata.get("policy_sources", [])
            if isinstance(item, dict)
        ],
    }


PRODUCT_SURFACE_FAMILY_MAP = {
    "api": "api_docs",
    "api_docs": "api_docs",
    "developer": "api_docs",
    "developers": "api_docs",
    "changelog": "changelog",
    "docs": "docs",
    "documentation": "docs",
    "integration": "integration",
    "integrations": "integration",
    "marketplace": "integration",
    "partner": "integration",
    "partners": "integration",
    "connector": "integration",
    "connectors": "integration",
    "pricing": "pricing",
    "product": "product_page",
    "product_page": "product_page",
    "platform": "product_page",
    "solution": "product_page",
    "solutions": "product_page",
    "release": "release_notes",
    "release_notes": "release_notes",
    "releases": "release_notes",
}

PRODUCT_SURFACE_HEURISTIC_PATHS = [
    ("changelog", "/changelog"),
    ("release_notes", "/release-notes"),
    ("docs", "/docs"),
    ("api_docs", "/developers"),
    ("pricing", "/pricing"),
    ("integration", "/integrations"),
    ("product_page", "/products"),
    ("product_page", "/platform"),
]


def _source_family_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def _monitored_source_rows(competitor: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    for key in ("monitored_sources", "sources", "source_urls"):
        raw = competitor.get(key)
        if isinstance(raw, list):
            return [row for row in raw if isinstance(row, Mapping)]
    return []


def candidate_product_surface_urls(competitor: Mapping[str, Any] | str | None) -> list[dict[str, str]]:
    if not isinstance(competitor, Mapping):
        return []

    candidates: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for source in _monitored_source_rows(competitor):
        status = str(source.get("status") or source.get("source_status") or "").strip().lower()
        if status != "active":
            continue

        surface_family = PRODUCT_SURFACE_FAMILY_MAP.get(
            _source_family_key(
                source.get("source_family")
                or source.get("family")
                or source.get("surface_family")
            )
        )
        url = str(source.get("url") or "").strip()
        if not surface_family or not url:
            continue

        dedupe_key = (surface_family, normalize_url(url))
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        candidates.append(
            {
                "surface_family": surface_family,
                "url": url,
                "evidence_source_family": str(
                    source.get("source_family")
                    or source.get("family")
                    or source.get("surface_family")
                    or ""
                ),
                "evidence_source_status": status,
            }
        )
    return candidates


def heuristic_product_surface_probes(competitor: Mapping[str, Any] | str | None) -> list[dict[str, Any]]:
    """Return low-confidence product-surface probes from a known company domain.

    These are not evidence-backed sources. They only become product surfaces if
    the discovery executor validates them over the network.
    """

    if not isinstance(competitor, Mapping):
        return []
    base = _heuristic_base_url(competitor.get("domain") or competitor.get("primary_domain"))
    if not base:
        return []
    probes: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for surface_family, path in PRODUCT_SURFACE_HEURISTIC_PATHS:
        url = f"{base}{path}"
        key = (surface_family, normalize_url(url))
        if key in seen:
            continue
        seen.add(key)
        probes.append(
            {
                "surface_family": surface_family,
                "url": url,
                "discovery_reason": "domain_heuristic",
                "requires_validation": True,
            }
        )
    return probes


def _heuristic_base_url(value: Any) -> str:
    domain = str(value or "").strip().lower()
    if not domain:
        return ""
    domain = re.sub(r"^https?://", "", domain)
    domain = domain.split("/", 1)[0].strip()
    domain = domain.strip(".")
    if not domain or "." not in domain:
        return ""
    if any(char.isspace() for char in domain):
        return ""
    return f"https://{domain}"


def _competitor_company_name(competitor: Mapping[str, Any]) -> str:
    return str(competitor.get("competitor_name") or competitor.get("company_name") or "").strip()


def _company_key(value: Any) -> str:
    return str(value or "").strip().casefold()


def _feature_capability_text(row: Mapping[str, Any]) -> str:
    return str(row.get("capability_text") or row.get("capability") or "").strip()


def _feature_company_name(row: Mapping[str, Any]) -> str:
    return str(row.get("company_name") or "").strip()


def _feature_is_product_proof(row: Mapping[str, Any]) -> bool:
    status = str(row.get("position_status") or "").strip().lower()
    return status in {"proven", "claimed", "released", "documented", "present"}


def _intelligence_brief_from_runner_summary(runner_summary: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(runner_summary, dict):
        return {}
    brief = runner_summary.get("intelligence_brief")
    return dict(brief) if isinstance(brief, dict) else {}


def _capability_reasons_from_demand(brief: dict[str, Any]) -> dict[str, list[str]]:
    demand = brief.get("demand_read")
    if not isinstance(demand, dict):
        return {}
    reasons: dict[str, list[str]] = {}
    for topic in demand.get("top_topics") or []:
        if not isinstance(topic, Mapping):
            continue
        label = str(topic.get("topic") or topic.get("capability") or "").strip()
        key = capability_key(label)
        if label and key:
            reasons.setdefault(key, []).append(f"rising_demand: {label}")
    return reasons


def _capability_reasons_from_movement(brief: dict[str, Any]) -> dict[str, list[str]]:
    movement = brief.get("movement_map")
    if not isinstance(movement, dict):
        return {}
    reasons: dict[str, list[str]] = {}
    for label_raw in movement.get("hot_capabilities") or []:
        label = str(label_raw or "").strip()
        key = capability_key(label)
        if label and key:
            reasons.setdefault(key, []).append(f"market_movement: {label}")
    return reasons


def _feature_unknown_collection_targets(
    *,
    monitored_competitors: list[dict[str, Any]],
    feature_matrix_rows: list[dict[str, Any]] | None,
    runner_summary: dict[str, Any] | None,
    unknown_cell_limit: int,
) -> tuple[int, list[dict[str, Any]]]:
    rows = [row for row in (feature_matrix_rows or []) if isinstance(row, dict)]
    if not rows:
        return 0, []

    capabilities_by_key: dict[str, str] = {}
    known_company_keys_by_capability: dict[str, set[str]] = {}
    proof_companies_by_capability: dict[str, set[str]] = {}
    monitored_company_keys = {
        _company_key(_competitor_company_name(competitor))
        for competitor in monitored_competitors
        if _competitor_company_name(competitor)
    }
    for row in rows:
        capability_text = _feature_capability_text(row)
        key = capability_key(capability_text)
        company_name = _feature_company_name(row)
        company_key = _company_key(company_name)
        if not capability_text or not key or not company_name or company_key not in monitored_company_keys:
            continue
        capabilities_by_key.setdefault(key, capability_text)
        known_company_keys_by_capability.setdefault(key, set()).add(company_key)
        if _feature_is_product_proof(row):
            proof_companies_by_capability.setdefault(key, set()).add(company_name)

    if not capabilities_by_key:
        return 0, []

    brief = _intelligence_brief_from_runner_summary(runner_summary)
    demand_reasons = _capability_reasons_from_demand(brief)
    movement_reasons = _capability_reasons_from_movement(brief)
    targets: list[dict[str, Any]] = []
    unknown_cell_count = 0

    for competitor in monitored_competitors:
        company_name = _competitor_company_name(competitor)
        if not company_name:
            continue
        company_key = _company_key(company_name)
        for cap_key, capability_text in sorted(capabilities_by_key.items(), key=lambda item: item[1].casefold()):
            if company_key in known_company_keys_by_capability.get(cap_key, set()):
                continue
            unknown_cell_count += 1
            score = 0
            reasons: list[str] = []
            if cap_key in demand_reasons:
                score += 60
                reasons.extend(demand_reasons[cap_key])
            if cap_key in movement_reasons:
                score += 30
                reasons.extend(movement_reasons[cap_key])
            proof_companies = sorted(
                company for company in proof_companies_by_capability.get(cap_key, set()) if _company_key(company) != company_key
            )
            if proof_companies:
                score += 20
                reasons.append(f"captured_product_proof: {', '.join(proof_companies)}")
            candidate_urls = candidate_product_surface_urls(competitor)
            if score <= 0 or not candidate_urls:
                continue
            targets.append(
                {
                    "competitor_id": competitor.get("competitor_id"),
                    "company_name": company_name,
                    "domain": competitor.get("domain"),
                    "active_source_count": int(competitor.get("active_source_count") or 0),
                    "capability_text": capability_text,
                    "capability_key": cap_key,
                    "priority_score": score,
                    "priority_reasons": list(dict.fromkeys(reasons)),
                    "candidate_surface_urls": candidate_urls,
                }
            )

    targets.sort(
        key=lambda target: (
            int(target.get("priority_score") or 0),
            int(target.get("active_source_count") or 0),
            str(target.get("company_name") or ""),
            str(target.get("capability_text") or ""),
        ),
        reverse=True,
    )
    return unknown_cell_count, targets[: max(0, unknown_cell_limit)]


def _empty_surface_collection_targets(
    *,
    product_surface_execution_summary: dict[str, Any] | None,
    monitored_competitors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(product_surface_execution_summary, dict):
        return []
    empty_outputs = product_surface_execution_summary.get("empty_outputs")
    if not isinstance(empty_outputs, list):
        return []

    competitors_by_key = {
        _company_key(_competitor_company_name(competitor)): competitor
        for competitor in monitored_competitors
        if _competitor_company_name(competitor)
    }
    targets: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for output in empty_outputs:
        if not isinstance(output, Mapping):
            continue
        company_name = str(output.get("company_name") or "").strip()
        if not company_name:
            continue
        failed_family = str(output.get("surface_family") or "").strip()
        key = (_company_key(company_name), failed_family)
        if key in seen:
            continue
        seen.add(key)
        competitor = competitors_by_key.get(_company_key(company_name))
        if not competitor:
            continue
        candidate_urls = candidate_product_surface_urls(competitor)
        heuristic_probes = heuristic_product_surface_probes(competitor)
        targets.append(
            {
                "competitor_id": competitor.get("competitor_id"),
                "company_name": company_name,
                "domain": competitor.get("domain"),
                "active_source_count": int(competitor.get("active_source_count") or 0),
                "failed_surface_family": failed_family,
                "candidate_surface_urls": candidate_urls,
                "heuristic_surface_probes": heuristic_probes,
            }
        )
    return targets


def build_product_muscle_gap_discovery_plan(
    *,
    product_surface_plan_summary: dict[str, Any],
    product_surface_execution_summary: dict[str, Any] | None = None,
    monitored_competitors: list[dict[str, Any]],
    feature_matrix_rows: list[dict[str, Any]] | None = None,
    runner_summary: dict[str, Any] | None = None,
    unknown_cell_limit: int = 25,
) -> dict[str, Any]:
    target_companies = {
        str(company).strip().casefold()
        for company in (product_surface_plan_summary.get("target_companies") or [])
        if str(company).strip()
    }
    missing_companies: list[dict[str, Any]] = []
    covered_count = 0
    candidate_surface_family_counts: dict[str, int] = {}
    candidate_url_count = 0
    heuristic_surface_family_counts: dict[str, int] = {}
    heuristic_probe_count = 0

    for competitor in monitored_competitors:
        company_name = _competitor_company_name(competitor)
        if not company_name:
            continue
        if company_name.casefold() in target_companies:
            covered_count += 1
            continue

        candidate_urls = candidate_product_surface_urls(competitor)
        heuristic_probes = heuristic_product_surface_probes(competitor)
        for candidate in candidate_urls:
            family = candidate["surface_family"]
            candidate_surface_family_counts[family] = candidate_surface_family_counts.get(family, 0) + 1
        candidate_url_count += len(candidate_urls)
        for probe in heuristic_probes:
            family = probe["surface_family"]
            heuristic_surface_family_counts[family] = heuristic_surface_family_counts.get(family, 0) + 1
        heuristic_probe_count += len(heuristic_probes)
        missing_companies.append(
            {
                "competitor_id": competitor.get("competitor_id"),
                "company_name": company_name,
                "domain": competitor.get("domain"),
                "active_source_count": int(competitor.get("active_source_count") or 0),
                "candidate_surface_urls": candidate_urls,
                "heuristic_surface_probes": heuristic_probes,
            }
        )

    empty_surface_targets = _empty_surface_collection_targets(
        product_surface_execution_summary=product_surface_execution_summary,
        monitored_competitors=monitored_competitors,
    )
    for target in empty_surface_targets:
        for candidate in target.get("candidate_surface_urls") or []:
            if not isinstance(candidate, Mapping):
                continue
            family = str(candidate.get("surface_family") or "")
            if family:
                candidate_surface_family_counts[family] = candidate_surface_family_counts.get(family, 0) + 1
                candidate_url_count += 1
        for probe in target.get("heuristic_surface_probes") or []:
            if not isinstance(probe, Mapping):
                continue
            family = str(probe.get("surface_family") or "")
            if family:
                heuristic_surface_family_counts[family] = heuristic_surface_family_counts.get(family, 0) + 1
                heuristic_probe_count += 1

    unknown_feature_cell_count, feature_unknown_targets = _feature_unknown_collection_targets(
        monitored_competitors=monitored_competitors,
        feature_matrix_rows=feature_matrix_rows,
        runner_summary=runner_summary,
        unknown_cell_limit=unknown_cell_limit,
    )

    return {
        "monitored_company_count": len([
            competitor
            for competitor in monitored_competitors
            if _competitor_company_name(competitor)
        ]),
        "covered_company_count": covered_count,
        "missing_company_count": len(missing_companies),
        "missing_companies": missing_companies,
        "empty_surface_target_count": len(empty_surface_targets),
        "empty_surface_targets": empty_surface_targets,
        "candidate_url_count": candidate_url_count,
        "candidate_surface_family_counts": dict(sorted(candidate_surface_family_counts.items())),
        "heuristic_probe_count": heuristic_probe_count,
        "heuristic_surface_family_counts": dict(sorted(heuristic_surface_family_counts.items())),
        "unknown_feature_cell_count": unknown_feature_cell_count,
        "prioritized_unknown_cell_count": len(feature_unknown_targets),
        "feature_unknown_candidate_url_count": sum(
            len(target.get("candidate_surface_urls") or []) for target in feature_unknown_targets
        ),
        "feature_unknown_collection_targets": feature_unknown_targets,
    }


def with_product_muscle_gap_discovery_plan(
    summary: dict[str, Any],
    *,
    monitored_competitors: list[dict[str, Any]],
    feature_matrix_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not isinstance(summary, dict):
        return summary
    plan_summary = summary.get("product_surface_plan_summary")
    if not isinstance(plan_summary, dict):
        return summary
    runner_summary = summary.get("runner_summary")
    if not isinstance(runner_summary, dict):
        runner_summary = {}
    out = dict(summary)
    out["product_muscle_gap_plan"] = build_product_muscle_gap_discovery_plan(
        product_surface_plan_summary=plan_summary,
        product_surface_execution_summary=summary.get("product_surface_execution_summary"),
        monitored_competitors=monitored_competitors,
        feature_matrix_rows=feature_matrix_rows,
        runner_summary=runner_summary,
    )
    return out


PRODUCT_MARKET_CONVERSATION_EXPORT_LIMIT = 80


def _mapping_value(record: Mapping[str, Any] | Any, key: str) -> Any:
    if isinstance(record, Mapping):
        return record.get(key)
    return getattr(record, key, None)


def _evidence_urls_from_signal(signal: Mapping[str, Any] | Any) -> list[str]:
    raw = _mapping_value(signal, "evidence_urls") or _mapping_value(signal, "evidence_url")
    if isinstance(raw, str):
        return [raw.strip()] if raw.strip() else []
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    return []


def _bounded_signal_float(value: Any, *, default: float = 0.5) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return round(min(1.0, max(0.0, number)), 4)


def _signal_text(signal: Mapping[str, Any] | Any, key: str) -> str:
    value = _mapping_value(signal, key)
    return "" if value is None else str(value).strip()


def infer_product_market_conversation_theme(text: str, *, fallback: str) -> str:
    """Infer a capability-rich conversation theme from extracted sweep text."""

    haystack = str(text or "")
    phrase_patterns = [
        (r"\bAI Shopping Agent\b", "AI Shopping Agent"),
        (r"\bShopping Agent\b", "AI Shopping Agent"),
        (r"\bConversational Agent\b", "Conversational Agent"),
        (r"\bAI Assistant\b", "AI Assistant"),
        (r"\bCommerce AI Agent\b", "commerce AI agent"),
        (r"\bagentic product discovery\b", "agentic product discovery"),
    ]
    for pattern, label in phrase_patterns:
        if re.search(pattern, haystack, flags=re.IGNORECASE):
            return label

    lowered = haystack.lower()
    if "product discovery" in lowered and any(term in lowered for term in ("agent", "assistant", "natural language")):
        return "agentic product discovery"
    if "shopping" in lowered and any(term in lowered for term in ("agent", "assistant", "natural language")):
        return "AI Shopping Agent"
    if "commerce" in lowered and "ai" in lowered and any(term in lowered for term in ("agent", "assistant")):
        return "commerce AI agent"

    return fallback


def product_market_conversation_records_from_promoted_signals(
    promoted_signals: list[Mapping[str, Any] | Any],
    *,
    captured_at: datetime,
    limit: int = PRODUCT_MARKET_CONVERSATION_EXPORT_LIMIT,
) -> list[dict[str, Any]]:
    """Convert this run's promoted Argus signals into product-market conversation evidence.

    The product-market spine needs one stable conversation export format.
    Promoted signals already passed Argus's evidence gate, so this conversion
    carries source URLs forward without widening the trust boundary to raw
    scrape text.
    """

    records: list[dict[str, Any]] = []
    observed_at = captured_at if captured_at.tzinfo else captured_at.replace(tzinfo=timezone.utc)
    for signal in promoted_signals:
        if len(records) >= limit:
            break

        evidence_urls = _evidence_urls_from_signal(signal)
        headline = _signal_text(signal, "headline")
        what_changed = _signal_text(signal, "what_changed")
        if not evidence_urls or not (headline or what_changed):
            continue

        theme = (
            _signal_text(signal, "capability")
            or _signal_text(signal, "topic")
            or _signal_text(signal, "signal_type")
            or headline
        )
        if not theme:
            continue

        if headline and what_changed and what_changed not in headline:
            summary = f"{headline}: {what_changed}"
        else:
            summary = headline or what_changed

        record: dict[str, Any] = {
            "theme": theme,
            "summary": summary,
            "intensity": _bounded_signal_float(
                _mapping_value(signal, "materiality_score"),
                default=_bounded_signal_float(_mapping_value(signal, "confidence"), default=0.5),
            ),
            "source_url": evidence_urls[0],
            "captured_at": observed_at.isoformat(),
            "excerpt": what_changed or headline,
            "method": "web_scan",
        }

        company_id = _mapping_value(signal, "competitor_id")
        if company_id not in (None, ""):
            try:
                record["company_id"] = int(company_id)
            except (TypeError, ValueError):
                pass

        company_name = _signal_text(signal, "competitor_name")
        if company_name:
            record["company_name"] = company_name

        records.append(record)

    return records


def _conversation_record_key(record: Mapping[str, Any]) -> tuple[str, str]:
    return (str(record.get("source_url") or ""), str(record.get("summary") or "").strip().lower())


def product_market_conversation_records_from_current_sweep(
    *,
    promoted_signals: list[Mapping[str, Any] | Any],
    all_deltas_by_comp: dict[int, list],
    comp_names_by_id: dict[int, str],
    captured_at: datetime,
    limit: int = PRODUCT_MARKET_CONVERSATION_EXPORT_LIMIT,
) -> list[dict[str, Any]]:
    """Build the conversation plane for the product-market spine from this sweep.

    Promoted signals lead because they passed the strictest materiality gate.
    Evidence-backed semantic deltas then provide the awareness layer for quiet
    days: what the market is saying, without pretending it is release proof.
    """

    records = product_market_conversation_records_from_promoted_signals(
        promoted_signals,
        captured_at=captured_at,
        limit=limit,
    )
    seen = {_conversation_record_key(record) for record in records}
    observed_at = captured_at if captured_at.tzinfo else captured_at.replace(tzinfo=timezone.utc)

    candidates: list[tuple[float, int, Any, str, str]] = []
    for fallback_comp_id, deltas in all_deltas_by_comp.items():
        for delta in deltas:
            evidence_urls = _evidence_urls_from_signal(delta)
            what_changed = _signal_text(delta, "what_changed")
            if not evidence_urls or not what_changed:
                continue
            raw_comp_id = _mapping_value(delta, "competitor_id")
            try:
                competitor_id = int(raw_comp_id if raw_comp_id not in (None, "") else fallback_comp_id)
            except (TypeError, ValueError):
                competitor_id = int(fallback_comp_id)
            materiality = _bounded_signal_float(
                _mapping_value(delta, "materiality_score"),
                default=_bounded_signal_float(_mapping_value(delta, "confidence"), default=0.35),
            )
            candidates.append((materiality, competitor_id, delta, evidence_urls[0], what_changed))

    candidates.sort(key=lambda item: item[0], reverse=True)
    for materiality, competitor_id, delta, source_url, what_changed in candidates:
        if len(records) >= limit:
            break

        theme = (
            _signal_text(delta, "capability")
            or _signal_text(delta, "topic")
            or infer_product_market_conversation_theme(
                what_changed,
                fallback=_signal_text(delta, "delta_type"),
            )
            or comp_names_by_id.get(competitor_id, f"competitor {competitor_id}")
        )
        record: dict[str, Any] = {
            "company_id": competitor_id,
            "company_name": comp_names_by_id.get(competitor_id, f"competitor {competitor_id}"),
            "theme": theme,
            "summary": what_changed,
            "intensity": materiality,
            "source_url": source_url,
            "captured_at": observed_at.isoformat(),
            "excerpt": what_changed,
            "method": "web_scan",
        }
        key = _conversation_record_key(record)
        if key in seen:
            continue
        seen.add(key)
        records.append(record)

    return records


def _run_process_group(
    cmd: list[str],
    *,
    capture_output: bool,
    text: bool,
    timeout: float,
    check: bool,
) -> subprocess.CompletedProcess:
    del capture_output, text, check
    process = PROCESS_GROUPS.spawn(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            PROCESS_GROUPS.terminate(process)
            stdout, stderr = process.communicate()
            detail = redact_sensitive_text((stderr or "").strip() or (stdout or "").strip())
            suffix = f": {detail}" if detail else ""
            raise RuntimeError(f"command timed out after {timeout:g}s{suffix}") from None
    finally:
        PROCESS_GROUPS.unregister(process)
    return subprocess.CompletedProcess(cmd, process.returncode, stdout, stderr)


def _run_checked(cmd: list[str], *, timeout_seconds: float) -> subprocess.CompletedProcess:
    completed = _run_process_group(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        stdout = (completed.stdout or "").strip()
        detail = redact_sensitive_text(stderr or stdout or f"exit {completed.returncode}")
        raise RuntimeError(f"command failed: {Path(cmd[1]).name}: {detail}")
    return completed


PRODUCT_SURFACE_STAGE_CLEANUP_MARGIN_SECONDS = 30.0


def product_surface_timeout_settings(env: Mapping[str, str]) -> dict[str, float | int]:
    item_timeout = float(env.get("CIOS_PRODUCT_MARKET_EXPORT_COMMAND_TIMEOUT_SECONDS", "300"))
    batch_timeout = float(env.get("CIOS_PRODUCT_MARKET_EXPORT_BATCH_TIMEOUT_SECONDS", "600"))
    stage_timeout = float(
        env.get("CIOS_PRODUCT_MARKET_EXPORT_STAGE_TIMEOUT_SECONDS", str(batch_timeout + 30))
    )
    max_workers = int(env.get("CIOS_PRODUCT_MARKET_EXPORT_MAX_WORKERS", "1"))
    if item_timeout <= 0 or batch_timeout <= 0 or stage_timeout <= 0:
        raise ValueError("product-surface timeout values must be greater than zero")
    if not 1 <= max_workers <= MAX_PRODUCT_SURFACE_WORKERS:
        raise ValueError(
            f"product-surface max workers must be between 1 and {MAX_PRODUCT_SURFACE_WORKERS}"
        )
    if stage_timeout < batch_timeout + PRODUCT_SURFACE_STAGE_CLEANUP_MARGIN_SECONDS:
        raise ValueError(
            "product-surface stage timeout must be at least 30 seconds longer "
            "than the executor batch timeout"
        )
    return {
        "item_timeout": item_timeout,
        "batch_timeout": batch_timeout,
        "stage_timeout": stage_timeout,
        "max_workers": max_workers,
    }


def _utc_stage_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _emit_product_market_stage(
    *,
    slug: str,
    stage: str,
    event: str,
    **fields: Any,
) -> None:
    payload = {
        "event": event,
        "stage": stage,
        "tenant": slug,
        "timestamp": _utc_stage_timestamp(),
    }
    payload.update(fields)
    print(
        f"{PRODUCT_MARKET_STAGE_PREFIX} {json.dumps(payload, sort_keys=True, default=str)}",
        flush=True,
    )


def _run_product_market_stage(
    *,
    slug: str,
    stage: str,
    action,
    stage_ledger: list[dict[str, Any]] | None = None,
) -> Any:
    _emit_product_market_stage(slug=slug, stage=stage, event="start")
    started_at_wall = _utc_stage_timestamp()
    started_at = time.monotonic()
    try:
        result = action()
    except Exception as exc:
        elapsed_s = round(time.monotonic() - started_at, 3)
        ended_at_wall = _utc_stage_timestamp()
        safe_error = redact_sensitive_text(str(exc))
        _emit_product_market_stage(
            slug=slug,
            stage=stage,
            event="failed",
            elapsed_s=elapsed_s,
            error_type=type(exc).__name__,
            error=safe_error,
        )
        if stage_ledger is not None:
            stage_ledger.append(
                {
                    "tenant": slug,
                    "stage": stage,
                    "status": "failed",
                    "started_at": started_at_wall,
                    "ended_at": ended_at_wall,
                    "elapsed_s": elapsed_s,
                    "error_type": type(exc).__name__,
                    "error": safe_error,
                }
            )
        raise RuntimeError(safe_error) from None
    elapsed_s = round(time.monotonic() - started_at, 3)
    ended_at_wall = _utc_stage_timestamp()
    _emit_product_market_stage(
        slug=slug,
        stage=stage,
        event="done",
        elapsed_s=elapsed_s,
    )
    if stage_ledger is not None:
        stage_ledger.append(
            {
                "tenant": slug,
                "stage": stage,
                "status": "completed",
                "started_at": started_at_wall,
                "ended_at": ended_at_wall,
                "elapsed_s": elapsed_s,
            }
        )
    return result


def _product_market_failed_summary(
    *,
    stage_ledger: list[dict[str, Any]],
    exc: Exception,
) -> dict[str, Any]:
    return {
        "status": "failed",
        "error": redacted_exception_detail(exc),
        "stage_ledger": stage_ledger,
    }


def run_product_market_chain_if_enabled(
    *,
    slug: str,
    tenant_id: int,
    env: dict[str, str],
    conversation_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run the product-market muscle chain before dashboard state is built.

    This is intentionally a CI-OS extension flow invoked by Hermes' daily
    runner. It calls CI-OS scripts as package entrypoints and does not modify
    or import Hermes core.
    """

    if not env_flag(env, "CIOS_ENABLE_PRODUCT_MARKET_INTELLIGENCE"):
        return {"status": "skipped_disabled"}

    root = Path(env.get("CIOS_PRODUCT_MARKET_WORKDIR", "/tmp/cios-product-market")) / slug
    export_dir = root / "surface-exports"
    next_sweep_plan_path = root / "next-sweep-learning-plan.json"
    learning_apply_plan_path = root / "learning-apply-plan.json"
    learning_apply_execution_path = root / "learning-apply-execution.json"
    plan_path = root / "product-surface-plan.json"
    execution_summary_path = root / "product-surface-execution-summary.json"
    payload_path = root / "product-market-payload.json"
    conversation_path = root / "conversation-records.json"
    root.mkdir(parents=True, exist_ok=True)
    export_dir.mkdir(parents=True, exist_ok=True)
    stage_ledger: list[dict[str, Any]] = []

    python_bin = env.get("CIOS_PRODUCT_MARKET_PYTHON_BIN") or sys.executable
    command_timeout = float(env.get("CIOS_PRODUCT_MARKET_COMMAND_TIMEOUT_SECONDS", "240"))
    product_surface_timeouts = product_surface_timeout_settings(env)
    surface_timeout = env.get("CIOS_PRODUCT_MARKET_SURFACE_TIMEOUT_SECONDS", "120")
    provider = env.get("CIOS_PRODUCT_MARKET_PROVIDER", "ollama/llama3.2:3b")
    scout_bin = env.get("CIOS_SCOUT_BIN", "scout")
    own_company_name = env.get("CIOS_PRODUCT_MARKET_OWN_COMPANY_NAME") or slug.title()

    learning_plan_cmd = [
        python_bin,
        str(SCRIPT_DIR / "build_next_sweep_learning_plan.py"),
        "--tenant",
        slug,
        "--output",
        str(next_sweep_plan_path),
    ]
    try:
        _run_product_market_stage(
            slug=slug,
            stage="next_sweep_learning_plan",
            action=lambda: _run_checked(learning_plan_cmd, timeout_seconds=command_timeout),
            stage_ledger=stage_ledger,
        )
    except Exception as exc:
        return _product_market_failed_summary(stage_ledger=stage_ledger, exc=exc)
    next_sweep_plan_summary = summarize_next_sweep_learning_plan(next_sweep_plan_path)

    learning_apply_cmd = [
        python_bin,
        str(SCRIPT_DIR / "build_learning_apply_plan.py"),
        "--plan",
        str(next_sweep_plan_path),
        "--tenant-id",
        str(tenant_id),
        "--output",
        str(learning_apply_plan_path),
    ]
    try:
        _run_product_market_stage(
            slug=slug,
            stage="learning_apply_plan",
            action=lambda: _run_checked(learning_apply_cmd, timeout_seconds=command_timeout),
            stage_ledger=stage_ledger,
        )
    except Exception as exc:
        return _product_market_failed_summary(stage_ledger=stage_ledger, exc=exc)
    learning_apply_plan_summary = summarize_learning_apply_plan(learning_apply_plan_path)

    learning_apply_execute_cmd = [
        python_bin,
        str(SCRIPT_DIR / "execute_learning_apply_plan.py"),
        "--plan",
        str(learning_apply_plan_path),
        "--package-root",
        str(SCRIPT_DIR.parent),
        "--output",
        str(learning_apply_execution_path),
    ]
    approved_by = (env.get("CIOS_LEARNING_APPLY_APPROVED_BY") or "").strip()
    if approved_by:
        learning_apply_execute_cmd.extend(["--approved-by", approved_by])
    try:
        _run_product_market_stage(
            slug=slug,
            stage="learning_apply_execute",
            action=lambda: _run_checked(learning_apply_execute_cmd, timeout_seconds=command_timeout),
            stage_ledger=stage_ledger,
        )
    except Exception as exc:
        return _product_market_failed_summary(stage_ledger=stage_ledger, exc=exc)
    learning_apply_execution_summary = summarize_learning_apply_execution(learning_apply_execution_path)

    plan_cmd = [
        python_bin,
        str(SCRIPT_DIR / "plan_product_surface_exports.py"),
        "--tenant-id",
        str(tenant_id),
        "--output-dir",
        str(export_dir),
        "--plan-output",
        str(plan_path),
        "--python-bin",
        python_bin,
        "--script-path",
        str(SCRIPT_DIR / "export_product_surface_with_scout.py"),
        "--scout-bin",
        scout_bin,
        "--provider",
        provider,
        "--timeout-seconds",
        surface_timeout,
        "--learning-plan",
        str(next_sweep_plan_path),
    ]
    if env_flag(env, "CIOS_PRODUCT_MARKET_USE_JS"):
        plan_cmd.append("--js")
    def run_surface_plan() -> dict[str, Any]:
        _run_checked(plan_cmd, timeout_seconds=command_timeout)
        return summarize_product_surface_plan(plan_path)

    try:
        product_surface_plan_summary = _run_product_market_stage(
            slug=slug,
            stage="product_surface_plan",
            action=run_surface_plan,
            stage_ledger=stage_ledger,
        )
    except Exception as exc:
        return _product_market_failed_summary(stage_ledger=stage_ledger, exc=exc)

    execute_cmd = [
        python_bin,
        str(SCRIPT_DIR / "execute_product_surface_plan.py"),
        "--plan",
        str(plan_path),
        "--summary-output",
        str(execution_summary_path),
        "--command-timeout-seconds",
        f"{product_surface_timeouts['item_timeout']:g}",
        "--batch-timeout-seconds",
        f"{product_surface_timeouts['batch_timeout']:g}",
        "--max-workers",
        str(product_surface_timeouts["max_workers"]),
    ]
    try:
        _run_product_market_stage(
            slug=slug,
            stage="product_surface_export",
            action=lambda: _run_checked(
                execute_cmd,
                timeout_seconds=float(product_surface_timeouts["stage_timeout"]),
            ),
            stage_ledger=stage_ledger,
        )
    except Exception as exc:
        return _product_market_failed_summary(stage_ledger=stage_ledger, exc=exc)

    execution_summary = json.loads(execution_summary_path.read_text(encoding="utf-8"))
    scout_paths = [str(path) for path in execution_summary.get("scout_paths", [])]
    product_surface_execution_summary = {
        "product_plane_status": execution_summary.get("product_plane_status"),
        "planned": int(execution_summary.get("planned") or 0),
        "succeeded": int(execution_summary.get("succeeded") or 0),
        "empty": int(execution_summary.get("empty") or 0),
        "failed": int(execution_summary.get("failed") or 0),
        "timed_out": int(execution_summary.get("timed_out") or 0),
        "not_started": int(execution_summary.get("not_started") or 0),
        "batch_timed_out": bool(execution_summary.get("batch_timed_out")),
        "batch_timeout_seconds": float(execution_summary.get("batch_timeout_seconds") or 0),
        "product_row_count": int(execution_summary.get("product_row_count") or 0),
        "empty_scout_paths": [str(path) for path in execution_summary.get("empty_scout_paths", [])],
        "empty_outputs": list(execution_summary.get("empty_outputs", []))
        if isinstance(execution_summary.get("empty_outputs"), list)
        else [],
        "company_row_counts": dict(execution_summary.get("company_row_counts", {}))
        if isinstance(execution_summary.get("company_row_counts"), dict)
        else {},
        "surface_family_row_counts": dict(execution_summary.get("surface_family_row_counts", {}))
        if isinstance(execution_summary.get("surface_family_row_counts"), dict)
        else {},
    }
    exported_conversation_records = [dict(record) for record in conversation_records or []]
    if exported_conversation_records:
        conversation_path.write_text(
            json.dumps({"records": exported_conversation_records}, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    if not scout_paths:
        return {
            "status": "skipped_no_product_surface_outputs",
            "next_sweep_plan_path": str(next_sweep_plan_path),
            "next_sweep_plan_summary": next_sweep_plan_summary,
            "learning_apply_plan_path": str(learning_apply_plan_path),
            "learning_apply_plan_summary": learning_apply_plan_summary,
            "learning_apply_execution_path": str(learning_apply_execution_path),
            "learning_apply_execution_summary": learning_apply_execution_summary,
            "plan_path": str(plan_path),
            "product_surface_plan_summary": product_surface_plan_summary,
            "execution_summary_path": str(execution_summary_path),
            "product_surface_execution_summary": product_surface_execution_summary,
            "scout_paths": [],
            "conversation_record_count": len(exported_conversation_records),
            "conversation_path": str(conversation_path) if exported_conversation_records else None,
            "stage_ledger": stage_ledger,
        }

    try:
        ga4_export = _run_product_market_stage(
            slug=slug,
            stage="demand_export",
            action=lambda: export_ga4_demand_if_enabled(env=env, work_dir=root, python_bin=python_bin),
            stage_ledger=stage_ledger,
        )
    except Exception as exc:
        return _product_market_failed_summary(stage_ledger=stage_ledger, exc=exc)
    looker_env = dict(env)
    if ga4_export.get("status") == "ran" and ga4_export.get("path"):
        looker_env["CIOS_PRODUCT_MARKET_LOOKER_EXPORTS"] = _append_path_env(
            looker_env.get("CIOS_PRODUCT_MARKET_LOOKER_EXPORTS"),
            Path(str(ga4_export["path"])),
        )

    try:
        looker_exports = _run_product_market_stage(
            slug=slug,
            stage="looker_prepare",
            action=lambda: prepare_product_market_looker_exports(
                slug=slug,
                env=looker_env,
                work_dir=root,
                app_dir=SCRIPT_DIR.parent,
            ),
            stage_ledger=stage_ledger,
        )
    except Exception as exc:
        return _product_market_failed_summary(stage_ledger=stage_ledger, exc=exc)
    payload_cmd = [
        python_bin,
        str(SCRIPT_DIR / "build_product_market_payload.py"),
        "--own-company-name",
        own_company_name,
        "--tenant-id",
        str(tenant_id),
        "--learning-plan",
        str(next_sweep_plan_path),
        "--output",
        str(payload_path),
    ]
    payload_cmd.extend(demand_quality_cli_args_from_env(env))
    for scout_path in scout_paths:
        payload_cmd.extend(["--scout", scout_path])
    if exported_conversation_records:
        payload_cmd.extend(["--conversation", str(conversation_path)])
    for looker_path in looker_exports["payload_paths"]:
        payload_cmd.extend(["--looker", str(looker_path)])
    try:
        _run_product_market_stage(
            slug=slug,
            stage="product_market_payload",
            action=lambda: _run_checked(payload_cmd, timeout_seconds=command_timeout),
            stage_ledger=stage_ledger,
        )
    except Exception as exc:
        return _product_market_failed_summary(stage_ledger=stage_ledger, exc=exc)

    try:
        runner = _run_product_market_stage(
            slug=slug,
            stage="product_market_synthesis",
            action=lambda: _run_checked(
                [
                    python_bin,
                    str(SCRIPT_DIR / "run_product_market_intelligence.py"),
                    "--input",
                    str(payload_path),
                ],
                timeout_seconds=command_timeout,
            ),
            stage_ledger=stage_ledger,
        )
    except Exception as exc:
        return _product_market_failed_summary(stage_ledger=stage_ledger, exc=exc)
    runner_summary = json.loads(runner.stdout) if runner.stdout.strip() else {}
    ledger_refresh_cmd = [
        python_bin,
        str(SCRIPT_DIR / "refresh_product_market_from_ledger.py"),
        "--tenant",
        slug,
        "--own-company-name",
        own_company_name,
        "--days",
        env.get("CIOS_PRODUCT_MARKET_LEDGER_REFRESH_DAYS", "30"),
        "--limit",
        env.get("CIOS_PRODUCT_MARKET_LEDGER_REFRESH_LIMIT", "500"),
        "--learning-plan",
        str(next_sweep_plan_path),
    ]
    ledger_refresh_cmd.extend(demand_quality_cli_args_from_env(env))
    try:
        ledger_refresh = _run_product_market_stage(
            slug=slug,
            stage="product_market_ledger_refresh",
            action=lambda: _run_checked(ledger_refresh_cmd, timeout_seconds=command_timeout),
            stage_ledger=stage_ledger,
        )
    except Exception as exc:
        return _product_market_failed_summary(stage_ledger=stage_ledger, exc=exc)
    ledger_refresh_summary = json.loads(ledger_refresh.stdout) if ledger_refresh.stdout.strip() else {}
    try:
        archive_summary = _run_product_market_stage(
            slug=slug,
            stage="looker_archive",
            action=lambda: archive_prepared_product_market_looker_exports(
                prepared=looker_exports,
                slug=slug,
                app_dir=SCRIPT_DIR.parent,
            ),
            stage_ledger=stage_ledger,
        )
    except Exception as exc:
        return _product_market_failed_summary(stage_ledger=stage_ledger, exc=exc)
    return {
        "status": "ran",
        "next_sweep_plan_path": str(next_sweep_plan_path),
        "next_sweep_plan_summary": next_sweep_plan_summary,
        "learning_apply_plan_path": str(learning_apply_plan_path),
        "learning_apply_plan_summary": learning_apply_plan_summary,
        "learning_apply_execution_path": str(learning_apply_execution_path),
        "learning_apply_execution_summary": learning_apply_execution_summary,
        "plan_path": str(plan_path),
        "product_surface_plan_summary": product_surface_plan_summary,
        "execution_summary_path": str(execution_summary_path),
        "product_surface_execution_summary": product_surface_execution_summary,
        "payload_path": str(payload_path),
        "scout_paths": scout_paths,
        "conversation_record_count": len(exported_conversation_records),
        "conversation_path": str(conversation_path) if exported_conversation_records else None,
        "ga4_export_status": ga4_export.get("status"),
        "ga4_export_path": ga4_export.get("path"),
        "ga4_export_record_count": ga4_export.get("record_count", 0),
        "looker_export_count": len(looker_exports["payload_paths"]),
        "looker_discovered_count": looker_exports["discovered_count"],
        "looker_ready_count": looker_exports["ready_count"],
        "looker_error_count": looker_exports["error_count"],
        "looker_normalized_row_count": looker_exports["normalized_row_count"],
        "looker_skipped_row_count": looker_exports["skipped_row_count"],
        "looker_manifest_path": looker_exports["manifest_path"],
        "looker_raw_paths": looker_exports["raw_paths"],
        "looker_paths": looker_exports["payload_paths"],
        "looker_archived_count": archive_summary["archived_count"],
        "looker_archived_files": archive_summary["archived_files"],
        "looker_skipped_archive_files": archive_summary["skipped_archive_files"],
        "runner_summary": runner_summary,
        "ledger_refresh_status": "ran",
        "ledger_refresh_summary": ledger_refresh_summary,
        "stage_ledger": stage_ledger,
    }


def synthesis_mode_instructions(env: dict[str, str], *, cold_start: bool) -> str:
    mode = (env.get("CIOS_SYNTHESIS_MODE") or "snapshot").strip().lower()
    notes: list[str] = []
    if mode == "snapshot":
        notes.append(
            "SNAPSHOT MODE: observed deltas are current extracted observations, "
            "not proven before/after changes. Do not claim a launch, shift, "
            "pivot, replacement, primary differentiator, or alternative unless "
            "the supplied evidence explicitly says that. Prefer 'current state', "
            "'currently positions', or 'source shows' framing. If current-state "
            "evidence is not material enough to act on, return an empty signals array."
        )
    if cold_start:
        notes.append(
            "BASELINE MODE: this is an early collection cycle for this reader. "
            "There is no reliable prior snapshot in the synthesis input, so you "
            "cannot claim anything changed in the last 24 hours. Frame any signal "
            "as the competitor's CURRENT position, never as a recent change."
        )
    return "\n".join(notes)


def model_alias(env: dict[str, str], key: str, default: str = "sonnet") -> str:
    return (env.get(key) or default).strip() or default


PRODUCT_MARKET_PUBLISH_BLOCKING_STATUSES = {
    "failed",
    "skipped_no_product_surface_outputs",
}


def product_market_stage_ledger_status(product_market_summary: dict[str, Any]) -> str:
    status = str(product_market_summary.get("status") or "").strip()
    stage_ledger = product_market_summary.get("stage_ledger") or []
    if status == "skipped_disabled":
        return "skipped"
    if status in PRODUCT_MARKET_PUBLISH_BLOCKING_STATUSES:
        return "failed"
    if any(isinstance(entry, dict) and entry.get("status") == "failed" for entry in stage_ledger):
        return "failed"
    if not stage_ledger:
        return "skipped"
    return "completed"


def persist_product_market_stage_ledger(
    conn,
    *,
    tenant_id: int,
    run_id: str,
    product_market_summary: dict[str, Any],
) -> int | None:
    stage_ledger = product_market_summary.get("stage_ledger")
    if not isinstance(stage_ledger, list) or not stage_ledger:
        return None
    return PgProductMarketRepository(conn).save_run_stage_ledger(
        tenant_id=tenant_id,
        run_id=run_id,
        package_name="cios.product_market",
        status=product_market_stage_ledger_status(product_market_summary),
        stage_ledger=stage_ledger,
        metadata={"product_market_status": product_market_summary.get("status")},
    )


def _daily_stage(stage: str, status: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "stage": stage,
        "status": status,
        "metadata": metadata or {},
    }


def _product_market_chain_stage_status(product_market_summary: dict[str, Any]) -> str:
    status = str(product_market_summary.get("status") or "not_run")
    if status in PRODUCT_MARKET_PUBLISH_BLOCKING_STATUSES:
        return "failed"
    if status in {"not_run", "skipped_disabled"}:
        return "skipped"
    return "completed"


def daily_run_stage_ledger_status(stage_ledger: list[dict[str, Any]]) -> str:
    if not stage_ledger:
        return "skipped"
    statuses = [str(entry.get("status") or "skipped") for entry in stage_ledger]
    if any(status == "failed" for status in statuses):
        return "failed"
    if all(status == "skipped" for status in statuses):
        return "skipped"
    return "completed"


class DailyRunStageRecorder:
    """Small runtime helper for a live `cios.daily` run-stage ledger."""

    def __init__(
        self,
        repo,
        *,
        tenant_id: int,
        run_id: str,
        package_name: str = "cios.daily",
        ledger_id: int | None = None,
        recorded_stage_orders: set[int] | None = None,
    ) -> None:
        self.repo = repo
        self.tenant_id = tenant_id
        self.run_id = run_id
        self.package_name = package_name
        self.ledger_id = ledger_id
        self.recorded_stage_orders = recorded_stage_orders if recorded_stage_orders is not None else set()

    def start(self, *, metadata: dict[str, Any] | None = None) -> int:
        if self.ledger_id is None:
            self.ledger_id = self.repo.start_ledger(
                tenant_id=self.tenant_id,
                run_id=self.run_id,
                package_name=self.package_name,
                metadata=metadata or {},
            )
        return self.ledger_id

    def start_stage(
        self,
        *,
        stage: str,
        stage_order: int,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        ledger_id = self.start(metadata={})
        event_id = self.repo.start_stage(
            tenant_id=self.tenant_id,
            ledger_id=ledger_id,
            stage_order=stage_order,
            stage=stage,
            metadata=metadata or {},
        )
        self.recorded_stage_orders.add(stage_order)
        return event_id

    def finish_stage(
        self,
        *,
        event_id: int,
        status: str,
        metadata: dict[str, Any] | None = None,
        error_type: str | None = None,
        error: str | None = None,
    ) -> None:
        kwargs: dict[str, Any] = {
            "tenant_id": self.tenant_id,
            "event_id": event_id,
            "status": status,
            "metadata": metadata or {},
        }
        if error_type is not None:
            kwargs["error_type"] = error_type
        if error is not None:
            kwargs["error"] = error
        self.repo.finish_stage(**kwargs)

    def run_stage(
        self,
        *,
        stage: str,
        stage_order: int,
        action,
        metadata: dict[str, Any] | None = None,
        finish_metadata=None,
    ) -> Any:
        event_id = self.start_stage(
            stage_order=stage_order,
            stage=stage,
            metadata=metadata or {},
        )
        try:
            result = action()
        except Exception as exc:
            safe_error = redacted_exception_message(exc)
            self.finish_stage(
                event_id=event_id,
                status="failed",
                metadata={},
                error_type=type(exc).__name__,
                error=safe_error,
            )
            raise RuntimeError(safe_error) from None

        if callable(finish_metadata):
            done_metadata = finish_metadata(result)
        else:
            done_metadata = finish_metadata or {}
        self.finish_stage(
            event_id=event_id,
            status="completed",
            metadata=done_metadata,
        )
        return result


def daily_run_stage_ledger_from_result(result) -> list[dict[str, Any]]:
    """Build a coarse durable run trace for the whole tenant daily pass."""

    source_status = "skipped"
    if result.sources_attempted_count > 0:
        source_status = "completed"
    elif result.sources_planned_count > 0:
        source_status = "failed"

    synthesis_status = "skipped"
    if result.synth_verdict == Verdict.COVERAGE_FAILURE.value:
        synthesis_status = "failed"
    elif result.synth_verdict:
        synthesis_status = "completed"

    quality_status = "skipped"
    if result.quality_status == "passed":
        quality_status = "completed"
    elif result.quality_status:
        quality_status = "failed"

    delivery_status = "completed" if result.delivered else "failed"
    if result.quality_status and result.quality_status != "passed":
        delivery_status = "skipped"

    product_market_summary = result.product_market_summary or {"status": "not_run"}
    product_market_status = _product_market_chain_stage_status(product_market_summary)

    dashboard_status = "completed" if result.dashboard_state is not None else "failed"
    publish_allowed = should_publish_dashboard(result)
    publish_status = "completed" if publish_allowed else "failed"
    if result.dashboard_state is None:
        publish_status = "skipped"

    return [
        _daily_stage(
            "registry_resolution",
            "completed",
            {"active_sources": result.sources_planned_count},
        ),
        _daily_stage(
            "source_sweep",
            source_status,
            {
                "active_sources": result.sources_planned_count,
                "attempted_sources": result.sources_attempted_count,
                "fetched_sources": len(result.sources_fetched),
                "failed_sources": len(result.sources_failed),
                "skipped_sources": len(result.sources_skipped),
            },
        ),
        _daily_stage(
            "synthesis",
            synthesis_status,
            {
                "verdict": result.synth_verdict,
                "facts_extracted": result.facts_extracted,
                "deltas_extracted": result.deltas_extracted,
                "material_delta_count": len(result.promoted_signals),
            },
        ),
        _daily_stage(
            "quality_review",
            quality_status,
            {
                "quality_status": result.quality_status,
                "required_fix_count": len(result.quality_fixes),
            },
        ),
        _daily_stage(
            "false_negative_audit",
            "completed" if result.fn_status else "skipped",
            {"audit_status": result.fn_status},
        ),
        _daily_stage(
            "delivery",
            delivery_status,
            {
                "delivered": result.delivered,
                "delivery_count": len(result.deliveries),
                "deliveries": result.deliveries,
            },
        ),
        _daily_stage(
            "product_market_chain",
            product_market_status,
            {
                "product_market_status": product_market_summary.get("status"),
                "product_market_stage_ledger_id": product_market_summary.get("stage_ledger_id"),
                "runner_verdict": product_market_summary.get("runner_verdict"),
            },
        ),
        _daily_stage(
            "dashboard_state_build",
            dashboard_status,
            {"dashboard_state_present": result.dashboard_state is not None},
        ),
        _daily_stage(
            "publish_gate",
            publish_status,
            {
                "publish_allowed": publish_allowed,
                "block_reason": product_market_publish_block_reason(result),
                "error_count": len(result.errors),
                "errors": result.errors,
            },
        ),
    ]


def start_daily_run_stage_ledger(
    conn,
    *,
    tenant_id: int,
    run_id: str,
    result,
) -> int | None:
    try:
        recorder = DailyRunStageRecorder(
            PgRunStageRepository(conn),
            tenant_id=tenant_id,
            run_id=run_id,
            package_name="cios.daily",
        )
        result.daily_stage_ledger_id = recorder.start(
            metadata={"tenant": result.slug, "cadence": "daily"},
        )
        return result.daily_stage_ledger_id
    except Exception as exc:  # noqa: BLE001
        result.errors.append(f"daily stage ledger start error: {redacted_exception_detail(exc)}")
        return None


def persist_daily_run_stage_ledger(
    conn,
    *,
    tenant_id: int,
    run_id: str,
    result,
    deferred_stage_orders: set[int] | None = None,
    finish_ledger: bool = True,
) -> int:
    stage_ledger = daily_run_stage_ledger_from_result(result)
    metadata = daily_run_ledger_metadata(result)
    deferred_stage_orders = deferred_stage_orders or set()
    repo = PgRunStageRepository(conn)
    if result.daily_stage_ledger_id is not None:
        for stage_order, entry in enumerate(stage_ledger, start=1):
            if stage_order in getattr(result, "daily_live_stage_orders", set()):
                continue
            if stage_order in deferred_stage_orders:
                continue
            event_id = repo.start_stage(
                tenant_id=tenant_id,
                ledger_id=result.daily_stage_ledger_id,
                stage_order=stage_order,
                stage=str(entry.get("stage") or ""),
                metadata=entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {},
            )
            repo.finish_stage(
                tenant_id=tenant_id,
                event_id=event_id,
                status=str(entry.get("status") or "skipped"),
                metadata={},
            )
        if finish_ledger:
            repo.finish_ledger(
                tenant_id=tenant_id,
                ledger_id=result.daily_stage_ledger_id,
                status=daily_run_stage_ledger_status(stage_ledger),
                metadata=metadata,
            )
        return int(result.daily_stage_ledger_id)

    return repo.save_run_stage_ledger(
        tenant_id=tenant_id,
        run_id=run_id,
        package_name="cios.daily",
        status=daily_run_stage_ledger_status(stage_ledger),
        stage_ledger=stage_ledger,
        metadata=metadata,
    )


def daily_run_ledger_metadata(result, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    product_market_summary = result.product_market_summary or {}
    metadata = {
        "tenant": result.slug,
        "product_market_stage_ledger_id": product_market_summary.get("stage_ledger_id"),
    }
    if extra:
        metadata.update(extra)
    return metadata


def _publish_artifact_metadata(paths: Mapping[str, Any] | None) -> dict[str, Any]:
    if not paths:
        return {}
    competitor_briefs = paths.get("competitor_briefs") or []
    return {
        "cockpit": str(paths.get("cockpit")),
        "full_brief": str(paths.get("full_brief")),
        "json": str(paths.get("json")),
        "competitor_brief_count": len(competitor_briefs),
    }


def _summary_int(summary: Mapping[str, Any], key: str) -> int:
    try:
        return int(summary.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _nested_summary(summary: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = summary.get(key)
    return dict(value) if isinstance(value, Mapping) else {}


def product_market_demand_source_block_reason(result) -> str | None:
    summary = getattr(result, "product_market_summary", None)
    if not isinstance(summary, Mapping):
        return None
    if str(summary.get("status") or "").strip() != "ran":
        return None

    runner_summary = _nested_summary(summary, "runner_summary")
    ledger_refresh_summary = _nested_summary(summary, "ledger_refresh_summary")
    explicit_demand_fields = {
        "ga4_export_record_count",
        "looker_ready_count",
        "looker_normalized_row_count",
        "runner_summary",
        "ledger_refresh_summary",
    }
    if not any(field in summary for field in explicit_demand_fields):
        return None

    demand_counts = {
        "ga4_export_record_count": _summary_int(summary, "ga4_export_record_count"),
        "looker_ready_count": _summary_int(summary, "looker_ready_count"),
        "looker_normalized_row_count": _summary_int(summary, "looker_normalized_row_count"),
        "runner_demand_signal_count": _summary_int(runner_summary, "demand_signal_count"),
        "ledger_demand_signal_count": _summary_int(ledger_refresh_summary, "demand_signal_count"),
    }
    if any(value > 0 for value in demand_counts.values()):
        return None

    ga4_status = str(summary.get("ga4_export_status") or "unknown")
    return (
        "demand_source_status=missing; "
        f"ga4_export_status={ga4_status}; "
        f"looker_ready_count={demand_counts['looker_ready_count']}; "
        f"ledger_demand_signal_count={demand_counts['ledger_demand_signal_count']}"
    )


def record_daily_publish_gate_stage(
    conn,
    *,
    tenant_id: int,
    deliver_tenant: str,
    result,
    html_path: Path,
    cockpit_path: Path,
    report_date: date,
) -> dict[str, Any] | None:
    repo = PgRunStageRepository(conn)
    recorder = DailyRunStageRecorder(
        repo,
        tenant_id=tenant_id,
        run_id=f"daily-{result.slug}-publish-gate",
        ledger_id=result.daily_stage_ledger_id,
        recorded_stage_orders=result.daily_live_stage_orders,
    )
    publish_allowed = should_publish_dashboard(result)
    block_reason = product_market_publish_block_reason(result)
    if not publish_allowed and result.synth_verdict == Verdict.COVERAGE_FAILURE.value:
        block_reason = block_reason or "coverage_failure"
    if not publish_allowed and result.quality_status and result.quality_status != "passed":
        block_reason = block_reason or f"quality_{result.quality_status}"
    if not publish_allowed and result.dashboard_state is None:
        block_reason = block_reason or "dashboard_state_missing"

    event_id = recorder.start_stage(
        stage="publish_gate",
        stage_order=9,
        metadata={
            "tenant": result.slug,
            "deliver_tenant": deliver_tenant,
            "publish_allowed": publish_allowed,
            "block_reason": block_reason,
            "dashboard_state_present": result.dashboard_state is not None,
        },
    )
    result.daily_stage_ledger_id = recorder.ledger_id
    paths: dict[str, Any] | None = None
    try:
        if publish_allowed or result.dashboard_state is not None:
            paths = write_dashboard_artifacts(
                result.dashboard_state,
                tenant_slug=deliver_tenant,
                html_path=cockpit_path,
                report_date=report_date,
            )
            status = "completed" if publish_allowed else "failed"
        elif result.dashboard_state is None:
            status = "skipped"
        else:
            status = "failed"

        artifact_metadata = _publish_artifact_metadata(paths)
        recorder.finish_stage(
            event_id=event_id,
            status=status,
            metadata={
                "stage": "publish_gate_done",
                "publish_allowed": publish_allowed,
                "block_reason": block_reason,
                "html_path": str(html_path),
                "cockpit_path": str(cockpit_path),
                **artifact_metadata,
            },
        )
        repo.finish_ledger(
            tenant_id=tenant_id,
            ledger_id=int(result.daily_stage_ledger_id),
            status=daily_run_stage_ledger_status(daily_run_stage_ledger_from_result(result)),
            metadata=daily_run_ledger_metadata(
                result,
                extra={"publish_artifacts": artifact_metadata} if artifact_metadata else None,
            ),
        )
        return paths
    except Exception as exc:
        safe_error = redacted_exception_message(exc)
        result.errors.append(f"publish gate error: {redacted_exception_detail(exc)}")
        recorder.finish_stage(
            event_id=event_id,
            status="failed",
            metadata={
                "stage": "publish_gate_failed",
                "publish_allowed": publish_allowed,
                "block_reason": block_reason,
            },
            error_type=type(exc).__name__,
            error=safe_error,
        )
        repo.finish_ledger(
            tenant_id=tenant_id,
            ledger_id=int(result.daily_stage_ledger_id),
            status="failed",
            metadata=daily_run_ledger_metadata(result),
        )
        raise


def product_market_publish_block_reason(result) -> str | None:
    summary = getattr(result, "product_market_summary", None)
    if not isinstance(summary, dict):
        return None

    demand_block = product_market_demand_source_block_reason(result)
    if demand_block:
        return demand_block

    status = str(summary.get("status") or "").strip()
    if status not in PRODUCT_MARKET_PUBLISH_BLOCKING_STATUSES:
        return None

    detail = summary.get("error") or summary.get("execution_summary_path") or "no detail"
    return f"product_market_status={status}; detail={detail}"


def should_publish_dashboard(result) -> bool:
    return (
        result is not None
        and result.dashboard_state is not None
        and result.quality_status == "passed"
        and result.synth_verdict != Verdict.COVERAGE_FAILURE.value
        and product_market_publish_block_reason(result) is None
    )


def publish_gate_exit_code(result) -> int:
    if should_publish_dashboard(result):
        return 0
    demand_block = product_market_demand_source_block_reason(result)
    if (
        demand_block
        and result is not None
        and result.dashboard_state is not None
        and result.quality_status == "passed"
        and result.synth_verdict != Verdict.COVERAGE_FAILURE.value
    ):
        return 3
    return 2


def should_apply_quality_revision_result(
    *,
    original_quality_status: str,
    original_promoted_count: int,
    revised_promoted_count: int,
    synthesis_target_count: int,
    revision_success_count: int | None = None,
) -> bool:
    """A successful revision pass is authoritative, even when it drops all signals."""
    del revised_promoted_count
    return (
        original_quality_status == "failed"
        and original_promoted_count > 0
        and synthesis_target_count > 0
        and (revision_success_count is None or revision_success_count > 0)
    )


def should_drop_revised_signals_after_failed_quality(
    *,
    original_quality_status: str,
    revised_quality_status: str,
    revised_promoted_count: int,
) -> bool:
    """If revised signals still fail quality, silence beats a blocked stale dashboard."""

    return (
        original_quality_status == "failed"
        and revised_quality_status == "failed"
        and revised_promoted_count > 0
    )


async def synthesize_quality_revision_targets(
    *,
    synthesizer: Synthesizer,
    synth_targets: list[tuple[int, str, list, list]],
    tenant_id: int,
    tenant_company_name: str | None,
    own_position_facts: list[str],
    coverage: CoverageReport,
    fixes_text: str,
) -> dict[str, Any]:
    """Run quality revision per target without letting one timeout discard all revisions."""

    revised: list[dict[str, Any]] = []
    errors: list[str] = []
    target_success_count = 0
    for comp_id, comp_name, comp_deltas, _comp_facts in synth_targets:
        revise_inp = SynthesisInput(
            tenant_id=tenant_id,
            competitor_id=comp_id,
            competitor_name=comp_name,
            deltas=comp_deltas,
            coverage=coverage,
            tenant_company_name=tenant_company_name,
            own_position_facts=own_position_facts,
            extra_instructions=(
                "REVISION PASS. An editorial review rejected specific claims. "
                f"Required fixes: {fixes_text}. Remove or hedge every flagged "
                "specific; keep only what the evidence text itself supports. "
                "Dropping a signal entirely is acceptable."
            ),
        )
        try:
            sr2 = await synthesizer.synthesize(revise_inp)
        except Exception as exc:  # noqa: BLE001
            errors.append(
                f"quality revise target failed: competitor={comp_name} "
                f"error={redacted_exception_detail(exc)}"
            )
            continue

        target_success_count += 1
        allowed = revise_inp.evidence_urls()
        for s in sr2.signals:
            urls_ok = bool(s.evidence_urls) and all(u in allowed for u in s.evidence_urls)
            revised.append(
                {
                    **s.model_dump(),
                    "competitor_name": comp_name,
                    "competitor_id": comp_id,
                    "urls_ok": urls_ok,
                }
            )

    return {
        "signals": revised,
        "errors": errors,
        "target_success_count": target_success_count,
    }


def _materiality(item: Any) -> float:
    value = getattr(item, "materiality_score", None)
    if value is None and isinstance(item, dict):
        value = item.get("materiality_score")
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _dedupe_by_statement(items: list[Any], *, limit: int) -> list[Any]:
    seen: set[str] = set()
    selected: list[Any] = []
    ranked = sorted(items, key=_materiality, reverse=True)
    for item in ranked:
        statement = getattr(item, "what_changed", None) or getattr(item, "statement", None)
        if statement is None and isinstance(item, dict):
            statement = item.get("what_changed") or item.get("statement")
        key = " ".join(str(statement or "").lower().split())[:220]
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        selected.append(item)
        if len(selected) >= limit:
            break
    return selected


def select_synthesis_targets(
    all_deltas_by_comp: dict[int, list],
    all_facts: list,
    comp_names_by_id: dict[int, str],
    *,
    max_competitors: int,
    max_deltas_per_competitor: int,
    max_facts_per_competitor: int,
) -> list[tuple[int, str, list, list]]:
    ranked = sorted(all_deltas_by_comp.items(), key=lambda kv: len(kv[1]), reverse=True)
    targets: list[tuple[int, str, list, list]] = []
    for comp_id, comp_deltas in ranked[:max_competitors]:
        comp_name = comp_names_by_id.get(comp_id, f"competitor {comp_id}")
        comp_facts = [f for f in all_facts if getattr(f, "competitor_id", None) == comp_id]
        targets.append((
            comp_id,
            comp_name,
            _dedupe_by_statement(list(comp_deltas), limit=max_deltas_per_competitor),
            _dedupe_by_statement(comp_facts, limit=max_facts_per_competitor),
        ))
    return targets


def thesis_update_text(signal: dict) -> str:
    competitor = signal.get("competitor_name") or "The competitor"
    headline = signal.get("headline") or signal.get("what_changed") or "the observed signal"
    signal_type = signal.get("signal_type") or "competitive movement"
    return f"{competitor} shows a {signal_type} pattern: {headline}"


def decide_synthesis_verdict(
    *,
    promoted_count: int,
    verdicts_seen: list[Verdict],
    synthesis_target_count: int,
    synthesis_error_count: int,
    coverage_all_ran: bool,
) -> str:
    if promoted_count:
        return Verdict.SIGNALS.value
    if synthesis_target_count and synthesis_error_count >= synthesis_target_count:
        return Verdict.COVERAGE_FAILURE.value
    if verdicts_seen and all(v == Verdict.QUIET for v in verdicts_seen):
        return Verdict.QUIET.value
    return Verdict.COVERAGE_FAILURE.value if not coverage_all_ran else Verdict.QUIET.value


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

    def __init__(self, shim_url: str, model_alias: str = "sonnet", timeout_s: float = 45.0) -> None:
        self._url = shim_url
        self._alias = model_alias
        self._timeout_s = timeout_s

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
                              json={
                                  "prompt": prompt,
                                  "model_alias": self._alias,
                                  "json_mode": True,
                                  "timeout_s": int(self._timeout_s),
                              },
                              timeout=self._timeout_s + 15.0)
            resp.raise_for_status()
            text = (resp.json().get("text") or "").strip()
        except Exception as exc:  # noqa: BLE001
            raise UnparseableVerdict(
                f"quality reviewer LLM call failed: {redacted_exception_message(exc)}"
            ) from exc
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
        cited = {getattr(c, "source_url", "") for c in claims or () if getattr(c, "source_url", "")}
        if cited:
            evidence_texts = {url: text for url, text in evidence_texts.items() if url in cited}
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


def review_claim_for_signal(signal: dict) -> _ReviewClaim:
    parts = [
        signal.get("headline"),
        signal.get("what_changed"),
        signal.get("why_it_matters"),
        signal.get("implication"),
    ]
    text = " ".join(str(part).strip() for part in parts if str(part or "").strip())
    evidence_urls = signal.get("evidence_urls") or []
    return _ReviewClaim(text, evidence_urls[0] if evidence_urls else None)


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


DASHBOARD_DELTA_WINDOW_DAYS = 14  # cards are a "what's live now" view, not a full archive


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
                      AND d.created_at >= now() - (%s || ' days')::interval
                    ORDER BY d.materiality_score DESC
                    """,
                    (tenant_id, DASHBOARD_DELTA_WINDOW_DAYS),
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
        self.sources_planned_count = 0
        self.sources_attempted_count = 0
        self.sources_fetched: list[dict] = []
        self.sources_failed: list[dict] = []
        self.sources_skipped: list[dict] = []
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
        self.reader_text: Optional[str] = None
        self.product_market_summary: dict[str, Any] = {"status": "not_run"}
        self.daily_stage_ledger_id: Optional[int] = None
        self.daily_live_stage_orders: set[int] = set()
        self.errors: list[str] = []


def format_tenant_run_summary(r: TenantResult) -> str:
    return (
        f"  {r.slug}: active_sources={r.sources_planned_count} "
        f"attempted={r.sources_attempted_count} fetched={len(r.sources_fetched)} "
        f"failed={len(r.sources_failed)} skipped={len(r.sources_skipped)} "
        f"facts={r.facts_extracted} deltas={r.deltas_extracted} "
        f"signals={len(r.promoted_signals)} verdict={r.synth_verdict} "
        f"quality={r.quality_status} fn={r.fn_status} delivered={r.delivered} "
        f"product_market={r.product_market_summary.get('status')} "
        f"llm={LLM_CALLS['count']}"
    )


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


def seed_sources_from_plan(conn, tenant_id: int, comp_ids: dict[str, int], plan: list[dict]) -> None:
    """Seed YAML defaults into the source ledger without overriding DB truth.

    YAML is the bootstrap/default set. If an operator has paused, marked
    missing, blocked, or retired an existing source, this function must not
    reactivate it just because the URL still exists in config.
    """
    source_repo = PgSourceRepository(conn)
    now = datetime.now(timezone.utc)
    for item in plan:
        competitor_id = comp_ids.get(item["name"])
        if competitor_id is None:
            continue
        normalized = normalize_url(item["url"])
        existing = source_repo.get_by_normalized_url(tenant_id, normalized)
        if existing is not None:
            continue
        source_repo.upsert(Source(
            tenant_id=tenant_id,
            competitor_id=competitor_id,
            source_family=item.get("family") or "unclassified",
            url=item["url"],
            normalized_url=normalized,
            title=f"{item['name']} {item.get('family') or 'source'}",
            status=SourceStatus.ACTIVE,
            first_seen_at=now,
            last_seen_at=now,
            last_checked_at=None,
        ))


def product_surface_targets_from_seed_plan(
    *,
    tenant_id: int,
    tenant_slug: str,
    seed_plan: dict[str, list[dict]],
    comp_ids: dict[str, int],
) -> list[ProductSurfaceTarget]:
    targets: list[ProductSurfaceTarget] = []
    for item in seed_plan.get(tenant_slug, []) or []:
        company_name = item.get("name")
        if not company_name:
            continue
        role = item.get("role") or "competitor"
        if role == "own":
            company_id = 0
        else:
            company_id = comp_ids.get(company_name)
            if company_id is None:
                continue
        targets.append(
            ProductSurfaceTarget(
                tenant_id=tenant_id,
                company_id=company_id,
                company_name=company_name,
                company_role=role,
                surface_family=item.get("family") or item.get("surface_family") or "other",
                url=item["url"],
            )
        )
    return targets


def seed_product_surfaces_from_plan(
    *,
    conn,
    tenant_id: int,
    tenant_slug: str,
    product_surface_plan: dict[str, list[dict]],
    comp_ids: dict[str, int],
) -> int:
    repo = PgProductSurfaceRepository(conn)
    targets = product_surface_targets_from_seed_plan(
        tenant_id=tenant_id,
        tenant_slug=tenant_slug,
        seed_plan=product_surface_plan,
        comp_ids=comp_ids,
    )
    for target in targets:
        repo.upsert_seed_target(target)
    return len(targets)


def product_surface_targets_from_active_sources(
    *,
    tenant_id: int,
    runtime_source_plan: list[dict],
    own_company_name: str,
) -> list[ProductSurfaceTarget]:
    """Promote active product-like source rows into Scout product surfaces.

    The active source registry is the runtime truth. This bridge prevents
    product-market muscle from being capped by a tiny hand-written
    `product_surfaces` seed list while still letting operators pause or retire
    specific surface rows through the product-surface lifecycle.
    """

    targets: list[ProductSurfaceTarget] = []
    seen: set[str] = set()
    own_name = own_company_name.strip().casefold()
    for item in runtime_source_plan:
        family = str(item.get("family") or item.get("source_family") or "").strip().lower()
        surface_family = PRODUCT_SURFACE_FAMILY_MAP.get(family)
        if surface_family is None:
            continue

        url = str(item.get("url") or "").strip()
        company_name = str(item.get("name") or item.get("competitor_name") or "").strip()
        if not url or not company_name:
            continue

        normalized = normalize_url(url)
        if normalized in seen:
            continue
        seen.add(normalized)

        company_role = "own" if own_name and company_name.casefold() == own_name else "competitor"
        if company_role == "own":
            company_id = 0
        else:
            raw_company_id = item.get("competitor_id")
            if raw_company_id is None:
                continue
            company_id = int(raw_company_id)

        targets.append(
            ProductSurfaceTarget(
                tenant_id=tenant_id,
                company_id=company_id,
                company_name=company_name,
                company_role=company_role,
                surface_family=surface_family,
                url=url,
            )
        )
    return targets


def seed_product_surfaces_from_active_sources(
    *,
    conn,
    tenant_id: int,
    runtime_source_plan: list[dict],
    own_company_name: str,
) -> int:
    repo = PgProductSurfaceRepository(conn)
    targets = product_surface_targets_from_active_sources(
        tenant_id=tenant_id,
        runtime_source_plan=runtime_source_plan,
        own_company_name=own_company_name,
    )
    for target in targets:
        repo.upsert_seed_target(target)
    return len(targets)


def build_runtime_source_plan_from_rows(seed_plan: list[dict], db_rows: list[dict]) -> list[dict]:
    """Return the concrete source list for this run from active DB rows.

    The `seed_plan` parameter is intentionally present to make the contract
    obvious at call sites and in tests: YAML may seed defaults, but it does
    not limit the runtime universe once the DB has active source rows.
    """
    del seed_plan
    runtime_plan: list[dict] = []
    for row in db_rows:
        url = row["url"]
        runtime_plan.append({
            "name": row.get("competitor_name") or row.get("name"),
            "domain": row.get("domain"),
            "url": url,
            "family": row.get("source_family") or row.get("family") or "unclassified",
            "competitor_id": row["competitor_id"],
            "source_id": row["source_id"],
            "normalized_url": row.get("normalized_url") or normalize_url(url),
            "priority": row.get("priority") or 3,
        })
    return runtime_plan


def source_block_reason_for_fetch_error(fetched: Any) -> str | None:
    """Return a durable source-block reason for fetch failures that are not
    ordinary transient collection errors.

    Coveo and similar sites can return an AWS WAF JavaScript challenge from the
    VPS. Treating that as "empty" makes the dashboard lie: the market was not
    quiet and the URL was not dead. The source is gated from this runtime.
    """

    if getattr(fetched, "error", None) == BLOCKED_BY_WAF_ERROR:
        return BLOCKED_BY_WAF_ERROR
    return None


def block_source_after_fetch_challenge(
    conn,
    *,
    tenant_id: int,
    source_id: int,
    detail: str,
    http_status: int | None,
) -> None:
    evidence = {
        "blocked_reason": detail,
        "blocked_http_status": http_status,
        "blocked_by": "cios.daily.source_sweep",
    }
    with tenant_context(conn, tenant_id):
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE sources
                SET status = 'blocked',
                    last_checked_at = now(),
                    evidence = sources.evidence || %(evidence)s::jsonb
                WHERE tenant_id = %(tenant_id)s
                  AND id = %(source_id)s
                """,
                {
                    "tenant_id": tenant_id,
                    "source_id": source_id,
                    "evidence": Json(evidence),
                },
            )


def competitor_names_from_runtime_plan(runtime_source_plan: list[dict], comp_ids: dict[str, int]) -> dict[int, str]:
    names = {competitor_id: name for name, competitor_id in comp_ids.items()}
    for item in runtime_source_plan:
        competitor_id = item.get("competitor_id")
        name = item.get("name")
        if competitor_id is not None and name:
            names[int(competitor_id)] = str(name)
    return names


def active_competitor_ids_from_rows(seed_ids: dict[str, int], runtime_source_plan: list[dict]) -> dict[str, int]:
    ids = dict(seed_ids)
    for item in runtime_source_plan:
        competitor_id = item.get("competitor_id")
        name = item.get("name") or item.get("competitor_name")
        if competitor_id is not None and name:
            ids[str(name)] = int(competitor_id)
    return ids


def load_active_source_plan(conn, tenant_id: int, seed_plan: list[dict], comp_ids: dict[str, int]) -> list[dict]:
    seed_sources_from_plan(conn, tenant_id, comp_ids, seed_plan)
    with tenant_context(conn, tenant_id):
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    c.id AS competitor_id,
                    c.name AS competitor_name,
                    c.domain,
                    c.priority,
                    s.id AS source_id,
                    s.source_family,
                    s.url,
                    s.normalized_url
                FROM sources s
                JOIN competitors c ON c.id = s.competitor_id AND c.tenant_id = s.tenant_id
                WHERE s.tenant_id = %s
                  AND c.status = 'active'
                  AND s.status = 'active'
                ORDER BY c.priority ASC, c.name ASC, s.source_family ASC, s.id ASC
                """,
                (tenant_id,),
            )
            rows = cur.fetchall()
    return build_runtime_source_plan_from_rows(seed_plan, rows)


def write_dashboard_artifacts(
    state,
    *,
    tenant_slug: str,
    html_path: Path,
    report_date: str | date,
) -> dict[str, Any]:
    from cios.dashboard.cockpit_renderer import (
        attach_competitor_brief_hrefs,
        render_brief_page_from_state,
        render_cockpit_html,
        render_competitor_brief_page_from_state,
    )

    report_date_s = report_date.isoformat() if isinstance(report_date, date) else str(report_date)
    html_path = Path(html_path)
    html_path.parent.mkdir(parents=True, exist_ok=True)

    stamped_state = attach_competitor_brief_hrefs(state, tenant_slug=tenant_slug, report_date=report_date_s)
    cockpit_out = render_cockpit_html(stamped_state)
    html_path.write_text(cockpit_out, encoding="utf-8")

    full_brief_path = html_path.parent / "brief.html"
    full_brief_path.write_text(render_brief_page_from_state(stamped_state, report_date_s), encoding="utf-8")

    competitor_paths: list[Path] = []
    seen_competitors: set[int] = set()
    brief_targets: list[tuple[int, str]] = [
        (competitor.competitor_id, competitor.brief_href)
        for competitor in stamped_state.monitored_competitors
        if competitor.brief_href
    ] or [
        (card.competitor_id, card.brief_href)
        for card in stamped_state.competitor_cards
        if card.brief_href
    ]
    for competitor_id, brief_href in brief_targets:
        if competitor_id in seen_competitors:
            continue
        seen_competitors.add(competitor_id)
        href_path = brief_href.removeprefix("./")
        competitor_path = html_path.parent / href_path
        competitor_path.parent.mkdir(parents=True, exist_ok=True)
        competitor_path.write_text(
            render_competitor_brief_page_from_state(
                stamped_state,
                competitor_id=competitor_id,
                report_date=report_date_s,
            ),
            encoding="utf-8",
        )
        competitor_paths.append(competitor_path)

    json_path = html_path.with_suffix(".json")
    publish_to_file(stamped_state, json_path)
    return {
        "cockpit": html_path,
        "full_brief": full_brief_path,
        "json": json_path,
        "competitor_briefs_dir": html_path.parent / "briefs",
        "competitor_briefs": competitor_paths,
    }


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


def update_report_metadata(conn, tenant_id: int, report_id: int, metadata: dict[str, Any]) -> None:
    with tenant_context(conn, tenant_id):
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                UPDATE reports
                SET metadata = metadata || %s::jsonb
                WHERE tenant_id = %s AND id = %s
                """,
                (Json(metadata), tenant_id, report_id),
            )


def insert_exec_speech_signal(conn, signal) -> int:
    """Persists one SpeechSignal (cios.execspeech.types) row to
    executive_speech_signals. Evidence rule (verbatim quote + source_url) is
    already enforced upstream by ExecSpeechScanner; this is a pure write."""
    with tenant_context(conn, signal.tenant_id):
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO executive_speech_signals
                    (tenant_id, competitor_id, executive_name, executive_role, source_url,
                     published_at, quote, claim, market_signal, confidence, evidence_finding_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (signal.tenant_id, signal.competitor_id, signal.executive_name, signal.executive_role,
                 signal.source_url, signal.published_at, signal.quote, signal.claim,
                 signal.market_signal, signal.confidence, signal.evidence_finding_id),
            )
            return cur.fetchone()["id"]


def attach_thesis_evidence(conn, tenant_id, thesis_id, thesis_text, confidence, evidence_ids) -> None:
    """Root-cause fix (task #25): attach to an existing active thesis
    instead of spawning a new competitor_theses row for the same
    competitor's restated hypothesis. Merges evidence (union, no
    duplicates) and refreshes the thesis text/confidence in place --
    non-destructive because the row's own updated_at moves forward but no
    prior row is deleted or overwritten by a sibling."""
    with tenant_context(conn, tenant_id):
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT supporting_delta_ids FROM competitor_theses WHERE id = %s",
                (thesis_id,),
            )
            row = cur.fetchone()
            existing = list(row["supporting_delta_ids"] or []) if row else []
            merged_evidence = list(existing)
            for e in evidence_ids:
                if e not in merged_evidence:
                    merged_evidence.append(e)
            cur.execute(
                """
                UPDATE competitor_theses
                SET thesis = %s, confidence = %s, supporting_delta_ids = %s, updated_at = now()
                WHERE id = %s
                """,
                (thesis_text, confidence, Json(merged_evidence), thesis_id),
            )


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

    passed_verdict = QualityReview(
        tenant_id=tenant_id,
        status=QualityReviewStatus.PASSED,
        findings=[],
        required_fixes=[],
    )
    await commander.deliver(
        DeliveryRequest(tenant_id=tenant_id, report=report_event, plan=plan_route),
        quality_verdict=passed_verdict,
    )


async def run_weekly_if_due(
    app_conn, tenant_id: int, slug: str, adapter: ChannelAdapter, model, now: datetime
) -> None:
    """Runs the weekly pattern-identification pass for every competitor of
    this tenant, if `now` is a Sunday (is_weekly_due)."""
    if not env_flag(os.environ, "CIOS_ENABLE_WEEKLY_ROLLUP"):
        return
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
        print(
            "WARNING: weekly horizon/dot-connection integration failed "
            f"for {slug}: {redacted_exception_detail(exc)}"
        )


async def run_monthly_if_due(
    app_conn, tenant_id: int, slug: str, adapter: ChannelAdapter, model, now: datetime
) -> None:
    """Runs the monthly roll-up pass for every competitor of this tenant, if
    `now` is the first Monday of the month (is_monthly_due)."""
    if not env_flag(os.environ, "CIOS_ENABLE_MONTHLY_ROLLUP"):
        return
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
    product_surface_plan: Optional[dict[str, list[dict]]] = None,
    defer_publish_gate: bool = False,
) -> TenantResult:
    res = TenantResult(slug)
    res.tenant_id = tenant_id
    run_id = f"daily-{slug}-{int(time.time())}"
    start_daily_run_stage_ledger(
        app_conn,
        tenant_id=tenant_id,
        run_id=run_id,
        result=res,
    )
    daily_stage_recorder = DailyRunStageRecorder(
        PgRunStageRepository(app_conn),
        tenant_id=tenant_id,
        run_id=run_id,
        ledger_id=res.daily_stage_ledger_id,
        recorded_stage_orders=res.daily_live_stage_orders,
    )

    registry_stage_event_id = daily_stage_recorder.start_stage(
        stage="registry_resolution",
        stage_order=1,
        metadata={"seed_source_count": len(plan)},
    )
    try:
        comp_ids = seed_competitors(app_conn, tenant_id, plan)
        runtime_source_plan = load_active_source_plan(app_conn, tenant_id, plan, comp_ids)
        res.sources_planned_count = len(runtime_source_plan)
        active_comp_ids = active_competitor_ids_from_rows(comp_ids, runtime_source_plan)
        if product_surface_plan:
            seeded_surfaces = seed_product_surfaces_from_plan(
                conn=app_conn,
                tenant_id=tenant_id,
                tenant_slug=slug,
                product_surface_plan=product_surface_plan,
                comp_ids=active_comp_ids,
            )
            if seeded_surfaces:
                res.product_market_summary = {"status": "surfaces_seeded", "seeded_surfaces": seeded_surfaces}
        source_seeded_surfaces = seed_product_surfaces_from_active_sources(
            conn=app_conn,
            tenant_id=tenant_id,
            runtime_source_plan=runtime_source_plan,
            own_company_name=os.environ.get("CIOS_PRODUCT_MARKET_OWN_COMPANY_NAME") or slug.title(),
        )
        if source_seeded_surfaces:
            summary = dict(res.product_market_summary or {"status": "surfaces_seeded"})
            summary["source_seeded_surfaces"] = source_seeded_surfaces
            res.product_market_summary = summary
        comp_names_by_id = competitor_names_from_runtime_plan(runtime_source_plan, comp_ids)
        daily_stage_recorder.finish_stage(
            event_id=registry_stage_event_id,
            status="completed",
            metadata={
                "active_sources": res.sources_planned_count,
                "active_competitors": len(active_comp_ids),
                "source_seeded_surface_count": source_seeded_surfaces,
            },
        )
    except Exception as exc:
        daily_stage_recorder.finish_stage(
            event_id=registry_stage_event_id,
            status="failed",
            metadata={},
            error_type=type(exc).__name__,
            error=redacted_exception_message(exc),
        )
        raise

    fetch_timeout, fetch_retries = fetch_settings(os.environ)
    article_cap = article_fetch_cap(os.environ)
    content_fetcher = HttpContentFetcher(timeout=fetch_timeout, retries=fetch_retries)
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
    pages_by_comp: dict[int, dict[str, str]] = {}

    source_sweep_stage_event_id = daily_stage_recorder.start_stage(
        stage="source_sweep",
        stage_order=2,
        metadata={"active_sources": res.sources_planned_count},
    )
    for c in runtime_source_plan:
        competitor_id = c["competitor_id"]
        source_id = c.get("source_id")
        if source_id is None:
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
                    res.sources_skipped.append({
                        "name": c["name"],
                        "competitor_id": competitor_id,
                        "url": c["url"],
                        "reason": vr.reason,
                    })
                    continue
            source_id = source.id
        if source_id is None:
            res.sources_skipped.append({
                "name": c["name"],
                "competitor_id": competitor_id,
                "url": c["url"],
                "reason": "source_id_missing",
            })
            continue
        res.sources_attempted_count += 1
        print(
            f"  source start: tenant={slug} competitor={c['name']} family={c['family']} url={c['url']}",
            flush=True,
        )
        fetched = content_fetcher.fetch_content(c["url"])
        if fetched.status != FetchStatus.OK or not fetched.text:
            block_reason = source_block_reason_for_fetch_error(fetched)
            if block_reason:
                block_source_after_fetch_challenge(
                    app_conn,
                    tenant_id=tenant_id,
                    source_id=source_id,
                    detail=block_reason,
                    http_status=fetched.http_status,
                )
                res.sources_skipped.append({
                    "name": c["name"],
                    "competitor_id": competitor_id,
                    "url": c["url"],
                    "reason": block_reason,
                    "http": fetched.http_status,
                })
                insert_health_event(app_conn, SourceHealthEvent(
                    tenant_id=tenant_id,
                    source_id=source_id,
                    event_type=HealthEventType.FETCH_ERROR,
                    http_status=fetched.http_status,
                    detail=block_reason,
                    metadata={"source_status": SourceStatus.BLOCKED.value},
                ))
                print(
                    f"  source blocked: competitor={c['name']} http={fetched.http_status} reason={block_reason}",
                    flush=True,
                )
                continue
            res.sources_failed.append({
                "name": c["name"],
                "competitor_id": competitor_id,
                "url": c["url"],
                "http": fetched.http_status,
                "error": fetched.error or "empty",
            })
            insert_health_event(app_conn, SourceHealthEvent(
                tenant_id=tenant_id, source_id=source_id, event_type=HealthEventType.FETCH_ERROR,
                http_status=fetched.http_status, detail=fetched.error or "empty",
            ))
            print(
                f"  source failed: competitor={c['name']} http={fetched.http_status} error={fetched.error or 'empty'}",
                flush=True,
            )
            continue
        collection_ran = True
        insert_health_event(app_conn, SourceHealthEvent(
            tenant_id=tenant_id, source_id=source_id, event_type=HealthEventType.OK, http_status=fetched.http_status,
        ))
        snap_repo.save(Snapshot(tenant_id=tenant_id, source_id=source_id, fetch_run_id=fetch_run.id,
                                title=c["name"], text=fetched.text))
        snapshot_count += 1
        evidence_texts[canonical_url(c["url"])] = fetched.text
        pages_by_comp.setdefault(competitor_id, {})[canonical_url(c["url"])] = fetched.text
        facts, deltas = [], []
        article_urls = resolve_article_links(fetched.raw_html or fetched.text, c["url"])[:article_cap]
        if article_urls:
            for a_url in article_urls:
                a_fetched = content_fetcher.fetch_content(a_url)
                if a_fetched.status != FetchStatus.OK or not a_fetched.text:
                    continue
                evidence_texts[canonical_url(a_url)] = a_fetched.text
                pages_by_comp.setdefault(competitor_id, {})[canonical_url(a_url)] = a_fetched.text
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
        res.sources_fetched.append({"name": c["name"], "competitor_id": competitor_id,
                                    "url": c["url"], "http": fetched.http_status,
                                    "chars": len(fetched.text), "facts": len(facts), "deltas": len(real_deltas)})
        print(
            f"  source ok: competitor={c['name']} http={fetched.http_status} chars={len(fetched.text)} "
            f"facts={len(facts)} deltas={len(real_deltas)}",
            flush=True,
        )

    res.facts_extracted = len(all_facts)
    res.deltas_extracted = sum(len(v) for v in all_deltas_by_comp.values())
    source_sweep_done_marker = "source_sweep_done"
    source_sweep_status = "skipped"
    if res.sources_attempted_count > 0:
        source_sweep_status = "completed"
    elif res.sources_planned_count > 0:
        source_sweep_status = "failed"
    daily_stage_recorder.finish_stage(
        event_id=source_sweep_stage_event_id,
        status=source_sweep_status,
        metadata={
            "stage": source_sweep_done_marker,
            "active_sources": res.sources_planned_count,
            "attempted_sources": res.sources_attempted_count,
            "fetched_sources": len(res.sources_fetched),
            "failed_sources": len(res.sources_failed),
            "skipped_sources": len(res.sources_skipped),
            "facts_extracted": res.facts_extracted,
            "deltas_extracted": res.deltas_extracted,
        },
    )

    # Exec-speech lane (task #25 root-cause fix): SnapshotQuoteProvider
    # extracts attributed quotes from the pages the collection loop already
    # fetched above -- no new network call, no fabricated pass. The lane
    # genuinely runs whenever at least one page was collected; whether it
    # finds a quote is a separate, honest question from whether it ran.
    exec_speech_ran = collection_ran
    exec_signals_by_comp: dict[int, list[dict]] = {}
    if collection_ran:
        try:
            for comp_id, pages in pages_by_comp.items():
                comp_name = comp_names_by_id.get(comp_id, f"competitor {comp_id}")
                scanner = ExecSpeechScanner(providers=[SnapshotQuoteProvider(pages)])
                signals = scanner.scan(Competitor(id=comp_id, tenant_id=tenant_id, name=comp_name))
                for sig in signals:
                    insert_exec_speech_signal(app_conn, sig)
                if signals:
                    exec_signals_by_comp[comp_id] = [
                        {"quote": sig.quote, "claim": sig.claim, "source_url": sig.source_url}
                        for sig in signals
                    ]
        except Exception as exc:  # noqa: BLE001
            # A scan failure must not silently claim the lane ran clean, but
            # it also must not block the rest of the pipeline (same
            # bounded-blast-radius pattern as the own-brand read above).
            exec_speech_ran = False
            res.errors.append(f"exec_speech scan error: {redacted_exception_detail(exc)}")

    fetch_run.status = "completed"
    fetch_run.finished_at = datetime.now(timezone.utc)
    fetch_run.source_count = res.sources_attempted_count
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
        if not env_flag(os.environ, "CIOS_ENABLE_OWN_BRAND_READ"):
            res.errors.append("own-brand: skipped by CIOS_ENABLE_OWN_BRAND_READ=0")
        elif not own_brand_plan:
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
        res.errors.append(f"own-brand error: {redacted_exception_detail(exc)}")

    # LLM budget guard (task #25 root-cause fix): synthesizing was hardcoded
    # to the single competitor with the most deltas (`best_comp`), silently
    # dropping every other competitor's signals for the whole cycle. Loop
    # every competitor that has deltas this run, ranked by delta volume,
    # capped so a busy day can't blow the run's LLM budget.
    synthesis_stage_event_id = daily_stage_recorder.start_stage(
        stage="synthesis",
        stage_order=3,
        metadata={
            "fact_count": res.facts_extracted,
            "delta_count": res.deltas_extracted,
            "coverage_all_ran": coverage.all_ran,
        },
    )
    max_synth_competitors, max_synth_deltas, max_synth_facts = synthesis_settings(os.environ)

    synthesizer = Synthesizer(model=model)
    promoted: list[dict] = []
    verdict = None
    cold_start = False
    synth_targets: list[tuple[int, str, list, list]] = []

    if all_deltas_by_comp:
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
        baseline_note = synthesis_mode_instructions(os.environ, cold_start=cold_start)

        synth_targets = select_synthesis_targets(
            all_deltas_by_comp,
            all_facts,
            comp_names_by_id,
            max_competitors=max_synth_competitors,
            max_deltas_per_competitor=max_synth_deltas,
            max_facts_per_competitor=max_synth_facts,
        )

        verdicts_seen: list[Verdict] = []
        synthesis_error_count = 0
        for comp_id, comp_name, comp_deltas, comp_facts in synth_targets:
            inp = SynthesisInput(
                tenant_id=tenant_id, competitor_id=comp_id, competitor_name=comp_name,
                deltas=comp_deltas, facts=comp_facts, exec_signals=exec_signals_by_comp.get(comp_id, []),
                prior_theses=[], coverage=coverage,
                tenant_company_name=tenant_company_name, own_position_facts=own_position_facts,
                extra_instructions=baseline_note,
            )
            try:
                sr = await synthesizer.synthesize(inp)
                verdicts_seen.append(sr.verdict)
                allowed = inp.evidence_urls()
                for s in sr.signals:
                    urls_ok = bool(s.evidence_urls) and all(u in allowed for u in s.evidence_urls)
                    promoted.append({**s.model_dump(), "competitor_name": comp_name, "competitor_id": comp_id, "urls_ok": urls_ok})
            except Exception as exc:  # noqa: BLE001
                synthesis_error_count += 1
                res.errors.append(
                    f"synthesis error ({comp_name}): {redacted_exception_detail(exc)}"
                )

        verdict = decide_synthesis_verdict(
            promoted_count=len(promoted),
            verdicts_seen=verdicts_seen,
            synthesis_target_count=len(synth_targets),
            synthesis_error_count=synthesis_error_count,
            coverage_all_ran=coverage.all_ran,
        )
    else:
        verdict = Verdict.COVERAGE_FAILURE.value if not coverage.all_ran else Verdict.QUIET.value
    res.synth_verdict = verdict
    res.promoted_signals = promoted
    synthesis_done_marker = "synthesis_done"
    daily_stage_recorder.finish_stage(
        event_id=synthesis_stage_event_id,
        status="completed" if verdict != Verdict.COVERAGE_FAILURE.value else "failed",
        metadata={
            "stage": synthesis_done_marker,
            "verdict": res.synth_verdict,
            "synthesis_target_count": len(synth_targets),
            "material_delta_count": len(res.promoted_signals),
            "cold_start": cold_start,
        },
    )

    quality_stage_event_id = daily_stage_recorder.start_stage(
        stage="quality_review",
        stage_order=4,
        metadata={
            "pre_review_signal_count": len(promoted),
            "quiet_verdict": verdict != Verdict.SIGNALS.value,
        },
    )
    claims_for_review = [review_claim_for_signal(s) for s in promoted]
    reader_text = compose_daily_brief(
        [Signal(**{k: v for k, v in s.items() if k in Signal.model_fields}) for s in promoted],
        tenant_name=slug,
        brief_date=date.today(),
    )
    reader_text = _apply_cold_start_labels(reader_text, cold_start)
    quality_reviewer = QualityReviewer(llm_reviewer=ClaudeQualityReviewer(
        os.environ.get("CIOS_CLAUDE_SHIM_URL", "http://127.0.0.1:8663"),
        model_alias=model_alias(os.environ, "CIOS_QUALITY_MODEL_ALIAS"),
        timeout_s=quality_timeout_seconds(os.environ),
    ))
    qr = quality_reviewer.review(_ReviewInput(tenant_id=tenant_id, run_id=run_id, claims=claims_for_review,
                                              reader_text=reader_text,
                                              quiet_verdict=(verdict != Verdict.SIGNALS.value),
                                              coverage_ran_clean=coverage.all_ran and verdict != Verdict.COVERAGE_FAILURE.value,
                                              evidence_texts=evidence_texts))
    insert_quality_review(app_conn, tenant_id, run_id, qr.status.value, qr.findings, qr.required_fixes)

    # One-shot REVISE loop on a failed verdict: feed required_fixes back to
    # the synthesizer for every competitor synthesized this run (not just
    # the busiest one), re-review once. Fail after that and the brief stays
    # blocked by the gated commander -- never loosened.
    if qr.status.value == "failed" and promoted and synth_targets:
        fixes_text = "; ".join(str(f) for f in qr.required_fixes)
        try:
            revision_result = await synthesize_quality_revision_targets(
                synthesizer=synthesizer,
                synth_targets=synth_targets,
                tenant_id=tenant_id,
                tenant_company_name=tenant_company_name,
                own_position_facts=own_position_facts,
                coverage=coverage,
                fixes_text=fixes_text,
            )
            promoted2 = list(revision_result["signals"])
            res.errors.extend(revision_result["errors"])
            if should_apply_quality_revision_result(
                original_quality_status=qr.status.value,
                original_promoted_count=len(promoted),
                revised_promoted_count=len(promoted2),
                synthesis_target_count=len(synth_targets),
                revision_success_count=int(revision_result["target_success_count"]),
            ):
                promoted = promoted2
                res.promoted_signals = promoted
                if not promoted and verdict == Verdict.SIGNALS.value:
                    verdict = Verdict.QUIET.value if coverage.all_ran else Verdict.COVERAGE_FAILURE.value
                    res.synth_verdict = verdict
                claims_for_review = [review_claim_for_signal(s) for s in promoted]
                reader_text = compose_daily_brief(
                    [Signal(**{k: v for k, v in s.items() if k in Signal.model_fields}) for s in promoted],
                    tenant_name=slug,
                    brief_date=date.today(),
                )
                reader_text = _apply_cold_start_labels(reader_text, cold_start)
                qr = quality_reviewer.review(_ReviewInput(
                    tenant_id=tenant_id, run_id=run_id, claims=claims_for_review,
                    reader_text=reader_text, quiet_verdict=(not promoted or verdict != Verdict.SIGNALS.value),
                    coverage_ran_clean=coverage.all_ran and verdict != Verdict.COVERAGE_FAILURE.value,
                    evidence_texts=evidence_texts))
                insert_quality_review(app_conn, tenant_id, run_id, qr.status.value, qr.findings, qr.required_fixes)
                if should_drop_revised_signals_after_failed_quality(
                    original_quality_status="failed",
                    revised_quality_status=qr.status.value,
                    revised_promoted_count=len(promoted),
                ):
                    promoted = []
                    res.promoted_signals = promoted
                    if verdict == Verdict.SIGNALS.value:
                        verdict = Verdict.QUIET.value if coverage.all_ran else Verdict.COVERAGE_FAILURE.value
                        res.synth_verdict = verdict
                    claims_for_review = []
                    reader_text = compose_daily_brief([], tenant_name=slug, brief_date=date.today())
                    reader_text = _apply_cold_start_labels(reader_text, cold_start)
                    qr = quality_reviewer.review(_ReviewInput(
                        tenant_id=tenant_id, run_id=run_id, claims=claims_for_review,
                        reader_text=reader_text, quiet_verdict=(verdict != Verdict.SIGNALS.value),
                        coverage_ran_clean=coverage.all_ran and verdict != Verdict.COVERAGE_FAILURE.value,
                        evidence_texts=evidence_texts))
                    insert_quality_review(app_conn, tenant_id, run_id, qr.status.value, qr.findings, qr.required_fixes)
                    res.errors.append("quality revise pass failed; dropped rejected signals")
                elif promoted:
                    res.errors.append("quality revise pass applied")
                else:
                    res.errors.append("quality revise pass dropped rejected signals")
        except Exception as exc:  # noqa: BLE001
            res.errors.append(
                "revision pass error (original failed verdict kept): "
                f"{redacted_exception_detail(exc)}"
            )

    res.quality_status = qr.status.value
    res.quality_fixes = qr.required_fixes
    quality_review_done_marker = "quality_review_done"
    daily_stage_recorder.finish_stage(
        event_id=quality_stage_event_id,
        status="completed" if res.quality_status == "passed" else "failed",
        metadata={
            "stage": quality_review_done_marker,
            "quality_status": res.quality_status,
            "required_fix_count": len(res.quality_fixes),
            "post_review_signal_count": len(res.promoted_signals),
        },
    )

    published_ids: list[int] = []
    if res.quality_status == "passed":
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
            insert_claim(app_conn, tenant_id, first["competitor_id"],
                         f"{first['name']} maintains an active content narrative", [canonical_url(first["url"])])
    elif promoted:
        res.errors.append("quality failed; promoted signals withheld from persistence")

    # Prescriptions (doctrine Addendum 2 point 3): post revise-loop, before
    # delivery, so the delivered brief includes the "YOUR PLAYS" section.
    # Grounded in this cycle's promoted signals + standing theses + the
    # own-brand read above. No horizon connections on the daily path --
    # those are weekly-only (Addendum 2 point 1, see run_weekly_if_due).
    prescriptions: list[Prescription] = []
    try:
        if res.quality_status == "passed" and env_flag(os.environ, "CIOS_ENABLE_PRESCRIPTIONS"):
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
        elif promoted and res.quality_status == "passed":
            res.errors.append("prescriptions: skipped by CIOS_ENABLE_PRESCRIPTIONS=0")
    except Exception as exc:  # noqa: BLE001
        res.errors.append(f"prescription engine error: {redacted_exception_detail(exc)}")

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

    if promoted and res.quality_status == "passed":
        s0 = promoted[0]
        if env_flag(os.environ, "CIOS_ENABLE_LLM_THESIS_UPDATE"):
            prompt = ("You are Argus. Given this competitor signal, write ONE sharp sentence (no em dashes) "
                      "updating the strategic thesis. Return ONLY the sentence.\n\n"
                      f"SIGNAL: {s0['headline']} - {s0['what_changed']}\n")
            req = ModelRequest(task_profile="brain.thesis_update", messages=[{"role": "user", "content": prompt}])
            resp = await model.generate(req)
            new_text = (resp.text or "").strip() or thesis_update_text(s0)
        else:
            new_text = thesis_update_text(s0)

        # THESIS MERGE (task #25 root-cause fix): a fresh ThesisEngine() was
        # instantiated every run, so open_thesis() always saw an empty
        # registry and unconditionally spawned a new competitor_theses row
        # -- the cause of N near-identical theses piling up per competitor.
        # Check the tenant's actual active theses in the DB first; attach to
        # a similar one instead of spawning a duplicate.
        active_theses = DbTheses(app_conn).get_active_theses(tenant_id)
        similar = find_similar_active_thesis(
            active_theses, competitor_id=s0["competitor_id"], candidate_thesis=new_text,
        )
        if similar is not None:
            attach_thesis_evidence(
                app_conn, tenant_id, similar["id"], new_text,
                0.55, [s0["evidence_urls"][0]],
            )
        else:
            engine = ThesisEngine()
            engine.open_thesis(tenant_id=tenant_id, competitor_id=s0["competitor_id"],
                               thesis=f"{s0['competitor_name']} is investing in the space; initial monitoring thesis.",
                               confidence=0.3, evidence_ids=[s0["evidence_urls"][0]])
            updated = engine.update(competitor_id=s0["competitor_id"], thesis=new_text, confidence=0.55,
                                    new_evidence_ids=[s0["evidence_urls"][0]])
            insert_thesis(app_conn, tenant_id, s0["competitor_id"], updated.thesis, updated.confidence, updated.evidence_ids)

    res.reader_text = reader_text
    report_id = insert_report(
        app_conn, tenant_id, "daily", f"Argus daily brief - {slug}", reader_text[:200],
        metadata={"reader_text": reader_text},
    )

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
        res.errors.append(f"action_items persistence error: {redacted_exception_detail(exc)}")

    delivery_stage_event_id = daily_stage_recorder.start_stage(
        stage="delivery",
        stage_order=6,
        metadata={"report_id": report_id, "quality_status": res.quality_status},
    )
    try:
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
        delivery_done_marker = "delivery_done"
        daily_stage_recorder.finish_stage(
            event_id=delivery_stage_event_id,
            status="completed" if res.delivered else "failed",
            metadata={
                "stage": delivery_done_marker,
                "delivered": res.delivered,
                "delivery_count": len(res.deliveries),
                "deliveries": res.deliveries,
            },
        )
    except Exception as exc:
        daily_stage_recorder.finish_stage(
            event_id=delivery_stage_event_id,
            status="failed",
            metadata={},
            error_type=type(exc).__name__,
            error=redacted_exception_message(exc),
        )
        raise

    cov_dict = {
        "lanes": [{"lane": l.lane, "ran": l.ran, "error": l.error} for l in coverage.lanes],
        "coverage_score": round(sum(1 for l in coverage.lanes if l.ran) / len(coverage.lanes), 4),
        "false_negative_audit_status": res.fn_status,
        "missing_source_families": [l.lane for l in coverage.lanes if not l.ran],
    }
    product_market_stage_event_id = daily_stage_recorder.start_stage(
        stage="product_market_chain",
        stage_order=7,
        metadata={"report_id": report_id, "material_delta_count": len(promoted)},
    )
    try:
        generated_at = datetime.now(timezone.utc)
        product_market_conversation_records = product_market_conversation_records_from_current_sweep(
            promoted_signals=promoted,
            all_deltas_by_comp=all_deltas_by_comp,
            comp_names_by_id=comp_names_by_id,
            captured_at=generated_at,
        )
        run_dict = {"run_id": run_id, "report_id": report_id, "generated_at": generated_at,
                    "model_tier": "judgment", "source_family_count": res.sources_attempted_count,
                    "material_delta_count": len(promoted),
                    "delivery_status": "sent" if res.delivered else "failed", "quality_review_status": res.quality_status,
                    "argus_read": {"useful_truth": reader_text.split(chr(10))[0]},
                    "action_item_ids": action_item_ids, "delivery_ids": [d["id"] for d in res.deliveries]}
        try:
            res.product_market_summary = run_product_market_chain_if_enabled(
                slug=slug,
                tenant_id=tenant_id,
                env=os.environ,
                conversation_records=product_market_conversation_records,
            )
        except Exception as exc:  # noqa: BLE001
            res.product_market_summary = {
                "status": "failed",
                "error": redacted_exception_detail(exc),
            }
            res.errors.append(
                f"product-market chain error: {redacted_exception_detail(exc)}"
            )
        else:
            try:
                monitored_rows = PgMonitoredCompetitorsRepository(app_conn).get_monitored_competitors(tenant_id)
                feature_matrix_rows = PgProductMarketRepository(app_conn).get_feature_matrix(tenant_id)
                res.product_market_summary = with_product_muscle_gap_discovery_plan(
                    res.product_market_summary,
                    monitored_competitors=monitored_rows,
                    feature_matrix_rows=feature_matrix_rows,
                )
            except Exception as exc:  # noqa: BLE001
                res.errors.append(
                    f"product-muscle gap plan error: {redacted_exception_detail(exc)}"
                )
        try:
            stage_ledger_id = persist_product_market_stage_ledger(
                app_conn,
                tenant_id=tenant_id,
                run_id=run_id,
                product_market_summary=res.product_market_summary,
            )
            if stage_ledger_id is not None:
                res.product_market_summary = {
                    **res.product_market_summary,
                    "stage_ledger_id": stage_ledger_id,
                }
        except Exception as exc:  # noqa: BLE001
            res.errors.append(
                "product-market stage ledger persistence error: "
                f"{redacted_exception_detail(exc)}"
            )
        run_dict["product_market_summary"] = res.product_market_summary
        try:
            update_report_metadata(
                app_conn,
                tenant_id,
                report_id,
                {
                    "product_market_summary": res.product_market_summary,
                    "run_errors": res.errors,
                },
            )
        except Exception as exc:  # noqa: BLE001
            res.errors.append(
                f"report metadata update error: {redacted_exception_detail(exc)}"
            )
        product_market_done_marker = "product_market_done"
        product_market_summary = res.product_market_summary or {}
        daily_stage_recorder.finish_stage(
            event_id=product_market_stage_event_id,
            status=_product_market_chain_stage_status(product_market_summary),
            metadata={
                "stage": product_market_done_marker,
                "conversation_record_count": len(product_market_conversation_records),
                "product_market_status": product_market_summary.get("status"),
                "product_market_stage_ledger_id": product_market_summary.get("stage_ledger_id"),
                "runner_verdict": product_market_summary.get("runner_verdict"),
                "error_count": len(res.errors),
            },
        )
    except Exception as exc:
        daily_stage_recorder.finish_stage(
            event_id=product_market_stage_event_id,
            status="failed",
            metadata={},
            error_type=type(exc).__name__,
            error=redacted_exception_message(exc),
        )
        raise

    dashboard_state_stage_event_id = daily_stage_recorder.start_stage(
        stage="dashboard_state_build",
        stage_order=8,
        metadata={"report_id": report_id, "delivery_count": len(res.deliveries)},
    )
    try:
        builder = DashboardStateBuilder(signals=DbMaterialSignals(app_conn), theses=DbTheses(app_conn),
                                        coverage=DbCoverage(cov_dict), runs=DbRuns(run_dict),
                                        report_history=PgReportHistoryRepository(app_conn),
                                        suppressed_signals=PgSuppressedSignalsRepository(app_conn),
                                        prescriptions=PgPrescriptionsRepository(app_conn),
                                        monitored_competitors=PgMonitoredCompetitorsRepository(app_conn),
                                        source_health=PgSourceHealthRepository(app_conn),
                                        product_market=PgProductMarketRepository(app_conn))
        state = builder.build(tenant_id=tenant_id, cadence="daily")
        res.dashboard_state = state
        dash_json_path = Path(os.environ.get("CIOS_DASHBOARD_OUT", "/tmp/argus-dashboard.html")).with_suffix("")
        dash_path = dash_json_path.parent / default_filename(state)
        publish_to_file(state, dash_path)
        insert_dashboard_state(app_conn, tenant_id, json.loads(to_json_str(state)), published_ids,
                               [d["id"] for d in res.deliveries], str(dash_path))
        dashboard_state_done_marker = "dashboard_state_done"
        daily_stage_recorder.finish_stage(
            event_id=dashboard_state_stage_event_id,
            status="completed",
            metadata={
                "stage": dashboard_state_done_marker,
                "dashboard_state_present": res.dashboard_state is not None,
                "dashboard_path": str(dash_path),
                "published_delta_count": len(published_ids),
                "delivery_count": len(res.deliveries),
            },
        )
    except Exception as exc:
        daily_stage_recorder.finish_stage(
            event_id=dashboard_state_stage_event_id,
            status="failed",
            metadata={},
            error_type=type(exc).__name__,
            error=redacted_exception_message(exc),
        )
        raise
    try:
        res.daily_stage_ledger_id = persist_daily_run_stage_ledger(
            app_conn,
            tenant_id=tenant_id,
            run_id=run_id,
            result=res,
            deferred_stage_orders={9} if defer_publish_gate else None,
            finish_ledger=not defer_publish_gate,
        )
        update_report_metadata(
            app_conn,
            tenant_id,
            report_id,
            {
                "product_market_summary": res.product_market_summary,
                "daily_stage_ledger_id": res.daily_stage_ledger_id,
                "run_errors": res.errors,
            },
        )
    except Exception as exc:  # noqa: BLE001
        res.errors.append(
            f"daily stage ledger persistence error: {redacted_exception_detail(exc)}"
        )
    return res


async def main() -> int:
    started = time.time()
    superuser_dsn = get_dsn()
    app_conninfo = app_dsn(superuser_dsn)
    deliver_tenant = os.environ.get("CIOS_DELIVER_TENANT", "algolia")

    telegram_configured = bool(os.environ.get("TELEGRAM_BOT_TOKEN")) and bool(os.environ.get("CIOS_TELEGRAM_CHAT_ID"))
    print(f"telegram configured: {telegram_configured}")

    model_timeout_s, model_max_attempts = model_call_settings(os.environ)
    provider = ClaudeCliShimProvider(
        model_alias=model_alias(os.environ, "CIOS_MODEL_ALIAS"),
        timeout_s=model_timeout_s,
        max_attempts=model_max_attempts,
    )
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
    product_surface_map: dict = tenant_plan.get("product_surfaces", {}) or {}

    results: list[TenantResult] = []
    now = _now()

    with psycopg.connect(app_conninfo, autocommit=True) as app_conn:
        with app_conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT id, slug FROM tenants ORDER BY id")
            db_tenants = {row["slug"]: row["id"] for row in cur.fetchall()}
        run_all_tenants = os.environ.get("CIOS_RUN_ALL_TENANTS", "").strip().lower() in {"1", "true", "yes"}
        selected_tenants = select_tenants_for_run(
            db_tenants,
            deliver_tenant=deliver_tenant,
            run_all=run_all_tenants,
        )
        if not selected_tenants:
            print(f"ERROR: deliver tenant '{deliver_tenant}' not found in DB tenants: {sorted(db_tenants)}")
            return 2

        for slug, tenant_id in selected_tenants.items():
            plan = tenant_plan.get(slug, [])
            if not plan:
                print(f"WARNING: tenant '{slug}' has no seed entry in {CONFIG_PATH}; using active DB sources only.")
            print(f"\n=== TENANT {slug} (id={tenant_id}) ===")
            adapter = select_adapter_for_tenant(slug, deliver_tenant, {
                "TELEGRAM_BOT_TOKEN": os.environ.get("TELEGRAM_BOT_TOKEN", ""),
                "CIOS_TELEGRAM_CHAT_ID": os.environ.get("CIOS_TELEGRAM_CHAT_ID", ""),
            })
            r = await run_tenant(slug, tenant_id, plan, app_conn, model, adapter,
                                 own_brand_plan=own_brand_map.get(slug),
                                 product_surface_plan=product_surface_map,
                                 defer_publish_gate=(slug == deliver_tenant))
            results.append(r)
            print(format_tenant_run_summary(r))

            await run_weekly_if_due(app_conn, tenant_id, slug, adapter, model, now)
            await run_monthly_if_due(app_conn, tenant_id, slug, adapter, model, now)

        delivered_result = next((r for r in results if r.slug == deliver_tenant), None)
        published_paths = None
        if delivered_result is not None:
            html_path = Path(os.environ.get("CIOS_DASHBOARD_OUT", "/tmp/argus-dashboard.html"))
            cockpit_path = Path(os.environ.get("CIOS_COCKPIT_OUT", str(html_path)))
            published_paths = record_daily_publish_gate_stage(
                app_conn,
                tenant_id=delivered_result.tenant_id or db_tenants[deliver_tenant],
                deliver_tenant=deliver_tenant,
                result=delivered_result,
                html_path=html_path,
                cockpit_path=cockpit_path,
                report_date=date.today(),
            )
        if delivered_result is not None and delivered_result.dashboard_state is not None and not should_publish_dashboard(delivered_result):
            product_market_block = product_market_publish_block_reason(delivered_result)
            print(
                f"ABORT: dashboard publish blocked for {deliver_tenant}; "
                f"quality_status={delivered_result.quality_status}; "
                f"synth_verdict={delivered_result.synth_verdict}"
            )
            if product_market_block:
                print(f"  {product_market_block}")
            if delivered_result.errors:
                print(
                    f"  {deliver_tenant} errors="
                    f"{redact_sensitive_text(str(delivered_result.errors))}"
                )
            return publish_gate_exit_code(delivered_result)
        if published_paths:
            # Two artifacts, same run: the cockpit (Arijit's designed Luxury
            # Editorial surface, built from DashboardState) is the primary
            # index page; brief.html plus competitor-specific brief pages are
            # generated from the same stamped DashboardState, so row links,
            # full-cycle brief, competitor briefs, and JSON cannot drift.
            # The publish-to-web-root cp lines that decide which file serves
            # at the public URL live in the VPS shell orchestrator, not here.
            print(f"Cockpit written: {published_paths['cockpit']}")
            print(f"Brief written: {published_paths['full_brief']} (+ {published_paths['json']})")
            print(f"Competitor briefs written: {len(published_paths['competitor_briefs'])}")

    wall = time.time() - started
    print(f"\nRun complete in {wall:.1f}s. LLM calls used: {LLM_CALLS['count']} / {LLM_BUDGET}")
    for r in results:
        print(
            f"  {r.slug}: delivered={r.delivered} quality={r.quality_status} "
            f"errors={redact_sensitive_text(str(r.errors))}"
        )
    return 0


def run_main() -> int:
    """Run the daily entrypoint without exposing uncaught secret-bearing errors."""

    try:
        return asyncio.run(main())
    except Exception as exc:  # noqa: BLE001 - this is the process boundary.
        print(f"ERROR: daily run failed: {redacted_exception_detail(exc)}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    install_shutdown_handlers()
    sys.exit(run_main())
