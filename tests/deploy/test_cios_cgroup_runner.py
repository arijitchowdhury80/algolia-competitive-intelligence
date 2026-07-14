"""Contract tests for the systemd/cgroup CI-OS run boundary."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "deploy/cios-runner.service"
HOST_RUNNER = ROOT / "deploy/cios-host-runner.sh"
FINALIZER = ROOT / "deploy/cios-run-finalize.sh"
DAILY_WRAPPER = ROOT / "deploy/cios-daily.sh"


def test_runner_service_delegates_cgroups_to_cios_and_enforces_outer_timeout():
    text = SERVICE.read_text(encoding="utf-8")

    assert "Type=exec" in text
    assert "User=cios" in text
    assert "Group=cios" in text
    assert "Delegate=yes" in text
    assert "DelegateSubgroup=supervisor" in text
    assert "KillMode=control-group" in text
    assert "RuntimeMaxSec=" in text
    assert "TimeoutStopSec=" in text
    assert "Environment=CIOS_REQUIRE_CGROUP_CONTAINMENT=1" in text
    assert "ExecStopPost=/opt/cios/app/deploy/cios-run-finalize.sh" in text


def test_daily_wrapper_has_no_pid_tree_watchdog():
    text = DAILY_WRAPPER.read_text(encoding="utf-8")

    assert "kill_process_tree" not in text
    assert "daily_production_run.py &" not in text


def test_host_runner_processes_only_one_request_per_service_activation(tmp_path):
    app = tmp_path / "app"
    public = tmp_path / "public"
    queue = app / "run-queue"
    queue.mkdir(parents=True)
    public.mkdir()
    daily = app / "deploy/cios-daily.sh"
    daily.parent.mkdir(parents=True)
    daily.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    daily.chmod(0o755)
    (queue / "001.request").write_text("first\n", encoding="utf-8")
    (queue / "002.request").write_text("second\n", encoding="utf-8")
    env = os.environ.copy()
    env.update(
        {
            "CIOS_APP_DIR": str(app),
            "CIOS_PUBLIC_DIR": str(public),
            "CIOS_RUNNER_QUEUE_DIR": str(queue),
        }
    )

    result = subprocess.run(
        ["sh", str(HOST_RUNNER)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert len(list(queue.glob("*.result"))) == 1
    assert len(list(queue.glob("*.done"))) == 1
    assert len(list(queue.glob("*.request"))) == 1
    assert not (queue / ".active-run").exists()


def test_systemd_timeout_finalizer_writes_terminal_result_after_cleanup(tmp_path):
    queue = tmp_path / "queue"
    public = tmp_path / "public"
    queue.mkdir()
    (queue / "run-1.running").write_text("request\n", encoding="utf-8")
    (queue / ".active-run").write_text("run-1\n", encoding="utf-8")
    env = os.environ.copy()
    env.update(
        {
            "CIOS_RUNNER_QUEUE_DIR": str(queue),
            "CIOS_PUBLIC_DIR": str(public),
            "SERVICE_RESULT": "timeout",
            "EXIT_CODE": "killed",
            "EXIT_STATUS": "KILL",
        }
    )

    result = subprocess.run(
        ["sh", str(FINALIZER)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert (queue / "run-1.result").read_text(encoding="utf-8") == "124\n"
    assert (queue / "run-1.done").exists()
    assert not (queue / "run-1.running").exists()
    assert "systemd runtime timeout" in (queue / "run-1.log").read_text(encoding="utf-8")
    assert "blocked_runtime_timeout" in (
        public / "data/argus-latest-run-status.json"
    ).read_text(encoding="utf-8")


def test_finalizer_does_not_overwrite_completed_result(tmp_path):
    queue = tmp_path / "queue"
    queue.mkdir()
    (queue / "run-1.done").write_text("request\n", encoding="utf-8")
    (queue / "run-1.result").write_text("0\n", encoding="utf-8")
    env = os.environ.copy()
    env.update({"CIOS_RUNNER_QUEUE_DIR": str(queue), "SERVICE_RESULT": "success"})

    result = subprocess.run(
        ["sh", str(FINALIZER)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert (queue / "run-1.result").read_text(encoding="utf-8") == "0\n"


def test_finalizer_does_not_claim_unrelated_stale_running_artifact(tmp_path):
    queue = tmp_path / "queue"
    queue.mkdir()
    (queue / "old.running").write_text("stale evidence\n", encoding="utf-8")
    env = os.environ.copy()
    env.update({"CIOS_RUNNER_QUEUE_DIR": str(queue), "SERVICE_RESULT": "timeout"})

    result = subprocess.run(
        ["sh", str(FINALIZER)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert (queue / "old.running").exists()
    assert not (queue / "old.result").exists()
