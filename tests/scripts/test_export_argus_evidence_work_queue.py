"""Smoke contract for the Hermes-callable Argus evidence work queue export."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from cios.admin.types import ArgusRunStatus, EvidenceLedgerState


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "export_argus_evidence_work_queue.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("export_argus_evidence_work_queue", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_export_argus_evidence_work_queue_script_exists_and_imports() -> None:
    module = _load_module()

    assert hasattr(module, "main")
    assert hasattr(module, "resolve_tenant_id")
    assert hasattr(module, "build_evidence_work_queue_payload")


def test_build_evidence_work_queue_payload_is_machine_readable_and_traceable() -> None:
    module = _load_module()
    run_status = ArgusRunStatus(
        tenant_slug="algolia",
        tenant_id=1,
        demand_plane_status="missing",
        looker_discovered_count=0,
        looker_ready_count=0,
        looker_error_count=0,
        looker_normalized_row_count=0,
        run_intelligence_history=[
            {
                "run_intelligence_id": 17,
                "verdict": "watch",
                "top_insight": "Pattern found but action withheld.",
                "confidence_limits": ["Demand evidence is missing, so Argus withheld owner recommendations."],
                "created_at": "2026-07-11T19:50:00+00:00",
                "product_event_count": 2,
                "conversation_theme_count": 1,
                "demand_signal_count": 0,
                "pattern_count": 1,
                "recommendation_count": 0,
            }
        ],
    )
    ledger = EvidenceLedgerState(
        tenant_slug="algolia",
        tenant_id=1,
        product_events=[],
        conversation_themes=[],
        demand_signals=[],
        patterns=[],
    )

    payload = module.build_evidence_work_queue_payload(
        tenant_slug="algolia",
        tenant_id=1,
        run_status=run_status,
        evidence_ledger=ledger,
        generated_at="2026-07-11T20:00:00Z",
    )

    assert payload["tenant_slug"] == "algolia"
    assert payload["tenant_id"] == 1
    assert payload["generated_at"] == "2026-07-11T20:00:00Z"
    assert payload["work_item_count"] == 1
    assert payload["blocking_count"] == 1
    assert payload["limiting_count"] == 0
    assert payload["items"][0]["work_item_id"] == "argus-evidence:17:demand"
    assert payload["items"][0]["evidence_plane"] == "demand"
    assert payload["items"][0]["primary_action_label"] == "Download demand template"
    assert payload["items"][0]["observed_state"]["demand_plane_status"] == "missing"


def test_export_argus_evidence_work_queue_writes_output_file(tmp_path) -> None:
    module = _load_module()
    payload = {
        "tenant_slug": "algolia",
        "tenant_id": 1,
        "generated_at": "2026-07-11T20:00:00Z",
        "work_item_count": 0,
        "blocking_count": 0,
        "limiting_count": 0,
        "items": [],
    }
    output = tmp_path / "work" / "argus-evidence-work-queue.json"

    module.write_payload(payload, output)

    assert json.loads(output.read_text(encoding="utf-8")) == payload


def test_export_argus_evidence_work_queue_resolves_tenant_slug() -> None:
    module = _load_module()

    class Conn:
        def execute(self, sql, params):
            assert "FROM tenants" in sql
            assert params == ("algolia",)
            return self

        def fetchone(self):
            return {"id": 42}

    assert module.resolve_tenant_id(Conn(), "algolia") == 42


def test_export_argus_evidence_work_queue_resolves_tenant_slug_from_tuple_rows() -> None:
    module = _load_module()

    class Conn:
        def execute(self, sql, params):
            assert "FROM tenants" in sql
            assert params == ("algolia",)
            return self

        def fetchone(self):
            return (42,)

    assert module.resolve_tenant_id(Conn(), "algolia") == 42
