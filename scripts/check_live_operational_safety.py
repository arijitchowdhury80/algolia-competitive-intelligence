#!/usr/bin/env python3
"""Check live CI-OS deployment safety before launch claims.

This checker is meant to run on the production host, but it has no side
effects. It inspects the installed package, public publication roots, artifact
ownership, and currently running CI-OS processes, then emits one JSON verdict.
"""

from __future__ import annotations

import argparse
import json
import pwd
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ORPHAN_PROCESS_TOKENS = (
    "deploy/cios-daily.sh",
    "scripts/daily_production_run.py",
    "scripts/run_product_market_intelligence.py",
    "scripts/execute_product_surface_plan.py",
    "scripts/scout_http_shim",
    "scout_http_shim.py",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _owner_name(path: Path) -> str:
    try:
        return pwd.getpwuid(path.stat().st_uid).pw_name
    except KeyError:
        return str(path.stat().st_uid)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _finding(requirement: str, actual: str, next_step: str) -> dict[str, str]:
    return {
        "requirement": requirement,
        "actual": actual,
        "next_step": next_step,
    }


def _resolve_current_release(public_store_dir: Path) -> Path | None:
    current = public_store_dir / "current"
    if not current.is_symlink():
        return None
    target = Path(current.readlink())
    if not target.is_absolute():
        target = public_store_dir / target
    return target.resolve(strict=False)


def _hidden_staging_dirs(*roots: Path) -> list[Path]:
    hidden: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        hidden.extend(path for path in root.glob(".argus-publish.*") if path.is_dir())
    return sorted(hidden)


def _root_owned_artifacts(*roots: Path) -> list[Path]:
    root_owned: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        paths = [root]
        if root.is_dir():
            paths.extend(path for path in root.rglob("*") if path.exists())
        for path in paths:
            if _owner_name(path) == "root":
                root_owned.append(path)
    return sorted(root_owned)


def collect_ps_text() -> str:
    completed = subprocess.run(
        ["ps", "-eo", "user,ppid,pid,stat,cmd"],
        text=True,
        capture_output=True,
        check=False,
    )
    return completed.stdout if completed.returncode == 0 else ""


def parse_orphan_processes(ps_text: str) -> list[str]:
    orphans: list[str] = []
    for line in ps_text.splitlines():
        stripped = line.strip()
        if not stripped or "check_live_operational_safety.py" in stripped:
            continue
        if any(token in stripped for token in ORPHAN_PROCESS_TOKENS):
            orphans.append(stripped)
    return orphans


def evaluate_operational_safety(
    *,
    app_dir: Path,
    public_dir: Path,
    public_store_dir: Path,
    expected_package_commit: str | None = None,
    ps_text: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    package_commit_path = app_dir / ".cios-package-commit"
    package_commit = _read_text(package_commit_path)
    current_release = _resolve_current_release(public_store_dir)
    served_dir = public_store_dir / "served"

    current_release_exists = bool(current_release and current_release.is_dir())
    served_release_ready = (
        served_dir.is_dir()
        and (served_dir / "index.html").is_file()
        and (served_dir / "publication-manifest.json").is_file()
    )
    hidden_dirs = _hidden_staging_dirs(
        public_dir,
        served_dir,
        current_release if current_release else public_store_dir / "current",
    )
    root_owned = _root_owned_artifacts(
        app_dir / "out",
        public_dir,
        served_dir,
        current_release if current_release else public_store_dir / "current",
    )
    orphan_processes = parse_orphan_processes(collect_ps_text() if ps_text is None else ps_text)

    findings: list[dict[str, str]] = []
    if not package_commit:
        findings.append(
            _finding(
                "package_commit_recorded",
                f"missing {package_commit_path}",
                "Stamp the deployed package with .cios-package-commit before launch validation.",
            )
        )
    if expected_package_commit and package_commit != expected_package_commit:
        findings.append(
            _finding(
                "package_commit_matches_expected",
                f"package_commit={package_commit or 'missing'} expected={expected_package_commit}",
                "Sync and stamp the expected CI-OS package commit before launch validation.",
            )
        )
    if not current_release_exists:
        findings.append(
            _finding(
                "public_store_current_release_exists",
                "public-store/current is missing or does not resolve to a release directory",
                "Promote a public-store release before launch validation.",
            )
        )
    if not served_release_ready:
        findings.append(
            _finding(
                "public_store_served_release_ready",
                "served release is missing index.html or publication-manifest.json",
                "Repair the public-store served release before launch validation.",
            )
        )
    if hidden_dirs:
        findings.append(
            _finding(
                "no_hidden_staging_dirs",
                f"hidden_staging_dir_count={len(hidden_dirs)}",
                "Remove leaked .argus-publish.* staging directories and fix promotion cleanup.",
            )
        )
    if root_owned:
        findings.append(
            _finding(
                "no_root_owned_artifacts",
                f"root_owned_artifact_count={len(root_owned)}",
                "Repair CI-OS artifact ownership so the application user owns runtime outputs.",
            )
        )
    if orphan_processes:
        findings.append(
            _finding(
                "no_orphan_cios_processes",
                f"orphan_process_count={len(orphan_processes)}",
                "Stop stale CI-OS run processes and investigate timeout cleanup.",
            )
        )

    operational_safe = not findings
    return {
        "gate": "cios_live_operational_safety",
        "generated_at": generated_at or _now(),
        "status": "passed" if operational_safe else "failed",
        "exit_code": 0 if operational_safe else 2,
        "operational_safe": operational_safe,
        "package_commit": package_commit or None,
        "expected_package_commit": expected_package_commit,
        "public_store_current": str(current_release) if current_release else None,
        "current_release_exists": current_release_exists,
        "served_release_ready": served_release_ready,
        "hidden_staging_dir_count": len(hidden_dirs),
        "hidden_staging_dirs": [str(path) for path in hidden_dirs],
        "root_owned_artifact_count": len(root_owned),
        "root_owned_artifacts": [str(path) for path in root_owned[:50]],
        "orphan_process_count": len(orphan_processes),
        "orphan_processes": orphan_processes,
        "findings": findings,
    }


def write_payload(payload: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(f"{json.dumps(payload, indent=2, sort_keys=True)}\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check live CI-OS operational safety.")
    parser.add_argument("--app-dir", type=Path, default=Path("/opt/cios/app"))
    parser.add_argument("--public-dir", type=Path, default=Path("/opt/cios/public"))
    parser.add_argument("--public-store-dir", type=Path, default=Path("/opt/cios/public-store"))
    parser.add_argument("--expected-package-commit")
    parser.add_argument("--ps-text")
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = evaluate_operational_safety(
        app_dir=args.app_dir,
        public_dir=args.public_dir,
        public_store_dir=args.public_store_dir,
        expected_package_commit=args.expected_package_commit,
        ps_text=args.ps_text,
    )
    if args.output:
        write_payload(payload, args.output)
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return int(payload["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
