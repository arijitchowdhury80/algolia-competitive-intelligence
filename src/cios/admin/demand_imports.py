"""Filesystem-backed demand import status for the local CI-OS admin app."""

from __future__ import annotations

import csv
import io
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cios.admin.types import (
    DemandImportCreate,
    DemandImportFile,
    DemandImportLedgerPersistResult,
    DemandImportPrepareResult,
    DemandImportPreview,
    DemandImportStatus,
    DemandImportUploadResult,
    Ga4ExportRunResult,
    Ga4ExportStatus,
)
from cios.intelligence.adapters import looker_row_to_demand_signal
from cios.intelligence.ga4_exporter import EXPLICIT_GA4_DATE_KEYS, resolve_ga4_date_windows
from cios.intelligence.importers import diagnose_looker_rows, load_export_records, normalize_looker_rows

ACCEPTED_DEMAND_SUFFIXES = (".csv", ".json", ".jsonl")
DEMAND_IMPORT_TEMPLATE_FIELDS = (
    "Page title",
    "Page path",
    "Engaged sessions",
    "Engaged sessions previous period",
    "Period start",
    "Period end",
    "Looker Studio URL",
)
DEMAND_IMPORT_TEMPLATE_CSV = ",".join(DEMAND_IMPORT_TEMPLATE_FIELDS) + "\n"
DEMAND_COLLECTION_PLAN_TEMPLATE_FIELDS = (
    *DEMAND_IMPORT_TEMPLATE_FIELDS,
    "Argus topic",
    "Capability key",
    "Assessment",
    "Suggested filters",
    "Related competitors",
    "Why collect",
    "Evidence URLs",
)
GA4_REQUIRED_ENV_KEYS = ("CIOS_GA4_PROPERTY_ID",)


def demand_collection_plan_template_csv(plan: dict[str, Any]) -> str:
    """Build a GA/Looker import work order from the latest Argus demand plan."""

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(DEMAND_COLLECTION_PLAN_TEMPLATE_FIELDS), lineterminator="\n")
    writer.writeheader()
    topics = plan.get("topics") if isinstance(plan, dict) else []
    if not isinstance(topics, list):
        topics = []
    for topic in topics:
        if not isinstance(topic, dict):
            continue
        writer.writerow(
            {
                "Argus topic": str(topic.get("topic") or ""),
                "Capability key": str(topic.get("capability_key") or ""),
                "Assessment": str(topic.get("assessment") or ""),
                "Suggested filters": " | ".join(_string_list(topic.get("suggested_filter_terms"))),
                "Related competitors": " | ".join(_string_list(topic.get("related_competitors"))),
                "Why collect": str(topic.get("why_collect") or ""),
                "Evidence URLs": " | ".join(_string_list(topic.get("evidence_urls"))),
            }
        )
    return output.getvalue()


def demand_collection_plan_operator_guide(
    plan: dict[str, Any] | None,
    *,
    tenant_slug: str,
) -> dict[str, Any]:
    """Return a public-safe operator guide for collecting Argus demand evidence."""

    topics = _planned_demand_topics(plan)
    status = "ready" if topics else "missing_plan"
    return {
        "tenant_slug": tenant_slug,
        "status": status,
        "template_filename": "argus-demand-plan-template.csv",
        "template_href": f"/api/tenants/{tenant_slug}/argus/demand-imports/template?planned=1",
        "upload_action": f"/admin/{tenant_slug}/argus/demand-imports",
        "refresh_action": f"/admin/{tenant_slug}/argus/demand-imports/refresh",
        "accepted_suffixes": list(ACCEPTED_DEMAND_SUFFIXES),
        "required_columns": list(DEMAND_IMPORT_TEMPLATE_FIELDS),
        "required_metric": "Engaged sessions",
        "required_comparison": "Engaged sessions previous period",
        "match_fields": [
            "Page title",
            "Page path",
            "Argus topic",
            "Capability key",
            "Suggested filters",
        ],
        "source_dashboard_field": _text_value((plan or {}).get("source_dashboard_field")) if isinstance(plan, dict) else "",
        "topic_count": len(topics),
        "topics": [_demand_operator_topic(topic) for topic in topics],
        "steps": [
            "Open GA4 or Looker for Algolia and select page-level rows for the current and previous comparison periods.",
            "Use the listed filter terms against page title, page path, or report search to find rows for each Argus topic.",
            "Fill the required metric and period columns in the Argus demand plan template without changing the Argus topic or capability fields.",
            "Upload the completed CSV, JSON, or JSONL file to the tenant demand import surface.",
            "Run Prepare demand and refresh Argus so Hermes can persist demand signals, replay the ledger, and update the public blocked/published state.",
        ],
    }


def _demand_operator_topic(topic: dict[str, Any]) -> dict[str, Any]:
    return {
        "topic": _text_value(topic.get("topic") or topic.get("capability_key")),
        "capability_key": _text_value(topic.get("capability_key")),
        "assessment": _text_value(topic.get("assessment")),
        "filter_terms": _demand_topic_terms(topic),
        "related_competitors": _string_list(topic.get("related_competitors")),
        "evidence_url_count": len(_string_list(topic.get("evidence_urls"))),
        "row_status": "needs_metrics",
    }


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def default_app_dir() -> Path:
    configured = os.environ.get("CIOS_APP_DIR")
    if configured:
        return Path(configured).expanduser()
    return Path(__file__).resolve().parents[3]


def default_work_root() -> Path:
    configured = os.environ.get("CIOS_PRODUCT_MARKET_WORK_DIR") or os.environ.get("CIOS_PRODUCT_MARKET_WORKDIR")
    if configured:
        return Path(configured).expanduser()
    return Path("/tmp/cios-product-market")


def _file_record(path: Path) -> DemandImportFile:
    stat = path.stat()
    return DemandImportFile(
        name=path.name,
        path=str(path),
        size_bytes=int(stat.st_size),
        modified_at=datetime.fromtimestamp(stat.st_mtime, timezone.utc),
    )


def _list_direct_files(directory: Path) -> list[DemandImportFile]:
    if not directory.is_dir():
        return []
    return [
        _file_record(path)
        for path in sorted(directory.iterdir(), key=lambda item: item.name)
        if path.is_file() and path.suffix.lower() in ACCEPTED_DEMAND_SUFFIXES
    ]


def _preview_file(path: Path, *, demand_plan: dict[str, Any] | None = None) -> DemandImportPreview:
    try:
        rows = load_export_records(path)
        normalized = normalize_looker_rows(rows, source_path=path)
    except Exception as exc:  # noqa: BLE001 - preview must report bad user files, not hide them.
        return DemandImportPreview(
            name=path.name,
            path=str(path),
            status="error",
            error=f"{exc.__class__.__name__}: {exc}",
        )

    topics = sorted({str(row.get("topic") or "").strip() for row in normalized if row.get("topic")})
    demand_plan_coverage = _demand_plan_coverage(demand_plan, normalized)
    return DemandImportPreview(
        name=path.name,
        path=str(path),
        status="ready" if normalized else "empty",
        raw_row_count=len(rows),
        normalized_row_count=len(normalized),
        skipped_row_count=max(0, len(rows) - len(normalized)),
        topics=topics,
        demand_plan_coverage=demand_plan_coverage,
    )


def _preview_direct_files(
    directory: Path,
    *,
    demand_plan: dict[str, Any] | None = None,
) -> list[DemandImportPreview]:
    if not directory.is_dir():
        return []
    return [
        _preview_file(path, demand_plan=demand_plan)
        for path in sorted(directory.iterdir(), key=lambda item: item.name)
        if path.is_file() and path.suffix.lower() in ACCEPTED_DEMAND_SUFFIXES
    ]


def _demand_plan_coverage(demand_plan: dict[str, Any] | None, rows: list[dict[str, Any]]) -> dict[str, Any]:
    planned_topics = _planned_demand_topics(demand_plan)
    if not planned_topics:
        return {}

    matched_by_key: dict[str, dict[str, Any]] = {}
    off_plan_count = 0
    for row in rows:
        match = _matching_demand_plan_topic(row, planned_topics)
        if match is None:
            off_plan_count += 1
            continue
        key = _demand_topic_key(match)
        if key and key not in matched_by_key:
            matched_by_key[key] = _demand_topic_summary(match)

    planned_by_key = {
        _demand_topic_key(topic): _demand_topic_summary(topic)
        for topic in planned_topics
        if _demand_topic_key(topic)
    }
    matched_keys = set(matched_by_key)
    missing_topics = [
        topic
        for key, topic in planned_by_key.items()
        if key not in matched_keys
    ]
    if len(matched_keys) == len(planned_by_key) and off_plan_count == 0:
        status = "covered"
    elif matched_keys:
        status = "partial_coverage"
    elif rows:
        status = "off_plan"
    else:
        status = "not_evaluated"
    return {
        "status": status,
        "planned_topic_count": len(planned_by_key),
        "matched_plan_topic_count": len(matched_keys),
        "off_plan_record_count": off_plan_count,
        "matched_topics": list(matched_by_key.values()),
        "missing_topics": missing_topics,
    }


def _annotate_rows_with_demand_plan(
    rows: list[dict[str, Any]],
    demand_plan: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    planned_topics = _planned_demand_topics(demand_plan)
    if not planned_topics:
        return rows
    annotated_rows: list[dict[str, Any]] = []
    for row in rows:
        annotated = dict(row)
        match = _matching_demand_plan_topic(annotated, planned_topics)
        if match is not None:
            annotated.update(_demand_plan_metadata(match))
            annotated["argus_plan_matched"] = True
        annotated_rows.append(annotated)
    return annotated_rows


def _demand_plan_metadata(topic: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    capability_key = _text_value(topic.get("capability_key") or topic.get("topic"))
    assessment = _text_value(topic.get("assessment"))
    why_collect = _text_value(topic.get("why_collect"))
    suggested_filters = _string_list(topic.get("suggested_filter_terms"))
    related_competitors = _string_list(topic.get("related_competitors"))
    evidence_urls = _string_list(topic.get("evidence_urls"))
    if capability_key:
        metadata["argus_capability_key"] = capability_key
    if assessment:
        metadata["argus_assessment"] = assessment
    if suggested_filters:
        metadata["argus_suggested_filters"] = suggested_filters
    if related_competitors:
        metadata["argus_related_competitors"] = related_competitors
    if why_collect:
        metadata["argus_why_collect"] = why_collect
    if evidence_urls:
        metadata["argus_evidence_urls"] = evidence_urls
    return metadata


def _planned_demand_topics(demand_plan: dict[str, Any] | None) -> list[dict[str, Any]]:
    topics = demand_plan.get("topics") if isinstance(demand_plan, dict) else None
    if not isinstance(topics, list):
        return []
    return [topic for topic in topics if isinstance(topic, dict)]


def _matching_demand_plan_topic(row: dict[str, Any], planned_topics: list[dict[str, Any]]) -> dict[str, Any] | None:
    row_key = _text_value(row.get("argus_capability_key") or row.get("capability_key"))
    if row_key:
        normalized_key = row_key.casefold()
        for topic in planned_topics:
            if normalized_key == _demand_topic_key(topic):
                return topic
    haystack = _demand_row_haystack(row)
    for topic in planned_topics:
        terms = _demand_topic_terms(topic)
        if any(term.casefold() in haystack for term in terms):
            return topic
    return None


def _demand_topic_terms(topic: dict[str, Any]) -> list[str]:
    candidates: list[Any] = []
    candidates.extend(_list_value(topic.get("suggested_filter_terms")))
    candidates.append(topic.get("topic"))
    candidates.append(topic.get("capability_key"))
    return _string_list(candidates)


def _demand_row_haystack(row: dict[str, Any]) -> str:
    parts = [
        row.get("topic"),
        row.get("excerpt"),
        row.get("source_file"),
        row.get("argus_capability_key"),
    ]
    return " ".join(_text_value(part) for part in parts if _text_value(part)).casefold()


def _demand_topic_key(topic: dict[str, Any]) -> str:
    return _text_value(topic.get("capability_key") or topic.get("topic")).casefold()


def _demand_topic_summary(topic: dict[str, Any]) -> dict[str, Any]:
    return {
        "topic": _text_value(topic.get("topic") or topic.get("capability_key")),
        "capability_key": _text_value(topic.get("capability_key")),
    }


def _text_value(value: Any) -> str:
    return str(value or "").strip()


def _list_value(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _normalized_filename(path: Path, seen: set[str]) -> str:
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


def _unique_destination(path: Path) -> Path:
    if not path.exists():
        return path
    index = 2
    while True:
        candidate = path.with_name(f"{path.stem}-{index}{path.suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def _list_nested_files(directory: Path) -> list[DemandImportFile]:
    if not directory.is_dir():
        return []
    files = [
        path
        for path in directory.rglob("*")
        if path.is_file() and path.suffix.lower() in ACCEPTED_DEMAND_SUFFIXES
    ]
    files.sort(key=lambda item: (item.stat().st_mtime, str(item)), reverse=True)
    return [_file_record(path) for path in files]


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            "error": "manifest_json_invalid",
            "path": str(path),
        }
    return data if isinstance(data, dict) else {"error": "manifest_not_object", "path": str(path)}


def _safe_upload_name(filename: str) -> str:
    path = Path(filename)
    name = path.name
    if not name or name != filename or name in {".", ".."}:
        raise ValueError("filename must be a safe basename")
    if path.suffix.lower() not in ACCEPTED_DEMAND_SUFFIXES:
        allowed = ", ".join(ACCEPTED_DEMAND_SUFFIXES)
        raise ValueError(f"demand import filename must end with one of: {allowed}")
    return name


def _env_flag(env: dict[str, str], key: str, *, default: bool = False) -> bool:
    value = env.get(key)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(env: dict[str, str], key: str, default: int) -> int:
    raw = (env.get(key) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _env_float(env: dict[str, str], key: str, default: float) -> float:
    raw = (env.get(key) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _safe_error(text: str, env: dict[str, str]) -> str:
    redacted = text
    for key in ("CIOS_GA4_CREDENTIALS_JSON", "GOOGLE_APPLICATION_CREDENTIALS", "CIOS_GA4_PROPERTY_ID"):
        value = env.get(key)
        if value:
            redacted = redacted.replace(value, "[redacted]")
    return redacted


def _unique_setup_keys(keys: list[str]) -> list[str]:
    results: list[str] = []
    seen: set[str] = set()
    for key in keys:
        if not key or key in seen:
            continue
        seen.add(key)
        results.append(key)
    return results


class DemandImportStore:
    """Reads and writes tenant demand export files without touching Hermes core."""

    def __init__(self, *, app_dir: Path | None = None, work_root: Path | None = None) -> None:
        self._app_dir = app_dir
        self._work_root = work_root

    @property
    def app_dir(self) -> Path:
        return self._app_dir or default_app_dir()

    @property
    def work_root(self) -> Path:
        return self._work_root or default_work_root()

    def drop_folder(self, tenant_slug: str) -> Path:
        return self.app_dir / "data" / "looker" / tenant_slug

    def manifest_path(self, tenant_slug: str) -> Path:
        return self.work_root / tenant_slug / "looker-export-manifest.json"

    def normalized_dir(self, tenant_slug: str) -> Path:
        return self.work_root / tenant_slug / "looker-normalized"

    def status(self, tenant_slug: str, *, demand_plan: dict[str, Any] | None = None) -> DemandImportStatus:
        drop_folder = self.drop_folder(tenant_slug)
        manifest_path = self.manifest_path(tenant_slug)
        manifest = _load_manifest(manifest_path)
        return DemandImportStatus(
            tenant_slug=tenant_slug,
            drop_folder=str(drop_folder),
            manifest_path=str(manifest_path),
            manifest_exists=manifest_path.exists(),
            discovered_count=int(manifest.get("discovered_count") or 0),
            ready_count=int(manifest.get("ready_count") or 0),
            error_count=int(manifest.get("error_count") or 0),
            normalized_row_count=int(manifest.get("normalized_row_count") or 0),
            skipped_row_count=int(manifest.get("skipped_row_count") or 0),
            manifest=manifest,
            inbox_files=_list_direct_files(drop_folder),
            inbox_previews=_preview_direct_files(drop_folder, demand_plan=demand_plan),
            archived_files=_list_nested_files(drop_folder / "_archive"),
            rejected_files=_list_nested_files(drop_folder / "_rejected"),
            accepted_suffixes=list(ACCEPTED_DEMAND_SUFFIXES),
        )

    def upload(
        self,
        tenant_slug: str,
        payload: DemandImportCreate,
        *,
        demand_plan: dict[str, Any] | None = None,
    ) -> DemandImportUploadResult:
        name = _safe_upload_name(payload.filename)
        drop_folder = self.drop_folder(tenant_slug)
        drop_folder.mkdir(parents=True, exist_ok=True)
        destination = drop_folder / name
        destination.write_text(payload.content, encoding="utf-8")
        preview = _preview_file(destination, demand_plan=demand_plan)
        return DemandImportUploadResult(
            name=name,
            path=str(destination),
            size_bytes=destination.stat().st_size,
            status="queued_for_next_sweep",
            preview_status=preview.status,
            raw_row_count=preview.raw_row_count,
            normalized_row_count=preview.normalized_row_count,
            skipped_row_count=preview.skipped_row_count,
            topics=preview.topics,
            demand_plan_coverage=preview.demand_plan_coverage,
            error=preview.error,
        )

    def prepare(self, tenant_slug: str, *, demand_plan: dict[str, Any] | None = None) -> DemandImportPrepareResult:
        """Normalize queued demand exports into the product-market workdir.

        This deliberately does not archive or delete inbox files. The full
        Hermes product-market run still owns the archive step after synthesis
        succeeds.
        """

        drop_folder = self.drop_folder(tenant_slug)
        raw_paths = [
            Path(item.path)
            for item in _list_direct_files(drop_folder)
        ]
        normalized_dir = self.normalized_dir(tenant_slug)
        normalized_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = self.manifest_path(tenant_slug)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        seen_names: set[str] = set()
        files: list[dict[str, Any]] = []
        payload_paths: list[str] = []
        normalized_row_count = 0
        skipped_row_count = 0
        error_count = 0

        for raw_path in raw_paths:
            entry: dict[str, Any] = {
                "path": str(raw_path),
                "auto_discovered": True,
                "status": "pending",
                "raw_row_count": 0,
                "normalized_row_count": 0,
                "skipped_row_count": 0,
            }
            try:
                rows = load_export_records(raw_path)
                diagnosis = diagnose_looker_rows(rows, source_path=raw_path)
                normalized = _annotate_rows_with_demand_plan(
                    list(diagnosis["normalized"]),
                    demand_plan,
                )
            except Exception as exc:  # noqa: BLE001 - surface bad exports in the manifest.
                entry["status"] = "error"
                entry["error"] = f"{exc.__class__.__name__}: {exc}"
                error_count += 1
                files.append(entry)
                continue

            entry["raw_row_count"] = len(rows)
            entry["normalized_row_count"] = len(normalized)
            entry["skipped_row_count"] = int(diagnosis["skipped_row_count"])
            entry["skipped_rows"] = diagnosis["skipped_rows"]
            entry["duplicate_row_count"] = int(diagnosis["duplicate_row_count"])
            entry["demand_plan_coverage"] = _demand_plan_coverage(demand_plan, normalized)
            normalized_row_count += len(normalized)
            skipped_row_count += entry["skipped_row_count"]

            if not normalized:
                entry["status"] = "empty"
                files.append(entry)
                continue

            payload_path = normalized_dir / _normalized_filename(raw_path, seen_names)
            payload_path.write_text(
                json.dumps({"records": normalized}, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            entry["status"] = "ready"
            entry["payload_path"] = str(payload_path)
            payload_paths.append(str(payload_path))
            files.append(entry)

        manifest = {
            "tenant": tenant_slug,
            "discovered_count": len(raw_paths),
            "ready_count": len(payload_paths),
            "error_count": error_count,
            "normalized_row_count": normalized_row_count,
            "skipped_row_count": skipped_row_count,
            "files": files,
        }
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        return DemandImportPrepareResult(
            tenant_slug=tenant_slug,
            manifest_path=str(manifest_path),
            discovered_count=len(raw_paths),
            ready_count=len(payload_paths),
            error_count=error_count,
            normalized_row_count=normalized_row_count,
            skipped_row_count=skipped_row_count,
            raw_paths=[str(path) for path in raw_paths],
            payload_paths=payload_paths,
            manifest=manifest,
        )

    def archive_prepared(
        self,
        tenant_slug: str,
        prepared: DemandImportPrepareResult,
        *,
        archive_label: str | None = None,
    ) -> dict[str, Any]:
        """Move consumed queued exports out of the active inbox.

        Preparing is intentionally non-destructive so operators can inspect bad
        uploads. Once a prepared import has been persisted and the requested
        downstream refresh path has succeeded, the same raw files should leave
        the inbox so future sweeps do not keep treating consumed evidence as a
        fresh queued action.
        """

        label = archive_label or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        moved: list[dict[str, str]] = []
        skipped: list[dict[str, str]] = []
        files = prepared.manifest.get("files") if isinstance(prepared.manifest, dict) else []
        if not isinstance(files, list):
            files = []
        for entry in files:
            if not isinstance(entry, dict):
                continue
            raw_path = Path(str(entry.get("path") or ""))
            if not entry.get("auto_discovered"):
                skipped.append({"path": str(raw_path), "reason": "explicit_path"})
                continue
            if not raw_path.exists():
                skipped.append({"path": str(raw_path), "reason": "missing"})
                continue

            status = str(entry.get("status") or "")
            if status == "ready":
                archive_dir = self.drop_folder(tenant_slug) / "_archive" / label
            elif status in {"empty", "error"}:
                archive_dir = self.drop_folder(tenant_slug) / "_rejected" / label
            else:
                skipped.append({"path": str(raw_path), "reason": f"status:{status}"})
                continue

            archive_dir.mkdir(parents=True, exist_ok=True)
            destination = _unique_destination(archive_dir / raw_path.name)
            raw_path.replace(destination)
            moved.append({"path": str(raw_path), "archived_path": str(destination), "status": status})

        return {
            "archived_count": len(moved),
            "archived_files": moved,
            "skipped_archive_files": skipped,
        }


class DemandImportLedgerPersister:
    """Persist prepared demand imports into the product-market demand ledger."""

    def __init__(self, *, repository) -> None:
        self._repository = repository

    def persist(self, *, tenant_id: int, prepared: DemandImportPrepareResult) -> DemandImportLedgerPersistResult:
        saved_ids: list[int] = []
        payload_paths = [str(path) for path in prepared.payload_paths]
        for payload_path in payload_paths:
            path = Path(payload_path)
            rows = load_export_records(path)
            normalized_rows = normalize_looker_rows(rows, source_path=path)
            for row in normalized_rows:
                signal = looker_row_to_demand_signal(tenant_id=tenant_id, row=row)
                saved_ids.append(int(self._repository.save_demand_signal(signal)))
        return DemandImportLedgerPersistResult(
            tenant_id=tenant_id,
            status="persisted",
            demand_signal_count=len(saved_ids),
            saved_ids=saved_ids,
            payload_paths=payload_paths,
        )


class Ga4DemandExportControl:
    """Safe operator control for the GA4 inward-demand connector.

    CI-OS owns this package boundary. Hermes can schedule the daily script,
    while admins can inspect whether analytics demand is configured and run a
    bounded export into the same tenant drop folder used by demand imports.
    """

    def __init__(self, *, app_dir: Path | None = None, env: dict[str, str] | None = None) -> None:
        self._app_dir = app_dir
        self._env = env

    @property
    def app_dir(self) -> Path:
        return self._app_dir or default_app_dir()

    @property
    def env(self) -> dict[str, str]:
        return dict(os.environ if self._env is None else self._env)

    def drop_folder(self, tenant_slug: str) -> Path:
        return self.app_dir / "data" / "looker" / tenant_slug

    def output_path(self, tenant_slug: str) -> Path:
        return self.drop_folder(tenant_slug) / "ga4-demand.json"

    def demand_plan_path(self, tenant_slug: str) -> Path:
        return self.drop_folder(tenant_slug) / "argus-demand-plan.json"

    def script_path(self) -> Path:
        configured = (self.env.get("CIOS_GA4_EXPORT_SCRIPT") or "").strip()
        if configured:
            return Path(configured).expanduser()
        return self.app_dir / "scripts" / "export_ga4_demand.py"

    def status(self, tenant_slug: str) -> Ga4ExportStatus:
        env = self.env
        enabled = _env_flag(env, "CIOS_GA4_EXPORT_ENABLED", default=False)
        credential_path = (env.get("CIOS_GA4_CREDENTIALS_JSON") or "").strip()
        adc_path = (env.get("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
        credentials_path_exists = bool(credential_path and Path(credential_path).expanduser().is_file())
        adc_path_exists = bool(adc_path and Path(adc_path).expanduser().is_file())
        credentials_configured = credentials_path_exists or adc_path_exists
        script_path_exists = self.script_path().is_file()
        property_configured = bool((env.get("CIOS_GA4_PROPERTY_ID") or "").strip())
        missing_required: list[str] = []
        setup_required: list[str] = []

        if enabled:
            missing_required.extend(key for key in GA4_REQUIRED_ENV_KEYS if not (env.get(key) or "").strip())
            explicit_date_values = {key: (env.get(key) or "").strip() for key in EXPLICIT_GA4_DATE_KEYS}
            if any(explicit_date_values.values()) and not all(explicit_date_values.values()):
                missing_required.extend(key for key, value in explicit_date_values.items() if not value)
            if not credentials_configured:
                missing_required.append("CIOS_GA4_CREDENTIALS_JSON or GOOGLE_APPLICATION_CREDENTIALS")
            if not script_path_exists:
                missing_required.append("CIOS_GA4_EXPORT_SCRIPT")
            setup_required.extend(missing_required)
        else:
            setup_required.append("CIOS_GA4_EXPORT_ENABLED")
            if not property_configured:
                setup_required.append("CIOS_GA4_PROPERTY_ID")
            if not credentials_configured:
                setup_required.append("CIOS_GA4_CREDENTIALS_JSON or GOOGLE_APPLICATION_CREDENTIALS")
            if not script_path_exists:
                setup_required.append("CIOS_GA4_EXPORT_SCRIPT")
        setup_required = _unique_setup_keys(setup_required)

        date_window = resolve_ga4_date_windows(env)
        ready = enabled and not missing_required
        state = "ready" if ready else ("not_ready" if enabled else "disabled")
        message = (
            "GA4 export is ready to run."
            if ready
            else (
                "GA4 export is enabled but missing required configuration."
                if enabled
                else "GA4 export is disabled."
            )
        )
        return Ga4ExportStatus(
            tenant_slug=tenant_slug,
            enabled=enabled,
            ready=ready,
            status=state,
            missing_required=missing_required,
            setup_required=setup_required,
            property_configured=property_configured,
            credentials_configured=credentials_configured,
            credentials_path_exists=credentials_path_exists,
            application_default_credentials_configured=adc_path_exists,
            script_path_exists=script_path_exists,
            current_start=date_window.current_start,
            current_end=date_window.current_end,
            previous_start=date_window.previous_start,
            previous_end=date_window.previous_end,
            topic_dimension=env.get("CIOS_GA4_TOPIC_DIMENSION") or "pageTitle",
            url_dimension=env.get("CIOS_GA4_URL_DIMENSION") or "pagePath",
            metric=env.get("CIOS_GA4_METRIC") or "engagedSessions",
            limit=_env_int(env, "CIOS_GA4_LIMIT", 1000),
            source_url_configured=bool((env.get("CIOS_GA4_SOURCE_URL") or "").strip()),
            output_path=str(self.output_path(tenant_slug)),
            message=message,
        )

    def run(self, tenant_slug: str, demand_plan: dict[str, Any] | None = None) -> Ga4ExportRunResult:
        env = self.env
        status = self.status(tenant_slug)
        if not status.ready:
            missing = ", ".join(status.missing_required) or "GA4 export disabled"
            raise ValueError(f"GA4 export is not ready: {missing}")

        output_path = self.output_path(tenant_slug)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        demand_plan_path: Path | None = None
        if isinstance(demand_plan, dict) and demand_plan:
            demand_plan_path = self.demand_plan_path(tenant_slug)
            demand_plan_path.write_text(
                json.dumps(demand_plan, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        cmd = [
            sys.executable,
            str(self.script_path()),
            "--property-id",
            str(env["CIOS_GA4_PROPERTY_ID"]),
            "--current-start",
            str(status.current_start),
            "--current-end",
            str(status.current_end),
            "--previous-start",
            str(status.previous_start),
            "--previous-end",
            str(status.previous_end),
            "--topic-dimension",
            status.topic_dimension,
            "--metric",
            status.metric,
            "--limit",
            str(status.limit),
            "--output",
            str(output_path),
        ]
        if demand_plan_path is not None:
            cmd.extend(["--demand-plan", str(demand_plan_path)])
        if status.url_dimension:
            cmd.extend(["--url-dimension", status.url_dimension])
        source_url = (env.get("CIOS_GA4_SOURCE_URL") or "").strip()
        if source_url:
            cmd.extend(["--source-url", source_url])
        credential_path = (env.get("CIOS_GA4_CREDENTIALS_JSON") or "").strip()
        if credential_path:
            cmd.extend(["--credentials-json", credential_path])

        timeout = _env_float(env, "CIOS_GA4_EXPORT_TIMEOUT_SECONDS", 60.0)
        try:
            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"GA4 export timed out after {timeout:g}s") from exc

        if completed.returncode != 0:
            detail = _safe_error((completed.stderr or completed.stdout or "").strip(), env)
            raise RuntimeError(detail or f"GA4 export failed with exit {completed.returncode}")

        record_count = 0
        demand_plan_status = None
        demand_plan_topic_count = 0
        matched_plan_topic_count = 0
        off_plan_record_count = 0
        if completed.stdout.strip():
            try:
                payload = json.loads(completed.stdout)
            except json.JSONDecodeError:
                payload = {}
            if isinstance(payload, dict):
                try:
                    record_count = int(payload.get("record_count") or 0)
                except (TypeError, ValueError):
                    record_count = 0
                demand_plan_status = payload.get("demand_plan_status")
                demand_plan_topic_count = _int_value(payload.get("demand_plan_topic_count"))
                matched_plan_topic_count = _int_value(payload.get("matched_plan_topic_count"))
                off_plan_record_count = _int_value(payload.get("off_plan_record_count"))

        return Ga4ExportRunResult(
            tenant_slug=tenant_slug,
            output_path=str(output_path),
            record_count=record_count,
            credentials_configured=status.credentials_configured,
            demand_plan_path=str(demand_plan_path) if demand_plan_path is not None else None,
            demand_plan_status=str(demand_plan_status) if demand_plan_status else None,
            demand_plan_topic_count=demand_plan_topic_count,
            matched_plan_topic_count=matched_plan_topic_count,
            off_plan_record_count=off_plan_record_count,
        )
