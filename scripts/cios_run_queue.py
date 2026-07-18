#!/usr/bin/env python3
"""Symlink-safe request queue for the CI-OS systemd runner boundary."""

from __future__ import annotations

import argparse
import json
import os
import pwd
import re
import stat
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Sequence


SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
CLOEXEC = getattr(os, "O_CLOEXEC", 0)


class QueueSafetyError(OSError):
    """Raised when queue state cannot be accessed without following links."""


def require_cios_user() -> None:
    if pwd.getpwuid(os.geteuid()).pw_name != "cios":
        raise PermissionError("privileged CI-OS queue operation must run as cios")


def _write_all(fd: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(fd, view)
        view = view[written:]


class RunQueue:
    def __init__(self, path: Path):
        self.path = path
        self.fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | NOFOLLOW | CLOEXEC)
        if not stat.S_ISDIR(os.fstat(self.fd).st_mode):
            os.close(self.fd)
            raise QueueSafetyError("CI-OS queue is not a directory")

    def close(self) -> None:
        os.close(self.fd)

    def __enter__(self) -> RunQueue:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    @staticmethod
    def _validate_name(name: str) -> None:
        if not name or "/" in name or name in {".", ".."}:
            raise QueueSafetyError("unsafe CI-OS queue entry name")

    def _read_regular(self, name: str, *, limit: int = 8192) -> bytes | None:
        self._validate_name(name)
        try:
            fd = os.open(name, os.O_RDONLY | NOFOLLOW | CLOEXEC, dir_fd=self.fd)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise QueueSafetyError(f"unsafe CI-OS queue entry: {name}") from exc
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise QueueSafetyError(f"CI-OS queue entry is not regular: {name}")
            payload = os.read(fd, limit + 1)
            if len(payload) > limit:
                raise QueueSafetyError(f"CI-OS queue entry is too large: {name}")
            return payload
        finally:
            os.close(fd)

    def _write_atomic(self, name: str, payload: bytes, *, mode: int = 0o640) -> None:
        self._validate_name(name)
        temporary = f".{name}.{uuid.uuid4().hex}.tmp"
        fd = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | NOFOLLOW | CLOEXEC,
            mode,
            dir_fd=self.fd,
        )
        try:
            _write_all(fd, payload)
            os.fsync(fd)
        finally:
            os.close(fd)
        try:
            os.replace(temporary, name, src_dir_fd=self.fd, dst_dir_fd=self.fd)
            os.fsync(self.fd)
        finally:
            try:
                os.unlink(temporary, dir_fd=self.fd)
            except FileNotFoundError:
                pass

    def _create_regular(self, name: str, *, mode: int = 0o640) -> int:
        self._validate_name(name)
        try:
            fd = os.open(
                name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | NOFOLLOW | CLOEXEC,
                mode,
                dir_fd=self.fd,
            )
        except OSError as exc:
            raise QueueSafetyError(f"refusing unsafe existing CI-OS queue entry: {name}") from exc
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            os.close(fd)
            raise QueueSafetyError(f"CI-OS queue entry is not regular: {name}")
        return fd

    def _state_fd(self) -> int:
        try:
            os.mkdir(".state", mode=0o700, dir_fd=self.fd)
        except FileExistsError:
            pass
        try:
            fd = os.open(
                ".state",
                os.O_RDONLY | os.O_DIRECTORY | NOFOLLOW | CLOEXEC,
                dir_fd=self.fd,
            )
        except OSError as exc:
            raise QueueSafetyError("unsafe CI-OS private queue state") from exc
        state = os.fstat(fd)
        if not stat.S_ISDIR(state.st_mode) or state.st_uid != os.geteuid():
            os.close(fd)
            raise QueueSafetyError("CI-OS private queue state has the wrong owner")
        os.fchmod(fd, 0o700)
        return fd

    def _write_active(self, request_id: str) -> None:
        state_fd = self._state_fd()
        try:
            temporary = f".active-{uuid.uuid4().hex}.tmp"
            fd = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | NOFOLLOW | CLOEXEC,
                0o600,
                dir_fd=state_fd,
            )
            try:
                _write_all(fd, f"{request_id}\n".encode())
                os.fsync(fd)
            finally:
                os.close(fd)
            os.replace(temporary, "active-run", src_dir_fd=state_fd, dst_dir_fd=state_fd)
            os.fsync(state_fd)
        finally:
            os.close(state_fd)

    def _create_state_regular(self, name: str) -> int:
        self._validate_name(name)
        state_fd = self._state_fd()
        try:
            fd = os.open(
                name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | NOFOLLOW | CLOEXEC,
                0o600,
                dir_fd=state_fd,
            )
        except OSError as exc:
            raise QueueSafetyError(f"refusing unsafe CI-OS private state entry: {name}") from exc
        finally:
            os.close(state_fd)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            os.close(fd)
            raise QueueSafetyError(f"CI-OS private state entry is not regular: {name}")
        return fd

    def _read_active(self) -> str | None:
        state_fd = self._state_fd()
        try:
            try:
                fd = os.open("active-run", os.O_RDONLY | NOFOLLOW | CLOEXEC, dir_fd=state_fd)
            except FileNotFoundError:
                return None
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    raise QueueSafetyError("CI-OS active-run state is not regular")
                request_id = os.read(fd, 256).decode("ascii", errors="strict").strip()
            finally:
                os.close(fd)
        finally:
            os.close(state_fd)
        if not SAFE_ID.fullmatch(request_id):
            raise QueueSafetyError("invalid CI-OS active request id")
        return request_id

    def _clear_active(self, request_id: str) -> None:
        active = self._read_active()
        if active != request_id:
            return
        state_fd = self._state_fd()
        try:
            os.unlink("active-run", dir_fd=state_fd)
            os.fsync(state_fd)
        except FileNotFoundError:
            pass
        finally:
            os.close(state_fd)

    def enqueue(self, metadata: dict[str, str]) -> str:
        request_id = uuid.uuid4().hex
        payload = json.dumps(metadata, sort_keys=True).encode() + b"\n"
        self._write_atomic(f"{request_id}.request", payload)
        return request_id

    def result(self, request_id: str) -> int | None:
        if not SAFE_ID.fullmatch(request_id):
            raise QueueSafetyError("invalid CI-OS request id")
        payload = self._read_regular(f"{request_id}.result", limit=16)
        if payload is None:
            return None
        value = payload.decode("ascii", errors="strict").strip()
        if not value.isdigit() or not 0 <= int(value) <= 255:
            raise QueueSafetyError("invalid CI-OS runner result")
        return int(value)

    def claim_next(self) -> str | None:
        for name in sorted(os.listdir(self.fd)):
            if not name.endswith(".request"):
                continue
            request_id = name[: -len(".request")]
            if not SAFE_ID.fullmatch(request_id):
                continue
            try:
                source_fd = os.open(name, os.O_RDONLY | NOFOLLOW | CLOEXEC, dir_fd=self.fd)
            except OSError:
                continue
            try:
                source_stat = os.fstat(source_fd)
                if not stat.S_ISREG(source_stat.st_mode):
                    continue
                running = f"{request_id}.running"
                try:
                    os.stat(running, dir_fd=self.fd, follow_symlinks=False)
                    continue
                except FileNotFoundError:
                    pass
                self._write_active(request_id)
                try:
                    os.rename(name, running, src_dir_fd=self.fd, dst_dir_fd=self.fd)
                except OSError:
                    self._clear_active(request_id)
                    continue
                moved_stat = os.stat(running, dir_fd=self.fd, follow_symlinks=False)
                if (source_stat.st_dev, source_stat.st_ino) != (moved_stat.st_dev, moved_stat.st_ino):
                    os.unlink(running, dir_fd=self.fd)
                    self._clear_active(request_id)
                    continue
                return request_id
            finally:
                os.close(source_fd)
        return None

    def _append_log(self, request_id: str, message: str) -> None:
        name = f"{request_id}.log"
        state_fd = self._state_fd()
        try:
            fd = os.open(name, os.O_WRONLY | os.O_APPEND | NOFOLLOW | CLOEXEC, dir_fd=state_fd)
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                os.close(fd)
                raise QueueSafetyError("CI-OS runner log is not regular")
        except FileNotFoundError:
            os.close(state_fd)
            fd = self._create_state_regular(name)
        except OSError:
            try:
                temporary = f".{name}.{uuid.uuid4().hex}.tmp"
                fd = os.open(
                    temporary,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | NOFOLLOW | CLOEXEC,
                    0o600,
                    dir_fd=state_fd,
                )
                try:
                    _write_all(fd, message.encode())
                    os.fsync(fd)
                finally:
                    os.close(fd)
                os.replace(temporary, name, src_dir_fd=state_fd, dst_dir_fd=state_fd)
            finally:
                os.close(state_fd)
            return
        else:
            os.close(state_fd)
        try:
            _write_all(fd, message.encode())
            os.fsync(fd)
        finally:
            os.close(fd)

    def finish(self, request_id: str, code: int) -> None:
        self._write_atomic(f"{request_id}.result", f"{code}\n".encode())
        running = f"{request_id}.running"
        done = f"{request_id}.done"
        try:
            os.replace(running, done, src_dir_fd=self.fd, dst_dir_fd=self.fd)
        except FileNotFoundError:
            pass
        self._clear_active(request_id)

    def _run_claimed(self, request_id: str, app: Path, public: Path) -> None:
        try:
            log_fd = self._create_state_regular(f"{request_id}.log")
        except QueueSafetyError:
            self.finish(request_id, 2)
            return
        code = 2
        try:
            env = os.environ.copy()
            env.update(
                {
                    "CIOS_APP_DIR": str(app),
                    "CIOS_PUBLIC_DIR": str(public),
                    "CIOS_APP_USER": pwd.getpwuid(os.geteuid()).pw_name,
                }
            )
            env.pop("CIOS_DISABLE_RUNNER_HANDOFF", None)
            env.pop("CIOS_RUNNER_HANDOFF", None)
            log = os.fdopen(log_fd, "wb", buffering=0)
            with log:
                completed = subprocess.run(
                    [str(app / "deploy/cios-daily.sh")],
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
                code = completed.returncode if 0 <= completed.returncode <= 255 else 2
        except Exception as exc:  # noqa: BLE001 - boundary must always publish a result
            self._append_log(request_id, f"CI-OS runner failed: {type(exc).__name__}\n")
        self.finish(request_id, code)

    def run_pending(self, app: Path, public: Path) -> None:
        found = False
        while True:
            request_id = self.claim_next()
            if request_id is None:
                if not found:
                    print("no CI-OS runner requests found")
                return
            found = True
            self._run_claimed(request_id, app, public)

    def finalize(self, public: Path, service_result: str) -> None:
        request_id = self._read_active()
        if request_id is None:
            return
        running = self._read_regular(f"{request_id}.running")
        if running is None:
            self._clear_active(request_id)
            return
        try:
            existing = self.result(request_id)
        except (OSError, UnicodeError, ValueError):
            existing = None
        timed_out = service_result in {"timeout", "watchdog"}
        code = existing if existing is not None else (124 if timed_out else 2)
        if existing is None:
            message = "systemd runtime timeout" if timed_out else "systemd stopped CI-OS before normal completion"
            stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            self._append_log(request_id, f"{stamp}: {message}\n")
        self.finish(request_id, code)
        if code == 124:
            _publish_timeout_status(public, request_id)


def _publish_timeout_status(public: Path, request_id: str) -> None:
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "request_id": request_id,
        "publish_status": "blocked",
        "status": "blocked_runtime_timeout",
        "public_dashboard_updated": False,
    }
    data = (json.dumps(payload, indent=2) + "\n").encode()
    for directory in (public / "data", public / "v2/data"):
        directory.mkdir(parents=True, exist_ok=True)
        dir_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | NOFOLLOW | CLOEXEC)
        try:
            temporary = f".argus-latest-run-status.{uuid.uuid4().hex}.tmp"
            fd = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | NOFOLLOW | CLOEXEC,
                0o640,
                dir_fd=dir_fd,
            )
            try:
                _write_all(fd, data)
                os.fsync(fd)
            finally:
                os.close(fd)
            os.replace(
                temporary,
                "argus-latest-run-status.json",
                src_dir_fd=dir_fd,
                dst_dir_fd=dir_fd,
            )
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    enqueue = subparsers.add_parser("enqueue")
    enqueue.add_argument("--queue", required=True, type=Path)
    enqueue.add_argument("--requested-by", required=True)
    enqueue.add_argument("--app-user", required=True)
    enqueue.add_argument("--app", required=True)
    enqueue.add_argument("--public", required=True)

    result = subparsers.add_parser("read-result")
    result.add_argument("--queue", required=True, type=Path)
    result.add_argument("--request-id", required=True)

    run_pending = subparsers.add_parser("run-pending")
    run_pending.add_argument("--queue", required=True, type=Path)
    run_pending.add_argument("--app", required=True, type=Path)
    run_pending.add_argument("--public", required=True, type=Path)

    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("--queue", required=True, type=Path)
    finalize.add_argument("--public", required=True, type=Path)
    finalize.add_argument("--service-result", default="unknown")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command in {"run-pending", "finalize"}:
            require_cios_user()
        with RunQueue(args.queue) as queue:
            if args.command == "enqueue":
                print(
                    queue.enqueue(
                        {
                            "requested_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "requested_by": args.requested_by,
                            "app_user": args.app_user,
                            "app_dir": args.app,
                            "public_dir": args.public,
                        }
                    )
                )
            elif args.command == "read-result":
                code = queue.result(args.request_id)
                if code is None:
                    return 3
                print(code)
            elif args.command == "run-pending":
                queue.run_pending(args.app, args.public)
            elif args.command == "finalize":
                queue.finalize(args.public, args.service_result)
    except (OSError, UnicodeError, ValueError) as exc:
        detail = exc.strerror if isinstance(exc, OSError) and exc.strerror else type(exc).__name__
        print(f"CI-OS queue operation failed: {detail}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
