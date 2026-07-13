"""Smoke tests for building product-market runner payloads from export files."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "build_product_market_payload.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("build_product_market_payload", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_product_market_payload_script_writes_json_payload(tmp_path) -> None:
    module = _load_module()
    scout = tmp_path / "scout.json"
    out = tmp_path / "payload.json"
    scout.write_text(
        json.dumps([
            {
                "company_id": 20,
                "company_name": "Constructor",
                "company_role": "competitor",
                "capability": "agentic product discovery",
                "change_type": "release",
                "summary": "Constructor documented AI Shopping Agent.",
                "source_url": "https://constructor.com/changelog/ai-shopping-agent",
                "captured_at": "2026-07-10T19:00:00+00:00",
            }
        ]),
        encoding="utf-8",
    )

    code = module.main([
        "--own-company-name",
        "Algolia",
        "--tenant-id",
        "1",
        "--scout",
        str(scout),
        "--output",
        str(out),
    ])

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert code == 0
    assert payload["tenant_id"] == 1
    assert payload["own_company_name"] == "Algolia"
    assert payload["scout_records"][0]["company_name"] == "Constructor"
    assert payload["conversation_records"] == []
    assert payload["looker_rows"] == []


def test_build_product_market_payload_script_writes_demand_quality_config(tmp_path) -> None:
    module = _load_module()
    out = tmp_path / "payload.json"

    code = module.main([
        "--own-company-name",
        "Algolia",
        "--tenant-id",
        "1",
        "--demand-change-floor",
        "0.03",
        "--demand-value-floor",
        "25",
        "--output",
        str(out),
    ])

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert code == 0
    assert payload["demand_quality"] == {
        "change_floor": 0.03,
        "value_floor": 25.0,
    }


def test_build_product_market_payload_script_merges_multiple_scout_files(tmp_path) -> None:
    module = _load_module()
    scout_a = tmp_path / "constructor.json"
    scout_b = tmp_path / "elastic.json"
    out = tmp_path / "payload.json"
    scout_a.write_text(json.dumps([{"company_name": "Constructor"}]), encoding="utf-8")
    scout_b.write_text(json.dumps([{"company_name": "Elastic"}]), encoding="utf-8")

    code = module.main([
        "--own-company-name",
        "Algolia",
        "--tenant-id",
        "1",
        "--scout",
        str(scout_a),
        "--scout",
        str(scout_b),
        "--output",
        str(out),
    ])

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert code == 0
    assert [row["company_name"] for row in payload["scout_records"]] == [
        "Constructor",
        "Elastic",
    ]


def test_build_product_market_payload_script_merges_multiple_looker_files(tmp_path) -> None:
    module = _load_module()
    looker_a = tmp_path / "demand-a.csv"
    looker_b = tmp_path / "demand-b.csv"
    out = tmp_path / "payload.json"
    header = "topic,metric,value,change_pct,period_start,period_end,source_label,source_url\n"
    looker_a.write_text(
        header
        + "agentic product discovery,engaged_sessions,100,0.10,2026-07-01T00:00:00+00:00,2026-07-08T00:00:00+00:00,GA4,looker://algolia/a\n",
        encoding="utf-8",
    )
    looker_b.write_text(
        header
        + "context engineering,engaged_sessions,200,0.20,2026-07-01T00:00:00+00:00,2026-07-08T00:00:00+00:00,GA4,looker://algolia/b\n",
        encoding="utf-8",
    )

    code = module.main([
        "--own-company-name",
        "Algolia",
        "--tenant-id",
        "1",
        "--looker",
        str(looker_a),
        "--looker",
        str(looker_b),
        "--output",
        str(out),
    ])

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert code == 0
    assert [row["topic"] for row in payload["looker_rows"]] == [
        "agentic product discovery",
        "context engineering",
    ]


def test_build_product_market_payload_script_normalizes_ga_looker_export(tmp_path) -> None:
    module = _load_module()
    looker = tmp_path / "ga-pages.csv"
    out = tmp_path / "payload.json"
    looker.write_text(
        "Page title,Page path,Engaged sessions,Engaged sessions previous period,Period start,Period end,Looker Studio URL\n"
        "AI Shopping Agent guide,/solutions/ai-shopping-agent,240,160,2026-07-01,2026-07-08,https://lookerstudio.google.com/reporting/abc\n",
        encoding="utf-8",
    )

    code = module.main([
        "--own-company-name",
        "Algolia",
        "--tenant-id",
        "1",
        "--looker",
        str(looker),
        "--output",
        str(out),
    ])

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert code == 0
    assert payload["looker_rows"][0]["topic"] == "AI Shopping Agent"
    assert payload["looker_rows"][0]["metric"] == "engaged_sessions"
    assert payload["looker_rows"][0]["value"] == 240.0
    assert payload["looker_rows"][0]["change_pct"] == 0.5


def test_build_product_market_payload_script_includes_learning_plan_instructions(tmp_path) -> None:
    module = _load_module()
    learning_plan = tmp_path / "next-sweep-learning-plan.json"
    out = tmp_path / "payload.json"
    learning_plan.write_text(
        json.dumps(
            {
                "tenant_id": 1,
                "instructions": [
                    {
                        "tenant_id": 1,
                        "kind": "other",
                        "priority": "critical",
                        "summary": "Re-audit Coveo before ranking Constructor.",
                        "instruction": "Re-audit Coveo before ranking Constructor.",
                        "status": "ready_for_next_sweep",
                        "evidence_event_ids": [101],
                        "source_improvement_ids": [202],
                    }
                ],
                "skipped": [{"improvement_id": 203, "reason": "missing evidence"}],
            }
        ),
        encoding="utf-8",
    )

    code = module.main([
        "--own-company-name",
        "Algolia",
        "--tenant-id",
        "1",
        "--learning-plan",
        str(learning_plan),
        "--output",
        str(out),
    ])

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert code == 0
    assert payload["learning_instructions"] == [
        {
            "tenant_id": 1,
            "kind": "other",
            "priority": "critical",
            "summary": "Re-audit Coveo before ranking Constructor.",
            "instruction": "Re-audit Coveo before ranking Constructor.",
            "status": "ready_for_next_sweep",
            "evidence_event_ids": [101],
            "source_improvement_ids": [202],
        }
    ]


def test_build_product_market_payload_script_runs_scout_command_json(tmp_path) -> None:
    module = _load_module()
    scout_output = tmp_path / "scout-command.json"
    payload_output = tmp_path / "payload.json"
    command = [
        sys.executable,
        "-c",
        (
            "import json, sys; "
            "open(sys.argv[1], 'w', encoding='utf-8').write(json.dumps(["
            "{'company_name':'Elastic','capability':'context engineering'}"
            "]))"
        ),
        str(scout_output),
    ]

    code = module.main([
        "--own-company-name",
        "Algolia",
        "--tenant-id",
        "1",
        "--scout-command-json",
        json.dumps(
            {
                "command": command,
                "output_path": str(scout_output),
                "timeout_seconds": 5,
            }
        ),
        "--output",
        str(payload_output),
    ])

    payload = json.loads(payload_output.read_text(encoding="utf-8"))
    assert code == 0
    assert payload["scout_records"] == [
        {"company_name": "Elastic", "capability": "context engineering"}
    ]
