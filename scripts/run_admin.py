#!/usr/bin/env python3
"""Run the CI-OS local admin app on loopback only."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import uvicorn


def _unquote(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        raise SystemExit(f"missing CIOS env file: {path}")
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or not key.replace("_", "").isalnum() or key[0].isdigit():
            continue
        os.environ[key] = _unquote(value)


def _default_env_file() -> Path | None:
    configured = os.environ.get("CIOS_ENV_FILE")
    if configured:
        path = Path(configured).expanduser()
        if not path.is_file():
            raise SystemExit(f"missing CIOS env file: {path}")
        return path
    for candidate in (Path("/opt/data/cios-env"), Path("/root/.hermes/cios-env")):
        if candidate.is_file():
            return candidate
    return None


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--env-file", type=Path, help="CI-OS env file to load before starting admin.")
    parser.add_argument("--no-env-file", action="store_true", help="Skip automatic CI-OS env file loading.")
    args = parser.parse_args(argv)
    if args.host not in {"127.0.0.1", "::1", "localhost"}:
        raise SystemExit("Refusing non-loopback admin bind. Use an SSH tunnel instead.")
    if args.env_file and args.no_env_file:
        raise SystemExit("--env-file and --no-env-file cannot be used together")
    if args.env_file:
        _load_env_file(args.env_file.expanduser())
    elif not args.no_env_file:
        env_file = _default_env_file()
        if env_file is not None:
            _load_env_file(env_file)
    uvicorn.run("cios.admin.app:create_app", factory=True, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
