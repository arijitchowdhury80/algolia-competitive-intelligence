#!/usr/bin/env python3
"""Evaluate the CI-OS end-to-end launch readiness gate.

This script intentionally does not run the full world by itself. It consumes
the authoritative outputs from the Hermes package contract, the public run
status artifact, and the Playwright dashboard click suite, then produces one
machine-readable verdict. Launch readiness is not inferred from scattered logs.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


PASS_CLICK_TOKEN = "PASS dashboard_click_validation"
PASS_PACKAGE_TOKEN = "PASS: CI-OS Hermes package contract satisfied"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _load_text(path: Path | None, literal: str | None) -> str:
    if literal is not None:
        return literal
    if path is None:
        return ""
    return path.read_text(encoding="utf-8")


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int_value(value: Any, default: int = 0) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return default


def _public_status_publishable(public_status: Mapping[str, Any]) -> bool:
    return (
        public_status.get("publish_status") == "published"
        and public_status.get("status") == "published"
        and public_status.get("public_dashboard_updated") is True
    )


def _source_coverage_complete(public_status: Mapping[str, Any], *, min_active_sources: int) -> bool:
    coverage = _dict_value(public_status.get("source_coverage"))
    active = _int_value(coverage.get("active_source_count"))
    checked = _int_value(coverage.get("checked_source_count"))
    return active >= min_active_sources and checked >= active and active > 0


def _source_failure_budget_ok(public_status: Mapping[str, Any], *, max_failed_sources: int) -> bool:
    coverage = _dict_value(public_status.get("source_coverage"))
    return _int_value(coverage.get("failed_source_count")) <= max_failed_sources


def _audience_demand_processed(public_status: Mapping[str, Any]) -> bool:
    planes = _dict_value(public_status.get("planes"))
    demand = _dict_value(planes.get("audience_demand"))
    run = _dict_value(public_status.get("product_market_run"))
    status = str(demand.get("status") or "").strip().lower()
    demand_signal_count = _int_value(
        _dict_value(demand.get("counts")).get("demand_signal_count"),
        _int_value(run.get("demand_signal_count")),
    )
    return status in {"processed", "present", "ready"} and demand_signal_count > 0 and not bool(
        demand.get("blocks_action")
    )


def _product_reality_present(public_status: Mapping[str, Any]) -> bool:
    planes = _dict_value(public_status.get("planes"))
    product = _dict_value(planes.get("product_reality"))
    run = _dict_value(public_status.get("product_market_run"))
    status = str(product.get("status") or "").strip().lower()
    product_event_count = _int_value(
        _dict_value(product.get("counts")).get("product_event_count"),
        _int_value(run.get("product_event_count")),
    )
    return (
        product_event_count > 0
        and not bool(product.get("blocks_action"))
        and status not in {"missing", "blocked", "failed", "blocked_on_evidence"}
    )


def _public_safety_ok(public_status: Mapping[str, Any]) -> bool:
    safety = _dict_value(public_status.get("safety"))
    return (
        safety.get("public_safe") is True
        and safety.get("artifact_paths_redacted") is True
        and safety.get("secret_values_included") is False
    )


def _click_validation_passed(log_text: str) -> bool:
    return PASS_CLICK_TOKEN in log_text


def _package_contract_passed(log_text: str) -> bool:
    return PASS_PACKAGE_TOKEN in log_text


def _public_redaction_passed(redaction: Mapping[str, Any] | None) -> bool:
    if not redaction:
        return False
    return (
        redaction.get("status") in {"clean", "redacted", "passed"}
        and redaction.get("public_safe_for_scan") is True
        and not _dict_value(redaction).get("error")
    )


def _public_scan_passed(scan: Mapping[str, Any] | None) -> bool:
    if not scan:
        return False
    findings = scan.get("findings")
    finding_count = _int_value(scan.get("finding_count"))
    if isinstance(findings, list):
        finding_count = len(findings)
    return scan.get("status") == "passed" and scan.get("public_safe") is True and finding_count == 0


def _operational_safety_passed(safety: Mapping[str, Any] | None) -> bool:
    if not safety:
        return False
    return (
        safety.get("status") == "passed"
        and safety.get("operational_safe") is True
        and safety.get("current_release_exists") is True
        and safety.get("served_release_ready") is True
        and _int_value(safety.get("hidden_staging_dir_count")) == 0
        and _int_value(safety.get("root_owned_artifact_count")) == 0
        and _int_value(safety.get("orphan_process_count")) == 0
    )


def _blocker(requirement: str, actual: str, next_step: str) -> dict[str, str]:
    return {
        "requirement": requirement,
        "actual": actual,
        "next_step": next_step,
    }


def _demand_status(public_status: Mapping[str, Any]) -> str:
    demand = _dict_value(_dict_value(public_status.get("planes")).get("audience_demand"))
    return str(demand.get("status") or "missing").strip() or "missing"


def _demand_signal_count(public_status: Mapping[str, Any]) -> int:
    demand = _dict_value(_dict_value(public_status.get("planes")).get("audience_demand"))
    run = _dict_value(public_status.get("product_market_run"))
    return _int_value(_dict_value(demand.get("counts")).get("demand_signal_count"), _int_value(run.get("demand_signal_count")))


def evaluate_launch_readiness(
    *,
    public_status: dict[str, Any],
    click_validation_log: str = "",
    package_contract_log: str = "",
    public_redaction: dict[str, Any] | None = None,
    public_safety_scan: dict[str, Any] | None = None,
    operational_safety: dict[str, Any] | None = None,
    min_active_sources: int = 1,
    max_failed_sources: int = 0,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Return a launch readiness verdict from current authoritative artifacts."""

    coverage = _dict_value(public_status.get("source_coverage"))
    checks = {
        "public_status_publishable": _public_status_publishable(public_status),
        "source_coverage_complete": _source_coverage_complete(
            public_status,
            min_active_sources=min_active_sources,
        ),
        "source_failure_budget_ok": _source_failure_budget_ok(
            public_status,
            max_failed_sources=max_failed_sources,
        ),
        "audience_demand_processed": _audience_demand_processed(public_status),
        "product_reality_present": _product_reality_present(public_status),
        "dashboard_click_validation_passed": _click_validation_passed(click_validation_log),
        "hermes_package_contract_passed": _package_contract_passed(package_contract_log),
        "public_safety_ok": _public_safety_ok(public_status),
        "public_artifact_redaction_passed": _public_redaction_passed(public_redaction),
        "public_artifact_scan_passed": _public_scan_passed(public_safety_scan),
        "live_operational_safety_passed": _operational_safety_passed(operational_safety),
    }

    blockers: list[dict[str, str]] = []
    if not checks["public_status_publishable"]:
        blockers.append(
            _blocker(
                "public_status_publishable",
                f"publish_status={public_status.get('publish_status')} status={public_status.get('status')}",
                "Run the Hermes daily path until public status is published and the dashboard is updated.",
            )
        )
    if not checks["source_coverage_complete"]:
        blockers.append(
            _blocker(
                "source_coverage_complete",
                (
                    f"active_source_count={_int_value(coverage.get('active_source_count'))} "
                    f"checked_source_count={_int_value(coverage.get('checked_source_count'))} "
                    f"min_active_sources={min_active_sources}"
                ),
                "Complete or explicitly skip all active monitored sources before launch.",
            )
        )
    if not checks["source_failure_budget_ok"]:
        blockers.append(
            _blocker(
                "source_failure_budget_ok",
                f"failed_source_count={_int_value(coverage.get('failed_source_count'))} max_failed_sources={max_failed_sources}",
                "Repair failed sources or raise the launch failure budget with a documented degradation decision.",
            )
        )
    if not checks["audience_demand_processed"]:
        blockers.append(
            _blocker(
                "audience_demand_processed",
                f"audience_demand.status={_demand_status(public_status)} demand_signal_count={_demand_signal_count(public_status)}",
                "Configure GA4 or upload a valid GA / Looker export, then refresh Argus demand and dashboard state.",
            )
        )
    if not checks["product_reality_present"]:
        blockers.append(
            _blocker(
                "product_reality_present",
                f"product_event_count={_int_value(_dict_value(public_status.get('product_market_run')).get('product_event_count'))}",
                "Run Scout-backed product-surface extraction until product reality evidence is present.",
            )
        )
    if not checks["dashboard_click_validation_passed"]:
        blockers.append(
            _blocker(
                "dashboard_click_validation_passed",
                "missing PASS dashboard_click_validation",
                "Run scripts/validate_dashboard_clicks.py against the target dashboard and pass its output into this gate.",
            )
        )
    if not checks["hermes_package_contract_passed"]:
        blockers.append(
            _blocker(
                "hermes_package_contract_passed",
                "missing PASS: CI-OS Hermes package contract satisfied",
                "Run scripts/verify_hermes_package_contract.py against the deployed package and pass its output into this gate.",
            )
        )
    if not checks["public_safety_ok"]:
        blockers.append(
            _blocker(
                "public_safety_ok",
                f"safety={json.dumps(_dict_value(public_status.get('safety')), sort_keys=True)}",
                "Redact internal paths and secrets from public artifacts before launch.",
            )
        )
    if not checks["public_artifact_redaction_passed"]:
        blockers.append(
            _blocker(
                "public_artifact_redaction_passed",
                f"redaction_status={_dict_value(public_redaction).get('status', 'missing')}",
                "Run scripts/redact_public_artifacts.py and pass its JSON artifact into this gate.",
            )
        )
    if not checks["public_artifact_scan_passed"]:
        blockers.append(
            _blocker(
                "public_artifact_scan_passed",
                f"scan_status={_dict_value(public_safety_scan).get('status', 'missing')}",
                "Run scripts/scan_public_artifacts.py and pass its JSON artifact into this gate.",
            )
        )
    if not checks["live_operational_safety_passed"]:
        blockers.append(
            _blocker(
                "live_operational_safety_passed",
                f"operational_status={_dict_value(operational_safety).get('status', 'missing')}",
                "Run scripts/check_live_operational_safety.py against the deployed host and pass its JSON artifact into this gate.",
            )
        )

    status = "pass" if not blockers else "fail"
    payload: dict[str, Any] = {
        "gate": "cios_e2e_launch_readiness",
        "generated_at": generated_at or _now(),
        "tenant_slug": public_status.get("tenant_slug"),
        "status": status,
        "exit_code": 0 if status == "pass" else 2,
        "summary": "CI-OS launch readiness gate passed."
        if status == "pass"
        else "CI-OS launch readiness gate failed.",
        "checks": checks,
        "blockers": blockers,
        "source_coverage": coverage,
        "public_status": {
            "publish_status": public_status.get("publish_status"),
            "status": public_status.get("status"),
            "public_dashboard_updated": public_status.get("public_dashboard_updated"),
            "generated_at": public_status.get("generated_at"),
        },
    }
    next_action = public_status.get("next_hermes_action")
    if next_action:
        payload["next_action"] = next_action
    demand_plan = _dict_value(public_status.get("demand_collection_plan"))
    if demand_plan:
        payload["demand_collection_plan"] = demand_plan
    return payload


def write_payload(payload: Mapping[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(f"{json.dumps(payload, indent=2, sort_keys=True)}\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check CI-OS E2E launch readiness.")
    parser.add_argument("--public-status", type=Path, required=True)
    parser.add_argument("--click-validation-log", type=Path)
    parser.add_argument("--click-validation-log-text")
    parser.add_argument("--package-contract-log", type=Path)
    parser.add_argument("--package-contract-log-text")
    parser.add_argument("--public-redaction", type=Path)
    parser.add_argument("--public-safety-scan", type=Path)
    parser.add_argument("--operational-safety", type=Path)
    parser.add_argument("--min-active-sources", type=int, default=1)
    parser.add_argument("--max-failed-sources", type=int, default=0)
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = evaluate_launch_readiness(
        public_status=_load_json(args.public_status),
        click_validation_log=_load_text(args.click_validation_log, args.click_validation_log_text),
        package_contract_log=_load_text(args.package_contract_log, args.package_contract_log_text),
        public_redaction=_load_json(args.public_redaction) if args.public_redaction else None,
        public_safety_scan=_load_json(args.public_safety_scan) if args.public_safety_scan else None,
        operational_safety=_load_json(args.operational_safety) if args.operational_safety else None,
        min_active_sources=args.min_active_sources,
        max_failed_sources=args.max_failed_sources,
    )
    if args.output:
        write_payload(payload, args.output)
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return int(payload["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
