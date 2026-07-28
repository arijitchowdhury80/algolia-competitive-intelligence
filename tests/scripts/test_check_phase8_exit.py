"""Contract tests for the Phase 8 controlled-pilot exit gate."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "check_phase8_exit.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_phase8_exit", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _monitor() -> dict:
    return {
        "status": "pass",
        "release_id": "cios-pilot-algolia-20260728-63f819b",
        "package_commit": "63f819b649fedf2625fad126dcd776fb5fe66788",
        "monitoring": {
            "recommendations": {
                "recommendation_count": 1,
                "pattern_count": 4,
                "next_monitoring_action_count": 2,
            }
        },
    }


def _launch() -> dict:
    return {"status": "pass", "summary": "CI-OS launch readiness gate passed."}


def _public_status() -> dict:
    return {
        "status": "limited_by_evidence",
        "publish_status": "published",
        "public_dashboard_updated": True,
        "product_market_run": {"recommendation_count": 1},
        "current_recommendations": [
            {
                "recommendation_id": 2,
                "owner": "PMM",
                "action": "Turn Agent Studio into an evidence-backed market narrative.",
            }
        ],
    }


def _disposition(decision: str = "used", *, exit_evidence: bool = True) -> dict:
    return {
        "phase": "phase8_controlled_pilot",
        "decision": decision,
        "phase8_exit_evidence": exit_evidence,
        "recommendation_status_to_set": "done" if decision == "used" else "dismissed",
        "recommendation": {
            "recommendation_id": 2,
            "owner": "PMM",
            "action": "Turn Agent Studio into an evidence-backed market narrative.",
        },
        "disposition": {
            "named_team": "Product Marketing",
            "decided_by": "arijit",
            "use_case": "Drafted the PMM narrative brief for Agent Studio launch-defense messaging.",
            "reason": "The read connected shipped proof, rising demand, and a narrative gap.",
        },
    }


def test_phase8_exit_passes_with_green_monitor_and_final_named_team_disposition() -> None:
    module = _load_module()

    payload = module.evaluate_phase8_exit(
        pilot_monitoring=_monitor(),
        launch_readiness=_launch(),
        public_status=_public_status(),
        disposition=_disposition(),
        release_id="cios-pilot-algolia-20260728-63f819b",
        package_commit="63f819b649fedf2625fad126dcd776fb5fe66788",
        generated_at="2026-07-28T16:00:00Z",
    )

    assert payload["status"] == "pass"
    assert payload["phase8_exit_evidence"] is True
    assert payload["checks"]["named_team_disposition_final"] is True
    assert payload["checks"]["current_recommendation_matches_disposition"] is True
    assert payload["blockers"] == []


def test_phase8_exit_fails_when_disposition_is_pending() -> None:
    module = _load_module()

    payload = module.evaluate_phase8_exit(
        pilot_monitoring=_monitor(),
        launch_readiness=_launch(),
        public_status=_public_status(),
        disposition=_disposition("pending", exit_evidence=False),
        release_id="cios-pilot-algolia-20260728-63f819b",
        package_commit="63f819b649fedf2625fad126dcd776fb5fe66788",
        generated_at="2026-07-28T16:00:00Z",
    )

    assert payload["status"] == "fail"
    assert payload["phase8_exit_evidence"] is False
    assert any(item["requirement"] == "named_team_disposition_final" for item in payload["blockers"])


def test_phase8_exit_fails_when_disposition_references_different_recommendation() -> None:
    module = _load_module()
    disposition = _disposition()
    disposition["recommendation"]["recommendation_id"] = 99

    payload = module.evaluate_phase8_exit(
        pilot_monitoring=_monitor(),
        launch_readiness=_launch(),
        public_status=_public_status(),
        disposition=disposition,
        release_id="cios-pilot-algolia-20260728-63f819b",
        package_commit="63f819b649fedf2625fad126dcd776fb5fe66788",
        generated_at="2026-07-28T16:00:00Z",
    )

    assert payload["status"] == "fail"
    assert any(item["requirement"] == "current_recommendation_matches_disposition" for item in payload["blockers"])


def test_phase8_exit_cli_writes_json_and_returns_failure_for_pending(tmp_path) -> None:
    module = _load_module()
    monitor = tmp_path / "monitor.json"
    launch = tmp_path / "launch.json"
    public_status = tmp_path / "public.json"
    disposition = tmp_path / "disposition.json"
    output = tmp_path / "exit.json"
    monitor.write_text(json.dumps(_monitor()), encoding="utf-8")
    launch.write_text(json.dumps(_launch()), encoding="utf-8")
    public_status.write_text(json.dumps(_public_status()), encoding="utf-8")
    disposition.write_text(json.dumps(_disposition("pending", exit_evidence=False)), encoding="utf-8")

    rc = module.main(
        [
            "--pilot-monitoring",
            str(monitor),
            "--launch-readiness",
            str(launch),
            "--public-status",
            str(public_status),
            "--disposition",
            str(disposition),
            "--release-id",
            "cios-pilot-algolia-20260728-63f819b",
            "--package-commit",
            "63f819b649fedf2625fad126dcd776fb5fe66788",
            "--output",
            str(output),
        ]
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert rc == 2
    assert payload["status"] == "fail"
    assert payload["blockers"]
