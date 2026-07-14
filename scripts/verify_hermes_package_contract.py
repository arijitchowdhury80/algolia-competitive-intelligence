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
    "deploy/cios-daily-app.sh",
    "deploy/cios-host-permissions.sh",
    "deploy/cios-host-runner.sh",
    "deploy/cios-run-finalize.sh",
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
    "scripts/cios_run_queue.py",
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
    "src/cios/intelligence/product_surface_executor.py",
    "src/cios/platform/process_supervisor.py",
    "src/cios/platform/cgroup_launcher.py",
    "src/cios/platform/redaction.py",
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
    "wrapper missing product-surface batch timeout guard": "CIOS_PRODUCT_MARKET_EXPORT_BATCH_TIMEOUT_SECONDS",
    "wrapper missing product-surface stage timeout guard": "CIOS_PRODUCT_MARKET_EXPORT_STAGE_TIMEOUT_SECONDS",
    "wrapper missing app-owned product-market workdir": 'CIOS_PRODUCT_MARKET_WORKDIR:-$APP/tmp/product-market',
    "wrapper missing fixed cios identity gate": '"$current_user" = "cios"',
    "wrapper missing fixed host queue client root": "HOST_CLIENT_ROOT=/opt/cios/app",
    "wrapper missing fixed Hermes queue client root": "HERMES_CLIENT_ROOT=/opt/data/apps/cios",
    "wrapper missing selected systemd request queue": 'QUEUE="$CLIENT_ROOT/run-queue"',
    "wrapper wait must exceed systemd cleanup window": "WAIT_SECONDS=1800",
    "wrapper missing secure queue enqueue": '"$HELPER" enqueue',
    "wrapper missing secure result read": '"$HELPER" read-result',
    "wrapper must sanitize the queue client environment": '"$ENV" -i PATH=/usr/bin:/bin',
    "wrapper missing marked-output cleanup": ".cios-output-dir",
    "wrapper missing scoped output cleanup": 'find "$OUT" -mindepth 1 ! -name .cios-output-dir -exec rm -rf -- {} +',
    "wrapper missing current-run artifact validation": "missing dashboard artifact from current run",
    "wrapper missing staged publish directory": ".argus-publish.$$",
}

PUBLIC_WRAPPER_INVARIANTS = {
    "wrapper missing fixed host queue selection": (
        'if [ -d "$HOST_CLIENT_ROOT" ] && [ ! -L "$HOST_CLIENT_ROOT" ]; then\n'
        '  CLIENT_ROOT="$HOST_CLIENT_ROOT"'
    ),
    "wrapper missing Hermes container queue fallback": (
        'elif [ -d "$HERMES_CLIENT_ROOT" ] && [ ! -L "$HERMES_CLIENT_ROOT" ]; then\n'
        '  CLIENT_ROOT="$HERMES_CLIENT_ROOT"'
    ),
}

HOST_RUNNER_INVARIANTS = {
    "host runner must fix the /opt CI-OS app mount": "APP=/opt/cios/app",
    "host runner must fix the /opt CI-OS public mount": "PUB=/opt/cios/public",
    "host runner missing secure queue helper": "cios_run_queue.py",
    "host runner must require cios identity": '$(/usr/bin/id -un)" != "cios"',
    "host runner must drain requests through queue helper": '"$HELPER" run-pending',
}

RUN_FINALIZER_INVARIANTS = {
    "run finalizer missing systemd result handling": "SERVICE_RESULT",
    "run finalizer missing secure queue helper": "cios_run_queue.py",
    "run finalizer must require cios identity": '$(/usr/bin/id -un)" != "cios"',
    "run finalizer must delegate finalization": '"$HELPER" finalize',
}

RUN_QUEUE_INVARIANTS = {
    "run queue missing no-follow filesystem access": "O_NOFOLLOW",
    "run queue missing atomic state replacement": "os.replace",
    "run queue missing private active state": '".state"',
    "run queue missing unguessable request ids": "uuid.uuid4",
    "run queue missing serial request draining": "def run_pending",
    "run queue missing privileged cios identity check": "require_cios_user()",
    "run queue raw logs must be cios-private": "_create_state_regular",
    "run queue private files must use mode 0600": "0o600",
    "run queue missing timeout exit mapping": "124 if timed_out else 2",
    "run queue missing blocked timeout status": '"blocked_runtime_timeout"',
}

HOST_PERMISSIONS_INVARIANTS = {
    "host permissions must define Hermes source app": 'SOURCE_APP="${CIOS_SOURCE_APP_DIR:-/root/.hermes/apps/cios}"',
    "host permissions must define Hermes source public dir": 'SOURCE_PUB="${CIOS_SOURCE_PUBLIC_DIR:-/root/.hermes/apps/algolia-competitive-intelligence/apps/dashboard/public}"',
    "host permissions must default app runtime mount to /opt": 'APP="${CIOS_APP_DIR:-/opt/cios/app}"',
    "host permissions must default public runtime mount to /opt": 'PUB="${CIOS_PUBLIC_DIR:-/opt/cios/public}"',
    "host permissions must harden the /opt/cios parent": "install -d -o root -g root -m 0755 /opt/cios",
    "host permissions must bind-mount CI-OS app": 'mount --bind "$SOURCE_APP" "$APP"',
    "host permissions must bind-mount CI-OS public dir": 'mount --bind "$SOURCE_PUB" "$PUB"',
    "host permissions must persist app bind mount": 'app_fstab="$SOURCE_APP $APP none bind 0 0"',
    "host permissions must persist public bind mount": 'pub_fstab="$SOURCE_PUB $PUB none bind 0 0"',
    "host permissions must create CI-OS app user": "useradd --system",
    "host permissions must add app user to Hermes group": 'usermod -aG "$HERMES_GROUP" "$APP_USER"',
    "host permissions must manage Hermes cron wrapper": 'ROOT_WRAPPER="${CIOS_ROOT_WRAPPER:-/root/.hermes/scripts/cios-daily.sh}"',
    "host permissions must manage host env copy": 'HOST_ENV_FILE="${CIOS_HOST_ENV_FILE:-/etc/cios-env}"',
    "host permissions must know CI-OS shim user": 'SHIM_USER="${CIOS_SHIM_USER:-cios-shim}"',
    "host permissions must prefer ACL traversal for cios": 'setfacl -m "u:$APP_USER:--x,m:--x" /root/.hermes /root/.hermes/apps',
    "host permissions must grant shim ACL traversal when present": 'setfacl -m "u:$SHIM_USER:--x,m:--x" /root/.hermes /root/.hermes/apps',
    "host permissions must preserve execute-only Hermes traversal fallback": "chmod 711 /root/.hermes /root/.hermes/apps",
    "host permissions must chown source app and public trees to app user": 'chown -R "$APP_USER:$HERMES_GROUP" "$SOURCE_APP" "$SOURCE_PUB"',
    "host permissions must keep request queue setgid and sticky": 'chmod 3770 "$APP/run-queue"',
    "host permissions must make active state private to cios": 'chown "$APP_USER:$APP_USER" "$APP/run-queue/.state"',
    "host permissions must protect active state permissions": 'chmod 700 "$APP/run-queue/.state"',
    "host permissions must create app-owned product-market workdir": 'PRODUCT_MARKET_WORKDIR="${CIOS_PRODUCT_MARKET_WORKDIR:-$APP/tmp/product-market}"',
    "host permissions must repair legacy product-market tmp ownership": 'LEGACY_PRODUCT_MARKET_TMP="${CIOS_LEGACY_PRODUCT_MARKET_TMP:-/tmp/cios-product-market}"',
    "host permissions must make Hermes cron wrapper group executable": 'chown "$APP_USER:$HERMES_GROUP" "$ROOT_WRAPPER"',
    "host permissions must protect Hermes CI-OS env file": 'chmod 640 "$ENV_FILE"',
    "host permissions must install host-readable CI-OS env file": 'install -o "$APP_USER" -g "$HERMES_GROUP" -m 0640 "$ENV_FILE" "$HOST_ENV_FILE"',
    "host permissions must protect run finalizer for cios only": 'chmod 700 "$APP/deploy/cios-run-finalize.sh"',
    "host permissions must install executable secure queue helper": 'chmod 755 "$APP/scripts/cios_run_queue.py"',
    "host permissions must make app body cios-private": 'chown "$APP_USER:$APP_USER" "$APP/deploy/cios-daily-app.sh"',
    "host permissions must make host runner cios-private": 'chmod 700 "$APP/deploy/cios-host-runner.sh"',
    "host permissions must remove group write from code trees": 'chmod -R g-w,o-w "$code_dir"',
}

RUNNER_SERVICE_INVARIANTS = {
    "runner service must use executable service type": "Type=exec",
    "runner service must run as cios user": "User=cios",
    "runner service must run as cios group": "Group=cios",
    "runner service must include hermes supplementary group": "SupplementaryGroups=hermes",
    "runner service must use /opt CI-OS app working directory": "WorkingDirectory=/opt/cios/app",
    "runner service must set /opt CI-OS app directory": "Environment=CIOS_APP_DIR=/opt/cios/app",
    "runner service must set /opt CI-OS public directory": "Environment=CIOS_PUBLIC_DIR=/opt/cios/public",
    "runner service must use host-readable CI-OS env file": "Environment=CIOS_ENV_FILE=/etc/cios-env",
    "runner service must call /opt host runner": "ExecStart=/opt/cios/app/deploy/cios-host-runner.sh",
    "runner service must finalize after cgroup cleanup": "ExecStopPost=/opt/cios/app/deploy/cios-run-finalize.sh",
    "runner service must require command cgroups": "Environment=CIOS_REQUIRE_CGROUP_CONTAINMENT=1",
    "runner service must name supervisor subgroup": "Environment=CIOS_CGROUP_SUPERVISOR_SUBGROUP=supervisor",
    "runner service must delegate cgroup subtree": "Delegate=yes",
    "runner service must place main process in supervisor subgroup": "DelegateSubgroup=supervisor",
    "runner service must kill the full run cgroup": "KillMode=control-group",
    "runner service must enforce a runtime ceiling": "RuntimeMaxSec=",
    "runner service must bound stop cleanup": "TimeoutStopSec=",
    "runner service must keep no-new-privileges enabled": "NoNewPrivileges=true",
    "runner service must keep group-writable artifacts": "UMask=0007",
}

RUNNER_PATH_INVARIANTS = {
    "runner path must watch /opt request files": "PathExistsGlob=/opt/cios/app/run-queue/*.request",
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
    "admin service must load host-readable CI-OS env file": "--env-file /etc/cios-env",
    "admin service must use the expected local admin port": "--port 8765",
    "admin service must use /opt CI-OS app working directory": "WorkingDirectory=/opt/cios/app",
    "admin service must set /opt CI-OS app directory": "Environment=CIOS_APP_DIR=/opt/cios/app",
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
    "product-surface executor missing process-group supervision": "start_new_session=True",
    "product-surface executor missing contained process spawn": "PROCESS_GROUPS.spawn",
    "product-surface executor missing batch deadline": "batch_timeout_seconds",
    "product-surface executor missing not-started accounting": "not_started",
    "product-surface executor missing sensitive-error redaction": "redact_sensitive_text",
    "product-surface executor missing worker hard cap": "MAX_PRODUCT_SURFACE_WORKERS",
}

PRODUCT_SURFACE_EXECUTION_CLI_INVARIANTS = {
    "product-surface executor CLI missing batch deadline option": "--batch-timeout-seconds",
    "product-surface executor CLI missing shutdown handlers": "install_shutdown_handlers",
}

PROCESS_SUPERVISOR_INVARIANTS = {
    "process supervisor missing process-group termination": "os.killpg",
    "process supervisor missing active-process shutdown": "terminate_all",
    "process supervisor missing delegated cgroup backend": "CgroupV2Backend",
    "process supervisor missing atomic cgroup kill": "cgroup.kill",
    "process supervisor missing launch-before-exec containment": "cgroup_launcher",
}

DAILY_RUNTIME_SECURITY_INVARIANTS = {
    "daily runtime missing sensitive-error redaction": "redact_sensitive_text",
    "daily runtime missing contained process spawn": "PROCESS_GROUPS.spawn",
    "daily runtime missing process-group termination": "PROCESS_GROUPS.terminate",
    "daily runtime missing shutdown-handler installation": "install_shutdown_handlers()",
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

PROCESS_SUPERVISION_PROBE = r'''
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from cios.platform.process_supervisor import PROCESS_GROUPS

child_code = r"""
import signal
import sys
import time
from pathlib import Path

signal.signal(signal.SIGTERM, signal.SIG_IGN)
time.sleep(0.8)
Path(sys.argv[1]).write_text("survived", encoding="utf-8")
"""

parent_code = r"""
import subprocess
import sys
import time
from pathlib import Path

def spawn_detached():
    subprocess.Popen(
        [sys.executable, "-c", sys.argv[1], sys.argv[2]],
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

spawn_detached()
Path(sys.argv[3]).write_text("ready", encoding="utf-8")
deadline = time.monotonic() + 5
while time.monotonic() < deadline:
    spawn_detached()
    time.sleep(0.01)
"""

with tempfile.TemporaryDirectory(prefix="cios-process-probe-") as temp_dir:
    if not PROCESS_GROUPS.cgroup_enabled:
        raise SystemExit(4)
    marker = Path(temp_dir) / "detached-survivor"
    ready = Path(temp_dir) / "ready"
    parent = PROCESS_GROUPS.spawn(
        [sys.executable, "-c", parent_code, child_code, str(marker), str(ready)],
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 1.0
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        if not ready.exists():
            PROCESS_GROUPS.terminate(parent)
            raise SystemExit(3)
        PROCESS_GROUPS.terminate(parent)
    finally:
        PROCESS_GROUPS.unregister(parent)
    time.sleep(1.0)
    raise SystemExit(2 if marker.exists() else 0)
'''


def collect_path_errors(app_dir: Path) -> list[str]:
    errors: list[str] = []
    for rel in REQUIRED_PATHS:
        if not (app_dir / rel).exists():
            errors.append(f"missing required path: {rel}")
    return errors


def collect_wrapper_errors(app_dir: Path) -> list[str]:
    wrapper_path = app_dir / "deploy" / "cios-daily.sh"
    app_wrapper_path = app_dir / "deploy" / "cios-daily-app.sh"
    if not wrapper_path.exists() or not app_wrapper_path.exists():
        return []
    public_text = wrapper_path.read_text(encoding="utf-8")
    text = public_text + "\n" + app_wrapper_path.read_text(encoding="utf-8")
    errors = [message for message, needle in WRAPPER_INVARIANTS.items() if needle not in text]
    errors.extend(
        message for message, needle in PUBLIC_WRAPPER_INVARIANTS.items() if needle not in public_text
    )
    forbidden = (
        "CIOS_APP_DIR",
        "CIOS_PUBLIC_DIR",
        "CIOS_RUNNER_QUEUE_DIR",
        "CIOS_PYTHON_BIN",
        "CIOS_RUN_QUEUE_HELPER",
        "CIOS_APP_USER",
        "CIOS_RUNNER_HANDOFF",
        "CIOS_DISABLE_RUNNER_HANDOFF",
    )
    if any(name in public_text for name in forbidden):
        errors.append("wrapper permits caller-controlled execution paths")
    if 'cat "$log"' in public_text or 'tail -120 "$log"' in public_text:
        errors.append("wrapper exposes unredacted runner logs")
    return errors


def collect_host_runner_errors(app_dir: Path) -> list[str]:
    errors = collect_text_invariant_errors(
        app_dir,
        rel_path="deploy/cios-host-runner.sh",
        invariants=HOST_RUNNER_INVARIANTS,
    )
    path = app_dir / "deploy/cios-host-runner.sh"
    forbidden = ("CIOS_APP_DIR", "CIOS_PUBLIC_DIR", "CIOS_RUNNER_QUEUE_DIR", "CIOS_PYTHON_BIN", "CIOS_RUN_QUEUE_HELPER")
    if path.exists() and any(name in path.read_text(encoding="utf-8") for name in forbidden):
        errors.append("host runner permits caller-controlled execution paths")
    return errors


def collect_run_finalizer_errors(app_dir: Path) -> list[str]:
    errors = collect_text_invariant_errors(
        app_dir,
        rel_path="deploy/cios-run-finalize.sh",
        invariants=RUN_FINALIZER_INVARIANTS,
    )
    path = app_dir / "deploy/cios-run-finalize.sh"
    forbidden = ("CIOS_APP_DIR", "CIOS_PUBLIC_DIR", "CIOS_RUNNER_QUEUE_DIR", "CIOS_PYTHON_BIN", "CIOS_RUN_QUEUE_HELPER")
    if path.exists() and any(name in path.read_text(encoding="utf-8") for name in forbidden):
        errors.append("run finalizer permits caller-controlled execution paths")
    return errors


def collect_run_queue_errors(app_dir: Path) -> list[str]:
    return collect_text_invariant_errors(
        app_dir,
        rel_path="scripts/cios_run_queue.py",
        invariants=RUN_QUEUE_INVARIANTS,
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
    checks = (
        (
            "src/cios/intelligence/product_surface_executor.py",
            PRODUCT_SURFACE_EXECUTION_INVARIANTS,
        ),
        (
            "scripts/execute_product_surface_plan.py",
            PRODUCT_SURFACE_EXECUTION_CLI_INVARIANTS,
        ),
        ("src/cios/platform/process_supervisor.py", PROCESS_SUPERVISOR_INVARIANTS),
        ("scripts/daily_production_run.py", DAILY_RUNTIME_SECURITY_INVARIANTS),
    )
    errors: list[str] = []
    for rel_path, invariants in checks:
        errors.extend(
            collect_text_invariant_errors(
                app_dir,
                rel_path=rel_path,
                invariants=invariants,
            )
        )
    return errors


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


def collect_process_supervision_runtime_errors(app_dir: Path) -> list[str]:
    python_bin = app_dir / ".venv" / "bin" / "python"
    if not python_bin.exists():
        return []

    env = os.environ.copy()
    env["PYTHONPATH"] = str(app_dir / "src")
    try:
        completed = subprocess.run(
            [str(python_bin), "-c", PROCESS_SUPERVISION_PROBE],
            text=True,
            capture_output=True,
            env=env,
            timeout=5,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return ["process supervision self-test failed: runtime probe timed out"]
    if completed.returncode == 0:
        return []
    if completed.returncode == 2:
        return ["process supervision self-test failed: detached descendant survived cleanup"]
    if completed.returncode == 4:
        return ["process supervision self-test failed: delegated cgroup v2 unavailable"]
    return ["process supervision self-test failed: runtime probe error"]


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
        errors.extend(collect_run_finalizer_errors(app_dir))
        errors.extend(collect_run_queue_errors(app_dir))
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
            errors.extend(collect_process_supervision_runtime_errors(app_dir))
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
