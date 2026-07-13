"""GA4 Data API demand export adapter for Argus.

This module owns the CI-OS side of the GA4 boundary. It converts GA4 report
rows into the canonical Looker/GA demand rows that the product-market runner
already understands. Credentials stay outside the package and are only read by
the optional Google client adapter when Hermes invokes the script.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol


_METRIC_NAMES = {
    "activeUsers": "active_users",
    "engagedSessions": "engaged_sessions",
    "screenPageViews": "screen_page_views",
    "sessions": "sessions",
    "totalUsers": "total_users",
    "eventCount": "event_count",
}


@dataclass(frozen=True)
class Ga4ReportRow:
    topic: str
    value: float
    url: str | None = None


@dataclass(frozen=True)
class Ga4DateWindow:
    current_start: str
    current_end: str
    previous_start: str
    previous_end: str
    source: str
    rolling_days: int | None = None


@dataclass(frozen=True)
class Ga4DemandExportConfig:
    property_id: str
    current_start: str
    current_end: str
    previous_start: str
    previous_end: str
    topic_dimension: str = "pageTitle"
    url_dimension: str | None = "pagePath"
    metric: str = "engagedSessions"
    source_url: str | None = None
    limit: int = 5000
    planned_topics: list[dict[str, Any]] = field(default_factory=list)

    @property
    def dimensions(self) -> list[str]:
        dimensions = [self.topic_dimension]
        if self.url_dimension:
            dimensions.append(self.url_dimension)
        return dimensions

    @property
    def normalized_metric(self) -> str:
        return _METRIC_NAMES.get(self.metric, _camel_to_snake(self.metric))


EXPLICIT_GA4_DATE_KEYS = (
    "CIOS_GA4_CURRENT_START",
    "CIOS_GA4_CURRENT_END",
    "CIOS_GA4_PREVIOUS_START",
    "CIOS_GA4_PREVIOUS_END",
)


def resolve_ga4_date_windows(env: Mapping[str, str], *, today: date | None = None) -> Ga4DateWindow:
    """Resolve GA4 comparison dates from explicit env or a rolling complete-day window."""

    explicit_values = {key: str(env.get(key) or "").strip() for key in EXPLICIT_GA4_DATE_KEYS}
    if all(explicit_values.values()):
        return Ga4DateWindow(
            current_start=explicit_values["CIOS_GA4_CURRENT_START"],
            current_end=explicit_values["CIOS_GA4_CURRENT_END"],
            previous_start=explicit_values["CIOS_GA4_PREVIOUS_START"],
            previous_end=explicit_values["CIOS_GA4_PREVIOUS_END"],
            source="explicit",
        )

    rolling_days = _positive_int(env.get("CIOS_GA4_ROLLING_DAYS"), default=7)
    anchor = today or _today_from_env(env) or datetime.now(timezone.utc).date()
    current_end = anchor - timedelta(days=1)
    current_start = current_end - timedelta(days=rolling_days - 1)
    previous_end = current_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=rolling_days - 1)
    return Ga4DateWindow(
        current_start=current_start.isoformat(),
        current_end=current_end.isoformat(),
        previous_start=previous_start.isoformat(),
        previous_end=previous_end.isoformat(),
        source="rolling",
        rolling_days=rolling_days,
    )


class Ga4ReportClient(Protocol):
    def run_report(
        self,
        *,
        property_id: str,
        dimensions: list[str],
        metric: str,
        start_date: str,
        end_date: str,
        limit: int,
    ) -> list[Ga4ReportRow]:
        """Return GA4 rows for one date range."""


class GoogleAnalyticsDataApiClient:
    """Thin optional wrapper around the Google Analytics Data API client.

    The google packages are imported lazily so CI-OS can run tests and local
    tooling without GA credentials or the optional dependency installed.
    """

    def __init__(self, *, credentials_path: str | Path | None = None) -> None:
        try:
            from google.analytics.data_v1beta import BetaAnalyticsDataClient
            from google.analytics.data_v1beta.types import DateRange, Dimension, Metric, RunReportRequest
        except ImportError as exc:
            raise RuntimeError(
                "GA4 export requires optional dependency google-analytics-data. "
                "Install CI-OS with the ga4 extra and provide application-default "
                "credentials or --credentials-json."
            ) from exc

        self._DateRange = DateRange
        self._Dimension = Dimension
        self._Metric = Metric
        self._RunReportRequest = RunReportRequest

        credentials = None
        if credentials_path is not None:
            try:
                from google.oauth2 import service_account
            except ImportError as exc:
                raise RuntimeError("GA4 service account auth requires google-auth.") from exc
            credentials = service_account.Credentials.from_service_account_file(
                str(credentials_path),
                scopes=["https://www.googleapis.com/auth/analytics.readonly"],
            )
        self._client = BetaAnalyticsDataClient(credentials=credentials)

    def run_report(
        self,
        *,
        property_id: str,
        dimensions: list[str],
        metric: str,
        start_date: str,
        end_date: str,
        limit: int,
    ) -> list[Ga4ReportRow]:
        request = self._RunReportRequest(
            property=f"properties/{property_id}",
            dimensions=[self._Dimension(name=name) for name in dimensions],
            metrics=[self._Metric(name=metric)],
            date_ranges=[self._DateRange(start_date=start_date, end_date=end_date)],
            limit=limit,
        )
        response = self._client.run_report(request)
        rows: list[Ga4ReportRow] = []
        for row in getattr(response, "rows", []):
            dimension_values = list(getattr(row, "dimension_values", []))
            metric_values = list(getattr(row, "metric_values", []))
            topic = dimension_values[0].value if dimension_values else ""
            url = dimension_values[1].value if len(dimension_values) > 1 else None
            value = _float(metric_values[0].value if metric_values else 0.0)
            rows.append(Ga4ReportRow(topic=topic, url=url, value=value))
        return rows


def export_ga4_demand_records(*, config: Ga4DemandExportConfig, client: Ga4ReportClient) -> list[dict]:
    current_rows = client.run_report(
        property_id=config.property_id,
        dimensions=config.dimensions,
        metric=config.metric,
        start_date=config.current_start,
        end_date=config.current_end,
        limit=config.limit,
    )
    previous_rows = client.run_report(
        property_id=config.property_id,
        dimensions=config.dimensions,
        metric=config.metric,
        start_date=config.previous_start,
        end_date=config.previous_end,
        limit=config.limit,
    )
    return build_ga4_demand_records(
        config=config,
        current_rows=current_rows,
        previous_rows=previous_rows,
    )


def build_ga4_demand_records(
    *,
    config: Ga4DemandExportConfig,
    current_rows: list[Ga4ReportRow],
    previous_rows: list[Ga4ReportRow],
) -> list[dict]:
    previous_by_topic = _sum_by_topic(previous_rows)
    current_by_topic = _merge_rows(current_rows)
    records: list[dict] = []
    for topic, row in current_by_topic.items():
        previous = previous_by_topic.get(topic, 0.0)
        change_pct = None if previous == 0 else round((row.value - previous) / previous, 4)
        source_url = config.source_url or (
            f"ga4://properties/{config.property_id}/runReport"
            f"?dimension={config.topic_dimension}&metric={config.metric}"
        )
        excerpt_parts = [
            f"{config.topic_dimension}: {topic}",
        ]
        if config.url_dimension and row.url:
            excerpt_parts.append(f"{config.url_dimension}: {row.url}")
        excerpt_parts.extend([
            f"{config.metric}: {row.value}",
            f"previous: {previous}",
        ])
        record = {
            "topic": topic,
            "metric": config.normalized_metric,
            "value": row.value,
            "change_pct": change_pct,
            "period_start": _iso_date(config.current_start),
            "period_end": _iso_date(config.current_end),
            "source_label": "GA4 Data API export",
            "source_url": source_url,
            "excerpt": "; ".join(excerpt_parts),
        }
        plan_topic = _matching_planned_topic(row, config.planned_topics)
        if plan_topic is not None:
            record.update(_argus_plan_metadata(plan_topic))
            record["argus_plan_matched"] = True
        records.append(record)
    records.sort(key=lambda item: (-float(item["value"]), str(item["topic"]).lower()))
    return records


def summarize_ga4_demand_plan_coverage(
    planned_topics: list[dict[str, Any]],
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    plan_keys = [
        _topic_key(topic)
        for topic in planned_topics
        if _topic_key(topic)
    ]
    matched_keys = sorted(
        {
            _topic_key({"capability_key": record.get("argus_capability_key")})
            for record in records
            if record.get("argus_capability_key")
        }
    )
    missing_keys = sorted(set(plan_keys) - set(matched_keys))
    off_plan_count = sum(1 for record in records if not record.get("argus_capability_key"))
    if not plan_keys:
        status = "not_supplied"
    elif len(matched_keys) == len(set(plan_keys)) and off_plan_count == 0:
        status = "covered"
    elif matched_keys:
        status = "partial_coverage"
    elif records:
        status = "off_plan"
    else:
        status = "not_evaluated"
    return {
        "status": status,
        "planned_topic_count": len(set(plan_keys)),
        "matched_plan_topic_count": len(matched_keys),
        "off_plan_record_count": off_plan_count,
        "matched_topics": matched_keys,
        "missing_topics": missing_keys,
    }


def _matching_planned_topic(row: Ga4ReportRow, planned_topics: list[dict[str, Any]]) -> dict[str, Any] | None:
    haystack = f"{row.topic} {row.url or ''}".casefold()
    for topic in planned_topics:
        terms = _topic_filter_terms(topic)
        if any(term.casefold() in haystack for term in terms):
            return topic
    return None


def _topic_filter_terms(topic: Mapping[str, Any]) -> list[str]:
    candidates: list[Any] = []
    candidates.extend(_list_value(topic.get("suggested_filter_terms")))
    candidates.append(topic.get("topic"))
    candidates.append(topic.get("capability_key"))
    return _string_list(candidates)


def _argus_plan_metadata(topic: Mapping[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    capability_key = _text(topic.get("capability_key") or topic.get("topic"))
    assessment = _text(topic.get("assessment"))
    why_collect = _text(topic.get("why_collect"))
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


def _topic_key(topic: Mapping[str, Any]) -> str:
    return _text(topic.get("capability_key") or topic.get("topic")).casefold()


def _list_value(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return [value]
    return []


def _string_list(value: Any) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in _list_value(value):
        text = _text(item)
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _sum_by_topic(rows: list[Ga4ReportRow]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for row in rows:
        topic = str(row.topic).strip()
        if not topic:
            continue
        totals[topic] = totals.get(topic, 0.0) + float(row.value)
    return totals


def _merge_rows(rows: list[Ga4ReportRow]) -> dict[str, Ga4ReportRow]:
    merged: dict[str, Ga4ReportRow] = {}
    for row in rows:
        topic = str(row.topic).strip()
        if not topic:
            continue
        if topic not in merged:
            merged[topic] = Ga4ReportRow(topic=topic, url=row.url, value=float(row.value))
            continue
        existing = merged[topic]
        merged[topic] = Ga4ReportRow(
            topic=topic,
            url=existing.url or row.url,
            value=float(existing.value) + float(row.value),
        )
    return merged


def _iso_date(value: str) -> str:
    parsed = datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
    return parsed.isoformat()


def _today_from_env(env: Mapping[str, str]) -> date | None:
    raw = str(env.get("CIOS_GA4_TODAY") or "").strip()
    if not raw:
        return None
    return date.fromisoformat(raw)


def _positive_int(value: str | None, *, default: int) -> int:
    try:
        parsed = int(str(value or "").strip())
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _camel_to_snake(value: str) -> str:
    out = []
    for index, char in enumerate(value):
        if char.isupper() and index > 0:
            out.append("_")
        out.append(char.lower())
    return "".join(out)


def _float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


__all__ = [
    "EXPLICIT_GA4_DATE_KEYS",
    "Ga4DateWindow",
    "Ga4DemandExportConfig",
    "Ga4ReportClient",
    "Ga4ReportRow",
    "GoogleAnalyticsDataApiClient",
    "build_ga4_demand_records",
    "export_ga4_demand_records",
    "resolve_ga4_date_windows",
    "summarize_ga4_demand_plan_coverage",
]
