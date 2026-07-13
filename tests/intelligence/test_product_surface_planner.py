"""Tests for planning Hermes-executable product-surface Scout exports."""

from __future__ import annotations

from pathlib import Path

from cios.intelligence.product_surface_planner import plan_product_surface_exports
from cios.intelligence.scout_surface_exporter import ProductSurfaceTarget


def test_plan_product_surface_exports_builds_deterministic_commands(tmp_path) -> None:
    target = ProductSurfaceTarget(
        surface_id=11,
        tenant_id=1,
        company_id=20,
        company_name="Constructor",
        company_role="competitor",
        surface_family="changelog",
        url="https://constructor.com/changelog",
    )
    script_path = Path("/opt/cios/scripts/export_product_surface_with_scout.py")

    plan = plan_product_surface_exports(
        [target],
        output_dir=tmp_path,
        python_bin="/usr/bin/python3",
        script_path=script_path,
        scout_bin="scout",
        provider="gemini/gemini-2.5-flash",
        timeout_seconds=90,
        use_js=True,
    )

    assert len(plan) == 1
    item = plan[0]
    assert item.output_path == tmp_path / "000011-constructor-changelog.json"
    assert item.command == [
        "/usr/bin/python3",
        str(script_path),
        "--tenant-id",
        "1",
        "--company-id",
        "20",
        "--company-name",
        "Constructor",
        "--company-role",
        "competitor",
        "--surface-family",
        "changelog",
        "--url",
        "https://constructor.com/changelog",
        "--scout-bin",
        "scout",
        "--provider",
        "gemini/gemini-2.5-flash",
        "--timeout-seconds",
        "90",
        "--js",
        "--output",
        str(tmp_path / "000011-constructor-changelog.json"),
    ]


def test_plan_product_surface_exports_prioritizes_coverage_learning_targets(tmp_path) -> None:
    constructor = ProductSurfaceTarget(
        surface_id=11,
        tenant_id=1,
        company_id=20,
        company_name="Constructor",
        company_role="competitor",
        surface_family="changelog",
        url="https://constructor.com/changelog",
    )
    coveo = ProductSurfaceTarget(
        surface_id=12,
        tenant_id=1,
        company_id=21,
        company_name="Coveo",
        company_role="competitor",
        surface_family="docs",
        url="https://www.coveo.com/en/docs",
    )

    plan = plan_product_surface_exports(
        [constructor, coveo],
        output_dir=tmp_path,
        python_bin="/usr/bin/python3",
        script_path=Path("/opt/cios/scripts/export_product_surface_with_scout.py"),
        scout_bin="scout",
        provider="gemini/gemini-2.5-flash",
        timeout_seconds=90,
        use_js=False,
        learning_instructions=[
            {
                "kind": "coverage_recheck",
                "instruction": "Re-audit Coveo source coverage before ranking Constructor again.",
                "source_improvement_ids": [202],
            }
        ],
    )

    assert [item.target.company_name for item in plan] == ["Coveo", "Constructor"]
    assert plan[0].learning_priority == 100
    assert plan[0].learning_reasons == [
        "coverage_recheck: Re-audit Coveo source coverage before ranking Constructor again."
    ]
    assert plan[1].learning_priority == 0


def test_plan_product_surface_exports_passes_focus_capability_to_export_command(tmp_path) -> None:
    target = ProductSurfaceTarget(
        surface_id=12,
        tenant_id=1,
        company_id=21,
        company_name="Coveo",
        company_role="competitor",
        surface_family="docs",
        url="https://www.coveo.com/en/docs",
    )
    script_path = Path("/opt/cios/scripts/export_product_surface_with_scout.py")

    plan = plan_product_surface_exports(
        [target],
        output_dir=tmp_path,
        python_bin="/usr/bin/python3",
        script_path=script_path,
        scout_bin="scout",
        provider="gemini/gemini-2.5-flash",
        timeout_seconds=90,
        use_js=False,
        focus_capability="Channel Assistant",
    )

    command = plan[0].command
    assert command[command.index("--focus-capability") + 1] == "Channel Assistant"
    assert plan[0].focus_capability == "Channel Assistant"
