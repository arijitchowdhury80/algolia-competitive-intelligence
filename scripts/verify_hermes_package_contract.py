#!/usr/bin/env python3
"""Preflight a deployed CI-OS package before trusting Hermes cron.

This is intentionally a package-boundary checker. Hermes owns scheduling; this
script verifies that the installed CI-OS app has the brain modules and safe
publish wrapper needed before a daily run is considered production-acceptable.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


REQUIRED_PATHS = [
    "deploy/cios-admin.service",
    "deploy/cios-daily.sh",
    "deploy/cios-host-permissions.sh",
    "deploy/cios-host-runner.sh",
    "deploy/cios-runner.service",
    "deploy/cios-runner.path",
    "deploy/claude-shim/cios-claude-shim.service",
    "scripts/apply_product_market_schema.py",
    "scripts/daily_production_run.py",
    "scripts/run_product_market_intelligence.py",
    "scripts/build_product_market_payload.py",
    "scripts/build_learning_apply_plan.py",
    "scripts/execute_learning_apply_plan.py",
    "scripts/audit_learning_policies.py",
    "scripts/export_ga4_demand.py",
    "scripts/export_argus_demand_readiness.py",
    "scripts/export_argus_demand_plan_template.py",
    "scripts/import_demand_and_refresh.py",
    "scripts/run_argus_demand_intake.py",
    "scripts/run_admin.py",
    "scripts/execute_product_muscle_gap_discovery.py",
    "scripts/attach_post_run_summaries.py",
    "scripts/rerender_dashboard.py",
    "scripts/plan_product_surface_exports.py",
    "scripts/execute_product_surface_plan.py",
    "scripts/run_product_surface_repair.py",
    "scripts/promote_product_surface_candidates.py",
    "scripts/export_argus_evidence_work_queue.py",
    "scripts/export_argus_product_muscle_work_queue.py",
    "scripts/build_argus_operator_handoff.py",
    "scripts/attach_operator_handoff_to_dashboard.py",
    "scripts/export_argus_data_plane_manifest.py",
    "scripts/export_public_run_status.py",
    "scripts/build_phase0_release_record.py",
    "scripts/check_e2e_launch_readiness.py",
    "scripts/scout_http_shim",
    "scripts/scout_http_shim.py",
    "docs/plan/e2e-validation.md",
    "src/cios/admin/app.py",
    "src/cios/admin/data_plane_manifest.py",
    "src/cios/admin/product_muscle_work_queue.py",
    "src/cios/admin/product_surface_candidates.py",
    "src/cios/admin/product_surface_extraction.py",
    "src/cios/admin/product_surface_repair.py",
    "src/cios/admin/dashboard_refresh.py",
    "src/cios/intelligence",
    "src/cios/admin/learning_apply.py",
    "src/cios/admin/demand_imports.py",
    "src/cios/db/repos/product_market.py",
    "src/cios/admin",
]

WRAPPER_INVARIANTS = {
    "wrapper missing product-market default enable": "CIOS_ENABLE_PRODUCT_MARKET_INTELLIGENCE:-1",
    "wrapper missing package src PYTHONPATH": 'PYTHONPATH="$APP/src',
    "wrapper missing package preflight call": "verify_hermes_package_contract.py",
    "wrapper missing learning-policy audit gate": "audit_learning_policies.py",
    "wrapper missing product-market schema apply": "apply_product_market_schema.py",
    "wrapper missing product-surface candidate promotion": "promote_product_surface_candidates.py",
    "wrapper missing demand-readiness export": "export_argus_demand_readiness.py",
    "wrapper missing demand plan template export": "export_argus_demand_plan_template.py",
    "wrapper missing demand-intake coordinator": "run_argus_demand_intake.py",
    "wrapper missing demand-intake history recording": "--record-history",
    "wrapper missing post-run summary attach": "attach_post_run_summaries.py",
    "wrapper missing demand-readiness attach": "--demand-readiness",
    "wrapper missing demand plan template manifest input": "--demand-plan-template",
    "wrapper missing demand-intake manifest input": "--demand-intake",
    "wrapper missing post-run dashboard rerender": "rerender_dashboard.py",
    "wrapper missing evidence work queue export": "export_argus_evidence_work_queue.py",
    "wrapper missing product muscle work queue export": "export_argus_product_muscle_work_queue.py",
    "wrapper missing product muscle work queue handoff input": "--product-muscle-queue",
    "wrapper missing product muscle work queue manifest input": "--product-muscle-work-queue",
    "wrapper missing Argus operator handoff builder": "build_argus_operator_handoff.py",
    "wrapper missing dashboard operator handoff attach": "attach_operator_handoff_to_dashboard.py",
    "wrapper missing Argus data-plane manifest export": "export_argus_data_plane_manifest.py",
    "wrapper missing public run status export": "export_public_run_status.py",
    "wrapper missing public latest run status artifact": "argus-latest-run-status.json",
    "wrapper missing daily-run timeout guard": "CIOS_DAILY_RUN_TIMEOUT_SECONDS",
    "wrapper missing app-owned product-market workdir": 'CIOS_PRODUCT_MARKET_WORKDIR:-$APP/tmp/product-market',
    "wrapper missing app-user runner handoff switch": "CIOS_RUNNER_HANDOFF",
    "wrapper missing app-user runner request queue": ".request",
    "wrapper missing app-user runner result wait": ".result",
    "wrapper missing handoff bypass for app-user execution": "CIOS_DISABLE_RUNNER_HANDOFF",
    "wrapper missing marked-output cleanup": ".cios-output-dir",
    "wrapper missing scoped output cleanup": 'find "$OUT" -mindepth 1 ! -name .cios-output-dir -exec rm -rf -- {} +',
    "wrapper missing current-run artifact validation": "missing dashboard artifact from current run",
    "wrapper missing staged publish directory": ".argus-publish.$$",
}

HOST_RUNNER_INVARIANTS = {
    "host runner missing handoff bypass": "CIOS_DISABLE_RUNNER_HANDOFF=1",
    "host runner missing app directory handoff": 'CIOS_APP_DIR="$APP"',
    "host runner missing public directory handoff": 'CIOS_PUBLIC_DIR="$PUB"',
    "host runner missing request glob": "*.request",
    "host runner missing result artifact": ".result",
    "host runner missing log artifact": ".log",
    "host runner missing cios daily wrapper call": "deploy/cios-daily.sh",
}

HOST_PERMISSIONS_INVARIANTS = {
    "host permissions must create CI-OS app user": "useradd --system",
    "host permissions must add app user to Hermes group": 'usermod -aG "$HERMES_GROUP" "$APP_USER"',
    "host permissions must manage Hermes cron wrapper": 'ROOT_WRAPPER="${CIOS_ROOT_WRAPPER:-/root/.hermes/scripts/cios-daily.sh}"',
    "host permissions must know CI-OS shim user": 'SHIM_USER="${CIOS_SHIM_USER:-cios-shim}"',
    "host permissions must prefer ACL traversal for cios": 'setfacl -m "u:$APP_USER:--x" /root/.hermes /root/.hermes/apps',
    "host permissions must grant shim ACL traversal when present": 'setfacl -m "u:$SHIM_USER:--x" /root/.hermes /root/.hermes/apps',
    "host permissions must preserve execute-only Hermes traversal fallback": "chmod 711 /root/.hermes /root/.hermes/apps",
    "host permissions must chown app and public trees to app user": 'chown -R "$APP_USER:$HERMES_GROUP" "$APP" "$PUB"',
    "host permissions must keep queue group-sticky": 'chmod 2775 "$APP" "$APP/run-queue"',
    "host permissions must create app-owned product-market workdir": 'PRODUCT_MARKET_WORKDIR="${CIOS_PRODUCT_MARKET_WORKDIR:-$APP/tmp/product-market}"',
    "host permissions must repair legacy product-market tmp ownership": 'LEGACY_PRODUCT_MARKET_TMP="${CIOS_LEGACY_PRODUCT_MARKET_TMP:-/tmp/cios-product-market}"',
    "host permissions must make Hermes cron wrapper group executable": 'chown "$APP_USER:$HERMES_GROUP" "$ROOT_WRAPPER"',
    "host permissions must protect CI-OS env file": 'chmod 640 "$ENV_FILE"',
}

RUNNER_SERVICE_INVARIANTS = {
    "runner service must run as cios user": "User=cios",
    "runner service must run as cios group": "Group=cios",
    "runner service must include hermes supplementary group": "SupplementaryGroups=hermes",
    "runner service must use CI-OS app working directory": "WorkingDirectory=/root/.hermes/apps/cios",
    "runner service must call host runner": "ExecStart=/root/.hermes/apps/cios/deploy/cios-host-runner.sh",
    "runner service must keep no-new-privileges enabled": "NoNewPrivileges=true",
    "runner service must keep group-writable artifacts": "UMask=0007",
}

RUNNER_PATH_INVARIANTS = {
    "runner path must watch request files": "PathExistsGlob=/root/.hermes/apps/cios/run-queue/*.request",
    "runner path must trigger runner service": "Unit=cios-runner.service",
}

CLAUDE_SHIM_SERVICE_INVARIANTS = {
    "claude shim service must run as cios-shim user": "User=cios-shim",
    "claude shim service must run as cios-shim group": "Group=cios-shim",
    "claude shim service must include hermes supplementary group": "SupplementaryGroups=hermes",
    "claude shim service must bind localhost only": "--host 127.0.0.1",
    "claude shim service must use expected local port": "--port 8663",
    "claude shim service must keep no-new-privileges enabled": "NoNewPrivileges=true",
}

ADMIN_SERVICE_INVARIANTS = {
    "admin service must run package admin runner": "scripts/run_admin.py",
    "admin service must bind to 127.0.0.1 only": "--host 127.0.0.1",
    "admin service must load /root/.hermes/cios-env": "--env-file /root/.hermes/cios-env",
    "admin service must use the expected local admin port": "--port 8765",
    "admin service must run as cios user": "User=cios",
    "admin service must run as cios group": "Group=cios",
    "admin service must keep no-new-privileges enabled": "NoNewPrivileges=true",
    "admin service must read Hermes product-market artifacts": "PrivateTmp=false",
}

MANUAL_DEMAND_FAST_LANE_INVARIANTS = {
    "manual demand fast lane missing demand plan template export": "export_argus_demand_plan_template.py",
    "manual demand fast lane missing demand plan template artifact": "argus-demand-plan-template.csv",
}

ADMIN_REFRESH_INVARIANTS = {
    "admin refresh missing demand plan template export": "export_argus_demand_plan_template.py",
    "admin refresh missing demand plan template artifact": "argus-demand-plan-template.csv",
}

OPERATOR_HANDOFF_INVARIANTS = {
    "operator handoff missing demand plan template input": "--demand-plan-template",
    "operator handoff missing demand plan template summary": "demand_plan_template",
}

GA4_EXPORT_PLAN_INVARIANTS = {
    "ga4 export missing demand-plan CLI input": "--demand-plan",
    "ga4 export missing Argus demand-plan output summary": "argus_demand_plan",
    "ga4 export missing demand-plan coverage summary": "summarize_ga4_demand_plan_coverage",
}

DEMAND_INTAKE_PLAN_INVARIANTS = {
    "demand intake missing demand-plan handoff to GA4 export": "demand_plan=demand_plan",
}

PRODUCT_SURFACE_EXECUTION_INVARIANTS = {
    "product-surface executor missing row-count summary": "product_row_count",
    "product-surface executor missing empty output accounting": "empty_scout_paths",
    "product-surface executor missing product-plane status": "product_plane_status",
}

PRODUCT_SURFACE_PLANNER_INVARIANTS = {
    "product-surface planner missing company-name filter": "--company-name",
    "product-surface planner missing company-id filter": "--company-id",
    "product-surface planner missing surface-id filter": "--surface-id",
    "product-surface planner missing limit filter": "--limit",
}

PRODUCT_SURFACE_EXTRACTION_INVARIANTS = {
    "product-surface extraction control missing Scout bridge default": "scout_http_shim",
    "product-surface extraction control missing provider env default": "CIOS_PRODUCT_MARKET_PROVIDER",
    "product-surface extraction control missing planner command": "plan_product_surface_exports.py",
    "product-surface extraction control missing executor command": "execute_product_surface_plan.py",
}

PRODUCT_SURFACE_CANDIDATE_PROMOTION_INVARIANTS = {
    "product-surface candidate promotion missing promote script command": "promote_product_surface_candidates.py",
    "product-surface candidate promotion missing company-name filter": "--company-name",
    "product-surface candidate promotion missing surface-family filter": "--surface-family",
    "product-surface candidate promotion missing limit": "--limit",
}

PRODUCT_MUSCLE_WORK_QUEUE_INVARIANTS = {
    "product muscle work queue missing first-run extraction action": "Run surface extraction",
    "product muscle work queue missing first-run extraction route": "product-surface-extraction",
    "product muscle work queue missing candidate promotion action": "Promote candidate surface",
    "product muscle work queue missing candidate promotion route": "product-surface-candidates/promote",
}

ADMIN_APP_PRODUCT_SURFACE_EXTRACTION_INVARIANTS = {
    "admin app missing product-surface extraction route": "product-surface-extraction",
    "admin app missing product-surface extraction control": "ProductSurfaceExtractionControl",
    "admin app missing product-surface candidate promotion route": "product-surface-candidates/promote",
    "admin app missing product-surface candidate promotion control": "ProductSurfaceCandidatePromotionControl",
}

IMPORT_CHECKS = [
    "psycopg",
    "yaml",
    "httpx",
    "cios.intelligence",
    "cios.admin",
]

TEST_DEPENDENCY_IMPORTS = [
    "pytest_asyncio",
]


def collect_path_errors(app_dir: Path) -> list[str]:
    errors: list[str] = []
    for rel in REQUIRED_PATHS:
        if not (app_dir / rel).exists():
            errors.append(f"missing required path: {rel}")
    return errors


def collect_wrapper_errors(app_dir: Path) -> list[str]:
    wrapper_path = app_dir / "deploy" / "cios-daily.sh"
    if not wrapper_path.exists():
        return []
    text = wrapper_path.read_text(encoding="utf-8")
    return [message for message, needle in WRAPPER_INVARIANTS.items() if needle not in text]


def collect_host_runner_errors(app_dir: Path) -> list[str]:
    return collect_text_invariant_errors(
        app_dir,
        rel_path="deploy/cios-host-runner.sh",
        invariants=HOST_RUNNER_INVARIANTS,
    )


def collect_host_permissions_errors(app_dir: Path) -> list[str]:
    return collect_text_invariant_errors(
        app_dir,
        rel_path="deploy/cios-host-permissions.sh",
        invariants=HOST_PERMISSIONS_INVARIANTS,
    )


def collect_runner_service_errors(app_dir: Path) -> list[str]:
    return collect_text_invariant_errors(
        app_dir,
        rel_path="deploy/cios-runner.service",
        invariants=RUNNER_SERVICE_INVARIANTS,
    )


def collect_runner_path_errors(app_dir: Path) -> list[str]:
    return collect_text_invariant_errors(
        app_dir,
        rel_path="deploy/cios-runner.path",
        invariants=RUNNER_PATH_INVARIANTS,
    )


def collect_claude_shim_service_errors(app_dir: Path) -> list[str]:
    return collect_text_invariant_errors(
        app_dir,
        rel_path="deploy/claude-shim/cios-claude-shim.service",
        invariants=CLAUDE_SHIM_SERVICE_INVARIANTS,
    )


def collect_admin_service_errors(app_dir: Path) -> list[str]:
    service_path = app_dir / "deploy" / "cios-admin.service"
    if not service_path.exists():
        return []
    text = service_path.read_text(encoding="utf-8")
    errors = [message for message, needle in ADMIN_SERVICE_INVARIANTS.items() if needle not in text]
    if "0.0.0.0" in text and "admin service must bind to 127.0.0.1 only" not in errors:
        errors.append("admin service must bind to 127.0.0.1 only")
    return errors


def collect_text_invariant_errors(
    app_dir: Path,
    *,
    rel_path: str,
    invariants: dict[str, str],
) -> list[str]:
    path = app_dir / rel_path
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    return [message for message, needle in invariants.items() if needle not in text]


def collect_manual_demand_fast_lane_errors(app_dir: Path) -> list[str]:
    return collect_text_invariant_errors(
        app_dir,
        rel_path="scripts/import_demand_and_refresh.py",
        invariants=MANUAL_DEMAND_FAST_LANE_INVARIANTS,
    )


def collect_admin_refresh_errors(app_dir: Path) -> list[str]:
    return collect_text_invariant_errors(
        app_dir,
        rel_path="src/cios/admin/dashboard_refresh.py",
        invariants=ADMIN_REFRESH_INVARIANTS,
    )


def collect_operator_handoff_errors(app_dir: Path) -> list[str]:
    return collect_text_invariant_errors(
        app_dir,
        rel_path="scripts/build_argus_operator_handoff.py",
        invariants=OPERATOR_HANDOFF_INVARIANTS,
    )


def collect_ga4_export_plan_errors(app_dir: Path) -> list[str]:
    return collect_text_invariant_errors(
        app_dir,
        rel_path="scripts/export_ga4_demand.py",
        invariants=GA4_EXPORT_PLAN_INVARIANTS,
    )


def collect_demand_intake_plan_errors(app_dir: Path) -> list[str]:
    return collect_text_invariant_errors(
        app_dir,
        rel_path="scripts/run_argus_demand_intake.py",
        invariants=DEMAND_INTAKE_PLAN_INVARIANTS,
    )


def collect_product_surface_execution_errors(app_dir: Path) -> list[str]:
    return collect_text_invariant_errors(
        app_dir,
        rel_path="scripts/execute_product_surface_plan.py",
        invariants=PRODUCT_SURFACE_EXECUTION_INVARIANTS,
    )


def collect_product_surface_planner_errors(app_dir: Path) -> list[str]:
    return collect_text_invariant_errors(
        app_dir,
        rel_path="scripts/plan_product_surface_exports.py",
        invariants=PRODUCT_SURFACE_PLANNER_INVARIANTS,
    )


def collect_product_surface_extraction_errors(app_dir: Path) -> list[str]:
    return collect_text_invariant_errors(
        app_dir,
        rel_path="src/cios/admin/product_surface_extraction.py",
        invariants=PRODUCT_SURFACE_EXTRACTION_INVARIANTS,
    )


def collect_product_surface_candidate_promotion_errors(app_dir: Path) -> list[str]:
    return collect_text_invariant_errors(
        app_dir,
        rel_path="src/cios/admin/product_surface_candidates.py",
        invariants=PRODUCT_SURFACE_CANDIDATE_PROMOTION_INVARIANTS,
    )


def collect_product_muscle_work_queue_errors(app_dir: Path) -> list[str]:
    return collect_text_invariant_errors(
        app_dir,
        rel_path="src/cios/admin/product_muscle_work_queue.py",
        invariants=PRODUCT_MUSCLE_WORK_QUEUE_INVARIANTS,
    )


def collect_admin_app_product_surface_extraction_errors(app_dir: Path) -> list[str]:
    return collect_text_invariant_errors(
        app_dir,
        rel_path="src/cios/admin/app.py",
        invariants=ADMIN_APP_PRODUCT_SURFACE_EXTRACTION_INVARIANTS,
    )


def collect_import_errors(app_dir: Path) -> list[str]:
    python_bin = app_dir / ".venv" / "bin" / "python"
    if not python_bin.exists():
        return [f"missing package python: {python_bin}"]

    code = "\n".join([f"import {module}" for module in IMPORT_CHECKS])
    env = os.environ.copy()
    env["PYTHONPATH"] = str(app_dir / "src")
    completed = subprocess.run(
        [str(python_bin), "-c", code],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    if completed.returncode == 0:
        return []
    detail = (completed.stderr or completed.stdout or "").strip()
    return [f"python import preflight failed: {detail}"]


def collect_test_dependency_errors(app_dir: Path) -> list[str]:
    python_bin = app_dir / ".venv" / "bin" / "python"
    if not python_bin.exists():
        return [f"missing package python: {python_bin}"]

    code = "\n".join([f"import {module}" for module in TEST_DEPENDENCY_IMPORTS])
    completed = subprocess.run(
        [str(python_bin), "-c", code],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode == 0:
        return []
    return [f"missing required test dependency: {module}" for module in TEST_DEPENDENCY_IMPORTS]


def collect_scout_errors(scout_bin: str) -> list[str]:
    if shutil.which(scout_bin):
        return []
    return [f"missing required Scout binary: {scout_bin}"]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify a deployed CI-OS Hermes package contract.")
    parser.add_argument("--app-dir", required=True, type=Path, help="Installed CI-OS app directory.")
    parser.add_argument(
        "--skip-python-imports",
        action="store_true",
        help="Only check filesystem and wrapper contract, not the deployed venv imports.",
    )
    parser.add_argument(
        "--require-scout",
        action="store_true",
        help="Require the configured Scout CLI to be available for product-market runs.",
    )
    parser.add_argument(
        "--require-test-deps",
        action="store_true",
        help="Require test-only dependencies needed for remote full-suite validation.",
    )
    parser.add_argument("--scout-bin", default="scout", help="Scout CLI command name/path.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    app_dir = args.app_dir

    errors: list[str] = []
    if not app_dir.exists():
        errors.append(f"missing app directory: {app_dir}")
    else:
        errors.extend(collect_path_errors(app_dir))
        errors.extend(collect_wrapper_errors(app_dir))
        errors.extend(collect_host_runner_errors(app_dir))
        errors.extend(collect_host_permissions_errors(app_dir))
        errors.extend(collect_runner_service_errors(app_dir))
        errors.extend(collect_runner_path_errors(app_dir))
        errors.extend(collect_claude_shim_service_errors(app_dir))
        errors.extend(collect_admin_service_errors(app_dir))
        errors.extend(collect_manual_demand_fast_lane_errors(app_dir))
        errors.extend(collect_admin_refresh_errors(app_dir))
        errors.extend(collect_operator_handoff_errors(app_dir))
        errors.extend(collect_ga4_export_plan_errors(app_dir))
        errors.extend(collect_demand_intake_plan_errors(app_dir))
        errors.extend(collect_product_surface_execution_errors(app_dir))
        errors.extend(collect_product_surface_planner_errors(app_dir))
        errors.extend(collect_product_surface_extraction_errors(app_dir))
        errors.extend(collect_product_surface_candidate_promotion_errors(app_dir))
        errors.extend(collect_product_muscle_work_queue_errors(app_dir))
        errors.extend(collect_admin_app_product_surface_extraction_errors(app_dir))
        if not args.skip_python_imports:
            errors.extend(collect_import_errors(app_dir))
        if args.require_scout:
            errors.extend(collect_scout_errors(args.scout_bin))
        if args.require_test_deps:
            errors.extend(collect_test_dependency_errors(app_dir))

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 2

    print("PASS: CI-OS Hermes package contract satisfied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
