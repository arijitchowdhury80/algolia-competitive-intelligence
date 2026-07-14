from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "publish_generation.py"
RUN_ID = "cios-20260714T090000Z-1234"
GENERATED_AT = datetime(2026, 7, 14, 9, 0, tzinfo=timezone.utc)


def _load_module():
    spec = importlib.util.spec_from_file_location("publish_generation", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _status(path: Path, *, run_id: str, publish_status: str) -> Path:
    return _write(
        path,
        json.dumps(
            {
                "schema_version": 2,
                "run_id": run_id,
                "tenant_slug": "algolia",
                "generated_at": GENERATED_AT.isoformat(),
                "publish_status": publish_status,
                "status": "published" if publish_status == "published" else "blocked_on_evidence",
                "public_dashboard_updated": publish_status == "published",
                "safety": {
                    "artifact_paths_redacted": False,
                    "secret_values_included": True,
                    "public_safe": False,
                },
            }
        ),
    )


def test_cli_publishes_complete_decision_and_structured_verdict(tmp_path: Path) -> None:
    module = _load_module()
    source = tmp_path / "source"
    store = tmp_path / "store"
    verdict = tmp_path / "publication-verdict.json"
    dashboard = {
        "generated_at": GENERATED_AT.isoformat(),
        "run_health": {"run_id": RUN_ID},
        "product_market_run": {"run_id": RUN_ID},
    }
    brief = _write(source / "briefs" / "algolia" / "constructor.html", "<article>Constructor</article>")
    package_verdict = _write(
        source / "package-verdict.json",
        json.dumps(
            {
                "schema_version": 1,
                "gate": "hermes_package_contract",
                "run_id": RUN_ID,
                "generated_at": GENERATED_AT.isoformat(),
                "status": "pass",
                "exit_code": 0,
                "checks": {"required_contract": True},
            }
        ),
    )

    code = module.main(
        [
            "--store-root", str(store),
            "--run-id", RUN_ID,
            "--tenant", "algolia",
            "--kind", "decision",
            "--dashboard-html", str(_write(source / "index.html", "<main>Argus</main>")),
            "--brief", str(_write(source / "brief.html", "<article>Brief</article>")),
            "--dashboard-json", str(_write(source / "dashboard.json", json.dumps(dashboard))),
            "--data-plane-manifest", str(_write(source / "data-plane.json", json.dumps({"run_id": RUN_ID, "generated_at": GENERATED_AT.isoformat()}))),
            "--status", str(_status(source / "status.json", run_id=RUN_ID, publish_status="published")),
            "--briefs-dir", str(source / "briefs"),
            "--package-verdict", str(package_verdict),
            "--output", str(verdict),
            "--now", (GENERATED_AT + timedelta(minutes=5)).isoformat(),
        ]
    )

    payload = json.loads(verdict.read_text(encoding="utf-8"))
    assert code == 0
    assert payload["gate"] == "publication_integrity"
    assert payload["run_id"] == RUN_ID
    assert payload["status"] == "pass"
    assert payload["checks"] == {
        "generation_validated": True,
        "pointer_promoted": True,
        "status_committed": True,
    }
    assert (store / "served" / "index.html").resolve().read_text(encoding="utf-8") == "<main>Argus</main>"
    assert (store / "served" / "briefs" / "algolia" / brief.name).is_file()
    published_status = json.loads((store / "latest-status.json").read_text(encoding="utf-8"))
    assert published_status["safety"]["public_safe"] is True
