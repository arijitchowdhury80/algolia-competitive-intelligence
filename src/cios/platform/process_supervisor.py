"""Bounded process-group supervision for CI-OS child commands."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from collections import defaultdict


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
        descendants = self._snapshot_descendants(process.pid)
        self._signal_descendants(descendants, signal.SIGTERM)
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        deadline = time.monotonic() + grace_seconds
        while time.monotonic() < deadline and self._tree_exists(process, descendants):
            time.sleep(0.05)
        if self._tree_exists(process, descendants):
            self._signal_descendants(descendants, signal.SIGKILL)
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

    @classmethod
    def _tree_exists(
        cls,
        process: subprocess.Popen[str],
        descendants: list[tuple[int, int]],
    ) -> bool:
        return cls._group_exists(process) or any(cls._pid_exists(pid) for pid, _ in descendants)

    @staticmethod
    def _pid_exists(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    @staticmethod
    def _snapshot_descendants(root_pid: int) -> list[tuple[int, int]]:
        try:
            completed = subprocess.run(
                ["ps", "-e", "-o", "pid=,ppid=,pgid="],
                text=True,
                capture_output=True,
                timeout=1,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return []
        children: dict[int, list[tuple[int, int]]] = defaultdict(list)
        for line in completed.stdout.splitlines():
            fields = line.split()
            if len(fields) != 3:
                continue
            pid, parent_pid, group_id = (int(field) for field in fields)
            children[parent_pid].append((pid, group_id))
        descendants: list[tuple[int, int]] = []
        pending = [root_pid]
        while pending:
            parent_pid = pending.pop()
            for child in children.get(parent_pid, []):
                descendants.append(child)
                pending.append(child[0])
        return list(reversed(descendants))

    @classmethod
    def _signal_descendants(cls, descendants: list[tuple[int, int]], signum: int) -> None:
        current_group = os.getpgrp()
        signaled_groups: set[int] = set()
        for pid, group_id in descendants:
            if group_id == pid and group_id != current_group and group_id not in signaled_groups:
                try:
                    os.killpg(group_id, signum)
                except (ProcessLookupError, PermissionError):
                    pass
                signaled_groups.add(group_id)
            try:
                os.kill(pid, signum)
            except (ProcessLookupError, PermissionError):
                pass

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
