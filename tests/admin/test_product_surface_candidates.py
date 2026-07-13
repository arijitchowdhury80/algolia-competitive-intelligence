from __future__ import annotations

import json
import subprocess
from pathlib import Path

from cios.admin.product_surface_candidates import ProductSurfaceCandidatePromotionControl


def test_product_surface_candidate_promotion_control_runs_filtered_promote_script(
    tmp_path, monkeypatch
) -> None:
    app_dir = tmp_path / "app"
    scripts = app_dir / "scripts"
    scripts.mkdir(parents=True)
    work_root = tmp_path / "work"
    calls: list[dict] = []

    def fake_run(command, *, cwd, text, capture_output, check):
        calls.append(
            {
                "command": command,
                "cwd": cwd,
                "text": text,
                "capture_output": capture_output,
                "check": check,
            }
        )
        output = work_root / "algolia" / "product-surface-candidate-promotion-summary.json"
        output.parent.mkdir(parents=True)
        output.write_text(
            json.dumps(
                {
                    "status": "completed",
                    "promoted_count": 1,
                    "promoted_surfaces": [{"company_name": "Klevu"}],
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr("cios.admin.product_surface_candidates.subprocess.run", fake_run)

    result = ProductSurfaceCandidatePromotionControl(
        app_dir=app_dir,
        work_root=work_root,
        python_bin="/venv/bin/python",
    ).run(
        tenant_slug="algolia",
        tenant_id=1,
        company_name="Klevu",
        company_id=9,
        surface_family="changelog",
        discovery_source="product_muscle_gap_plan",
        promoted_by="argus",
        limit=1,
    )

    command = calls[0]["command"]
    assert command[:2] == [
        "/venv/bin/python",
        str(scripts / "promote_product_surface_candidates.py"),
    ]
    assert command[command.index("--tenant-id") + 1] == "1"
    assert command[command.index("--company-name") + 1] == "Klevu"
    assert command[command.index("--company-id") + 1] == "9"
    assert command[command.index("--surface-family") + 1] == "changelog"
    assert command[command.index("--promoted-by") + 1] == "argus"
    assert command[command.index("--limit") + 1] == "1"
    assert calls[0]["cwd"] == str(app_dir)
    assert result["status"] == "completed"
    assert result["tenant_id"] == 1
    assert result["tenant_slug"] == "algolia"
    assert result["command_status"] == "ok"
    assert Path(result["summary_path"]).name == "product-surface-candidate-promotion-summary.json"
