from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from cios.admin import demand_imports
from cios.admin.demand_imports import (
    DemandImportLedgerPersister,
    DemandImportStore,
    Ga4DemandExportControl,
    demand_collection_plan_operator_guide,
)
from cios.admin.types import DemandImportPrepareResult


class FakeProductMarketRepository:
    def __init__(self) -> None:
        self.saved_signals = []

    def save_demand_signal(self, signal):
        self.saved_signals.append(signal)
        return 700 + len(self.saved_signals)


def test_demand_collection_plan_operator_guide_turns_plan_into_actionable_work_order() -> None:
    plan = {
        "status": "needs_demand_source",
        "topic_count": 2,
        "topics": [
            {
                "topic": "AI Shopping Agent",
                "capability_key": "ai shopping agent",
                "assessment": "own_product_gap",
                "why_collect": "Measure whether Algolia demand exists for AI shopping agents.",
                "suggested_filter_terms": ["AI Shopping Agent", "shopping agent"],
                "related_competitors": ["Constructor", "Elastic"],
                "evidence_urls": ["https://constructor.com/changelog/ai-shopping-agent"],
            },
            {
                "topic": "Context engineering",
                "capability_key": "context engineering",
                "assessment": "own_narrative_gap",
                "suggested_filter_terms": ["Context engineering", "context"],
                "related_competitors": ["Elastic"],
                "evidence_urls": ["https://elastic.co/blog/context-engineering"],
            },
        ],
    }

    guide = demand_collection_plan_operator_guide(plan, tenant_slug="algolia")

    assert guide["status"] == "ready"
    assert guide["tenant_slug"] == "algolia"
    assert guide["template_filename"] == "argus-demand-plan-template.csv"
    assert guide["template_href"] == "/api/tenants/algolia/argus/demand-imports/template?planned=1"
    assert guide["upload_action"] == "/admin/algolia/argus/demand-imports"
    assert guide["refresh_action"] == "/admin/algolia/argus/demand-imports/refresh"
    assert guide["accepted_suffixes"] == [".csv", ".json", ".jsonl"]
    assert guide["required_columns"] == [
        "Page title",
        "Page path",
        "Engaged sessions",
        "Engaged sessions previous period",
        "Period start",
        "Period end",
        "Looker Studio URL",
    ]
    assert guide["required_metric"] == "Engaged sessions"
    assert guide["required_comparison"] == "Engaged sessions previous period"
    assert guide["topic_count"] == 2
    assert guide["topics"][0]["topic"] == "AI Shopping Agent"
    assert guide["topics"][0]["row_status"] == "needs_metrics"
    assert guide["topics"][0]["filter_terms"] == ["AI Shopping Agent", "shopping agent", "ai shopping agent"]
    assert guide["topics"][0]["related_competitors"] == ["Constructor", "Elastic"]
    assert guide["topics"][0]["evidence_url_count"] == 1
    assert guide["steps"][0].startswith("Open GA4 or Looker")
    assert all("240" not in json.dumps(step) for step in guide["steps"])
    assert "Measure whether Algolia" not in json.dumps(guide)


def test_demand_import_ledger_persister_saves_prepared_rows_as_demand_signals(tmp_path):
    payload_path = tmp_path / "ga-pages.normalized.json"
    payload_path.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "topic": "AI Shopping Agent",
                        "metric": "engaged_sessions",
                        "value": 240,
                        "change_pct": 0.5,
                        "period_start": "2026-07-01T00:00:00+00:00",
                        "period_end": "2026-07-08T00:00:00+00:00",
                        "source_label": "Looker Studio GA4 export",
                        "source_url": "https://lookerstudio.google.com/reporting/abc",
                        "source_file": "ga-pages.csv",
                        "source_row_number": 1,
                        "source_fingerprint": "abc123",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    prepared = DemandImportPrepareResult(
        tenant_slug="algolia",
        manifest_path=str(tmp_path / "looker-export-manifest.json"),
        normalized_row_count=1,
        payload_paths=[str(payload_path)],
    )
    repo = FakeProductMarketRepository()

    result = DemandImportLedgerPersister(repository=repo).persist(tenant_id=1, prepared=prepared)

    assert result.status == "persisted"
    assert result.tenant_id == 1
    assert result.demand_signal_count == 1
    assert result.saved_ids == [701]
    assert len(repo.saved_signals) == 1
    signal = repo.saved_signals[0]
    assert signal.tenant_id == 1
    assert signal.topic == "AI Shopping Agent"
    assert signal.metric == "engaged_sessions"
    assert signal.value == 240
    assert signal.change_pct == 0.5
    assert signal.metadata["source_fingerprint"] == "abc123"
    assert signal.evidence[0].source_url == "https://lookerstudio.google.com/reporting/abc"


def test_demand_import_prepare_rejects_incomplete_pre_normalized_rows(tmp_path):
    app_dir = tmp_path / "app"
    work_root = tmp_path / "work"
    drop_folder = app_dir / "data" / "looker" / "algolia"
    drop_folder.mkdir(parents=True)
    (drop_folder / "bad-normalized.json").write_text(
        json.dumps(
            {
                "records": [
                    {
                        "topic": "AI Shopping Agent",
                        "metric": "engaged_sessions",
                        "value": 240,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = DemandImportStore(app_dir=app_dir, work_root=work_root).prepare("algolia")

    assert result.ready_count == 0
    assert result.normalized_row_count == 0
    assert result.skipped_row_count == 1
    assert result.payload_paths == []
    assert result.manifest["files"][0]["status"] == "empty"
    assert result.manifest["files"][0]["skipped_rows"] == [
        {
            "row_number": 1,
            "reason": "missing_period",
            "missing_fields": ["period"],
            "source_file": "bad-normalized.json",
            "available_columns": ["metric", "topic", "value"],
        }
    ]


def test_demand_import_status_reports_argus_plan_coverage_for_queued_files(tmp_path):
    app_dir = tmp_path / "app"
    work_root = tmp_path / "work"
    drop_folder = app_dir / "data" / "looker" / "algolia"
    drop_folder.mkdir(parents=True)
    (drop_folder / "ga-pages.csv").write_text(
        "Page title,Page path,Engaged sessions,Engaged sessions previous period,Period start,Period end,Looker Studio URL\n"
        "AI Shopping Agent guide,/solutions/ai-shopping-agent,240,160,2026-07-01,2026-07-08,https://lookerstudio.google.com/reporting/abc\n",
        encoding="utf-8",
    )
    demand_plan = {
        "status": "needs_demand_source",
        "topic_count": 2,
        "topics": [
            {
                "topic": "AI Shopping Agent",
                "capability_key": "ai shopping agent",
                "suggested_filter_terms": ["AI Shopping Agent", "agentic commerce"],
            },
            {
                "topic": "Context engineering",
                "capability_key": "context engineering",
                "suggested_filter_terms": ["context engineering"],
            },
        ],
    }

    status = DemandImportStore(app_dir=app_dir, work_root=work_root).status(
        "algolia",
        demand_plan=demand_plan,
    )

    preview = status.inbox_previews[0]
    assert preview.name == "ga-pages.csv"
    assert preview.demand_plan_coverage["status"] == "partial_coverage"
    assert preview.demand_plan_coverage["planned_topic_count"] == 2
    assert preview.demand_plan_coverage["matched_plan_topic_count"] == 1
    assert preview.demand_plan_coverage["off_plan_record_count"] == 0
    assert preview.demand_plan_coverage["matched_topics"][0]["topic"] == "AI Shopping Agent"
    assert preview.demand_plan_coverage["missing_topics"][0]["topic"] == "Context engineering"


def test_demand_import_prepare_attaches_argus_plan_metadata_to_matching_rows(tmp_path):
    app_dir = tmp_path / "app"
    work_root = tmp_path / "work"
    drop_folder = app_dir / "data" / "looker" / "algolia"
    drop_folder.mkdir(parents=True)
    (drop_folder / "ga-pages.csv").write_text(
        "Page title,Page path,Engaged sessions,Engaged sessions previous period,Period start,Period end,Looker Studio URL\n"
        "AI Shopping Agent guide,/solutions/ai-shopping-agent,240,160,2026-07-01,2026-07-08,https://lookerstudio.google.com/reporting/abc\n",
        encoding="utf-8",
    )
    demand_plan = {
        "status": "needs_demand_source",
        "topic_count": 1,
        "topics": [
            {
                "topic": "AI Shopping Agent",
                "capability_key": "ai shopping agent",
                "assessment": "own_product_gap",
                "why_collect": "Decide whether Algolia needs product proof for AI shopping agents.",
                "suggested_filter_terms": ["AI Shopping Agent", "agentic commerce"],
                "related_competitors": ["Constructor", "Elastic"],
                "evidence_urls": ["https://constructor.com/changelog/ai-shopping-agent"],
            }
        ],
    }

    result = DemandImportStore(app_dir=app_dir, work_root=work_root).prepare(
        "algolia",
        demand_plan=demand_plan,
    )

    assert result.ready_count == 1
    assert result.manifest["files"][0]["demand_plan_coverage"]["status"] == "covered"
    payload = json.loads(Path(result.payload_paths[0]).read_text(encoding="utf-8"))
    row = payload["records"][0]
    assert row["argus_plan_matched"] is True
    assert row["argus_capability_key"] == "ai shopping agent"
    assert row["argus_assessment"] == "own_product_gap"
    assert row["argus_suggested_filters"] == ["AI Shopping Agent", "agentic commerce"]
    assert row["argus_related_competitors"] == ["Constructor", "Elastic"]
    assert row["argus_why_collect"] == "Decide whether Algolia needs product proof for AI shopping agents."
    assert row["argus_evidence_urls"] == ["https://constructor.com/changelog/ai-shopping-agent"]


def test_ga4_export_control_passes_argus_demand_plan_to_export_script(tmp_path, monkeypatch):
    app_dir = tmp_path / "app"
    script = app_dir / "scripts" / "export_ga4_demand.py"
    script.parent.mkdir(parents=True)
    script.write_text("# fake export script\n", encoding="utf-8")
    credentials = tmp_path / "credentials.json"
    credentials.write_text("{}", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append([str(part) for part in cmd])
        plan_path = cmd[cmd.index("--demand-plan") + 1]
        assert json.loads(open(plan_path, encoding="utf-8").read())["topics"][0]["capability_key"] == "ai assistant"
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "status": "ok",
                    "output": str(app_dir / "data" / "looker" / "algolia" / "ga4-demand.json"),
                    "record_count": 2,
                    "demand_plan_status": "partial_coverage",
                    "demand_plan_topic_count": 1,
                    "matched_plan_topic_count": 1,
                    "off_plan_record_count": 1,
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(demand_imports.subprocess, "run", fake_run)

    result = Ga4DemandExportControl(
        app_dir=app_dir,
        env={
            "CIOS_GA4_EXPORT_ENABLED": "1",
            "CIOS_GA4_PROPERTY_ID": "properties/123456",
            "CIOS_GA4_CREDENTIALS_JSON": str(credentials),
        },
    ).run(
        "algolia",
        demand_plan={
            "status": "ready_to_collect",
            "topics": [
                {
                    "topic": "AI Assistant",
                    "capability_key": "ai assistant",
                    "suggested_filter_terms": ["AI Shopping Agent"],
                }
            ],
        },
    )

    assert calls
    command = calls[0]
    assert "--demand-plan" in command
    plan_path = Path(command[command.index("--demand-plan") + 1])
    assert plan_path == app_dir / "data" / "looker" / "algolia" / "argus-demand-plan.json"
    assert result.demand_plan_path == str(plan_path)
    assert result.demand_plan_status == "partial_coverage"
    assert result.demand_plan_topic_count == 1
    assert result.matched_plan_topic_count == 1
    assert result.off_plan_record_count == 1
