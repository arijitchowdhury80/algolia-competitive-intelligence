#!/usr/bin/env python3
"""Export GA4 demand rows into the CI-OS product-market payload format.

Hermes can call this before build_product_market_payload.py and pass the
resulting JSON file with --looker. The script reads GA4 through application
default credentials or a service-account JSON path supplied by the operator.
It never stores credentials in CI-OS output.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cios.intelligence.ga4_exporter import (
    Ga4DemandExportConfig,
    GoogleAnalyticsDataApiClient,
    export_ga4_demand_records,
    summarize_ga4_demand_plan_coverage,
)


def _property_id(value: str | None) -> str:
    property_id = value or os.environ.get("CIOS_GA4_PROPERTY_ID")
    if not property_id:
        raise ValueError("GA4 property id is required via --property-id or CIOS_GA4_PROPERTY_ID")
    if property_id.startswith("properties/"):
        property_id = property_id.split("/", 1)[1]
    return property_id


def _load_demand_plan(path: Path | None) -> dict:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    plan = payload.get("demand_collection_plan")
    if isinstance(plan, dict):
        return dict(plan)
    contract = payload.get("demand_source_contract")
    if isinstance(contract, dict) and isinstance(contract.get("demand_plan"), dict):
        return dict(contract["demand_plan"])
    plan = payload.get("demand_plan")
    if isinstance(plan, dict):
        return dict(plan)
    if isinstance(payload.get("topics"), list):
        return payload
    return {}


def _plan_topics(plan: dict) -> list[dict]:
    topics = plan.get("topics")
    if not isinstance(topics, list):
        topics = plan.get("top_topics")
    return [dict(topic) for topic in topics or [] if isinstance(topic, dict)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export GA4 demand rows for CI-OS product-market intelligence.")
    parser.add_argument("--property-id", help="GA4 property id. Also accepts CIOS_GA4_PROPERTY_ID.")
    parser.add_argument("--current-start", required=True, help="Current period start date, YYYY-MM-DD.")
    parser.add_argument("--current-end", required=True, help="Current period end date, YYYY-MM-DD.")
    parser.add_argument("--previous-start", required=True, help="Previous period start date, YYYY-MM-DD.")
    parser.add_argument("--previous-end", required=True, help="Previous period end date, YYYY-MM-DD.")
    parser.add_argument("--topic-dimension", default="pageTitle")
    parser.add_argument("--url-dimension", default="pagePath")
    parser.add_argument("--metric", default="engagedSessions")
    parser.add_argument("--source-url", help="Stable operator-facing Looker/GA report URL.")
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--credentials-json", help="Optional service account JSON path. Do not put this in output.")
    parser.add_argument("--demand-plan", type=Path, help="Argus demand-readiness or demand-plan JSON.")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    demand_plan = _load_demand_plan(args.demand_plan)
    planned_topics = _plan_topics(demand_plan)

    config = Ga4DemandExportConfig(
        property_id=_property_id(args.property_id),
        current_start=args.current_start,
        current_end=args.current_end,
        previous_start=args.previous_start,
        previous_end=args.previous_end,
        topic_dimension=args.topic_dimension,
        url_dimension=args.url_dimension or None,
        metric=args.metric,
        source_url=args.source_url,
        limit=args.limit,
        planned_topics=planned_topics,
    )
    client = GoogleAnalyticsDataApiClient(credentials_path=args.credentials_json)
    records = export_ga4_demand_records(config=config, client=client)
    plan_coverage = summarize_ga4_demand_plan_coverage(planned_topics, records)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {"records": records}
    if args.demand_plan:
        payload["argus_demand_plan"] = plan_coverage
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "output": str(output),
                "record_count": len(records),
                "demand_plan_status": plan_coverage["status"],
                "demand_plan_topic_count": plan_coverage["planned_topic_count"],
                "matched_plan_topic_count": plan_coverage["matched_plan_topic_count"],
                "off_plan_record_count": plan_coverage["off_plan_record_count"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
