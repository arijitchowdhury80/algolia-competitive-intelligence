"""Contract tests for the systemd/cgroup CI-OS run boundary."""

from __future__ import annotations

import runpy
import stat
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "deploy/cios-runner.service"
HOST_RUNNER = ROOT / "deploy/cios-host-runner.sh"
FINALIZER = ROOT / "deploy/cios-run-finalize.sh"
DAILY_WRAPPER = ROOT / "deploy/cios-daily.sh"
QUEUE_HELPER = ROOT / "scripts/cios_run_queue.py"
QUEUE_API = runpy.run_path(str(QUEUE_HELPER))
RunQueue = QUEUE_API["RunQueue"]


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


def test_runner_finalizer_is_executable_in_release_archives():
    assert FINALIZER.stat().st_mode & stat.S_IXUSR


def test_daily_wrapper_has_no_pid_tree_watchdog():
    text = DAILY_WRAPPER.read_text(encoding="utf-8")

    assert "kill_process_tree" not in text
    assert "daily_production_run.py &" not in text


def test_daily_wrapper_defaults_to_systemd_queue_and_waits_past_service_cleanup():
    text = DAILY_WRAPPER.read_text(encoding="utf-8")

    assert "HOST_CLIENT_ROOT=/opt/cios/app" in text
    assert "HERMES_CLIENT_ROOT=/opt/data/apps/cios" in text
    assert 'QUEUE="$CLIENT_ROOT/run-queue"' in text
    assert "WAIT_SECONDS=1800" in text
    assert "CIOS_RUNNER_HANDOFF" not in text
    assert "CIOS_DISABLE_RUNNER_HANDOFF" not in text


def test_runner_drains_all_requests_per_service_activation(tmp_path):
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
    with RunQueue(queue) as run_queue:
        run_queue.run_pending(app, public)

    assert len(list(queue.glob("*.result"))) == 2
    assert len(list(queue.glob("*.done"))) == 2
    assert len(list(queue.glob("*.request"))) == 0
    assert not (queue / ".state/active-run").exists()


def test_systemd_timeout_finalizer_writes_terminal_result_after_cleanup(tmp_path):
    queue = tmp_path / "queue"
    public = tmp_path / "public"
    queue.mkdir()
    (queue / "run-1.running").write_text("request\n", encoding="utf-8")
    state = queue / ".state"
    state.mkdir(mode=0o700)
    (state / "active-run").write_text("run-1\n", encoding="utf-8")
    with RunQueue(queue) as run_queue:
        run_queue.finalize(public, "timeout")

    assert (queue / "run-1.result").read_text(encoding="utf-8") == "124\n"
    assert (queue / "run-1.done").exists()
    assert not (queue / "run-1.running").exists()
    assert "systemd runtime timeout" in (state / "run-1.log").read_text(encoding="utf-8")
    assert stat.S_IMODE((state / "run-1.log").stat().st_mode) == 0o600
    assert "blocked_runtime_timeout" in (
        public / "data/argus-latest-run-status.json"
    ).read_text(encoding="utf-8")


def test_finalizer_does_not_overwrite_completed_result(tmp_path):
    queue = tmp_path / "queue"
    queue.mkdir()
    (queue / "run-1.done").write_text("request\n", encoding="utf-8")
    (queue / "run-1.result").write_text("0\n", encoding="utf-8")
    with RunQueue(queue) as run_queue:
        run_queue.finalize(tmp_path / "public", "success")

    assert (queue / "run-1.result").read_text(encoding="utf-8") == "0\n"


def test_finalizer_does_not_claim_unrelated_stale_running_artifact(tmp_path):
    queue = tmp_path / "queue"
    queue.mkdir()
    (queue / "old.running").write_text("stale evidence\n", encoding="utf-8")
    with RunQueue(queue) as run_queue:
        run_queue.finalize(tmp_path / "public", "timeout")

    assert (queue / "old.running").exists()
    assert not (queue / "old.result").exists()


def test_run_queue_refuses_symlink_log_without_touching_target(tmp_path):
    app = tmp_path / "app"
    public = tmp_path / "public"
    queue = tmp_path / "queue"
    queue.mkdir()
    public.mkdir()
    state = queue / ".state"
    state.mkdir(mode=0o700)
    daily = app / "deploy/cios-daily.sh"
    daily.parent.mkdir(parents=True)
    daily.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    daily.chmod(0o755)
    request_id = "run-safe"
    (queue / f"{request_id}.request").write_text("request\n", encoding="utf-8")
    target = tmp_path / "target"
    target.write_text("do not change\n", encoding="utf-8")
    (state / f"{request_id}.log").symlink_to(target)

    with RunQueue(queue) as run_queue:
        run_queue.run_pending(app, public)

    assert target.read_text(encoding="utf-8") == "do not change\n"
    assert (queue / f"{request_id}.result").read_text(encoding="utf-8") == "2\n"


def test_timeout_finalizer_replaces_result_symlink_without_touching_target(tmp_path):
    queue = tmp_path / "queue"
    public = tmp_path / "public"
    queue.mkdir()
    state = queue / ".state"
    state.mkdir(mode=0o700)
    request_id = "run-safe"
    (queue / f"{request_id}.running").write_text("request\n", encoding="utf-8")
    (state / "active-run").write_text(f"{request_id}\n", encoding="utf-8")
    target = tmp_path / "target"
    target.write_text("do not change\n", encoding="utf-8")
    (queue / f"{request_id}.result").symlink_to(target)
    with RunQueue(queue) as run_queue:
        run_queue.finalize(public, "timeout")

    assert target.read_text(encoding="utf-8") == "do not change\n"
    assert (queue / f"{request_id}.result").read_text(encoding="utf-8") == "124\n"


def test_privileged_queue_commands_require_cios_before_opening_queue(tmp_path, monkeypatch):
    queue = tmp_path / "queue"
    queue.mkdir()
    (queue / "run.request").write_text("request\n", encoding="utf-8")
    identity = type("Identity", (), {"pw_name": "hermes"})()
    monkeypatch.setattr(QUEUE_API["pwd"], "getpwuid", lambda _uid: identity)

    with pytest.raises(PermissionError, match="must run as cios"):
        QUEUE_API["require_cios_user"]()

    assert (queue / "run.request").exists()


def test_claim_records_active_request_before_renaming_request():
    text = QUEUE_HELPER.read_text(encoding="utf-8")
    claim = text[text.index("def claim_next") : text.index("def _append_log")]

    assert claim.index("self._write_active(request_id)") < claim.index("os.rename(")
