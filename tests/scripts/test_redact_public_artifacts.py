from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "redact_public_artifacts.py"
SCAN_SCRIPT = ROOT / "scripts" / "scan_public_artifacts.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_redacts_private_paths_from_public_json_and_html_before_scan(tmp_path) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "semantic-dashboard.json").write_text(
        json.dumps(
            {
                "artifact_refs": {
                    "dashboard": "/opt/cios/app/out/argus-dashboard.json",
                    "drop_folder": "/opt/cios/app/data/looker/algolia",
                },
                "debug_link": "file:///tmp/private.csv",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "index.html").write_text(
        '<script>{"path":"/root/.hermes/apps/cios/out/private.json"}</script>',
        encoding="utf-8",
    )
    redact = _load_module(SCRIPT, "redact_public_artifacts")
    scan = _load_module(SCAN_SCRIPT, "scan_public_artifacts")

    result = redact.redact_public_artifacts(tmp_path)
    scan_result = scan.scan_public_artifacts(tmp_path)
    dashboard_text = (tmp_path / "data" / "semantic-dashboard.json").read_text(encoding="utf-8")
    html_text = (tmp_path / "index.html").read_text(encoding="utf-8")

    assert result["status"] == "redacted"
    assert result["redacted_file_count"] == 2
    assert "[redacted-internal-path]" in dashboard_text
    assert "/opt/cios/app" not in dashboard_text
    assert "file:///tmp" not in dashboard_text
    assert "/root/.hermes" not in html_text
    assert scan_result["status"] == "passed"


def test_redaction_does_not_hide_secret_like_values(tmp_path) -> None:
    (tmp_path / "app.js").write_text(
        'const token = "ghp_abcdefghijklmnopqrstuvwxyz1234567890";',
        encoding="utf-8",
    )
    redact = _load_module(SCRIPT, "redact_public_artifacts")
    scan = _load_module(SCAN_SCRIPT, "scan_public_artifacts")

    result = redact.redact_public_artifacts(tmp_path)
    scan_result = scan.scan_public_artifacts(tmp_path)

    assert result["status"] == "clean"
    assert scan_result["status"] == "failed"
    assert {finding["code"] for finding in scan_result["findings"]} == {"secret_like_value"}


def test_redaction_cli_writes_report(tmp_path) -> None:
    (tmp_path / "index.html").write_text("/private/tmp/generated.html", encoding="utf-8")
    output = tmp_path / "redaction.json"
    redact = _load_module(SCRIPT, "redact_public_artifacts")

    code = redact.main(["--public-dir", str(tmp_path), "--output", str(output)])

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert code == 0
    assert payload["status"] == "redacted"
    assert payload["redaction_count"] == 1
