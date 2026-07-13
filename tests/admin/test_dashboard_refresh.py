from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cios.admin.dashboard_refresh import AdminDashboardRefreshRunner


def _write_dashboard_artifacts(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "argus-dashboard.html").write_text("cockpit", encoding="utf-8")
    (out_dir / "brief.html").write_text("brief", encoding="utf-8")
    (out_dir / "argus-dashboard.json").write_text('{"schema_version":17}', encoding="utf-8")
    (out_dir / "argus-data-plane-manifest.json").write_text('{"schema_version":1}', encoding="utf-8")
    brief_dir = out_dir / "briefs" / "algolia"
    brief_dir.mkdir(parents=True, exist_ok=True)
    (brief_dir / "constructor-2026-07-11.html").write_text("constructor", encoding="utf-8")


def _write_demand_intake_artifact(out_dir: Path) -> None:
    (out_dir / "argus-demand-intake.json").write_text(
        '{"status":"blocked_missing_demand_source","exit_code":2}',
        encoding="utf-8",
    )


def test_admin_dashboard_refresh_runner_rerenders_and_publishes(tmp_path, monkeypatch) -> None:
    app_dir = tmp_path / "app"
    out_dir = tmp_path / "out"
    work_root = tmp_path / "work"
    public_dir = tmp_path / "public"
    script = app_dir / "scripts" / "rerender_dashboard.py"
    script.parent.mkdir(parents=True)
    script.write_text("# fake rerender script path\n", encoding="utf-8")
    calls: list[dict] = []

    def fake_run(cmd, **kwargs):
        calls.append({"cmd": [str(part) for part in cmd], "kwargs": kwargs})
        _write_dashboard_artifacts(out_dir)
        if str(cmd[1]).endswith("run_argus_demand_intake.py"):
            _write_demand_intake_artifact(out_dir)
            return subprocess.CompletedProcess(cmd, 2, stdout="blocked\n", stderr="")
        if str(cmd[1]).endswith("export_argus_demand_plan_template.py"):
            (out_dir / "argus-demand-plan-template.csv").write_text(
                "Page title,Argus topic\n,Channel Assistant\n",
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(cmd, 0, stdout="template\n", stderr="")
        if str(cmd[1]).endswith("export_public_run_status.py"):
            (out_dir / "argus-public-run-status.json").write_text(
                '{"status":"blocked_on_evidence","publish_status":"blocked"}',
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(cmd, 0, stdout="status\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="rerendered\n", stderr="")

    monkeypatch.setattr("cios.admin.dashboard_refresh.subprocess.run", fake_run)

    runner = AdminDashboardRefreshRunner(
        app_dir=app_dir,
        out_dir=out_dir,
        public_dir=public_dir,
        work_root=work_root,
        python_bin="/venv/bin/python",
    )
    result = runner(tenant_slug="algolia")

    assert result["status"] == "published"
    assert result["rerender"]["returncode"] == 0
    assert result["sidecars"]["demand_readiness"]["returncode"] == 0
    assert result["sidecars"]["demand_plan_template"]["returncode"] == 0
    assert result["sidecars"]["demand_intake"]["returncode"] == 2
    assert result["sidecars"]["product_muscle_work_queue"]["returncode"] == 0
    assert result["sidecars"]["attach_operator_handoff"]["returncode"] == 0
    assert result["sidecars"]["data_plane_manifest"]["returncode"] == 0
    assert result["sidecars"]["public_run_status"]["returncode"] == 0
    assert result["publish"]["status"] == "published"
    assert [Path(call["cmd"][1]).name for call in calls] == [
        "rerender_dashboard.py",
        "export_argus_demand_readiness.py",
        "export_argus_demand_plan_template.py",
        "run_argus_demand_intake.py",
        "attach_post_run_summaries.py",
        "export_argus_evidence_work_queue.py",
        "export_argus_product_muscle_work_queue.py",
        "build_argus_operator_handoff.py",
        "attach_operator_handoff_to_dashboard.py",
        "export_argus_data_plane_manifest.py",
        "export_public_run_status.py",
    ]
    assert calls[0]["cmd"] == [
        "/venv/bin/python",
        str(script),
        "--tenant",
        "algolia",
        "--out-dir",
        str(out_dir),
    ]
    assert "--work-root" in calls[1]["cmd"]
    assert str(work_root) in calls[1]["cmd"]
    assert "--readiness" in calls[2]["cmd"]
    assert str(out_dir / "argus-demand-readiness.json") in calls[2]["cmd"]
    assert "--output" in calls[2]["cmd"]
    assert str(out_dir / "argus-demand-plan-template.csv") in calls[2]["cmd"]
    assert "--output" in calls[3]["cmd"]
    assert str(out_dir / "argus-demand-intake.json") in calls[3]["cmd"]
    assert "--dashboard" in calls[3]["cmd"]
    assert str(out_dir / "argus-dashboard.json") in calls[3]["cmd"]
    assert "--work-root" in calls[3]["cmd"]
    assert str(work_root) in calls[3]["cmd"]
    assert "--record-history" in calls[3]["cmd"]
    assert "--output" in calls[6]["cmd"]
    assert str(out_dir / "argus-product-muscle-work-queue.json") in calls[6]["cmd"]
    assert "--work-root" in calls[6]["cmd"]
    assert str(work_root) in calls[6]["cmd"]
    assert "--product-muscle-queue" in calls[7]["cmd"]
    assert str(out_dir / "argus-product-muscle-work-queue.json") in calls[7]["cmd"]
    assert "--demand-readiness" in calls[7]["cmd"]
    assert str(out_dir / "argus-demand-readiness.json") in calls[7]["cmd"]
    assert "--demand-plan-template" in calls[7]["cmd"]
    assert str(out_dir / "argus-demand-plan-template.csv") in calls[7]["cmd"]
    assert "--demand-intake" in calls[9]["cmd"]
    assert str(out_dir / "argus-demand-intake.json") in calls[9]["cmd"]
    assert "--demand-plan-template" in calls[9]["cmd"]
    assert str(out_dir / "argus-demand-plan-template.csv") in calls[9]["cmd"]
    assert "--product-muscle-work-queue" in calls[9]["cmd"]
    assert str(out_dir / "argus-product-muscle-work-queue.json") in calls[9]["cmd"]
    assert "--manifest" in calls[10]["cmd"]
    assert str(out_dir / "argus-data-plane-manifest.json") in calls[10]["cmd"]
    assert "--dashboard" in calls[10]["cmd"]
    assert str(out_dir / "argus-dashboard.json") in calls[10]["cmd"]
    assert "--publish-status" in calls[10]["cmd"]
    assert "blocked" in calls[10]["cmd"]
    assert "--output" in calls[10]["cmd"]
    assert str(out_dir / "argus-public-run-status.json") in calls[10]["cmd"]
    assert all(
        call["kwargs"] == {"cwd": str(app_dir), "text": True, "capture_output": True, "check": False}
        for call in calls
    )
    assert (public_dir / "index.html").read_text(encoding="utf-8") == "cockpit"
    assert (public_dir / "data" / "semantic-dashboard.json").read_text(encoding="utf-8") == '{"schema_version":17}'
    assert (public_dir / "data" / "argus-data-plane-manifest.json").read_text(encoding="utf-8") == (
        '{"schema_version":1}'
    )
    assert (public_dir / "data" / "argus-latest-run-status.json").read_text(encoding="utf-8") == (
        '{"status":"blocked_on_evidence","publish_status":"blocked"}'
    )
    assert (public_dir / "v2" / "data" / "argus-latest-run-status.json").exists()
    assert (public_dir / "data" / "argus-demand-plan-template.csv").read_text(encoding="utf-8") == (
        "Page title,Argus topic\n,Channel Assistant\n"
    )
    assert (public_dir / "v2" / "data" / "argus-demand-plan-template.csv").exists()
    assert (public_dir / "briefs" / "algolia" / "constructor-2026-07-11.html").exists()


def test_admin_dashboard_refresh_runner_blocks_failed_rerender(tmp_path, monkeypatch) -> None:
    app_dir = tmp_path / "app"
    out_dir = tmp_path / "out"
    script = app_dir / "scripts" / "rerender_dashboard.py"
    script.parent.mkdir(parents=True)
    script.write_text("# fake rerender script path\n", encoding="utf-8")

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 2, stdout="", stderr="database unavailable")

    monkeypatch.setattr("cios.admin.dashboard_refresh.subprocess.run", fake_run)

    runner = AdminDashboardRefreshRunner(app_dir=app_dir, out_dir=out_dir, python_bin="/venv/bin/python")

    with pytest.raises(RuntimeError, match="database unavailable"):
        runner(tenant_slug="algolia")


def test_admin_dashboard_refresh_runner_blocks_failed_sidecar_before_publish(tmp_path, monkeypatch) -> None:
    app_dir = tmp_path / "app"
    out_dir = tmp_path / "out"
    public_dir = tmp_path / "public"
    script = app_dir / "scripts" / "rerender_dashboard.py"
    script.parent.mkdir(parents=True)
    script.write_text("# fake rerender script path\n", encoding="utf-8")

    def fake_run(cmd, **kwargs):
        _write_dashboard_artifacts(out_dir)
        if str(cmd[1]).endswith("run_argus_demand_intake.py"):
            _write_demand_intake_artifact(out_dir)
            return subprocess.CompletedProcess(cmd, 2, stdout="blocked\n", stderr="")
        if str(cmd[1]).endswith("export_argus_evidence_work_queue.py"):
            return subprocess.CompletedProcess(cmd, 3, stdout="", stderr="database unavailable")
        return subprocess.CompletedProcess(cmd, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr("cios.admin.dashboard_refresh.subprocess.run", fake_run)

    runner = AdminDashboardRefreshRunner(
        app_dir=app_dir,
        out_dir=out_dir,
        public_dir=public_dir,
        python_bin="/venv/bin/python",
    )

    with pytest.raises(RuntimeError, match="dashboard sidecar evidence_work_queue failed: database unavailable"):
        runner(tenant_slug="algolia")

    assert not (public_dir / "index.html").exists()


def test_admin_dashboard_refresh_runner_blocks_failed_product_muscle_sidecar_before_publish(
    tmp_path, monkeypatch
) -> None:
    app_dir = tmp_path / "app"
    out_dir = tmp_path / "out"
    public_dir = tmp_path / "public"
    script = app_dir / "scripts" / "rerender_dashboard.py"
    script.parent.mkdir(parents=True)
    script.write_text("# fake rerender script path\n", encoding="utf-8")

    def fake_run(cmd, **kwargs):
        _write_dashboard_artifacts(out_dir)
        if str(cmd[1]).endswith("run_argus_demand_intake.py"):
            _write_demand_intake_artifact(out_dir)
            return subprocess.CompletedProcess(cmd, 2, stdout="blocked\n", stderr="")
        if str(cmd[1]).endswith("export_argus_product_muscle_work_queue.py"):
            return subprocess.CompletedProcess(cmd, 4, stdout="", stderr="product surfaces missing")
        return subprocess.CompletedProcess(cmd, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr("cios.admin.dashboard_refresh.subprocess.run", fake_run)

    runner = AdminDashboardRefreshRunner(
        app_dir=app_dir,
        out_dir=out_dir,
        public_dir=public_dir,
        python_bin="/venv/bin/python",
    )

    with pytest.raises(
        RuntimeError,
        match="dashboard sidecar product_muscle_work_queue failed: product surfaces missing",
    ):
        runner(tenant_slug="algolia")

    assert not (public_dir / "index.html").exists()


def test_admin_dashboard_refresh_runner_blocks_when_demand_intake_sidecar_is_missing(
    tmp_path, monkeypatch
) -> None:
    app_dir = tmp_path / "app"
    out_dir = tmp_path / "out"
    public_dir = tmp_path / "public"
    script = app_dir / "scripts" / "rerender_dashboard.py"
    script.parent.mkdir(parents=True)
    script.write_text("# fake rerender script path\n", encoding="utf-8")

    def fake_run(cmd, **kwargs):
        _write_dashboard_artifacts(out_dir)
        if str(cmd[1]).endswith("run_argus_demand_intake.py"):
            return subprocess.CompletedProcess(cmd, 2, stdout="blocked\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr("cios.admin.dashboard_refresh.subprocess.run", fake_run)

    runner = AdminDashboardRefreshRunner(
        app_dir=app_dir,
        out_dir=out_dir,
        public_dir=public_dir,
        python_bin="/venv/bin/python",
    )

    with pytest.raises(
        RuntimeError,
        match="dashboard sidecar demand_intake failed: missing demand intake artifact",
    ):
        runner(tenant_slug="algolia")

    assert not (public_dir / "index.html").exists()
