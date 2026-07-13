"""Smoke contract for the Hermes-callable GA4 demand export script."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from cios.intelligence.ga4_exporter import Ga4ReportRow


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "export_ga4_demand.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("export_ga4_demand", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeGoogleClient:
    def __init__(self, *, credentials_path=None):
        self.credentials_path = credentials_path

    def run_report(self, *, property_id, dimensions, metric, start_date, end_date, limit):
        assert property_id == "123456"
        assert dimensions == ["pageTitle", "pagePath"]
        assert metric == "engagedSessions"
        assert limit == 1000
        if start_date == "2026-07-01":
            return [Ga4ReportRow(topic="AI Shopping Agent guide", url="/solutions/ai-shopping-agent", value=240.0)]
        return [Ga4ReportRow(topic="AI Shopping Agent guide", url="/solutions/ai-shopping-agent", value=160.0)]


def test_export_ga4_demand_script_writes_canonical_json(monkeypatch, tmp_path) -> None:
    module = _load_module()
    out = tmp_path / "ga4-demand.json"
    plan = tmp_path / "argus-demand-readiness.json"
    plan.write_text(
        json.dumps(
            {
                "demand_collection_plan": {
                    "status": "ready_to_collect",
                    "topics": [
                        {
                            "topic": "AI Assistant",
                            "capability_key": "ai assistant",
                            "assessment": "own_product_gap",
                            "suggested_filter_terms": ["AI Shopping Agent", "shopping agent"],
                            "related_competitors": ["Constructor"],
                            "why_collect": "Collect tenant demand for AI Assistant.",
                            "evidence_urls": ["https://constructor.com/changelog/ai-assistant"],
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "GoogleAnalyticsDataApiClient", FakeGoogleClient)

    code = module.main([
        "--property-id",
        "123456",
        "--current-start",
        "2026-07-01",
        "--current-end",
        "2026-07-08",
        "--previous-start",
        "2026-06-24",
        "--previous-end",
        "2026-06-30",
        "--source-url",
        "https://lookerstudio.google.com/reporting/algolia-demand",
        "--demand-plan",
        str(plan),
        "--output",
        str(out),
    ])

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert code == 0
    assert payload["records"][0]["topic"] == "AI Shopping Agent guide"
    assert payload["records"][0]["metric"] == "engaged_sessions"
    assert payload["records"][0]["value"] == 240.0
    assert payload["records"][0]["change_pct"] == 0.5
    assert payload["records"][0]["source_label"] == "GA4 Data API export"
    assert payload["records"][0]["argus_capability_key"] == "ai assistant"
    assert payload["records"][0]["argus_related_competitors"] == ["Constructor"]
    assert payload["argus_demand_plan"] == {
        "status": "covered",
        "planned_topic_count": 1,
        "matched_plan_topic_count": 1,
        "off_plan_record_count": 0,
        "matched_topics": ["ai assistant"],
        "missing_topics": [],
    }
    assert "credentials" not in json.dumps(payload).lower()


def test_export_ga4_demand_script_imports_without_google_dependency() -> None:
    module = _load_module()

    assert hasattr(module, "main")
    assert hasattr(module, "GoogleAnalyticsDataApiClient")
