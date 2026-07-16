#!/usr/bin/env python3
"""Evaluate the CI-OS end-to-end launch readiness gate.

This script intentionally does not run the full world by itself. It consumes
the authoritative outputs from the Hermes package contract, the public run
status artifact, and the Playwright dashboard click suite, then produces one
machine-readable verdict. Launch readiness is not inferred from scattered logs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, cast

RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SOURCE_REF_PATTERN = re.compile(r"^[0-9a-f]{16}$")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return cast(dict[str, Any], payload) if isinstance(payload, dict) else {}


def _sha256_file(path: Path) -> str:
    """Return the digest of exact served bytes, or an empty digest if absent."""
    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _dict_value(value: Any) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


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


def _source_coverage_complete(
    public_status: Mapping[str, Any],
    *,
    run_id: str,
    min_active_sources: int,
) -> bool:
    coverage = _dict_value(public_status.get("source_coverage"))
    active = _int_value(coverage.get("active_source_count"))
    checked = _int_value(coverage.get("checked_source_count"))
    disposed = _int_value(coverage.get("disposed_source_count"))
    raw_dispositions = coverage.get("dispositions")
    dispositions = cast(list[object], raw_dispositions) if isinstance(raw_dispositions, list) else []
    source_refs = [
        str(_dict_value(item).get("source_ref") or "").strip()
        for item in dispositions
        if isinstance(item, dict)
    ]
    dispositions_valid = len(dispositions) == disposed and all(
        isinstance(item, dict)
        and SOURCE_REF_PATTERN.fullmatch(
            str(_dict_value(item).get("source_ref") or "").strip()
        )
        is not None
        and 0 < len(str(_dict_value(item).get("reason") or "").strip()) <= 120
        for item in dispositions
    ) and len(source_refs) == len(set(source_refs))
    return (
        coverage.get("run_id") == run_id
        and active >= min_active_sources
        and active > 0
        and checked + disposed == active
        and dispositions_valid
    )


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
    counts = _dict_value(product.get("counts"))
    product_event_count = _int_value(
        counts.get("product_event_count"),
        _int_value(run.get("product_event_count")),
    )
    extracted_row_count = _int_value(counts.get("product_surface_extracted_row_count"))
    has_product_proof = product_event_count > 0 or extracted_row_count > 0
    if status in {"present", "processed", "ready"}:
        return has_product_proof
    return (
        status == "limited_by_product_surface_evidence"
        and product.get("blocks_action") is False
        and has_product_proof
    )


def _public_safety_ok(public_status: Mapping[str, Any]) -> bool:
    safety = _dict_value(public_status.get("safety"))
    return (
        safety.get("public_safe") is True
        and safety.get("artifact_paths_redacted") is True
        and safety.get("secret_values_included") is False
    )


def _parse_aware_datetime(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _fresh(value: Any, *, now: datetime, max_age_seconds: int) -> bool:
    generated_at = _parse_aware_datetime(value)
    if generated_at is None:
        return False
    age = (now - generated_at).total_seconds()
    return -60 <= age <= max_age_seconds


def _structured_verdict_passed(
    verdict: Mapping[str, Any],
    *,
    expected_gate: str,
    run_id: str,
    now: datetime,
    max_age_seconds: int,
) -> bool:
    checks = verdict.get("checks")
    typed_checks = cast(dict[object, object], checks) if isinstance(checks, dict) else {}
    return (
        verdict.get("schema_version") == 1
        and verdict.get("gate") == expected_gate
        and verdict.get("run_id") == run_id
        and verdict.get("status") == "pass"
        and verdict.get("exit_code") == 0
        and bool(typed_checks)
        and all(value is True for value in typed_checks.values())
        and _fresh(verdict.get("generated_at"), now=now, max_age_seconds=max_age_seconds)
    )


def _public_status_current(
    public_status: Mapping[str, Any],
    *,
    run_id: str,
    now: datetime,
    max_age_seconds: int,
) -> bool:
    return (
        public_status.get("schema_version") == 2
        and RUN_ID_PATTERN.fullmatch(run_id) is not None
        and public_status.get("run_id") == run_id
        and _fresh(public_status.get("generated_at"), now=now, max_age_seconds=max_age_seconds)
    )


def _product_extraction_complete(public_status: Mapping[str, Any], *, run_id: str) -> bool:
    extraction = _dict_value(public_status.get("product_extraction"))
    planned = _int_value(extraction.get("planned"))
    attempted = _int_value(extraction.get("attempted"))
    terminal = _int_value(extraction.get("terminal"))
    successful = _int_value(extraction.get("successful"))
    failed = _int_value(extraction.get("failed"))
    not_started = _int_value(extraction.get("not_started"))
    return (
        extraction.get("run_id") == run_id
        and planned > 0
        and attempted + not_started == planned
        and terminal == attempted
        and successful + failed == terminal
        and not_started == 0
        and extraction.get("accounting_complete") is True
        and extraction.get("all_planned_terminal") is True
    )


def _publication_manifest_bound(
    manifest: Mapping[str, Any],
    verdict: Mapping[str, Any],
    *,
    run_id: str,
    manifest_sha256: str,
) -> bool:
    """Bind the launch decision to the exact served decision manifest bytes."""
    safety = _dict_value(manifest.get("safety"))
    expected_sha = str(verdict.get("manifest_sha256") or "")
    return (
        manifest.get("schema_version") == 1
        and manifest.get("run_id") == run_id
        and manifest.get("kind") == "decision"
        and isinstance(manifest.get("files"), list)
        and bool(manifest.get("files"))
        and safety.get("public_safe") is True
        and safety.get("artifact_paths_redacted") is True
        and safety.get("secret_values_included") is False
        and SHA256_PATTERN.fullmatch(manifest_sha256) is not None
        and expected_sha == manifest_sha256
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
    click_verdict: dict[str, Any] | None = None,
    package_verdict: dict[str, Any] | None = None,
    publication_verdict: dict[str, Any] | None = None,
    publication_manifest: dict[str, Any] | None = None,
    publication_manifest_sha256: str = "",
    now: datetime | None = None,
    max_verdict_age_seconds: int = 900,
    min_active_sources: int = 1,
    max_failed_sources: int = 0,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Return a launch readiness verdict from current authoritative artifacts."""

    coverage = _dict_value(public_status.get("source_coverage"))
    click_verdict = click_verdict or {}
    package_verdict = package_verdict or {}
    publication_verdict = publication_verdict or {}
    publication_manifest = publication_manifest or {}
    evaluated_at = now or datetime.now(timezone.utc)
    run_id = str(public_status.get("run_id") or "")
    checks = {
        "public_status_current_run": _public_status_current(
            public_status,
            run_id=run_id,
            now=evaluated_at,
            max_age_seconds=max_verdict_age_seconds,
        ),
        "public_status_publishable": _public_status_publishable(public_status),
        "source_coverage_complete": _source_coverage_complete(
            public_status,
            run_id=run_id,
            min_active_sources=min_active_sources,
        ),
        "source_failure_budget_ok": _source_failure_budget_ok(
            public_status,
            max_failed_sources=max_failed_sources,
        ),
        "audience_demand_processed": _audience_demand_processed(public_status),
        "product_reality_present": _product_reality_present(public_status),
        "product_extraction_complete": _product_extraction_complete(public_status, run_id=run_id),
        "dashboard_click_validation_passed": _structured_verdict_passed(
            click_verdict,
            expected_gate="dashboard_click_validation",
            run_id=run_id,
            now=evaluated_at,
            max_age_seconds=max_verdict_age_seconds,
        ),
        "hermes_package_contract_passed": _structured_verdict_passed(
            package_verdict,
            expected_gate="hermes_package_contract",
            run_id=run_id,
            now=evaluated_at,
            max_age_seconds=max_verdict_age_seconds,
        ),
        "publication_integrity_passed": _structured_verdict_passed(
            publication_verdict,
            expected_gate="publication_integrity",
            run_id=run_id,
            now=evaluated_at,
            max_age_seconds=max_verdict_age_seconds,
        ),
        "publication_manifest_bound": _publication_manifest_bound(
            publication_manifest,
            publication_verdict,
            run_id=run_id,
            manifest_sha256=publication_manifest_sha256,
        ),
        "public_safety_ok": _public_safety_ok(public_status),
    }

    blockers: list[dict[str, str]] = []
    if not checks["public_status_current_run"]:
        blockers.append(
            _blocker(
                "public_status_current_run",
                f"run_id={run_id or 'missing'} generated_at={public_status.get('generated_at')}",
                "Generate a fresh schema-v2 public status for the current run.",
            )
        )
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
                    f"disposed_source_count={_int_value(coverage.get('disposed_source_count'))} "
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
    if not checks["product_extraction_complete"]:
        extraction = _dict_value(public_status.get("product_extraction"))
        blockers.append(
            _blocker(
                "product_extraction_complete",
                (
                    f"planned={_int_value(extraction.get('planned'))} "
                    f"attempted={_int_value(extraction.get('attempted'))} "
                    f"terminal={_int_value(extraction.get('terminal'))} "
                    f"not_started={_int_value(extraction.get('not_started'))}"
                ),
                "Complete every current-run product extraction or record a terminal failure before launch.",
            )
        )
    if not checks["dashboard_click_validation_passed"]:
        blockers.append(
            _blocker(
                "dashboard_click_validation_passed",
                "missing, stale, failed, or run-mismatched dashboard click verdict",
                "Run scripts/validate_dashboard_clicks.py for this run and provide its JSON verdict.",
            )
        )
    if not checks["hermes_package_contract_passed"]:
        blockers.append(
            _blocker(
                "hermes_package_contract_passed",
                "missing, stale, failed, or run-mismatched package verdict",
                "Run scripts/verify_hermes_package_contract.py for this run and provide its JSON verdict.",
            )
        )
    if not checks["publication_integrity_passed"]:
        blockers.append(
            _blocker(
                "publication_integrity_passed",
                "missing, stale, failed, or run-mismatched publication verdict",
                "Publish this run through scripts/publish_generation.py and provide its JSON verdict.",
            )
        )
    if not checks["publication_manifest_bound"]:
        blockers.append(
            _blocker(
                "publication_manifest_bound",
                "served manifest is missing, unsafe, non-decision, run-mismatched, or digest-mismatched",
                "Read the served publication manifest and verify its exact digest against the publication verdict.",
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

    status = "pass" if not blockers else "fail"
    payload: dict[str, Any] = {
        "schema_version": 1,
        "gate": "cios_e2e_launch_readiness",
        "run_id": run_id,
        "generated_at": generated_at or evaluated_at.isoformat().replace("+00:00", "Z"),
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
    parser.add_argument("--click-verdict", type=Path, required=True)
    parser.add_argument("--package-verdict", type=Path, required=True)
    parser.add_argument("--publication-verdict", type=Path, required=True)
    parser.add_argument("--publication-manifest", type=Path, required=True)
    parser.add_argument("--now", help="Optional aware ISO timestamp for deterministic validation.")
    parser.add_argument("--max-verdict-age-seconds", type=int, default=900)
    parser.add_argument("--min-active-sources", type=int, default=1)
    parser.add_argument("--max-failed-sources", type=int, default=0)
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = evaluate_launch_readiness(
        public_status=_load_json(args.public_status),
        click_verdict=_load_json(args.click_verdict),
        package_verdict=_load_json(args.package_verdict),
        publication_verdict=_load_json(args.publication_verdict),
        publication_manifest=_load_json(args.publication_manifest),
        publication_manifest_sha256=_sha256_file(args.publication_manifest),
        now=_parse_aware_datetime(args.now) if args.now else None,
        max_verdict_age_seconds=args.max_verdict_age_seconds,
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
