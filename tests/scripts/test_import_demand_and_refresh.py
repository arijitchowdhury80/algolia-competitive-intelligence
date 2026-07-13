"""Smoke contract for the operator demand-import fast lane."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from cios.admin.demand_intake import DemandIntakeHistoryStore


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "import_demand_and_refresh.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("import_demand_and_refresh", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_demand_csv(path: Path) -> None:
    path.write_text(
        "Page title,Page path,Engaged sessions,Engaged sessions previous period,Period start,Period end,Looker Studio URL\n"
        "AI Shopping Agent guide,/solutions/ai-shopping-agent,240,160,2026-07-01,2026-07-08,https://lookerstudio.google.com/reporting/abc\n",
        encoding="utf-8",
    )


def test_import_demand_and_refresh_script_exists_and_imports() -> None:
    module = _load_module()

    assert hasattr(module, "main")
    assert hasattr(module, "import_demand_exports")


def test_import_demand_and_refresh_prepares_uploaded_looker_file(tmp_path) -> None:
    module = _load_module()
    app_dir = tmp_path / "app"
    work_root = tmp_path / "work"
    source = tmp_path / "ga-pages.csv"
    output = tmp_path / "summary.json"
    _write_demand_csv(source)

    code = module.main(
        [
            "--tenant",
            "algolia",
            "--app-dir",
            str(app_dir),
            "--work-root",
            str(work_root),
            "--input",
            str(source),
            "--prepare-only",
            "--output",
            str(output),
        ]
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    drop_file = app_dir / "data" / "looker" / "algolia" / "ga-pages.csv"
    normalized_file = work_root / "algolia" / "looker-normalized" / "ga-pages.normalized.json"
    assert code == 0
    assert drop_file.exists()
    assert normalized_file.exists()
    assert payload["status"] == "prepared"
    assert payload["tenant"] == "algolia"
    assert payload["prepare"]["ready_count"] == 1
    assert payload["prepare"]["normalized_row_count"] == 1
    assert payload["copied_inputs"] == [str(drop_file)]


def test_import_demand_and_refresh_prepares_uploaded_file_against_current_argus_demand_plan(tmp_path) -> None:
    module = _load_module()
    app_dir = tmp_path / "app"
    work_root = tmp_path / "work"
    out_dir = app_dir / "out"
    out_dir.mkdir(parents=True)
    source = tmp_path / "ga-pages.csv"
    output = tmp_path / "summary.json"
    _write_demand_csv(source)
    (out_dir / "argus-demand-readiness.json").write_text(
        json.dumps(
            {
                "demand_collection_plan": {
                    "status": "needs_demand_source",
                    "topic_count": 2,
                    "topics": [
                        {
                            "topic": "AI Shopping Agent",
                            "capability_key": "ai shopping agent",
                            "assessment": "own_product_gap",
                            "suggested_filter_terms": ["AI Shopping Agent", "agentic commerce"],
                            "related_competitors": ["Constructor"],
                            "evidence_urls": ["https://constructor.com/changelog/ai-shopping-agent"],
                        },
                        {
                            "topic": "Context engineering",
                            "capability_key": "context engineering",
                            "suggested_filter_terms": ["context engineering"],
                        },
                    ],
                }
            }
        ),
        encoding="utf-8",
    )

    code = module.main(
        [
            "--tenant",
            "algolia",
            "--app-dir",
            str(app_dir),
            "--work-root",
            str(work_root),
            "--input",
            str(source),
            "--prepare-only",
            "--output",
            str(output),
        ]
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    normalized_file = work_root / "algolia" / "looker-normalized" / "ga-pages.normalized.json"
    normalized_payload = json.loads(normalized_file.read_text(encoding="utf-8"))
    normalized_row = normalized_payload["records"][0]
    coverage = payload["prepare"]["manifest"]["files"][0]["demand_plan_coverage"]
    assert code == 0
    assert payload["demand_plan"]["status"] == "loaded"
    assert payload["demand_plan"]["source_path"] == str(out_dir / "argus-demand-readiness.json")
    assert payload["demand_plan"]["topic_count"] == 2
    assert coverage["status"] == "partial_coverage"
    assert coverage["matched_plan_topic_count"] == 1
    assert coverage["planned_topic_count"] == 2
    assert coverage["matched_topics"][0]["topic"] == "AI Shopping Agent"
    assert normalized_row["argus_plan_matched"] is True
    assert normalized_row["argus_capability_key"] == "ai shopping agent"
    assert normalized_row["argus_related_competitors"] == ["Constructor"]


def test_import_demand_exports_accepts_explicit_argus_demand_plan_object(tmp_path) -> None:
    module = _load_module()
    app_dir = tmp_path / "app"
    work_root = tmp_path / "work"
    source = tmp_path / "ga-pages.csv"
    _write_demand_csv(source)
    demand_plan = {
        "status": "needs_demand_source",
        "topic_count": 1,
        "topics": [
            {
                "topic": "AI Shopping Agent",
                "capability_key": "ai shopping agent",
                "assessment": "own_product_gap",
                "suggested_filter_terms": ["AI Shopping Agent"],
                "related_competitors": ["Constructor"],
            }
        ],
    }

    payload = module.import_demand_exports(
        tenant="algolia",
        inputs=[source],
        app_dir=app_dir,
        work_root=work_root,
        prepare_only=True,
        demand_plan=demand_plan,
    )

    normalized_file = work_root / "algolia" / "looker-normalized" / "ga-pages.normalized.json"
    normalized_row = json.loads(normalized_file.read_text(encoding="utf-8"))["records"][0]
    assert payload["status"] == "prepared"
    assert payload["demand_plan"] == {
        "status": "provided",
        "source_path": None,
        "topic_count": 1,
    }
    assert payload["prepare"]["manifest"]["files"][0]["demand_plan_coverage"]["status"] == "covered"
    assert normalized_row["argus_plan_matched"] is True
    assert normalized_row["argus_capability_key"] == "ai shopping agent"


def test_import_demand_and_refresh_prepares_existing_queued_looker_file_without_input(tmp_path) -> None:
    module = _load_module()
    app_dir = tmp_path / "app"
    work_root = tmp_path / "work"
    output = tmp_path / "summary.json"
    queued = app_dir / "data" / "looker" / "algolia" / "ga-pages.csv"
    queued.parent.mkdir(parents=True)
    _write_demand_csv(queued)

    code = module.main(
        [
            "--tenant",
            "algolia",
            "--app-dir",
            str(app_dir),
            "--work-root",
            str(work_root),
            "--queued",
            "--prepare-only",
            "--output",
            str(output),
        ]
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    normalized_file = work_root / "algolia" / "looker-normalized" / "ga-pages.normalized.json"
    assert code == 0
    assert normalized_file.exists()
    assert payload["status"] == "prepared"
    assert payload["copied_inputs"] == []
    assert payload["prepare"]["raw_paths"] == [str(queued)]
    assert payload["prepare"]["ready_count"] == 1
    assert payload["prepare"]["normalized_row_count"] == 1


def test_import_demand_and_refresh_fails_queued_mode_when_no_ready_exports(tmp_path) -> None:
    module = _load_module()
    app_dir = tmp_path / "app"
    work_root = tmp_path / "work"
    output = tmp_path / "summary.json"

    code = module.main(
        [
            "--tenant",
            "algolia",
            "--app-dir",
            str(app_dir),
            "--work-root",
            str(work_root),
            "--queued",
            "--prepare-only",
            "--output",
            str(output),
        ]
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert code == 1
    assert payload["status"] == "no_ready_demand"
    assert payload["copied_inputs"] == []
    assert payload["prepare"]["ready_count"] == 0
    assert payload["prepare"]["normalized_row_count"] == 0
    assert payload["error"].startswith("No ready GA / Looker demand exports")


def test_import_demand_and_refresh_invokes_refresh_and_rerender_after_prepare(tmp_path, monkeypatch) -> None:
    module = _load_module()
    app_dir = tmp_path / "app"
    work_root = tmp_path / "work"
    source = tmp_path / "ga-pages.csv"
    output = tmp_path / "summary.json"
    _write_demand_csv(source)
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append([str(part) for part in cmd])
        return subprocess.CompletedProcess(cmd, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    code = module.main(
        [
            "--tenant",
            "algolia",
            "--app-dir",
            str(app_dir),
            "--work-root",
            str(work_root),
            "--input",
            str(source),
            "--skip-ledger-persist",
            "--demand-change-floor",
            "0.03",
            "--demand-value-floor",
            "25",
            "--output",
            str(output),
        ]
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert code == 0
    assert payload["status"] == "refreshed"
    assert payload["refresh"]["returncode"] == 0
    assert payload["rerender"]["returncode"] == 0
    assert calls[0][1].endswith("refresh_product_market_from_ledger.py")
    assert "--tenant" in calls[0]
    assert "algolia" in calls[0]
    assert calls[0][calls[0].index("--demand-change-floor") + 1] == "0.03"
    assert calls[0][calls[0].index("--demand-value-floor") + 1] == "25.0"
    assert calls[1][1].endswith("rerender_dashboard.py")
    assert "--out-dir" in calls[1]
    assert str(app_dir / "out") in calls[1]
    assert calls[2][1].endswith("export_argus_demand_readiness.py")
    assert calls[3][1].endswith("export_argus_demand_plan_template.py")
    assert "--readiness" in calls[3]
    assert str(app_dir / "out" / "argus-demand-readiness.json") in calls[3]
    assert "--output" in calls[3]
    assert str(app_dir / "out" / "argus-demand-plan-template.csv") in calls[3]
    assert calls[4][1].endswith("attach_post_run_summaries.py")
    assert calls[5][1].endswith("export_argus_evidence_work_queue.py")
    assert calls[6][1].endswith("export_argus_product_muscle_work_queue.py")
    assert "--work-root" in calls[6]
    assert str(work_root) in calls[6]
    assert "--output" in calls[6]
    assert str(app_dir / "out" / "argus-product-muscle-work-queue.json") in calls[6]
    assert calls[7][1].endswith("build_argus_operator_handoff.py")
    assert "--product-muscle-queue" in calls[7]
    assert str(app_dir / "out" / "argus-product-muscle-work-queue.json") in calls[7]
    assert "--demand-readiness" in calls[7]
    assert str(app_dir / "out" / "argus-demand-readiness.json") in calls[7]
    assert "--demand-plan-template" in calls[7]
    assert str(app_dir / "out" / "argus-demand-plan-template.csv") in calls[7]
    assert calls[8][1].endswith("attach_operator_handoff_to_dashboard.py")
    assert calls[9][1].endswith("export_argus_data_plane_manifest.py")
    assert "--product-muscle-work-queue" in calls[9]
    assert str(app_dir / "out" / "argus-product-muscle-work-queue.json") in calls[9]
    assert "--demand-intake" in calls[9]
    assert str(app_dir / "out" / "argus-demand-intake.json") in calls[9]
    assert "--demand-plan-template" in calls[9]
    assert str(app_dir / "out" / "argus-demand-plan-template.csv") in calls[9]
    demand_intake = json.loads((app_dir / "out" / "argus-demand-intake.json").read_text(encoding="utf-8"))
    assert demand_intake["status"] == "demand_imported_and_argus_refreshed"
    assert demand_intake["command_status"] == "ok"
    assert demand_intake["exit_code"] == 0
    assert demand_intake["mode"] == "manual_upload"
    assert demand_intake["next_hermes_action"] == "continue_product_market_synthesis"
    assert demand_intake["demand_import"]["prepare"]["ready_count"] == 1
    assert demand_intake["demand_import"]["prepare"]["normalized_row_count"] == 1
    assert payload["post_rerender_artifacts"]["demand_readiness"]["returncode"] == 0
    assert payload["post_rerender_artifacts"]["demand_plan_template"]["returncode"] == 0
    assert payload["post_rerender_artifacts"]["product_muscle_work_queue"]["returncode"] == 0
    assert payload["post_rerender_artifacts"]["attach_operator_handoff"]["returncode"] == 0
    assert payload["post_rerender_artifacts"]["data_plane_manifest"]["returncode"] == 0


def test_import_demand_and_refresh_persists_prepared_demand_before_refresh(tmp_path, monkeypatch) -> None:
    module = _load_module()
    app_dir = tmp_path / "app"
    work_root = tmp_path / "work"
    source = tmp_path / "ga-pages.csv"
    _write_demand_csv(source)
    events: list[str] = []
    calls: list[list[str]] = []

    class FakePersister:
        def __init__(self) -> None:
            self.calls = []

        def persist(self, *, tenant_id, prepared):
            events.append("persist")
            self.calls.append(
                {
                    "tenant_id": tenant_id,
                    "payload_paths": list(prepared.payload_paths),
                }
            )
            return {
                "status": "persisted",
                "tenant_id": tenant_id,
                "demand_signal_count": prepared.normalized_row_count,
                "saved_ids": [701],
            }

    persister = FakePersister()

    def fake_run(cmd, **kwargs):
        events.append("refresh" if str(cmd[1]).endswith("refresh_product_market_from_ledger.py") else "rerender")
        calls.append([str(part) for part in cmd])
        return subprocess.CompletedProcess(cmd, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    summary = module.import_demand_exports(
        tenant="algolia",
        tenant_id=1,
        inputs=[source],
        app_dir=app_dir,
        work_root=work_root,
        demand_import_ledger_persister=persister,
        demand_change_floor=0.03,
        demand_value_floor=25,
    )

    assert summary["status"] == "refreshed"
    assert summary["demand_ledger"] == {
        "status": "persisted",
        "tenant_id": 1,
        "demand_signal_count": 1,
        "saved_ids": [701],
    }
    assert persister.calls == [
        {
            "tenant_id": 1,
            "payload_paths": [str(work_root / "algolia" / "looker-normalized" / "ga-pages.normalized.json")],
        }
    ]
    assert events[:3] == ["persist", "refresh", "rerender"]
    assert calls[0][1].endswith("refresh_product_market_from_ledger.py")
    assert calls[0][calls[0].index("--demand-change-floor") + 1] == "0.03"
    assert calls[0][calls[0].index("--demand-value-floor") + 1] == "25"


def test_import_demand_and_refresh_archives_consumed_queued_file_after_success(tmp_path, monkeypatch) -> None:
    module = _load_module()
    app_dir = tmp_path / "app"
    work_root = tmp_path / "work"
    source = tmp_path / "ga-pages.csv"
    _write_demand_csv(source)

    class FakePersister:
        def persist(self, *, tenant_id, prepared):
            return {
                "status": "persisted",
                "tenant_id": tenant_id,
                "demand_signal_count": prepared.normalized_row_count,
                "saved_ids": [701],
            }

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    summary = module.import_demand_exports(
        tenant="algolia",
        tenant_id=1,
        inputs=[source],
        app_dir=app_dir,
        work_root=work_root,
        demand_import_ledger_persister=FakePersister(),
    )

    drop_file = app_dir / "data" / "looker" / "algolia" / "ga-pages.csv"
    archived = list((app_dir / "data" / "looker" / "algolia" / "_archive").glob("*/*.csv"))
    assert summary["status"] == "refreshed"
    assert not drop_file.exists()
    assert len(archived) == 1
    assert archived[0].name == "ga-pages.csv"
    assert summary["archive"]["archived_count"] == 1
    assert summary["archive"]["archived_files"][0]["status"] == "ready"
    assert summary["archive"]["archived_files"][0]["path"] == str(drop_file)
    assert summary["archive"]["archived_files"][0]["archived_path"] == str(archived[0])


def test_import_demand_and_refresh_generates_post_rerender_artifacts_after_archive(tmp_path, monkeypatch) -> None:
    module = _load_module()
    app_dir = tmp_path / "app"
    work_root = tmp_path / "work"
    source = tmp_path / "ga-pages.csv"
    _write_demand_csv(source)
    observed: dict[str, bool] = {}

    class FakePersister:
        def persist(self, *, tenant_id, prepared):
            return {
                "status": "persisted",
                "tenant_id": tenant_id,
                "demand_signal_count": prepared.normalized_row_count,
                "saved_ids": [701],
            }

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout="ok\n", stderr="")

    def fake_refresh_post_rerender_artifacts(**kwargs):
        drop_file = app_dir / "data" / "looker" / "algolia" / "ga-pages.csv"
        observed["drop_file_exists_when_sidecars_run"] = drop_file.exists()
        return {
            "demand_intake": {"status": "written"},
            "demand_readiness": {"returncode": 0},
            "attach_demand_readiness": {"returncode": 0},
            "evidence_work_queue": {"returncode": 0},
            "product_muscle_work_queue": {"returncode": 0},
            "operator_handoff": {"returncode": 0},
            "attach_operator_handoff": {"returncode": 0},
            "data_plane_manifest": {"returncode": 0},
        }

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(module, "_refresh_post_rerender_artifacts", fake_refresh_post_rerender_artifacts)

    summary = module.import_demand_exports(
        tenant="algolia",
        tenant_id=1,
        inputs=[source],
        app_dir=app_dir,
        work_root=work_root,
        demand_import_ledger_persister=FakePersister(),
    )

    assert summary["status"] == "refreshed"
    assert observed["drop_file_exists_when_sidecars_run"] is False
    assert summary["archive"]["archived_count"] == 1


def test_import_demand_and_refresh_source_contract_reflects_consumed_upload_after_archive(
    tmp_path,
    monkeypatch,
) -> None:
    module = _load_module()
    app_dir = tmp_path / "app"
    work_root = tmp_path / "work"
    source = tmp_path / "ga-pages.csv"
    _write_demand_csv(source)
    original_run = subprocess.run

    class FakePersister:
        def persist(self, *, tenant_id, prepared):
            return {
                "status": "persisted",
                "tenant_id": tenant_id,
                "demand_signal_count": prepared.normalized_row_count,
                "saved_ids": [701],
            }

    def fake_run(cmd, **kwargs):
        script_name = Path(str(cmd[1])).name
        if script_name == "rerender_dashboard.py":
            out_dir = Path(str(cmd[cmd.index("--out-dir") + 1]))
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "argus-dashboard.html").write_text("dashboard", encoding="utf-8")
            (out_dir / "argus-dashboard.json").write_text(
                json.dumps(
                    {
                        "schema_version": 24,
                        "product_market_run": {
                            "demand_plane_status": "processed",
                            "looker_normalized_row_count": 1,
                            "demand_signal_count": 1,
                        },
                    }
                ),
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(cmd, 0, stdout="rerendered\n", stderr="")
        if script_name == "export_argus_demand_readiness.py":
            return original_run(cmd, **kwargs)
        return subprocess.CompletedProcess(cmd, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    summary = module.import_demand_exports(
        tenant="algolia",
        tenant_id=1,
        inputs=[source],
        app_dir=app_dir,
        work_root=work_root,
        demand_import_ledger_persister=FakePersister(),
    )

    contract = json.loads((work_root / "algolia" / "demand-source-contract.json").read_text(encoding="utf-8"))
    readiness = json.loads((app_dir / "out" / "argus-demand-readiness.json").read_text(encoding="utf-8"))
    manual_source = next(source for source in contract["sources"] if source["source_id"] == "manual_looker_export")

    assert summary["status"] == "refreshed"
    assert summary["archive"]["archived_count"] == 1
    assert contract["status"] == "processed_current_demand"
    assert contract["ready_source_count"] == 0
    assert manual_source["status"] == "waiting_for_upload"
    assert manual_source["inbox_file_count"] == 0
    assert readiness["demand_source_contract"]["sources"][0]["status"] == "waiting_for_upload"


def test_import_demand_and_refresh_records_manual_import_in_demand_intake_history(tmp_path, monkeypatch) -> None:
    module = _load_module()
    app_dir = tmp_path / "app"
    work_root = tmp_path / "work"
    source = tmp_path / "ga-pages.csv"
    _write_demand_csv(source)

    class FakePersister:
        def persist(self, *, tenant_id, prepared):
            return {
                "status": "persisted",
                "tenant_id": tenant_id,
                "demand_signal_count": prepared.normalized_row_count,
                "saved_ids": [701],
            }

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    summary = module.import_demand_exports(
        tenant="algolia",
        tenant_id=1,
        inputs=[source],
        app_dir=app_dir,
        work_root=work_root,
        demand_import_ledger_persister=FakePersister(),
    )

    history_path = Path(summary["demand_intake_history"]["path"])
    sidecar_path = app_dir / "out" / "argus-demand-intake.json"
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    history = DemandIntakeHistoryStore(work_root=work_root).status("algolia", limit=5)

    assert summary["status"] == "refreshed"
    assert history_path.exists()
    assert history_path.name == "demand-intake-summary.json"
    assert history_path.parent.parent == work_root / "algolia" / "demand-intake-runs"
    assert sidecar["summary_path"] == str(history_path)
    assert history["attempt_count"] == 1
    assert history["latest"]["status"] == "demand_imported_and_argus_refreshed"
    assert history["latest"]["mode"] == "manual_upload"
    assert history["latest"]["normalized_row_count"] == 1
    assert history["latest"]["demand_signal_count"] == 1


def test_import_demand_and_refresh_keeps_queued_file_when_refresh_fails(tmp_path, monkeypatch) -> None:
    module = _load_module()
    app_dir = tmp_path / "app"
    work_root = tmp_path / "work"
    source = tmp_path / "ga-pages.csv"
    _write_demand_csv(source)

    class FakePersister:
        def persist(self, *, tenant_id, prepared):
            return {
                "status": "persisted",
                "tenant_id": tenant_id,
                "demand_signal_count": prepared.normalized_row_count,
                "saved_ids": [701],
            }

    def fake_run(cmd, **kwargs):
        if str(cmd[1]).endswith("refresh_product_market_from_ledger.py"):
            return subprocess.CompletedProcess(cmd, 2, stdout="", stderr="refresh failed")
        return subprocess.CompletedProcess(cmd, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    summary = module.import_demand_exports(
        tenant="algolia",
        tenant_id=1,
        inputs=[source],
        app_dir=app_dir,
        work_root=work_root,
        demand_import_ledger_persister=FakePersister(),
    )

    drop_file = app_dir / "data" / "looker" / "algolia" / "ga-pages.csv"
    assert summary["status"] == "refresh_failed"
    assert drop_file.exists()
    assert not (app_dir / "data" / "looker" / "algolia" / "_archive").exists()
    assert "archive" not in summary


def test_import_demand_and_refresh_surfaces_refreshed_argus_read(tmp_path, monkeypatch) -> None:
    module = _load_module()
    app_dir = tmp_path / "app"
    work_root = tmp_path / "work"
    source = tmp_path / "ga-pages.csv"
    output = tmp_path / "summary.json"
    _write_demand_csv(source)

    refresh_payload = {
        "verdict": "actionable",
        "product_event_count": 2,
        "conversation_theme_count": 1,
        "demand_signal_count": 1,
        "pattern_count": 1,
        "recommendation_count": 1,
        "intelligence_brief": {
            "top_insight": "Demand now matches Constructor's AI shopping agent movement.",
            "primary_action": "Create the PMM response.",
            "demand_read": {
                "summary": "1 rising demand topic found; 1 matched product proof and 0 still need product proof.",
                "top_topics": [{"topic": "agentic product discovery"}],
            },
            "conversion_diagnostics": {
                "summary": "2 product events and 1 demand signal became 1 product-market pattern."
            },
            "demand_recommendation_trace": {
                "status": "linked_to_recommendations",
                "demand_signal_count": 1,
                "recommendation_count": 1,
                "demand_topics": [
                    {
                        "topic": "agentic product discovery",
                        "recommendation_actions": ["Create the PMM response."],
                    }
                ],
            },
        },
    }

    def fake_run(cmd, **kwargs):
        if str(cmd[1]).endswith("refresh_product_market_from_ledger.py"):
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(refresh_payload) + "\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="rerendered\n", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    code = module.main(
        [
            "--tenant",
            "algolia",
            "--app-dir",
            str(app_dir),
            "--work-root",
            str(work_root),
            "--input",
            str(source),
            "--skip-ledger-persist",
            "--output",
            str(output),
        ]
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert code == 0
    assert payload["status"] == "refreshed"
    assert payload["argus_read"]["verdict"] == "actionable"
    assert payload["argus_read"]["top_insight"] == "Demand now matches Constructor's AI shopping agent movement."
    assert payload["argus_read"]["primary_action"] == "Create the PMM response."
    assert payload["argus_read"]["demand_summary"].startswith("1 rising demand topic")
    assert payload["argus_read"]["conversion_summary"] == (
        "2 product events and 1 demand signal became 1 product-market pattern."
    )
    assert payload["argus_read"]["counts"] == {
        "product_events": 2,
        "conversation_themes": 1,
        "demand_signals": 1,
        "patterns": 1,
        "recommendations": 1,
    }
    assert payload["argus_read"]["demand_recommendation_trace"]["status"] == "linked_to_recommendations"
    assert payload["argus_read"]["demand_recommendation_trace"]["demand_topics"][0]["topic"] == (
        "agentic product discovery"
    )
    demand_intake = json.loads((app_dir / "out" / "argus-demand-intake.json").read_text(encoding="utf-8"))
    assert demand_intake["demand_import"]["argus_read"]["top_insight"] == (
        "Demand now matches Constructor's AI shopping agent movement."
    )
    assert demand_intake["demand_import"]["argus_read"]["counts"]["demand_signals"] == 1
    assert demand_intake["demand_import"]["argus_read"]["demand_recommendation_trace"]["status"] == (
        "linked_to_recommendations"
    )


def _write_dashboard_artifacts(out_dir: Path) -> None:
    out_dir.mkdir(parents=True)
    (out_dir / "argus-dashboard.html").write_text("cockpit", encoding="utf-8")
    (out_dir / "brief.html").write_text("brief", encoding="utf-8")
    (out_dir / "argus-dashboard.json").write_text('{"schema_version":17}', encoding="utf-8")
    (out_dir / "argus-data-plane-manifest.json").write_text('{"schema_version":1}', encoding="utf-8")
    (out_dir / "argus-demand-work-order-guide.json").write_text('{"status":"ready"}', encoding="utf-8")
    briefs = out_dir / "briefs" / "algolia"
    briefs.mkdir(parents=True)
    (briefs / "constructor-2026-07-11.html").write_text("constructor", encoding="utf-8")


def test_publish_dashboard_artifacts_uses_staged_public_copy(tmp_path) -> None:
    module = _load_module()
    out_dir = tmp_path / "out"
    public_dir = tmp_path / "public"
    _write_dashboard_artifacts(out_dir)

    result = module.publish_dashboard_artifacts(out_dir=out_dir, public_dir=public_dir)

    assert result["status"] == "published"
    assert (public_dir / "index.html").read_text(encoding="utf-8") == "cockpit"
    assert (public_dir / "v2" / "index.html").read_text(encoding="utf-8") == "cockpit"
    assert (public_dir / "brief.html").read_text(encoding="utf-8") == "brief"
    assert (public_dir / "data" / "semantic-dashboard.json").read_text(encoding="utf-8") == '{"schema_version":17}'
    assert (public_dir / "v2" / "data" / "semantic-dashboard.json").read_text(encoding="utf-8") == '{"schema_version":17}'
    assert (public_dir / "data" / "argus-data-plane-manifest.json").read_text(encoding="utf-8") == '{"schema_version":1}'
    assert (public_dir / "v2" / "data" / "argus-data-plane-manifest.json").read_text(encoding="utf-8") == (
        '{"schema_version":1}'
    )
    assert (public_dir / "data" / "argus-demand-work-order-guide.json").read_text(encoding="utf-8") == (
        '{"status":"ready"}'
    )
    assert (public_dir / "v2" / "data" / "argus-demand-work-order-guide.json").read_text(encoding="utf-8") == (
        '{"status":"ready"}'
    )
    assert (public_dir / "briefs" / "algolia" / "constructor-2026-07-11.html").exists()
    assert (public_dir / "v2" / "briefs" / "algolia" / "constructor-2026-07-11.html").exists()


def test_import_demand_and_refresh_can_publish_after_rerender(tmp_path, monkeypatch) -> None:
    module = _load_module()
    app_dir = tmp_path / "app"
    work_root = tmp_path / "work"
    source = tmp_path / "ga-pages.csv"
    public_dir = tmp_path / "public"
    output = tmp_path / "summary.json"
    _write_demand_csv(source)
    _write_dashboard_artifacts(app_dir / "out")

    def fake_run(cmd, **kwargs):
        calls.append([str(part) for part in cmd])
        return subprocess.CompletedProcess(cmd, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    calls: list[list[str]] = []

    code = module.main(
        [
            "--tenant",
            "algolia",
            "--app-dir",
            str(app_dir),
            "--work-root",
            str(work_root),
            "--input",
            str(source),
            "--skip-ledger-persist",
            "--publish",
            "--public-dir",
            str(public_dir),
            "--output",
            str(output),
        ]
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert code == 0
    assert payload["status"] == "published"
    assert payload["publish"]["status"] == "published"
    assert [Path(call[1]).name for call in calls] == [
        "refresh_product_market_from_ledger.py",
        "rerender_dashboard.py",
        "export_argus_demand_readiness.py",
        "export_argus_demand_plan_template.py",
        "attach_post_run_summaries.py",
        "export_argus_evidence_work_queue.py",
        "export_argus_product_muscle_work_queue.py",
        "build_argus_operator_handoff.py",
        "attach_operator_handoff_to_dashboard.py",
        "export_argus_data_plane_manifest.py",
    ]
    assert (public_dir / "data" / "semantic-dashboard.json").exists()
    assert (public_dir / "data" / "argus-data-plane-manifest.json").exists()
