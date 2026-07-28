from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "validate_market_field_visual_acceptance.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("validate_market_field_visual_acceptance", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_visual_acceptance_result_preserves_design_authority_gap() -> None:
    module = _load_module()

    result = module.build_visual_acceptance_result(
        url="file:///tmp/argus-dashboard.html",
        expected_hotspot="Agent Studio",
        viewport_results=[
            {
                "viewport": "desktop",
                "width": 1280,
                "height": 900,
                "canvas_nonblank": True,
                "selected_hotspot": "Agent Studio",
                "visible_terms": [
                    "Agent Studio",
                    "Product reality",
                    "Market conversation",
                    "Audience Demand",
                    "Product Marketing",
                    "Confidence boundaries",
                ],
                "clipped_selectors": [],
            }
        ],
        console_errors=[],
        design_authority_status="missing_or_unwaived",
    )

    assert result["status"] == "passed_with_design_authority_gap"
    assert result["design_authority_status"] == "missing_or_unwaived"
    assert result["final_visual_acceptance"] is False
    assert result["viewport_count"] == 1


def test_build_visual_acceptance_result_rejects_clipped_critical_ui() -> None:
    module = _load_module()

    with pytest.raises(AssertionError, match="clipped"):
        module.build_visual_acceptance_result(
            url="file:///tmp/argus-dashboard.html",
            expected_hotspot="Agent Studio",
            viewport_results=[
                {
                    "viewport": "mobile",
                    "width": 390,
                    "height": 844,
                    "canvas_nonblank": True,
                    "selected_hotspot": "Agent Studio",
                    "visible_terms": ["Agent Studio"],
                    "clipped_selectors": ["[data-selected-hotspot-title]"],
                }
            ],
            console_errors=[],
            design_authority_status="missing_or_unwaived",
        )


def test_cli_writes_gap_status_for_agent_studio_fixture(tmp_path) -> None:
    fixture_builder_path = ROOT / "scripts" / "build_agent_studio_market_field_fixture.py"
    fixture_spec = importlib.util.spec_from_file_location("build_agent_studio_market_field_fixture", fixture_builder_path)
    fixture_module = importlib.util.module_from_spec(fixture_spec)
    sys.modules[fixture_spec.name] = fixture_module
    fixture_spec.loader.exec_module(fixture_module)
    fixture_module.main(["--out-dir", str(tmp_path)])

    module = _load_module()
    output = tmp_path / "market-field-visual-acceptance.json"

    code = module.main(
        [
            "--url",
            (tmp_path / "argus-dashboard.html").resolve().as_uri(),
            "--output",
            str(output),
        ]
    )

    result = json.loads(output.read_text(encoding="utf-8"))
    assert code == 0
    assert result["status"] == "passed_with_design_authority_gap"
    assert result["expected_hotspot"] == "Agent Studio"
    assert result["final_visual_acceptance"] is False
    assert result["viewport_count"] == 3
    assert sorted(item["viewport"] for item in result["viewports"]) == ["desktop", "mobile", "tablet"]
