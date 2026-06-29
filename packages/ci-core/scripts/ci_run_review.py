#!/usr/bin/env python3
"""Argus post-run review and learning log for CI cron runs."""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def output_root_from_env() -> Path:
    return Path(os.environ.get("COMPETITIVE_RESEARCH_OUTPUT_ROOT", "artifacts/competitive-research"))


def load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def quality_issues(run_output: str) -> List[str]:
    issues: List[str] = []
    for line in run_output.splitlines():
        match = re.search(r"\[WARN\]\s+Output quality issues:\s*(.+)", line)
        if match:
            issues.extend([item.strip() for item in match.group(1).split(",") if item.strip()])
    return issues


def quality_score(run_output: str) -> Optional[float]:
    for line in run_output.splitlines():
        match = re.search(r"Quality score:\s*([0-9.]+)", line)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return None
    return None


def discrepancy_from_check(name: str, check: Dict[str, Any]) -> Optional[Dict[str, str]]:
    status = str(check.get("status", "unknown"))
    if status == "pass":
        return None
    return {
        "source": name,
        "severity": "high" if status == "fail" else "medium",
        "summary": "%s check returned %s" % (name, status),
        "evidence": str(check.get("details", "")),
    }


def action_for_discrepancy(discrepancy: Dict[str, str]) -> Dict[str, str]:
    source = discrepancy["source"]
    if source == "dashboard_publish":
        return {
            "owner": "CI Ops",
            "action": "Repair dashboard publishing and rerun the post-run self-check before trusting dashboard freshness.",
            "reason": discrepancy["evidence"],
        }
    if source == "weak_language_gate":
        return {
            "owner": "Product Marketing",
            "action": "Patch synthesis language so raw page-change phrasing is suppressed before delivery.",
            "reason": discrepancy["evidence"],
        }
    if source == "output_quality":
        return {
            "owner": "Competitive Intelligence",
            "action": "Investigate missing evidence links or weak report structure before treating the report as executive-grade.",
            "reason": discrepancy["evidence"],
        }
    if source == "audit_json":
        return {
            "owner": "CI Ops",
            "action": "Restore post-run self-check audit generation; Argus cannot learn from a missing audit artifact.",
            "reason": discrepancy["evidence"],
        }
    return {
        "owner": "CI Ops",
        "action": "Investigate and repair the failed CI post-run check: %s." % source,
        "reason": discrepancy["evidence"],
    }


def status_from(audit_status: str, discrepancies: List[Dict[str, str]]) -> str:
    if audit_status == "missing" or any(item["severity"] == "high" for item in discrepancies):
        return "failed"
    if audit_status != "pass" or discrepancies:
        return "needs_attention"
    return "healthy"


def write_review_files(output_root: Path, result: Dict[str, Any], date: str, cadence: str) -> Dict[str, Path]:
    review_dir = output_root / "run-reviews"
    review_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{date}-{cadence}"
    json_path = review_dir / f"{stem}.json"
    markdown_path = review_dir / f"{stem}.md"
    learning_log = review_dir / "argus-learning-log.md"

    json_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")

    lines = [
        f"# Argus run review - {cadence} - {date}",
        "",
        f"status: {result['status']}",
        f"generated_at: {result['generated_at']}",
        "",
        "## planned_vs_actual",
        "",
        f"- planned cadence: {cadence}",
        f"- actual cadence: {result['actual_cadence']}",
        f"- audit status: {result['audit_status']}",
        f"- quality score: {result['quality_score'] if result['quality_score'] is not None else 'unknown'}",
        "",
        "## discrepancies",
        "",
    ]
    if result["discrepancies"]:
        for item in result["discrepancies"]:
            lines.append("- {severity} | {source}: {summary}. Evidence: {evidence}".format(**item))
    else:
        lines.append("- none")
    lines.extend(["", "## improvement_actions", ""])
    if result["improvement_actions"]:
        for item in result["improvement_actions"]:
            lines.append("- **{owner}:** {action} Reason: {reason}".format(**item))
    else:
        lines.append("- none required")
    lines.append("")
    markdown_path.write_text("\n".join(lines))

    entry = [
        f"## {date} {cadence}",
        "",
        f"- status: {result['status']}",
        f"- audit_status: {result['audit_status']}",
        f"- discrepancies: {len(result['discrepancies'])}",
        f"- improvement_actions: {len(result['improvement_actions'])}",
        "",
    ]
    with learning_log.open("a") as handle:
        handle.write("\n".join(entry))

    return {"json_path": json_path, "markdown_path": markdown_path, "learning_log": learning_log}


def run_review(
    *,
    cadence: str,
    output_root: Path,
    audit_json_path: Path,
    run_output: str,
    date: Optional[str] = None,
    generated_at: Optional[str] = None,
) -> Dict[str, Any]:
    generated = generated_at or now_iso()
    run_date = date or generated[:10]
    audit = load_json(audit_json_path)
    discrepancies: List[Dict[str, str]] = []
    if audit is None:
        audit_status = "missing"
        actual_cadence = "unknown"
        semantic_delta_counts: Dict[str, int] = {}
        discrepancies.append(
            {
                "source": "audit_json",
                "severity": "high",
                "summary": "post-run self-check audit is missing",
                "evidence": str(audit_json_path),
            }
        )
    else:
        audit_status = str(audit.get("status", "unknown"))
        actual_cadence = str(audit.get("cadence", "unknown"))
        semantic_delta_counts = dict(audit.get("semantic_delta_counts") or {})
        for name, check in dict(audit.get("checks") or {}).items():
            discrepancy = discrepancy_from_check(str(name), dict(check or {}))
            if discrepancy:
                discrepancies.append(discrepancy)

    issues = quality_issues(run_output)
    for issue in issues:
        discrepancies.append(
            {
                "source": "output_quality",
                "severity": "medium",
                "summary": "output quality warning: %s" % issue,
                "evidence": issue,
            }
        )

    actions = [action_for_discrepancy(item) for item in discrepancies]
    result: Dict[str, Any] = {
        "cadence": cadence,
        "actual_cadence": actual_cadence,
        "date": run_date,
        "generated_at": generated,
        "status": status_from(audit_status, discrepancies),
        "audit_json": str(audit_json_path),
        "audit_status": audit_status,
        "semantic_delta_counts": semantic_delta_counts,
        "quality_score": quality_score(run_output),
        "discrepancies": discrepancies,
        "improvement_actions": actions,
    }
    paths = write_review_files(output_root, result, run_date, cadence)
    result["json_path"] = str(paths["json_path"])
    result["markdown_path"] = str(paths["markdown_path"])
    result["learning_log"] = str(paths["learning_log"])
    paths["json_path"].write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an Argus post-run review from a CI self-check audit.")
    parser.add_argument("--cadence", choices=["daily", "weekly"], required=True)
    parser.add_argument("--output-root", type=Path, default=output_root_from_env())
    parser.add_argument("--audit-json", type=Path, required=True)
    parser.add_argument("--run-output-file", default="")
    parser.add_argument("--date", default="")
    args = parser.parse_args()
    run_output = ""
    if args.run_output_file and Path(args.run_output_file).exists():
        run_output = Path(args.run_output_file).read_text(errors="replace")
    result = run_review(
        cadence=args.cadence,
        output_root=args.output_root,
        audit_json_path=args.audit_json,
        run_output=run_output,
        date=args.date or None,
    )
    print("Argus run review %s: %s" % (args.cadence, result["status"]))
    print("Review JSON: %s" % result["json_path"])
    print("Review Markdown: %s" % result["markdown_path"])
    print("Learning log: %s" % result["learning_log"])
    return 1 if result["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
