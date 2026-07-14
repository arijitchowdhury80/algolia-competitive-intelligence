"""Tests for kernel-enforced CI-OS child-process containment."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from cios.platform import cgroup_launcher
from cios.platform.process_supervisor import (
    CgroupV2Backend,
    ContainmentUnavailableError,
    ProcessGroupRegistry,
)


class _FakeProcess:
    pid = 4321
    returncode = 0

    def poll(self):
        return self.returncode


class _FakeBackend:
    def __init__(self, group: Path):
        self.group = group
        self.calls: list[tuple[str, object]] = []
        self.process = _FakeProcess()

    def launch(self, command, **kwargs):
        self.calls.append(("launch", (list(command), kwargs)))
        return self.process, self.group

    def terminate(self, process, group, *, grace_seconds):
        self.calls.append(("terminate", (process, group, grace_seconds)))

    def release(self, group):
        self.calls.append(("release", group))


def test_registry_requires_cgroup_when_deployment_contract_demands_it(monkeypatch):
    monkeypatch.setenv("CIOS_REQUIRE_CGROUP_CONTAINMENT", "1")
    monkeypatch.setattr(CgroupV2Backend, "discover", classmethod(lambda cls: None))

    registry = ProcessGroupRegistry.from_environment()

    with pytest.raises(ContainmentUnavailableError, match="delegated cgroup v2"):
        registry.spawn(["true"])


def test_cgroup_backend_discovers_explicit_delegated_root(tmp_path, monkeypatch):
    (tmp_path / "cgroup.procs").write_text("", encoding="utf-8")
    monkeypatch.setenv("CIOS_CGROUP_ROOT", str(tmp_path))

    backend = CgroupV2Backend.discover()

    assert backend is not None
    assert backend.root == tmp_path


def test_registry_launches_and_terminates_through_cgroup_backend(tmp_path):
    backend = _FakeBackend(tmp_path / "command-1")
    registry = ProcessGroupRegistry(backend=backend, require_cgroup=True)

    process = registry.spawn(["echo", "ok"], text=True)
    registry.terminate(process, grace_seconds=0.25)
    registry.unregister(process)

    assert process is backend.process
    assert backend.calls == [
        ("launch", (["echo", "ok"], {"text": True})),
        ("terminate", (process, backend.group, 0.25)),
        ("release", backend.group),
    ]


def test_registry_cleanup_is_idempotent_when_terminate_and_unregister_race(tmp_path):
    backend = _FakeBackend(tmp_path / "command-1")
    registry = ProcessGroupRegistry(backend=backend, require_cgroup=True)
    process = registry.spawn(["echo", "ok"])

    registry.terminate(process)
    registry.unregister(process)
    registry.terminate(process)

    assert [call[0] for call in backend.calls] == ["launch", "terminate", "release"]


def test_launcher_enters_cgroup_before_target_exec(tmp_path, monkeypatch):
    group = tmp_path / "command-1"
    group.mkdir()
    procs = group / "cgroup.procs"
    procs.write_text("", encoding="utf-8")
    read_fd, write_fd = os.pipe()
    observed: list[tuple[str, object]] = []

    def fake_execvp(executable, command):
        observed.append(("exec", (executable, list(command), procs.read_text(encoding="utf-8"))))
        raise RuntimeError("exec intercepted")

    monkeypatch.setattr(cgroup_launcher.os, "execvp", fake_execvp)

    with pytest.raises(RuntimeError, match="exec intercepted"):
        cgroup_launcher.enter_and_exec(group, write_fd, ["echo", "contained"])

    assert os.read(read_fd, 32) == b"READY\n"
    os.close(read_fd)
    assert observed == [("exec", ("echo", ["echo", "contained"], str(os.getpid())))]


def test_launcher_reports_exec_failure_without_echoing_command(tmp_path, monkeypatch, capsys):
    group = tmp_path / "command-1"
    group.mkdir()
    (group / "cgroup.procs").write_text("", encoding="utf-8")
    read_fd, write_fd = os.pipe()

    def fail_exec(_executable, _command):
        raise FileNotFoundError(2, "No such file or directory", "secret-command")

    monkeypatch.setattr(cgroup_launcher.os, "execvp", fail_exec)

    code = cgroup_launcher.main(
        ["--cgroup", str(group), "--ready-fd", str(write_fd), "--", "secret-command"]
    )

    os.close(read_fd)
    captured = capsys.readouterr()
    assert code == 125
    assert "contained exec failed: No such file or directory" in captured.err
    assert "secret-command" not in captured.err


def test_cgroup_kill_is_used_when_group_remains_populated(tmp_path, monkeypatch):
    group = tmp_path / "command-1"
    group.mkdir()
    (group / "cgroup.kill").write_text("", encoding="utf-8")
    backend = CgroupV2Backend(tmp_path)
    waits = iter([False, True])
    monkeypatch.setattr(backend, "_wait_empty", lambda _group, _timeout: next(waits))

    backend.terminate(_FakeProcess(), group, grace_seconds=0.1)

    assert (group / "cgroup.kill").read_text(encoding="utf-8") == "1"
