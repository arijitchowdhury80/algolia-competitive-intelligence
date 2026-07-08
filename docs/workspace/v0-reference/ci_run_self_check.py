#!/usr/bin/env python3
"""Post-run validation for the Competitive Intelligence cron wrappers."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


WEAK_LANGUAGE = [
    "page changed",
    "hash changed",
    "changed case_study",
    "changed blog",
    "changed source",
    "changed since previous snapshot",
]


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def output_root_from_env() -> Path:
    return Path(os.environ.get("COMPETITIVE_RESEARCH_OUTPUT_ROOT", "artifacts/competitive-research"))


def check_file(path: Optional[Path], label: str) -> Dict[str, Any]:
    if path is None:
        return {"status": "fail", "details": f"{label} path was not provided"}
    if not path.exists():
        return {"status": "fail", "details": f"{label} missing: {path}"}
    if path.stat().st_size <= 0:
        return {"status": "fail", "details": f"{label} is empty: {path}"}
    return {"status": "pass", "details": str(path)}


def check_dashboard_log(path: Optional[Path]) -> Dict[str, Any]:
    if path is None or not path.exists():
        return {"status": "warn", "details": f"dashboard publish log missing: {path}"}
    text = path.read_text(errors="replace")
    bad_tokens = ["Traceback", "fatal:", "error:", "[WARN] Dashboard publish failed"]
    found = [token for token in bad_tokens if token.lower() in text.lower()]
    if found:
        return {"status": "warn", "details": "dashboard log contains: " + ", ".join(found)}
    return {"status": "pass", "details": str(path)}


def semantic_delta_counts(db_path: Path, date: Optional[str]) -> Dict[str, int]:
    if not db_path.exists():
        return {}
    try:
        conn = sqlite3.connect(db_path)
        table = conn.execute(
            "select name from sqlite_master where type='table' and name='semantic_deltas'"
        ).fetchone()
        if table is None:
            return {}
        if date:
            rows = conn.execute(
                """
                select quality_status, count(*) as n
                from semantic_deltas
                where detected_date = ?
                group by quality_status
                """,
                (date,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                select quality_status, count(*) as n
                from semantic_deltas
                group by quality_status
                """
            ).fetchall()
        return {str(status or "unknown"): int(count) for status, count in rows}
    finally:
        try:
            conn.close()
        except Exception:
            pass


def check_ledger(db_path: Path) -> Dict[str, Any]:
    if not db_path.exists():
        return {"status": "fail", "details": f"ledger missing: {db_path}"}
    if db_path.stat().st_size <= 0:
        return {"status": "fail", "details": f"ledger is empty: {db_path}"}
    return {"status": "pass", "details": str(db_path)}


def check_weak_language(markdown_path: Optional[Path]) -> Dict[str, Any]:
    if markdown_path is None or not markdown_path.exists():
        return {"status": "fail", "details": "cannot inspect weak language without markdown"}
    text = markdown_path.read_text(errors="replace").lower()
    found = [phrase for phrase in WEAK_LANGUAGE if phrase in text]
    if found:
        return {"status": "warn", "details": ", ".join(found)}
    return {"status": "pass", "details": "no raw-change language found"}


def overall_status(checks: Dict[str, Dict[str, Any]]) -> str:
    statuses = {check["status"] for check in checks.values()}
    if "fail" in statuses:
        return "fail"
    if "warn" in statuses:
        return "warn"
    return "pass"


def write_audit_files(output_root: Path, result: Dict[str, Any], date: str, cadence: str) -> Dict[str, Path]:
    audit_dir = output_root / "run-audits"
    audit_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{date}-{cadence}"
    json_path = audit_dir / f"{stem}.json"
    markdown_path = audit_dir / f"{stem}.md"
    json_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    lines = [
        f"# CI run self-check - {cadence} - {date}",
        "",
        f"status: {result['status']}",
        "",
        "## planned_vs_actual",
        "",
        f"- planned cadence: {cadence}",
        f"- actual cadence: {result['cadence']}",
        f"- generated at: {result['generated_at']}",
        "",
        "## checks",
        "",
    ]
    for name, check in result["checks"].items():
        lines.append(f"- {name}: {check['status']} - {check['details']}")
    lines.extend(
        [
            "",
            "## semantic_delta_counts",
            "",
            json.dumps(result["semantic_delta_counts"], sort_keys=True),
            "",
        ]
    )
    markdown_path.write_text("\n".join(lines))
    return {"json_path": json_path, "markdown_path": markdown_path}


def run_self_check(
    *,
    cadence: str,
    output_root: Path,
    markdown_path: Optional[Path],
    html_path: Optional[Path],
    dashboard_log_path: Optional[Path],
    run_output: str,
    date: Optional[str] = None,
    generated_at: Optional[str] = None,
) -> Dict[str, Any]:
    generated = generated_at or now_iso()
    run_date = date or generated[:10]
    db_path = output_root / "ci.sqlite"
    checks = {
        "markdown_artifact": check_file(markdown_path, "markdown artifact"),
        "html_artifact": check_file(html_path, "html artifact"),
        "ledger": check_ledger(db_path),
        "dashboard_publish": check_dashboard_log(dashboard_log_path),
        "weak_language_gate": check_weak_language(markdown_path),
    }
    result: Dict[str, Any] = {
        "cadence": cadence,
        "date": run_date,
        "generated_at": generated,
        "status": overall_status(checks),
        "checks": checks,
        "semantic_delta_counts": semantic_delta_counts(db_path, run_date),
        "artifacts": {
            "markdown": str(markdown_path) if markdown_path else "",
            "html": str(html_path) if html_path else "",
            "dashboard_log": str(dashboard_log_path) if dashboard_log_path else "",
            "ledger": str(db_path),
        },
        "run_output_tail": "\n".join(run_output.splitlines()[-40:]),
    }
    paths = write_audit_files(output_root, result, run_date, cadence)
    result["json_path"] = str(paths["json_path"])
    result["markdown_path"] = str(paths["markdown_path"])
    paths["json_path"].write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def optional_path(value: str) -> Optional[Path]:
    return Path(value) if value else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a completed CI cron run.")
    parser.add_argument("--cadence", choices=["daily", "weekly"], required=True)
    parser.add_argument("--output-root", type=Path, default=output_root_from_env())
    parser.add_argument("--markdown-path", default="")
    parser.add_argument("--html-path", default="")
    parser.add_argument("--dashboard-log", default="")
    parser.add_argument("--run-output-file", default="")
    parser.add_argument("--date", default="")
    args = parser.parse_args()
    run_output = ""
    if args.run_output_file and Path(args.run_output_file).exists():
        run_output = Path(args.run_output_file).read_text(errors="replace")
    result = run_self_check(
        cadence=args.cadence,
        output_root=args.output_root,
        markdown_path=optional_path(args.markdown_path),
        html_path=optional_path(args.html_path),
        dashboard_log_path=optional_path(args.dashboard_log),
        run_output=run_output,
        date=args.date or None,
    )
    print("CI self-check %s: %s" % (args.cadence, result["status"]))
    print("Audit JSON: %s" % result["json_path"])
    print("Audit Markdown: %s" % result["markdown_path"])
    return 1 if result["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
