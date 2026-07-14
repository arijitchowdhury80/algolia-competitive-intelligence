"""Bounded subprocess supervision with delegated cgroup v2 containment."""

from __future__ import annotations

import os
import select
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Sequence


class ContainmentUnavailableError(OSError):
    """Raised when a deployment requires cgroups but none are delegated."""


class CgroupV2Backend:
    def __init__(self, root: Path):
        self.root = root

    @classmethod
    def discover(cls) -> CgroupV2Backend | None:
        override = os.environ.get("CIOS_CGROUP_ROOT", "").strip()
        if override:
            root = Path(override)
        elif sys.platform.startswith("linux"):
            root = cls._root_from_proc()
        else:
            return None
        if not root or not root.is_dir() or not (root / "cgroup.procs").exists():
            return None
        if not os.access(root, os.W_OK | os.X_OK):
            return None
        return cls(root)

    @staticmethod
    def _root_from_proc() -> Path | None:
        try:
            lines = Path("/proc/self/cgroup").read_text(encoding="utf-8").splitlines()
        except OSError:
            return None
        unified = next((line.split("::", 1)[1] for line in lines if "::" in line), None)
        if unified is None:
            return None
        current = Path("/sys/fs/cgroup") / unified.lstrip("/")
        subgroup = os.environ.get("CIOS_CGROUP_SUPERVISOR_SUBGROUP", "supervisor")
        return current.parent if current.name == subgroup else current

    def launch(
        self,
        command: Sequence[str],
        **popen_kwargs: Any,
    ) -> tuple[subprocess.Popen[str], Path]:
        group = self._create_group()
        read_fd, write_fd = os.pipe()
        wrapped = [
            sys.executable,
            "-m",
            "cios.platform.cgroup_launcher",
            "--cgroup",
            str(group),
            "--ready-fd",
            str(write_fd),
            "--",
            *(str(part) for part in command),
        ]
        try:
            if "pass_fds" in popen_kwargs:
                raise TypeError("pass_fds is reserved by CI-OS containment")
            popen_kwargs.setdefault("start_new_session", True)
            process = subprocess.Popen(wrapped, pass_fds=(write_fd,), **popen_kwargs)
        except Exception:
            os.close(read_fd)
            os.close(write_fd)
            self._remove_empty(group)
            raise
        os.close(write_fd)
        try:
            if not self._await_ready(read_fd, timeout_seconds=2.0):
                if process.poll() is None:
                    process.kill()
                try:
                    process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    pass
                if not self._wait_empty(group, 0):
                    self._kill_group(group)
                    self._wait_empty(group, 1.0)
                self._remove_empty(group)
                raise ContainmentUnavailableError("CI-OS cgroup launcher failed before target exec")
        finally:
            os.close(read_fd)
        return process, group

    def terminate(
        self,
        process: subprocess.Popen[str],
        group: Path,
        *,
        grace_seconds: float,
    ) -> None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
        if self._wait_empty(group, grace_seconds):
            return
        self._kill_group(group)
        if not self._wait_empty(group, grace_seconds):
            raise ContainmentUnavailableError("CI-OS command cgroup remained populated after cgroup.kill")

    def release(self, group: Path) -> None:
        if not group.exists():
            return
        if not self._wait_empty(group, 0):
            self._kill_group(group)
            if not self._wait_empty(group, 1.0):
                raise ContainmentUnavailableError("CI-OS command left a populated cgroup")
        self._remove_empty(group, strict=True)

    def _create_group(self) -> Path:
        group = self.root / f"command-{os.getpid()}-{uuid.uuid4().hex}"
        try:
            group.mkdir(mode=0o700)
        except OSError as exc:
            raise ContainmentUnavailableError("unable to create delegated CI-OS command cgroup") from exc
        required = ("cgroup.procs", "cgroup.events", "cgroup.kill")
        if not all((group / name).exists() for name in required):
            self._remove_empty(group)
            raise ContainmentUnavailableError("delegated cgroup v2 files are unavailable")
        return group

    @staticmethod
    def _await_ready(read_fd: int, *, timeout_seconds: float) -> bool:
        readable, _, _ = select.select([read_fd], [], [], timeout_seconds)
        return bool(readable and os.read(read_fd, 32) == b"READY\n")

    @staticmethod
    def _is_populated(group: Path) -> bool:
        try:
            values = dict(
                line.split(maxsplit=1)
                for line in (group / "cgroup.events").read_text(encoding="utf-8").splitlines()
            )
        except (OSError, ValueError):
            return True
        return values.get("populated") != "0"

    def _wait_empty(self, group: Path, timeout_seconds: float) -> bool:
        deadline = time.monotonic() + timeout_seconds
        while self._is_populated(group):
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.02)
        return True

    @staticmethod
    def _kill_group(group: Path) -> None:
        try:
            (group / "cgroup.kill").write_text("1", encoding="utf-8")
        except OSError as exc:
            raise ContainmentUnavailableError("unable to kill delegated CI-OS command cgroup") from exc

    @staticmethod
    def _remove_empty(group: Path, *, strict: bool = False) -> None:
        try:
            group.rmdir()
        except OSError as exc:
            if strict:
                raise ContainmentUnavailableError("unable to remove empty CI-OS command cgroup") from exc


class ProcessGroupRegistry:
    def __init__(
        self,
        *,
        backend: CgroupV2Backend | None = None,
        require_cgroup: bool = False,
    ) -> None:
        self._backend = backend
        self._require_cgroup = require_cgroup
        self._active: dict[subprocess.Popen[str], Path | None] = {}
        self._lock = threading.Lock()

    @classmethod
    def from_environment(cls) -> ProcessGroupRegistry:
        required = os.environ.get("CIOS_REQUIRE_CGROUP_CONTAINMENT", "0") == "1"
        return cls(backend=CgroupV2Backend.discover(), require_cgroup=required)

    @property
    def cgroup_enabled(self) -> bool:
        return self._backend is not None

    def spawn(self, command: Sequence[str], **popen_kwargs: Any) -> subprocess.Popen[str]:
        if self._backend is not None:
            process, group = self._backend.launch(command, **popen_kwargs)
        else:
            if self._require_cgroup:
                raise ContainmentUnavailableError("delegated cgroup v2 containment is required")
            process = subprocess.Popen(list(command), **popen_kwargs)
            group = None
        self.register(process, group=group)
        return process

    def register(self, process: subprocess.Popen[str], *, group: Path | None = None) -> None:
        with self._lock:
            self._active[process] = group

    def unregister(self, process: subprocess.Popen[str]) -> None:
        with self._lock:
            group = self._active.pop(process, None)
        if group is not None and self._backend is not None:
            self._backend.release(group)

    def terminate(self, process: subprocess.Popen[str], *, grace_seconds: float = 0.5) -> None:
        with self._lock:
            group = self._active.get(process)
        if group is not None and self._backend is not None:
            self._backend.terminate(process, group, grace_seconds=grace_seconds)
        else:
            self._terminate_process_group(process, grace_seconds=grace_seconds)
        self._reap(process, grace_seconds=grace_seconds)

    def terminate_all(self) -> None:
        with self._lock:
            processes = list(self._active)
        for process in processes:
            self.terminate(process)

    @staticmethod
    def _terminate_process_group(
        process: subprocess.Popen[str],
        *,
        grace_seconds: float,
    ) -> None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        deadline = time.monotonic() + grace_seconds
        while time.monotonic() < deadline and ProcessGroupRegistry._group_exists(process.pid):
            time.sleep(0.05)
        if ProcessGroupRegistry._group_exists(process.pid):
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except PermissionError:
                if process.poll() is None:
                    process.kill()

    @staticmethod
    def _group_exists(group_id: int) -> bool:
        try:
            os.killpg(group_id, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    @staticmethod
    def _reap(process: subprocess.Popen[str], *, grace_seconds: float) -> None:
        if process.poll() is not None:
            return
        try:
            process.wait(timeout=grace_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=grace_seconds)


PROCESS_GROUPS = ProcessGroupRegistry.from_environment()


def _shutdown_handler(signum, _frame) -> None:
    PROCESS_GROUPS.terminate_all()
    raise SystemExit(128 + int(signum))


def install_shutdown_handlers() -> None:
    signal.signal(signal.SIGTERM, _shutdown_handler)
    signal.signal(signal.SIGINT, _shutdown_handler)
