"""Enter a delegated command cgroup before executing a CI-OS child target."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Sequence


def enter_and_exec(cgroup: Path, ready_fd: int, command: Sequence[str]) -> None:
    if not command:
        raise ValueError("missing contained command")
    with (cgroup / "cgroup.procs").open("w", encoding="utf-8") as handle:
        handle.write(str(os.getpid()))
    os.write(ready_fd, b"READY\n")
    os.close(ready_fd)
    os.execvp(command[0], list(command))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch a command inside a delegated cgroup.")
    parser.add_argument("--cgroup", required=True, type=Path)
    parser.add_argument("--ready-fd", required=True, type=int)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.command[:1] == ["--"]:
        args.command = args.command[1:]
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        enter_and_exec(args.cgroup, args.ready_fd, args.command)
    except (OSError, ValueError):
        try:
            os.write(args.ready_fd, b"ERROR\n")
            os.close(args.ready_fd)
        except OSError:
            pass
        return 125
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
