from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "scan_public_artifacts.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("scan_public_artifacts", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_public_artifact_scan_passes_generated_agent_studio_bundle(tmp_path) -> None:
    fixture_builder_path = ROOT / "scripts" / "build_agent_studio_market_field_fixture.py"
    fixture_spec = importlib.util.spec_from_file_location("build_agent_studio_market_field_fixture", fixture_builder_path)
    fixture_module = importlib.util.module_from_spec(fixture_spec)
    sys.modules[fixture_spec.name] = fixture_module
    fixture_spec.loader.exec_module(fixture_module)
    fixture_module.main(["--out-dir", str(tmp_path)])

    module = _load_module()
    result = module.scan_public_artifacts(tmp_path)

    assert result["status"] == "passed"
    assert result["public_safe"] is True
    assert result["scanned_file_count"] >= 2
    assert result["findings"] == []


def test_public_artifact_scan_rejects_private_paths_and_file_urls(tmp_path) -> None:
    (tmp_path / "argus-dashboard.html").write_text(
        '<a href="file:///tmp/private.csv">debug</a><script>const path="/root/.hermes/apps/cios/out/private.json";</script>',
        encoding="utf-8",
    )
    module = _load_module()

    result = module.scan_public_artifacts(tmp_path)

    assert result["status"] == "failed"
    assert result["public_safe"] is False
    codes = {finding["code"] for finding in result["findings"]}
    assert "private_path" in codes
    assert "file_url" in codes


def test_public_artifact_scan_rejects_secret_like_values_and_external_cdn(tmp_path) -> None:
    (tmp_path / "app.js").write_text(
        'const api_key = "sk-live-abcdefghijklmnopqrstuvwxyz"; import("https://unpkg.com/three");',
        encoding="utf-8",
    )
    module = _load_module()

    result = module.scan_public_artifacts(tmp_path)

    assert result["status"] == "failed"
    codes = {finding["code"] for finding in result["findings"]}
    assert "secret_like_value" in codes
    assert "external_runtime_host" in codes


def test_public_artifact_scan_cli_writes_json_and_returns_failure(tmp_path) -> None:
    (tmp_path / "status.json").write_text('{"token":"ghp_abcdefghijklmnopqrstuvwxyz1234567890"}', encoding="utf-8")
    output = tmp_path / "scan.json"
    module = _load_module()

    code = module.main(["--public-dir", str(tmp_path), "--output", str(output)])

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert code == 2
    assert payload["status"] == "failed"
    assert payload["public_safe"] is False
