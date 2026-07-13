#!/usr/bin/env python3
"""Generate and verify a CI-OS Phase 0 source release record."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


KIND = "cios.phase0.release_record"


def run_git(source_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(source_root), *args],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(message or f"git {' '.join(args)} failed")
    return completed.stdout.strip()


def git_bytes(source_root: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(source_root), *args],
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout).decode(
            "utf-8",
            errors="replace",
        )
        raise RuntimeError(message.strip() or f"git {' '.join(args)} failed")
    return completed.stdout


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tracked_files(source_root: Path) -> list[str]:
    output = run_git(source_root, "ls-files")
    return sorted(line for line in output.splitlines() if line)


def tracked_manifest_sha256(files: list[dict[str, Any]]) -> str:
    lines = "\n".join(f"{item['sha256']}  {item['path']}" for item in files)
    return hashlib.sha256(lines.encode("utf-8")).hexdigest()


def archive_sha256(source_root: Path) -> str:
    archive = git_bytes(source_root, "archive", "--format=tar", "HEAD")
    return hashlib.sha256(archive).hexdigest()


def current_branch(source_root: Path) -> str:
    return run_git(source_root, "rev-parse", "--abbrev-ref", "HEAD")


def current_commit(source_root: Path) -> str:
    return run_git(source_root, "rev-parse", "HEAD")


def origin_url(source_root: Path) -> str:
    try:
        return run_git(source_root, "config", "--get", "remote.origin.url")
    except RuntimeError:
        return ""


def build_manifest(source_root: Path, app_dir: Path, tag: str) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    for relative_path in tracked_files(source_root):
        path = app_dir / relative_path
        if not path.is_file():
            raise RuntimeError(f"tracked file missing from app dir: {relative_path}")
        files.append(
            {
                "path": relative_path,
                "sha256": sha256_file(path),
                "size": path.stat().st_size,
            }
        )

    return {
        "schema_version": 1,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "source": {
            "repo_url": origin_url(source_root),
            "branch": current_branch(source_root),
            "commit": current_commit(source_root),
            "tag": tag,
            "archive_sha256": archive_sha256(source_root),
            "tracked_file_count": len(files),
            "tracked_file_manifest_sha256": tracked_manifest_sha256(files),
        },
        "package": {
            "app_dir": str(app_dir),
        },
        "files": files,
    }


def load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("kind") != KIND:
        raise RuntimeError(f"manifest kind must be {KIND}")
    if payload.get("schema_version") != 1:
        raise RuntimeError("manifest schema_version must be 1")
    return payload


def verify_manifest(manifest: dict[str, Any], app_dir: Path) -> list[str]:
    errors: list[str] = []
    for item in manifest.get("files", []):
        relative_path = item.get("path")
        expected_sha256 = item.get("sha256")
        if not isinstance(relative_path, str) or not isinstance(expected_sha256, str):
            errors.append("invalid manifest file entry")
            continue
        path = app_dir / relative_path
        if not path.exists():
            errors.append(f"missing file: {relative_path}")
            continue
        if not path.is_file():
            errors.append(f"not a regular file: {relative_path}")
            continue
        actual_sha256 = sha256_file(path)
        if actual_sha256 != expected_sha256:
            errors.append(f"checksum mismatch: {relative_path}")
    return errors


def generate(args: argparse.Namespace) -> int:
    source_root = args.source_root.resolve()
    app_dir = args.app_dir.resolve()
    output = args.output.resolve()
    manifest = build_manifest(source_root, app_dir, args.tag or "")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"WROTE: {output}")
    return 0


def verify(args: argparse.Namespace) -> int:
    app_dir = args.app_dir.resolve()
    manifest = load_manifest(args.manifest.resolve())
    errors = verify_manifest(manifest, app_dir)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 2
    print("PASS: app directory matches CI-OS Phase 0 release record")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate_parser = subparsers.add_parser("generate")
    generate_parser.add_argument("--source-root", type=Path, required=True)
    generate_parser.add_argument("--app-dir", type=Path, required=True)
    generate_parser.add_argument("--tag", default="")
    generate_parser.add_argument("--output", type=Path, required=True)
    generate_parser.set_defaults(func=generate)

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--app-dir", type=Path, required=True)
    verify_parser.add_argument("--manifest", type=Path, required=True)
    verify_parser.set_defaults(func=verify)

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        return args.func(args)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
