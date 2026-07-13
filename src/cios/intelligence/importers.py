"""File import helpers for product-market runner payloads."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .capabilities import capability_key
from .runner import ProductMarketRunPayload


def _load_json(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [dict(row) for row in data]
    if isinstance(data, dict):
        records = data.get("records")
        if isinstance(records, list):
            return [dict(row) for row in records]
    raise ValueError(f"{path} must contain a JSON list or an object with records")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(dict(json.loads(line)))
    return rows


def _load_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as f:
        return [dict(row) for row in csv.DictReader(f)]


def load_export_records(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return _load_json(path)
    if suffix == ".jsonl":
        return _load_jsonl(path)
    if suffix == ".csv":
        return _load_csv(path)
    raise ValueError(f"unsupported export file type: {path.suffix}")


def _records(path: Path | None) -> list[dict[str, Any]]:
    return [] if path is None else load_export_records(path)


def _learning_instructions(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a next-sweep plan object")
    instructions = data.get("instructions", [])
    if not isinstance(instructions, list):
        raise ValueError(f"{path} instructions must be a list")
    return [dict(row) for row in instructions]


def _lookup(row: dict[str, Any], *names: str) -> Any:
    normalized = {
        re.sub(r"[^a-z0-9]+", "", str(key).lower()): value
        for key, value in row.items()
    }
    for name in names:
        key = re.sub(r"[^a-z0-9]+", "", name.lower())
        if key in normalized:
            return normalized[key]
    return None


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    text = str(value).strip().replace(",", "")
    if text.endswith("%"):
        text = text[:-1]
        try:
            return float(text) / 100.0
        except ValueError:
            return None
    try:
        return float(text)
    except ValueError:
        return None


def _present(value: Any) -> bool:
    return value is not None and not (isinstance(value, str) and not value.strip())


def _iso_datetime(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _parse_looker_date(value: Any) -> str | None:
    if value in (None, ""):
        return None
    direct = _iso_datetime(value)
    if direct:
        return direct
    text = str(value).strip()
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%m/%d/%Y", "%m/%d/%y"):
        try:
            dt = datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        return dt.isoformat()
    return None


def _date_range(row: dict[str, Any]) -> tuple[str | None, str | None]:
    explicit_start = _parse_looker_date(
        _lookup(row, "period_start", "period start", "start date", "date range start")
    )
    explicit_end = _parse_looker_date(
        _lookup(row, "period_end", "period end", "end date", "date range end")
    )
    if explicit_start or explicit_end:
        return explicit_start, explicit_end

    raw_range = _lookup(row, "date range", "date", "period", "custom date range")
    if not raw_range:
        return None, None
    text = str(raw_range).strip()
    parts = re.split(r"\s+(?:-|–|—|to)\s+", text, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) != 2:
        return None, None
    return _parse_looker_date(parts[0]), _parse_looker_date(parts[1])


def _infer_demand_topic(row: dict[str, Any]) -> str | None:
    explicit = _lookup(row, "topic", "argus topic", "capability", "capability key", "theme", "search term", "query")
    if explicit:
        return str(explicit).strip()

    text = " ".join(
        str(value)
        for value in [
            _lookup(
                row,
                "page title",
                "pageTitle",
                "page title and screen name",
                "page title and screen class",
                "title",
            ),
            _lookup(row, "page path", "landing page", "landing page + query string", "url", "page location"),
            _lookup(row, "content group", "page category"),
        ]
        if value
    )
    key = capability_key(text)
    if key == "shopping agent":
        return "AI Shopping Agent"
    if "context engineering" in text.lower():
        return "context engineering"
    if "neural search" in text.lower():
        return "neural search"
    return None


def _split_argus_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        parts = [str(item) for item in value]
    else:
        text = str(value)
        parts = re.split(r"\s*(?:\||,)\s*", text)
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        cleaned = part.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        out.append(cleaned)
    return out


def _argus_plan_metadata(row: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    capability = _lookup(row, "capability key", "argus capability key")
    assessment = _lookup(row, "assessment", "argus assessment")
    why_collect = _lookup(row, "why collect", "argus rationale", "collection rationale")
    suggested_filters = _split_argus_list(_lookup(row, "suggested filters", "argus suggested filters"))
    related_competitors = _split_argus_list(_lookup(row, "related competitors", "argus related competitors"))
    evidence_urls = _split_argus_list(_lookup(row, "evidence urls", "argus evidence urls"))
    if capability:
        metadata["argus_capability_key"] = str(capability).strip()
    if assessment:
        metadata["argus_assessment"] = str(assessment).strip()
    if suggested_filters:
        metadata["argus_suggested_filters"] = suggested_filters
    if related_competitors:
        metadata["argus_related_competitors"] = related_competitors
    if why_collect:
        metadata["argus_why_collect"] = str(why_collect).strip()
    if evidence_urls:
        metadata["argus_evidence_urls"] = evidence_urls
    return metadata


def _metric_value(row: dict[str, Any]) -> tuple[str, float, float | None] | None:
    candidates = [
        ("engaged_sessions", "engaged sessions", "engaged sessions previous period"),
        ("active_users", "active users", "active users previous period"),
        ("views", "views", "views previous period"),
        ("screen_page_views", "screen page views", "screen page views previous period"),
        ("sessions", "sessions", "sessions previous period"),
        ("clicks", "clicks", "clicks previous period"),
    ]
    for metric, current_name, previous_name in candidates:
        current = _number(_lookup(row, current_name, metric))
        if current is None:
            continue
        previous = _number(_lookup(row, previous_name, f"previous {current_name}", f"{metric} previous period"))
        change_pct = None
        explicit_change = _number(_lookup(row, "change_pct", "change %", "percent change", "delta %"))
        if explicit_change is not None:
            change_pct = explicit_change
        elif previous not in (None, 0):
            change_pct = round((current - previous) / previous, 4)
        return metric, current, change_pct
    return None


def _canonical_looker_row(row: dict[str, Any], *, source_path: Path | None = None, row_number: int = 0) -> dict[str, Any] | None:
    canonical, _diagnostic = _canonical_looker_row_with_diagnostic(row, source_path=source_path, row_number=row_number)
    return canonical


def _skip_diagnostic(
    row: dict[str, Any],
    *,
    source_path: Path | None,
    row_number: int,
    reason: str,
    missing_fields: list[str],
) -> dict[str, Any]:
    return {
        "row_number": row_number,
        "reason": reason,
        "missing_fields": missing_fields,
        "source_file": source_path.name if source_path is not None else "manual-export",
        "available_columns": sorted(str(key) for key in row.keys() if str(key).strip()),
    }


def _canonical_looker_row_with_diagnostic(
    row: dict[str, Any], *, source_path: Path | None = None, row_number: int = 0
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    raw_topic = _lookup(row, "topic")
    raw_metric = _lookup(row, "metric")
    raw_value = _lookup(row, "value")
    if _present(raw_topic) and _present(raw_metric) and _present(raw_value):
        metric_value = _number(raw_value)
        if metric_value is not None and metric_value <= 0:
            return None, _skip_diagnostic(
                row,
                source_path=source_path,
                row_number=row_number,
                reason="non_positive_metric",
                missing_fields=["value"],
            )
        normalized = dict(row)
        period_start, period_end = _date_range(normalized)
        if not period_start or not period_end:
            return None, _skip_diagnostic(
                row,
                source_path=source_path,
                row_number=row_number,
                reason="missing_period",
                missing_fields=["period"],
            )
        normalized["period_start"] = period_start
        normalized["period_end"] = period_end
        if not str(_lookup(normalized, "source_label", "source label") or "").strip():
            normalized["source_label"] = "Looker Studio GA4 export"
        if not str(_lookup(normalized, "source_url", "Looker Studio URL", "Looker URL", "report url") or "").strip():
            source_name = source_path.name if source_path is not None else "manual-export"
            normalized["source_url"] = f"looker://{source_name}#row-{row_number}"
        normalized.setdefault("source_file", source_path.name if source_path is not None else "manual-export")
        normalized.setdefault("source_row_number", row_number)
        normalized.setdefault("source_fingerprint", _looker_source_fingerprint(normalized))
        normalized.update(_argus_plan_metadata(row))
        return normalized, None

    topic = _infer_demand_topic(row)
    metric = _metric_value(row)
    period_start, period_end = _date_range(row)
    missing_fields: list[str] = []
    if not topic:
        missing_fields.append("topic")
    if not metric:
        missing_fields.append("metric")
    if not period_start or not period_end:
        missing_fields.append("period")
    if missing_fields:
        return None, _skip_diagnostic(
            row,
            source_path=source_path,
            row_number=row_number,
            reason=f"missing_{missing_fields[0]}",
            missing_fields=missing_fields,
        )

    metric_name, value, change_pct = metric
    if value <= 0:
        return None, _skip_diagnostic(
            row,
            source_path=source_path,
            row_number=row_number,
            reason="non_positive_metric",
            missing_fields=["value"],
        )
    source_url = _lookup(row, "source_url", "Looker Studio URL", "Looker URL", "report url")
    if not source_url and source_path is not None:
        source_url = f"looker://{source_path.name}#row-{row_number}"
    page_title = _lookup(row, "page title", "title")
    if not page_title:
        page_title = _lookup(row, "page title and screen name", "page title and screen class")
    page_path = _lookup(row, "page path", "landing page", "landing page + query string", "url", "page location")
    excerpt_parts = []
    if page_title:
        excerpt_parts.append(f"Page title: {page_title}")
    if page_path:
        excerpt_parts.append(f"Page path: {page_path}")

    canonical = {
        "topic": topic,
        "metric": metric_name,
        "value": value,
        "change_pct": change_pct,
        "period_start": period_start,
        "period_end": period_end,
        "source_label": str(_lookup(row, "source_label", "source label") or "Looker Studio GA4 export"),
        "source_url": str(source_url or f"looker://manual-export#row-{row_number}"),
        "excerpt": "; ".join(excerpt_parts) if excerpt_parts else None,
    }
    canonical.update(_argus_plan_metadata(row))
    canonical["source_file"] = source_path.name if source_path is not None else "manual-export"
    canonical["source_row_number"] = row_number
    canonical["source_fingerprint"] = _looker_source_fingerprint(canonical)
    return canonical, None


def _looker_source_fingerprint(row: dict[str, Any]) -> str:
    payload = {
        "topic": row.get("topic"),
        "metric": row.get("metric"),
        "value": row.get("value"),
        "change_pct": row.get("change_pct"),
        "period_start": row.get("period_start"),
        "period_end": row.get("period_end"),
        "source_label": row.get("source_label"),
        "source_url": row.get("source_url"),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def normalize_looker_rows(rows: list[dict[str, Any]], *, source_path: Path | None = None) -> list[dict[str, Any]]:
    return list(diagnose_looker_rows(rows, source_path=source_path)["normalized"])


def diagnose_looker_rows(rows: list[dict[str, Any]], *, source_path: Path | None = None) -> dict[str, Any]:
    normalized: list[dict[str, Any]] = []
    skipped_rows: list[dict[str, Any]] = []
    seen_fingerprints: set[str] = set()
    duplicate_row_count = 0
    for index, row in enumerate(rows, start=1):
        canonical, diagnostic = _canonical_looker_row_with_diagnostic(
            dict(row),
            source_path=source_path,
            row_number=index,
        )
        if canonical is None:
            if diagnostic is not None:
                skipped_rows.append(diagnostic)
            continue
        fingerprint = str(canonical.get("source_fingerprint") or "")
        if fingerprint and fingerprint in seen_fingerprints:
            duplicate_row_count += 1
            continue
        if fingerprint:
            seen_fingerprints.add(fingerprint)
        normalized.append(canonical)
    return {
        "normalized": normalized,
        "normalized_row_count": len(normalized),
        "skipped_row_count": len(skipped_rows),
        "skipped_rows": skipped_rows,
        "duplicate_row_count": duplicate_row_count,
    }


def build_payload_from_exports(
    *,
    own_company_name: str,
    tenant_id: int | None = None,
    scout_path: Path | None = None,
    scout_paths: list[Path] | None = None,
    scout_records: list[dict[str, Any]] | None = None,
    conversation_path: Path | None = None,
    looker_path: Path | None = None,
    looker_paths: list[Path] | None = None,
    learning_plan_path: Path | None = None,
) -> ProductMarketRunPayload:
    all_scout_paths = []
    if scout_path is not None:
        all_scout_paths.append(scout_path)
    if scout_paths is not None:
        all_scout_paths.extend(scout_paths)
    file_scout_records = [row for path in all_scout_paths for row in load_export_records(path)]
    extra_scout_records = [] if scout_records is None else list(scout_records)
    all_looker_paths = []
    if looker_path is not None:
        all_looker_paths.append(looker_path)
    if looker_paths is not None:
        all_looker_paths.extend(looker_paths)
    looker_rows = [
        row
        for path in all_looker_paths
        for row in normalize_looker_rows(load_export_records(path), source_path=path)
    ]
    return ProductMarketRunPayload(
        tenant_id=tenant_id,
        own_company_name=own_company_name,
        scout_records=[*file_scout_records, *extra_scout_records],
        conversation_records=_records(conversation_path),
        looker_rows=looker_rows,
        learning_instructions=_learning_instructions(learning_plan_path),
    )


__all__ = ["build_payload_from_exports", "diagnose_looker_rows", "load_export_records", "normalize_looker_rows"]
