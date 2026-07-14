"""Bounded process-group supervision for CI-OS child commands."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time


class ProcessGroupRegistry:
    def __init__(self) -> None:
        self._active: set[subprocess.Popen[str]] = set()
        self._lock = threading.Lock()

    def register(self, process: subprocess.Popen[str]) -> None:
        with self._lock:
            self._active.add(process)

    def unregister(self, process: subprocess.Popen[str]) -> None:
        with self._lock:
            self._active.discard(process)

    def terminate(self, process: subprocess.Popen[str], *, grace_seconds: float = 0.5) -> None:
        group_id = process.pid
        try:
            os.killpg(group_id, signal.SIGTERM)
        except ProcessLookupError:
            return
        deadline = time.monotonic() + grace_seconds
        while time.monotonic() < deadline and self._group_exists(process):
            time.sleep(0.05)
        if self._group_exists(process):
            self._force_kill(process)
        self._reap(process, grace_seconds=grace_seconds)

    def terminate_all(self) -> None:
        with self._lock:
            processes = list(self._active)
        for process in processes:
            self.terminate(process)

    @staticmethod
    def _group_exists(process: subprocess.Popen[str]) -> bool:
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return process.poll() is None
        return True

    @staticmethod
    def _force_kill(process: subprocess.Popen[str]) -> None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        except PermissionError:
            if process.poll() is None:
                process.kill()

    @staticmethod
    def _reap(process: subprocess.Popen[str], *, grace_seconds: float) -> None:
        if process.poll() is not None:
            return
        try:
            process.wait(timeout=grace_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=grace_seconds)


PROCESS_GROUPS = ProcessGroupRegistry()


def _shutdown_handler(signum, _frame) -> None:
    PROCESS_GROUPS.terminate_all()
    raise SystemExit(128 + int(signum))


def install_shutdown_handlers() -> None:
    signal.signal(signal.SIGTERM, _shutdown_handler)
    signal.signal(signal.SIGINT, _shutdown_handler)
