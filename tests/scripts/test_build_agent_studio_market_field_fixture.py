from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "build_agent_studio_market_field_fixture.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("build_agent_studio_market_field_fixture", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_fixture_builder_writes_agent_studio_dashboard_and_manifest(tmp_path) -> None:
    module = _load_module()

    code = module.main(["--out-dir", str(tmp_path)])

    manifest = json.loads((tmp_path / "agent-studio-market-field-fixture-manifest.json").read_text(encoding="utf-8"))
    html = (tmp_path / "argus-dashboard.html").read_text(encoding="utf-8")
    assert code == 0
    assert (tmp_path / "argus-dashboard.json").exists()
    assert manifest["status"] == "built"
    assert manifest["selected_hotspot"] == "Agent Studio"
    assert "product_reality" in manifest["node_types"]
    assert "argus_recommendation" in manifest["proof_planes"]
    assert "Turn Agent Studio into an evidence-backed market narrative." in html
