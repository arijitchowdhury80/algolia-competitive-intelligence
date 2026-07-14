"""Tests for the CI-OS Hermes package preflight checker."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify_hermes_package_contract.py"


REQUIRED_FILES = [
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
    "src/cios/admin/learning_apply.py",
    "src/cios/admin/demand_imports.py",
    "src/cios/admin/dashboard_refresh.py",
    "src/cios/db/repos/product_market.py",
    "src/cios/intelligence/product_surface_executor.py",
    "src/cios/platform/process_supervisor.py",
    "src/cios/platform/cgroup_launcher.py",
    "src/cios/platform/redaction.py",
]

REQUIRED_DIRS = [
    "src/cios/intelligence",
    "src/cios/admin",
]

SAFE_ADMIN_SERVICE = """[Unit]
Description=CI-OS local admin (localhost-only)
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/cios/app
Environment=CIOS_APP_DIR=/opt/cios/app
User=cios
Group=cios
ExecStart=/opt/cios/app/.venv/bin/python /opt/cios/app/scripts/run_admin.py --env-file /etc/cios-env --host 127.0.0.1 --port 8765
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=false

[Install]
WantedBy=multi-user.target
"""


SAFE_WRAPPER = """#!/bin/sh
export PYTHONPATH="$APP/src${PYTHONPATH:+:$PYTHONPATH}"
export CIOS_ENABLE_PRODUCT_MARKET_INTELLIGENCE="${CIOS_ENABLE_PRODUCT_MARKET_INTELLIGENCE:-1}"
export CIOS_PRODUCT_MARKET_EXPORT_BATCH_TIMEOUT_SECONDS="${CIOS_PRODUCT_MARKET_EXPORT_BATCH_TIMEOUT_SECONDS:-600}"
export CIOS_PRODUCT_MARKET_EXPORT_STAGE_TIMEOUT_SECONDS="${CIOS_PRODUCT_MARKET_EXPORT_STAGE_TIMEOUT_SECONDS:-630}"
export CIOS_PRODUCT_MARKET_WORKDIR="${CIOS_PRODUCT_MARKET_WORKDIR:-$APP/tmp/product-market}"
touch "$OUT/.cios-output-dir"
find "$OUT" -mindepth 1 ! -name .cios-output-dir -exec rm -rf -- {} +
.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir "$APP"
.venv/bin/python scripts/audit_learning_policies.py --package-root "$APP"
.venv/bin/python scripts/apply_product_market_schema.py
.venv/bin/python scripts/promote_product_surface_candidates.py --tenant "$CIOS_DELIVER_TENANT" --output "$OUT/product-surface-candidate-promotion-summary.json"
.venv/bin/python scripts/export_argus_demand_readiness.py --tenant "$CIOS_DELIVER_TENANT" --output "$OUT/argus-demand-readiness.json"
.venv/bin/python scripts/export_argus_demand_plan_template.py --readiness "$OUT/argus-demand-readiness.json" --output "$OUT/argus-demand-plan-template.csv"
.venv/bin/python scripts/run_argus_demand_intake.py --tenant "$CIOS_DELIVER_TENANT" --record-history --output "$OUT/argus-demand-intake.json"
.venv/bin/python scripts/attach_post_run_summaries.py --dashboard "$OUT/argus-dashboard.json" --demand-readiness "$OUT/argus-demand-readiness.json"
.venv/bin/python scripts/rerender_dashboard.py --tenant "$CIOS_DELIVER_TENANT" --out-dir "$OUT"
.venv/bin/python scripts/export_argus_evidence_work_queue.py --tenant "$CIOS_DELIVER_TENANT" --output "$OUT/argus-evidence-work-queue.json"
.venv/bin/python scripts/export_argus_product_muscle_work_queue.py --tenant "$CIOS_DELIVER_TENANT" --output "$OUT/argus-product-muscle-work-queue.json"
.venv/bin/python scripts/build_argus_operator_handoff.py --tenant "$CIOS_DELIVER_TENANT" --work-queue "$OUT/argus-evidence-work-queue.json" --product-muscle-queue "$OUT/argus-product-muscle-work-queue.json" --dashboard "$OUT/argus-dashboard.json" --output "$OUT/argus-operator-handoff.json"
.venv/bin/python scripts/attach_operator_handoff_to_dashboard.py --dashboard "$OUT/argus-dashboard.json" --handoff "$OUT/argus-operator-handoff.json" --html "$CIOS_DASHBOARD_OUT"
.venv/bin/python scripts/export_argus_data_plane_manifest.py --tenant "$CIOS_DELIVER_TENANT" --dashboard "$OUT/argus-dashboard.json" --demand-readiness "$OUT/argus-demand-readiness.json" --demand-plan-template "$OUT/argus-demand-plan-template.csv" --demand-intake "$OUT/argus-demand-intake.json" --evidence-work-queue "$OUT/argus-evidence-work-queue.json" --product-muscle-work-queue "$OUT/argus-product-muscle-work-queue.json" --operator-handoff "$OUT/argus-operator-handoff.json" --output "$OUT/argus-data-plane-manifest.json"
.venv/bin/python scripts/export_public_run_status.py --tenant "$CIOS_DELIVER_TENANT" --manifest "$OUT/argus-data-plane-manifest.json" --dashboard "$OUT/argus-dashboard.json" --publish-status blocked --output "$OUT/argus-public-run-status.json"
cp "$OUT/argus-public-run-status.json" "$PUB/data/argus-latest-run-status.json"
if [ ! -s "$CIOS_DASHBOARD_OUT" ]; then
  echo "missing dashboard artifact from current run" >&2
  exit 2
fi
STAGE="$PUB/.argus-publish.$$"
mkdir -p "$STAGE"
"""


SAFE_HANDOFF_WRAPPER = """#!/bin/sh
current_user="$(/usr/bin/id -un)"
if [ "$current_user" = "cios" ]; then
  exec "$APP/deploy/cios-daily-app.sh"
fi
queue_dir="${CIOS_RUNNER_QUEUE_DIR:-/opt/cios/app/run-queue}"
wait_seconds="${CIOS_RUNNER_WAIT_SECONDS:-1800}"
"$queue_helper" enqueue
"$queue_helper" read-result
"""


SAFE_HOST_RUNNER = """#!/bin/sh
APP="${CIOS_APP_DIR:-/opt/cios/app}"
PUB="${CIOS_PUBLIC_DIR:-/opt/cios/public}"
HELPER="$APP/scripts/cios_run_queue.py"
"$HELPER" run-one
"""

SAFE_RUN_FINALIZER = """#!/bin/sh
service_result="${SERVICE_RESULT:-unknown}"
HELPER="$APP/scripts/cios_run_queue.py"
"$HELPER" finalize
"""


SAFE_RUN_QUEUE = '''#!/usr/bin/env python3
import os
import uuid
NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
os.replace
state = ".state"
request_id = uuid.uuid4().hex
def run_one():
    pass
code = 124 if timed_out else 2
status = "blocked_runtime_timeout"
'''


SAFE_HOST_PERMISSIONS = """#!/bin/sh
SOURCE_APP="${CIOS_SOURCE_APP_DIR:-/root/.hermes/apps/cios}"
SOURCE_PUB="${CIOS_SOURCE_PUBLIC_DIR:-/root/.hermes/apps/algolia-competitive-intelligence/apps/dashboard/public}"
APP="${CIOS_APP_DIR:-/opt/cios/app}"
PUB="${CIOS_PUBLIC_DIR:-/opt/cios/public}"
ENV_FILE="${CIOS_ENV_FILE:-/root/.hermes/cios-env}"
HOST_ENV_FILE="${CIOS_HOST_ENV_FILE:-/etc/cios-env}"
ROOT_WRAPPER="${CIOS_ROOT_WRAPPER:-/root/.hermes/scripts/cios-daily.sh}"
APP_USER="${CIOS_APP_USER:-cios}"
SHIM_USER="${CIOS_SHIM_USER:-cios-shim}"
HERMES_GROUP="${CIOS_HERMES_GROUP:-hermes}"
useradd --system --home-dir "/var/lib/$APP_USER" --shell /usr/sbin/nologin "$APP_USER"
usermod -aG "$HERMES_GROUP" "$APP_USER"
usermod -aG "$HERMES_GROUP" "$SHIM_USER"
setfacl -m "u:$APP_USER:--x,m:--x" /root/.hermes /root/.hermes/apps
setfacl -m "u:$SHIM_USER:--x,m:--x" /root/.hermes /root/.hermes/apps
mount --bind "$SOURCE_APP" "$APP"
mount --bind "$SOURCE_PUB" "$PUB"
app_fstab="$SOURCE_APP $APP none bind 0 0"
pub_fstab="$SOURCE_PUB $PUB none bind 0 0"
chmod 711 /root/.hermes /root/.hermes/apps
chown -R "$APP_USER:$HERMES_GROUP" "$SOURCE_APP" "$SOURCE_PUB"
chmod 3770 "$APP/run-queue"
chown "$APP_USER:$APP_USER" "$APP/run-queue/.state"
chmod 700 "$APP/run-queue/.state"
PRODUCT_MARKET_WORKDIR="${CIOS_PRODUCT_MARKET_WORKDIR:-$APP/tmp/product-market}"
LEGACY_PRODUCT_MARKET_TMP="${CIOS_LEGACY_PRODUCT_MARKET_TMP:-/tmp/cios-product-market}"
chown "$APP_USER:$HERMES_GROUP" "$ROOT_WRAPPER"
chmod 640 "$ENV_FILE"
install -o "$APP_USER" -g "$HERMES_GROUP" -m 0640 "$ENV_FILE" "$HOST_ENV_FILE"
chmod 755 "$APP/deploy/cios-run-finalize.sh"
chmod 755 "$APP/scripts/cios_run_queue.py"
chown "$APP_USER:$APP_USER" "$APP/deploy/cios-daily-app.sh"
"""


SAFE_RUNNER_SERVICE = """[Unit]
Description=CI-OS app-user daily runner

[Service]
Type=exec
User=cios
Group=cios
SupplementaryGroups=hermes
WorkingDirectory=/opt/cios/app
Environment=CIOS_APP_DIR=/opt/cios/app
Environment=CIOS_PUBLIC_DIR=/opt/cios/public
Environment=CIOS_ENV_FILE=/etc/cios-env
Environment=CIOS_REQUIRE_CGROUP_CONTAINMENT=1
Environment=CIOS_CGROUP_SUPERVISOR_SUBGROUP=supervisor
ExecStart=/opt/cios/app/deploy/cios-host-runner.sh
ExecStopPost=/opt/cios/app/deploy/cios-run-finalize.sh
Delegate=yes
DelegateSubgroup=supervisor
KillMode=control-group
RuntimeMaxSec=25min
TimeoutStopSec=15s
NoNewPrivileges=true
UMask=0007
"""


SAFE_RUNNER_PATH = """[Unit]
Description=Watch for CI-OS app-user runner requests

[Path]
PathExistsGlob=/opt/cios/app/run-queue/*.request
Unit=cios-runner.service
"""


SAFE_CLAUDE_SHIM_SERVICE = """[Unit]
Description=CI-OS Claude CLI shim (localhost-only)
After=network.target

[Service]
Type=simple
User=cios-shim
Group=cios-shim
SupplementaryGroups=hermes
WorkingDirectory=/opt/cios/claude-shim
EnvironmentFile=/etc/cios-claude-shim.env
ExecStart=/opt/cios/claude-shim/.venv/bin/uvicorn shim:app --host 127.0.0.1 --port 8663
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
"""


SAFE_DEMAND_FAST_LANE = """
def _refresh_post_rerender_artifacts():
    demand_readiness = out_dir / "argus-demand-readiness.json"
    demand_plan_template = out_dir / "argus-demand-plan-template.csv"
    commands = [
        [
            python,
            str(_script_dir() / "export_argus_demand_plan_template.py"),
            "--readiness",
            str(demand_readiness),
            "--output",
            str(demand_plan_template),
        ],
    ]
"""


SAFE_ADMIN_DASHBOARD_REFRESH = """
def _refresh_argus_sidecars():
    demand_readiness = out_dir / "argus-demand-readiness.json"
    demand_plan_template = out_dir / "argus-demand-plan-template.csv"
    steps = [
        [
            python_bin,
            str(scripts / "export_argus_demand_plan_template.py"),
            "--readiness",
            str(demand_readiness),
            "--output",
            str(demand_plan_template),
        ],
    ]
"""


SAFE_OPERATOR_HANDOFF_BUILDER = """
parser.add_argument("--demand-plan-template")
payload = {"demand_plan_template": {"filename": "argus-demand-plan-template.csv"}}
"""


SAFE_GA4_EXPORT_SCRIPT = """
parser.add_argument("--demand-plan")
payload = {"argus_demand_plan": summarize_ga4_demand_plan_coverage([], [])}
"""


SAFE_DEMAND_INTAKE = """
readiness = {"demand_collection_plan": {}}
control.run("algolia", demand_plan=demand_plan)
"""


SAFE_DAILY_RUNTIME = """
from cios.platform.redaction import redact_sensitive_text
from cios.platform.process_supervisor import PROCESS_GROUPS, install_shutdown_handlers
process = PROCESS_GROUPS.spawn(command, start_new_session=True)
PROCESS_GROUPS.terminate(process)
install_shutdown_handlers()
safe_error = redact_sensitive_text(stderr)
"""


SAFE_PRODUCT_SURFACE_EXECUTOR = """
from cios.platform.redaction import redact_sensitive_text
MAX_PRODUCT_SURFACE_WORKERS = 8
process = PROCESS_GROUPS.spawn(command, start_new_session=True)
batch_timeout_seconds = 600
safe_error = redact_sensitive_text(stderr)
summary = {
    "product_row_count": 1,
    "empty_scout_paths": [],
    "product_plane_status": "ready",
    "not_started": 0,
}
"""


SAFE_PRODUCT_SURFACE_EXECUTOR_CLI = """
parser.add_argument("--batch-timeout-seconds")
install_shutdown_handlers()
"""


SAFE_PROCESS_SUPERVISOR = """
class CgroupV2Backend:
    pass
cgroup_kill = "cgroup.kill"
cgroup_launcher = "cios.platform.cgroup_launcher"
os.killpg(process.pid, signal.SIGTERM)
PROCESS_GROUPS.terminate_all()
"""


SAFE_PRODUCT_SURFACE_PLANNER = """
parser.add_argument("--company-name")
parser.add_argument("--company-id")
parser.add_argument("--surface-id")
parser.add_argument("--limit", type=int)
"""


SAFE_PRODUCT_SURFACE_EXTRACTION_CONTROL = """
scout_bin = os.environ.get("CIOS_SCOUT_BIN") or str(scripts / "scout_http_shim")
provider = os.environ.get("CIOS_PRODUCT_MARKET_PROVIDER", "gemini/gemini-2.5-flash")
plan_command = [python, "plan_product_surface_exports.py", "--company-name", company_name, "--limit", "1"]
execute_command = [python, "execute_product_surface_plan.py", "--summary-output", summary_path]
"""


SAFE_PRODUCT_SURFACE_CANDIDATE_PROMOTION_CONTROL = """
command = [python, "promote_product_surface_candidates.py", "--company-name", company_name, "--surface-family", surface_family, "--limit", "1"]
"""


SAFE_PRODUCT_MUSCLE_WORK_QUEUE_ADMIN = """
action = {
    "primary_label": "Run surface extraction",
    "candidate_primary_label": "Promote candidate surface",
    "primary_href": "/admin/algolia/argus/product-surface-extraction?company_name=Klevu",
    "candidate_primary_href": "/admin/algolia/argus/product-surface-candidates/promote?company_name=Klevu&limit=1",
    "primary_method": "post",
}
"""


SAFE_ADMIN_APP = """
from cios.admin.product_surface_extraction import ProductSurfaceExtractionControl
from cios.admin.product_surface_candidates import ProductSurfaceCandidatePromotionControl

@app.post("/api/tenants/{tenant_slug}/argus/product-surface-extraction")
def run_argus_product_surface_extraction():
    pass

@app.post("/api/tenants/{tenant_slug}/argus/product-surface-candidates/promote")
def promote_argus_product_surface_candidates():
    pass

@app.post("/admin/{tenant_slug}/argus/product-surface-extraction")
def run_product_surface_extraction_form():
    pass

@app.post("/admin/{tenant_slug}/argus/product-surface-candidates/promote")
def promote_product_surface_candidates_form():
    pass
"""


def _make_app(
    tmp_path: Path,
    *,
    wrapper: str = SAFE_WRAPPER,
    include_intelligence: bool = True,
    include_demand_imports: bool = True,
    include_demand_plan_template: bool = True,
    include_demand_fast_lane: bool = True,
    include_demand_intake: bool = True,
    include_admin_runner: bool = True,
    include_candidate_promotion: bool = True,
    include_product_surface_executor: bool = True,
    include_product_surface_extraction_admin: bool = True,
    include_product_surface_candidate_promotion_admin: bool = True,
    include_product_surface_repair_runner: bool = True,
    include_evidence_work_queue_export: bool = True,
    include_product_muscle_work_queue_export: bool = True,
    include_operator_handoff_builder: bool = True,
    include_operator_handoff_attach: bool = True,
    include_data_plane_manifest_export: bool = True,
    include_learning_apply_plan: bool = True,
    include_learning_apply_executor: bool = True,
    include_learning_policy_audit: bool = True,
    include_learning_apply_admin: bool = True,
    include_data_plane_manifest_admin: bool = True,
    include_product_muscle_work_queue_admin: bool = True,
    include_admin_app: bool = True,
    include_product_surface_repair_admin: bool = True,
    include_admin_service: bool = True,
    admin_service: str = SAFE_ADMIN_SERVICE,
    host_runner: str = SAFE_HOST_RUNNER,
    host_permissions: str = SAFE_HOST_PERMISSIONS,
    runner_service: str = SAFE_RUNNER_SERVICE,
    runner_path: str = SAFE_RUNNER_PATH,
    claude_shim_service: str = SAFE_CLAUDE_SHIM_SERVICE,
    demand_fast_lane: str = SAFE_DEMAND_FAST_LANE,
    admin_dashboard_refresh: str = SAFE_ADMIN_DASHBOARD_REFRESH,
    operator_handoff_builder: str = SAFE_OPERATOR_HANDOFF_BUILDER,
    ga4_export_script: str = SAFE_GA4_EXPORT_SCRIPT,
    demand_intake: str = SAFE_DEMAND_INTAKE,
    daily_runtime: str = SAFE_DAILY_RUNTIME,
    product_surface_executor: str = SAFE_PRODUCT_SURFACE_EXECUTOR,
    product_surface_planner: str = SAFE_PRODUCT_SURFACE_PLANNER,
    product_surface_extraction_control: str = SAFE_PRODUCT_SURFACE_EXTRACTION_CONTROL,
    product_surface_candidate_promotion_control: str = SAFE_PRODUCT_SURFACE_CANDIDATE_PROMOTION_CONTROL,
    product_muscle_work_queue_admin: str = SAFE_PRODUCT_MUSCLE_WORK_QUEUE_ADMIN,
    admin_app: str = SAFE_ADMIN_APP,
) -> Path:
    app = tmp_path / "cios"
    for rel in REQUIRED_FILES:
        if rel == "src/cios/intelligence/product_surface_executor.py" and not include_intelligence:
            continue
        if rel == "scripts/build_learning_apply_plan.py" and not include_learning_apply_plan:
            continue
        if rel == "scripts/execute_learning_apply_plan.py" and not include_learning_apply_executor:
            continue
        if rel == "scripts/audit_learning_policies.py" and not include_learning_policy_audit:
            continue
        if rel == "src/cios/admin/learning_apply.py" and not include_learning_apply_admin:
            continue
        if rel == "src/cios/admin/data_plane_manifest.py" and not include_data_plane_manifest_admin:
            continue
        if rel == "src/cios/admin/product_muscle_work_queue.py" and not include_product_muscle_work_queue_admin:
            continue
        if rel == "src/cios/admin/product_surface_extraction.py" and not include_product_surface_extraction_admin:
            continue
        if (
            rel == "src/cios/admin/product_surface_candidates.py"
            and not include_product_surface_candidate_promotion_admin
        ):
            continue
        if rel == "src/cios/admin/app.py" and not include_admin_app:
            continue
        if rel == "src/cios/admin/product_surface_repair.py" and not include_product_surface_repair_admin:
            continue
        if rel == "src/cios/admin/demand_imports.py" and not include_demand_imports:
            continue
        if rel == "scripts/export_argus_demand_plan_template.py" and not include_demand_plan_template:
            continue
        if rel == "scripts/import_demand_and_refresh.py" and not include_demand_fast_lane:
            continue
        if rel == "scripts/run_argus_demand_intake.py" and not include_demand_intake:
            continue
        if rel == "scripts/run_admin.py" and not include_admin_runner:
            continue
        if rel == "scripts/promote_product_surface_candidates.py" and not include_candidate_promotion:
            continue
        if rel in {
            "scripts/execute_product_surface_plan.py",
            "src/cios/intelligence/product_surface_executor.py",
            "src/cios/platform/process_supervisor.py",
        } and not include_product_surface_executor:
            continue
        if rel == "scripts/run_product_surface_repair.py" and not include_product_surface_repair_runner:
            continue
        if rel == "scripts/export_argus_evidence_work_queue.py" and not include_evidence_work_queue_export:
            continue
        if rel == "scripts/export_argus_product_muscle_work_queue.py" and not include_product_muscle_work_queue_export:
            continue
        if rel == "scripts/build_argus_operator_handoff.py" and not include_operator_handoff_builder:
            continue
        if rel == "scripts/attach_operator_handoff_to_dashboard.py" and not include_operator_handoff_attach:
            continue
        if rel == "scripts/export_argus_data_plane_manifest.py" and not include_data_plane_manifest_export:
            continue
        path = app / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        content = "placeholder\n"
        if rel == "scripts/import_demand_and_refresh.py":
            content = demand_fast_lane
        elif rel == "scripts/export_ga4_demand.py":
            content = ga4_export_script
        elif rel == "scripts/run_argus_demand_intake.py":
            content = demand_intake
        elif rel == "scripts/daily_production_run.py":
            content = daily_runtime
        elif rel == "scripts/execute_product_surface_plan.py":
            content = SAFE_PRODUCT_SURFACE_EXECUTOR_CLI
        elif rel == "src/cios/intelligence/product_surface_executor.py":
            content = product_surface_executor
        elif rel == "src/cios/platform/process_supervisor.py":
            content = SAFE_PROCESS_SUPERVISOR
        elif rel == "src/cios/platform/redaction.py":
            content = "def redact_sensitive_text(text):\n    return text\n"
        elif rel == "scripts/plan_product_surface_exports.py":
            content = product_surface_planner
        elif rel == "scripts/build_argus_operator_handoff.py":
            content = operator_handoff_builder
        elif rel == "src/cios/admin/dashboard_refresh.py":
            content = admin_dashboard_refresh
        elif rel == "src/cios/admin/product_surface_extraction.py":
            content = product_surface_extraction_control
        elif rel == "src/cios/admin/product_surface_candidates.py":
            content = product_surface_candidate_promotion_control
        elif rel == "src/cios/admin/product_muscle_work_queue.py":
            content = product_muscle_work_queue_admin
        elif rel == "src/cios/admin/app.py":
            content = admin_app
        elif rel == "deploy/cios-host-runner.sh":
            content = host_runner
        elif rel == "deploy/cios-daily.sh":
            content = SAFE_HANDOFF_WRAPPER
        elif rel == "deploy/cios-daily-app.sh":
            content = wrapper
        elif rel == "deploy/cios-run-finalize.sh":
            content = SAFE_RUN_FINALIZER
        elif rel == "scripts/cios_run_queue.py":
            content = SAFE_RUN_QUEUE
        elif rel == "deploy/cios-host-permissions.sh":
            content = host_permissions
        elif rel == "deploy/cios-runner.service":
            content = runner_service
        elif rel == "deploy/cios-runner.path":
            content = runner_path
        elif rel == "deploy/claude-shim/cios-claude-shim.service":
            content = claude_shim_service
        path.write_text(content, encoding="utf-8")
    for rel in REQUIRED_DIRS:
        if rel == "src/cios/intelligence" and not include_intelligence:
            continue
        (app / rel).mkdir(parents=True, exist_ok=True)
        (app / rel / "__init__.py").write_text("", encoding="utf-8")
    (app / "deploy" / "cios-daily.sh").write_text(SAFE_HANDOFF_WRAPPER, encoding="utf-8")
    (app / "deploy" / "cios-daily-app.sh").write_text(wrapper, encoding="utf-8")
    if include_admin_service:
        (app / "deploy" / "cios-admin.service").write_text(admin_service, encoding="utf-8")
    return app


def _run_preflight(app: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--app-dir",
            str(app),
            "--skip-python-imports",
        ],
        text=True,
        capture_output=True,
        check=False,
    )


def _load_preflight_module():
    spec = importlib.util.spec_from_file_location("verify_hermes_package_contract", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_runtime_supervisor_app(tmp_path: Path, supervisor_source: str) -> Path:
    app = tmp_path / "runtime-supervisor-app"
    module_path = app / "src/cios/platform/process_supervisor.py"
    module_path.parent.mkdir(parents=True)
    module_path.write_text(supervisor_source, encoding="utf-8")
    (app / "src/cios/__init__.py").write_text("", encoding="utf-8")
    (app / "src/cios/platform/__init__.py").write_text("", encoding="utf-8")
    python_bin = app / ".venv/bin/python"
    python_bin.parent.mkdir(parents=True)
    python_bin.symlink_to(sys.executable)
    return app


def _run_preflight_with_scout(app: Path, scout_bin: str, *, path: str = "") -> subprocess.CompletedProcess[str]:
    env = {"PATH": path}
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--app-dir",
            str(app),
            "--skip-python-imports",
            "--require-scout",
            "--scout-bin",
            scout_bin,
        ],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def _run_preflight_with_test_deps(app: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--app-dir",
            str(app),
            "--skip-python-imports",
            "--require-test-deps",
        ],
        text=True,
        capture_output=True,
        check=False,
    )


def test_preflight_passes_complete_hermes_package_contract(tmp_path):
    app = _make_app(tmp_path)

    result = _run_preflight(app)

    assert result.returncode == 0, result.stderr + result.stdout
    assert "PASS: CI-OS Hermes package contract satisfied" in result.stdout


def test_preflight_fails_when_intelligence_package_missing(tmp_path):
    app = _make_app(tmp_path, include_intelligence=False)

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "missing required path: src/cios/intelligence" in result.stderr


def test_preflight_fails_when_admin_demand_imports_missing(tmp_path):
    app = _make_app(tmp_path, include_demand_imports=False)

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "missing required path: src/cios/admin/demand_imports.py" in result.stderr


def test_preflight_fails_when_demand_plan_template_export_missing(tmp_path):
    app = _make_app(tmp_path, include_demand_plan_template=False)

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "missing required path: scripts/export_argus_demand_plan_template.py" in result.stderr


def test_preflight_fails_when_launch_readiness_gate_missing(tmp_path):
    app = _make_app(tmp_path)
    (app / "scripts" / "check_e2e_launch_readiness.py").unlink()

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "missing required path: scripts/check_e2e_launch_readiness.py" in result.stderr


def test_preflight_fails_when_e2e_validation_plan_missing(tmp_path):
    app = _make_app(tmp_path)
    (app / "docs" / "plan" / "e2e-validation.md").unlink()

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "missing required path: docs/plan/e2e-validation.md" in result.stderr


def test_preflight_fails_when_manual_fast_lane_omits_demand_plan_template_export(tmp_path):
    app = _make_app(
        tmp_path,
        demand_fast_lane=SAFE_DEMAND_FAST_LANE.replace(
            "export_argus_demand_plan_template.py",
            "export_argus_demand_readiness.py",
        ),
    )

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "manual demand fast lane missing demand plan template export" in result.stderr


def test_preflight_fails_when_manual_fast_lane_omits_demand_plan_template_artifact(tmp_path):
    app = _make_app(
        tmp_path,
        demand_fast_lane=SAFE_DEMAND_FAST_LANE.replace(
            "argus-demand-plan-template.csv",
            "argus-demand-readiness.json",
        ),
    )

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "manual demand fast lane missing demand plan template artifact" in result.stderr


def test_preflight_fails_when_admin_refresh_omits_demand_plan_template_export(tmp_path):
    app = _make_app(
        tmp_path,
        admin_dashboard_refresh=SAFE_ADMIN_DASHBOARD_REFRESH.replace(
            "export_argus_demand_plan_template.py",
            "export_argus_demand_readiness.py",
        ),
    )

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "admin refresh missing demand plan template export" in result.stderr


def test_preflight_fails_when_admin_refresh_omits_demand_plan_template_artifact(tmp_path):
    app = _make_app(
        tmp_path,
        admin_dashboard_refresh=SAFE_ADMIN_DASHBOARD_REFRESH.replace(
            "argus-demand-plan-template.csv",
            "argus-demand-readiness.json",
        ),
    )

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "admin refresh missing demand plan template artifact" in result.stderr


def test_preflight_fails_when_admin_runner_missing(tmp_path):
    app = _make_app(tmp_path, include_admin_runner=False)

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "missing required path: scripts/run_admin.py" in result.stderr


def test_preflight_fails_when_admin_service_missing(tmp_path):
    app = _make_app(tmp_path, include_admin_service=False)

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "missing required path: deploy/cios-admin.service" in result.stderr


def test_preflight_fails_when_admin_service_binds_publicly(tmp_path):
    app = _make_app(
        tmp_path,
        admin_service=SAFE_ADMIN_SERVICE.replace("--host 127.0.0.1", "--host 0.0.0.0"),
    )

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "admin service must bind to 127.0.0.1 only" in result.stderr


def test_preflight_fails_when_admin_service_skips_env_file(tmp_path):
    app = _make_app(
        tmp_path,
        admin_service=SAFE_ADMIN_SERVICE.replace(" --env-file /etc/cios-env", ""),
    )

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "admin service must load host-readable CI-OS env file" in result.stderr


def test_preflight_fails_when_admin_service_private_tmp_hides_hermes_artifacts(tmp_path):
    app = _make_app(
        tmp_path,
        admin_service=SAFE_ADMIN_SERVICE.replace("PrivateTmp=false", "PrivateTmp=true"),
    )

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "admin service must read Hermes product-market artifacts" in result.stderr


def test_preflight_fails_when_demand_fast_lane_missing(tmp_path):
    app = _make_app(tmp_path, include_demand_fast_lane=False)

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "missing required path: scripts/import_demand_and_refresh.py" in result.stderr


def test_preflight_fails_when_demand_intake_coordinator_missing(tmp_path):
    app = _make_app(tmp_path, include_demand_intake=False)

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "missing required path: scripts/run_argus_demand_intake.py" in result.stderr


def test_preflight_fails_when_ga4_export_omits_demand_plan_input(tmp_path):
    app = _make_app(
        tmp_path,
        ga4_export_script=SAFE_GA4_EXPORT_SCRIPT.replace('parser.add_argument("--demand-plan")', ""),
    )

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "ga4 export missing demand-plan CLI input" in result.stderr


def test_preflight_fails_when_demand_intake_omits_ga4_plan_handoff(tmp_path):
    app = _make_app(
        tmp_path,
        demand_intake=SAFE_DEMAND_INTAKE.replace("demand_plan=demand_plan", ""),
    )

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "demand intake missing demand-plan handoff to GA4 export" in result.stderr


def test_preflight_fails_when_candidate_promotion_command_missing(tmp_path):
    app = _make_app(tmp_path, include_candidate_promotion=False)

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "missing required path: scripts/promote_product_surface_candidates.py" in result.stderr


def test_preflight_fails_when_product_surface_repair_runner_missing(tmp_path):
    app = _make_app(tmp_path, include_product_surface_repair_runner=False)

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "missing required path: scripts/run_product_surface_repair.py" in result.stderr


def test_preflight_fails_when_product_surface_executor_missing(tmp_path):
    app = _make_app(tmp_path, include_product_surface_executor=False)

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "missing required path: scripts/execute_product_surface_plan.py" in result.stderr


def test_preflight_fails_when_product_surface_executor_omits_row_quality_summary(tmp_path):
    app = _make_app(
        tmp_path,
        product_surface_executor=SAFE_PRODUCT_SURFACE_EXECUTOR.replace('"product_row_count": 1,', ""),
    )

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "product-surface executor missing row-count summary" in result.stderr


def test_preflight_fails_when_product_surface_executor_omits_process_group_supervision(tmp_path):
    app = _make_app(
        tmp_path,
        product_surface_executor=SAFE_PRODUCT_SURFACE_EXECUTOR.replace("start_new_session=True", "start_new_session=False"),
    )

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "product-surface executor missing process-group supervision" in result.stderr


def test_preflight_fails_when_product_surface_executor_omits_batch_deadline_accounting(tmp_path):
    app = _make_app(
        tmp_path,
        product_surface_executor=SAFE_PRODUCT_SURFACE_EXECUTOR.replace("batch_timeout_seconds", "batch_timeout_disabled"),
    )

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "product-surface executor missing batch deadline" in result.stderr


def test_preflight_fails_when_process_supervisor_omits_atomic_cgroup_kill(tmp_path):
    app = _make_app(tmp_path)
    supervisor = app / "src/cios/platform/process_supervisor.py"
    supervisor.write_text(
        SAFE_PROCESS_SUPERVISOR.replace("cgroup.kill", "unsafe_group_kill"),
        encoding="utf-8",
    )

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "process supervisor missing atomic cgroup kill" in result.stderr


def test_process_supervision_runtime_self_test_fails_closed_outside_delegated_service(tmp_path):
    module = _load_preflight_module()
    supervisor_source = (ROOT / "src/cios/platform/process_supervisor.py").read_text(
        encoding="utf-8"
    )
    app = _make_runtime_supervisor_app(tmp_path, supervisor_source)

    assert module.collect_process_supervision_runtime_errors(app) == [
        "process supervision self-test failed: delegated cgroup v2 unavailable"
    ]


def test_process_supervision_runtime_self_test_rejects_detached_descendant_escape(tmp_path):
    module = _load_preflight_module()
    unsafe_supervisor = """
import os
import signal

class UnsafeRegistry:
    cgroup_enabled = True

    def spawn(self, command, **kwargs):
        return __import__("subprocess").Popen(command, **kwargs)

    def unregister(self, process):
        pass

    def terminate(self, process):
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=1)

PROCESS_GROUPS = UnsafeRegistry()
"""
    app = _make_runtime_supervisor_app(tmp_path, unsafe_supervisor)

    assert module.collect_process_supervision_runtime_errors(app) == [
        "process supervision self-test failed: detached descendant survived cleanup"
    ]


def test_preflight_fails_when_runtime_redaction_module_missing(tmp_path):
    app = _make_app(tmp_path)
    (app / "src/cios/platform/redaction.py").unlink()

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "missing required path: src/cios/platform/redaction.py" in result.stderr


def test_preflight_fails_when_product_surface_executor_omits_error_redaction(tmp_path):
    app = _make_app(
        tmp_path,
        product_surface_executor=SAFE_PRODUCT_SURFACE_EXECUTOR.replace("redact_sensitive_text", "unsafe_error_text"),
    )

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "product-surface executor missing sensitive-error redaction" in result.stderr


def test_preflight_fails_when_product_surface_executor_omits_worker_hard_cap(tmp_path):
    app = _make_app(
        tmp_path,
        product_surface_executor=SAFE_PRODUCT_SURFACE_EXECUTOR.replace("MAX_PRODUCT_SURFACE_WORKERS", "UNBOUNDED_WORKERS"),
    )

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "product-surface executor missing worker hard cap" in result.stderr


def test_preflight_fails_when_daily_runtime_omits_error_redaction(tmp_path):
    app = _make_app(
        tmp_path,
        daily_runtime=SAFE_DAILY_RUNTIME.replace("redact_sensitive_text", "unsafe_error_text"),
    )

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "daily runtime missing sensitive-error redaction" in result.stderr


def test_preflight_fails_when_daily_runtime_omits_contained_spawn(tmp_path):
    app = _make_app(
        tmp_path,
        daily_runtime=SAFE_DAILY_RUNTIME.replace("PROCESS_GROUPS.spawn", "subprocess.Popen"),
    )

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "daily runtime missing contained process spawn" in result.stderr


def test_preflight_fails_when_product_surface_extraction_admin_control_missing(tmp_path):
    app = _make_app(tmp_path, include_product_surface_extraction_admin=False)

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "missing required path: src/cios/admin/product_surface_extraction.py" in result.stderr


def test_preflight_fails_when_product_surface_candidate_promotion_admin_control_missing(tmp_path):
    app = _make_app(tmp_path, include_product_surface_candidate_promotion_admin=False)

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "missing required path: src/cios/admin/product_surface_candidates.py" in result.stderr


def test_preflight_fails_when_product_surface_planner_omits_company_filters(tmp_path):
    app = _make_app(
        tmp_path,
        product_surface_planner=SAFE_PRODUCT_SURFACE_PLANNER.replace('parser.add_argument("--company-name")', ""),
    )

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "product-surface planner missing company-name filter" in result.stderr


def test_preflight_fails_when_product_surface_extraction_control_omits_scout_bridge_default(tmp_path):
    app = _make_app(
        tmp_path,
        product_surface_extraction_control=SAFE_PRODUCT_SURFACE_EXTRACTION_CONTROL.replace("scout_http_shim", "scout"),
    )

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "product-surface extraction control missing Scout bridge default" in result.stderr


def test_preflight_fails_when_product_surface_candidate_promotion_omits_company_filters(tmp_path):
    app = _make_app(
        tmp_path,
        product_surface_candidate_promotion_control=SAFE_PRODUCT_SURFACE_CANDIDATE_PROMOTION_CONTROL.replace(
            '"--company-name", company_name,',
            "",
        ),
    )

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "product-surface candidate promotion missing company-name filter" in result.stderr


def test_preflight_fails_when_product_muscle_queue_omits_first_run_extraction_action(tmp_path):
    app = _make_app(
        tmp_path,
        product_muscle_work_queue_admin=SAFE_PRODUCT_MUSCLE_WORK_QUEUE_ADMIN.replace(
            "Run surface extraction",
            "Open product surfaces",
        ),
    )

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "product muscle work queue missing first-run extraction action" in result.stderr


def test_preflight_fails_when_product_muscle_queue_omits_candidate_promotion_action(tmp_path):
    app = _make_app(
        tmp_path,
        product_muscle_work_queue_admin=SAFE_PRODUCT_MUSCLE_WORK_QUEUE_ADMIN.replace(
            "Promote candidate surface",
            "Open product surfaces",
        ),
    )

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "product muscle work queue missing candidate promotion action" in result.stderr


def test_preflight_fails_when_admin_app_omits_product_surface_extraction_route(tmp_path):
    app = _make_app(
        tmp_path,
        admin_app=SAFE_ADMIN_APP.replace("product-surface-extraction", "product-surface-repair"),
    )

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "admin app missing product-surface extraction route" in result.stderr


def test_preflight_fails_when_admin_app_omits_product_surface_candidate_promotion_route(tmp_path):
    app = _make_app(
        tmp_path,
        admin_app=SAFE_ADMIN_APP.replace("product-surface-candidates/promote", "product-surface-repair"),
    )

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "admin app missing product-surface candidate promotion route" in result.stderr


def test_preflight_fails_when_product_surface_repair_admin_control_missing(tmp_path):
    app = _make_app(tmp_path, include_product_surface_repair_admin=False)

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "missing required path: src/cios/admin/product_surface_repair.py" in result.stderr


def test_preflight_fails_when_evidence_work_queue_export_missing(tmp_path):
    app = _make_app(tmp_path, include_evidence_work_queue_export=False)

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "missing required path: scripts/export_argus_evidence_work_queue.py" in result.stderr


def test_preflight_fails_when_product_muscle_work_queue_export_missing(tmp_path):
    app = _make_app(tmp_path, include_product_muscle_work_queue_export=False)

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "missing required path: scripts/export_argus_product_muscle_work_queue.py" in result.stderr


def test_preflight_fails_when_operator_handoff_builder_missing(tmp_path):
    app = _make_app(tmp_path, include_operator_handoff_builder=False)

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "missing required path: scripts/build_argus_operator_handoff.py" in result.stderr


def test_preflight_fails_when_operator_handoff_omits_demand_plan_template_input(tmp_path):
    app = _make_app(
        tmp_path,
        operator_handoff_builder=SAFE_OPERATOR_HANDOFF_BUILDER.replace(
            'parser.add_argument("--demand-plan-template")',
            'parser.add_argument("--demand-readiness")',
        ),
    )

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "operator handoff missing demand plan template input" in result.stderr


def test_preflight_fails_when_operator_handoff_omits_demand_plan_template_summary(tmp_path):
    app = _make_app(
        tmp_path,
        operator_handoff_builder=SAFE_OPERATOR_HANDOFF_BUILDER.replace(
            '"demand_plan_template": {"filename": "argus-demand-plan-template.csv"}',
            '"demand_collection_plan": {}',
        ),
    )

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "operator handoff missing demand plan template summary" in result.stderr


def test_preflight_fails_when_operator_handoff_dashboard_attach_missing(tmp_path):
    app = _make_app(tmp_path, include_operator_handoff_attach=False)

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "missing required path: scripts/attach_operator_handoff_to_dashboard.py" in result.stderr


def test_preflight_fails_when_data_plane_manifest_export_missing(tmp_path):
    app = _make_app(tmp_path, include_data_plane_manifest_export=False)

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "missing required path: scripts/export_argus_data_plane_manifest.py" in result.stderr


def test_preflight_fails_when_learning_apply_plan_command_missing(tmp_path):
    app = _make_app(tmp_path, include_learning_apply_plan=False)

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "missing required path: scripts/build_learning_apply_plan.py" in result.stderr


def test_preflight_fails_when_learning_apply_executor_missing(tmp_path):
    app = _make_app(tmp_path, include_learning_apply_executor=False)

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "missing required path: scripts/execute_learning_apply_plan.py" in result.stderr


def test_preflight_fails_when_learning_policy_audit_missing(tmp_path):
    app = _make_app(tmp_path, include_learning_policy_audit=False)

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "missing required path: scripts/audit_learning_policies.py" in result.stderr


def test_preflight_fails_when_learning_apply_admin_reader_missing(tmp_path):
    app = _make_app(tmp_path, include_learning_apply_admin=False)

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "missing required path: src/cios/admin/learning_apply.py" in result.stderr


def test_preflight_fails_when_data_plane_manifest_admin_reader_missing(tmp_path):
    app = _make_app(tmp_path, include_data_plane_manifest_admin=False)

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "missing required path: src/cios/admin/data_plane_manifest.py" in result.stderr


def test_preflight_fails_when_product_muscle_work_queue_admin_reader_missing(tmp_path):
    app = _make_app(tmp_path, include_product_muscle_work_queue_admin=False)

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "missing required path: src/cios/admin/product_muscle_work_queue.py" in result.stderr


def test_preflight_fails_when_wrapper_does_not_enable_product_market_by_default(tmp_path):
    app = _make_app(
        tmp_path,
        wrapper="""#!/bin/sh
mkdir -p "$OUT"
cp "$CIOS_DASHBOARD_OUT" "$PUB/index.html"
""",
    )

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "wrapper missing product-market default enable" in result.stderr
    assert "wrapper missing package src PYTHONPATH" in result.stderr
    assert "wrapper missing package preflight call" in result.stderr
    assert "wrapper missing learning-policy audit gate" in result.stderr
    assert "wrapper missing product-market schema apply" in result.stderr
    assert "wrapper missing product-surface candidate promotion" in result.stderr
    assert "wrapper missing post-run summary attach" in result.stderr
    assert "wrapper missing demand-intake coordinator" in result.stderr
    assert "wrapper missing demand plan template manifest input" in result.stderr
    assert "wrapper missing demand-intake manifest input" in result.stderr
    assert "wrapper missing post-run dashboard rerender" in result.stderr
    assert "wrapper missing evidence work queue export" in result.stderr
    assert "wrapper missing product muscle work queue export" in result.stderr
    assert "wrapper missing Argus operator handoff builder" in result.stderr
    assert "wrapper missing Argus data-plane manifest export" in result.stderr
    assert "wrapper missing marked-output cleanup" in result.stderr
    assert "wrapper missing scoped output cleanup" in result.stderr
    assert "wrapper missing current-run artifact validation" in result.stderr
    assert "wrapper missing staged publish directory" in result.stderr


def test_preflight_fails_when_runner_service_missing_runtime_ceiling(tmp_path):
    app = _make_app(
        tmp_path,
        runner_service=SAFE_RUNNER_SERVICE.replace("RuntimeMaxSec=25min", ""),
    )

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "runner service must enforce a runtime ceiling" in result.stderr


def test_preflight_fails_when_wrapper_missing_product_surface_stage_timeout_guard(tmp_path):
    app = _make_app(
        tmp_path,
        wrapper=SAFE_WRAPPER.replace(
            "CIOS_PRODUCT_MARKET_EXPORT_STAGE_TIMEOUT_SECONDS",
            "CIOS_PRODUCT_MARKET_EXPORT_STAGE_TIMEOUT_DISABLED",
        ),
    )

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "wrapper missing product-surface stage timeout guard" in result.stderr


def test_preflight_fails_when_wrapper_missing_app_user_runner_handoff(tmp_path):
    app = _make_app(tmp_path)
    handoff = app / "deploy/cios-daily.sh"
    handoff.write_text(
        SAFE_HANDOFF_WRAPPER.replace('"$current_user" = "cios"', '"$current_user" = "disabled"'),
        encoding="utf-8",
    )

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "wrapper missing fixed cios identity gate" in result.stderr


def test_preflight_fails_when_host_runner_does_not_use_secure_queue_helper(tmp_path):
    app = _make_app(
        tmp_path,
        host_runner=SAFE_HOST_RUNNER.replace('"$HELPER" run-one', '"$HELPER" unsafe-run'),
    )

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "host runner must delegate one request to queue helper" in result.stderr


def test_preflight_fails_when_run_queue_omits_timeout_mapping(tmp_path):
    app = _make_app(tmp_path)
    helper = app / "scripts/cios_run_queue.py"
    helper.write_text(
        SAFE_RUN_QUEUE.replace("124 if timed_out else 2", "2 if timed_out else 2"),
        encoding="utf-8",
    )

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "run queue missing timeout exit mapping" in result.stderr


def test_preflight_fails_when_host_permissions_do_not_prefer_acl_traversal(tmp_path):
    app = _make_app(
        tmp_path,
        host_permissions=SAFE_HOST_PERMISSIONS.replace('setfacl -m "u:$APP_USER:--x,m:--x" /root/.hermes /root/.hermes/apps', ""),
    )

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "host permissions must prefer ACL traversal for cios" in result.stderr


def test_preflight_fails_when_host_permissions_do_not_grant_shim_acl_traversal(tmp_path):
    app = _make_app(
        tmp_path,
        host_permissions=SAFE_HOST_PERMISSIONS.replace('setfacl -m "u:$SHIM_USER:--x,m:--x" /root/.hermes /root/.hermes/apps', ""),
    )

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "host permissions must grant shim ACL traversal when present" in result.stderr


def test_preflight_fails_when_host_permissions_do_not_allow_cios_traversal_fallback(tmp_path):
    app = _make_app(
        tmp_path,
        host_permissions=SAFE_HOST_PERMISSIONS.replace("chmod 711 /root/.hermes /root/.hermes/apps", ""),
    )

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "host permissions must preserve execute-only Hermes traversal fallback" in result.stderr


def test_preflight_fails_when_host_permissions_do_not_fix_cron_wrapper_owner(tmp_path):
    app = _make_app(
        tmp_path,
        host_permissions=SAFE_HOST_PERMISSIONS.replace('chown "$APP_USER:$HERMES_GROUP" "$ROOT_WRAPPER"', ""),
    )

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "host permissions must make Hermes cron wrapper group executable" in result.stderr


def test_preflight_fails_when_runner_service_does_not_run_as_cios(tmp_path):
    app = _make_app(
        tmp_path,
        runner_service=SAFE_RUNNER_SERVICE.replace("User=cios\nGroup=cios\n", ""),
    )

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "runner service must run as cios user" in result.stderr
    assert "runner service must run as cios group" in result.stderr


def test_preflight_fails_when_runner_service_does_not_delegate_cgroups(tmp_path):
    app = _make_app(
        tmp_path,
        runner_service=SAFE_RUNNER_SERVICE.replace("Delegate=yes\n", ""),
    )

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "runner service must delegate cgroup subtree" in result.stderr


def test_preflight_fails_when_runner_service_allows_cgroup_fallback(tmp_path):
    app = _make_app(
        tmp_path,
        runner_service=SAFE_RUNNER_SERVICE.replace(
            "Environment=CIOS_REQUIRE_CGROUP_CONTAINMENT=1\n",
            "",
        ),
    )

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "runner service must require command cgroups" in result.stderr


def test_preflight_fails_when_runner_path_does_not_watch_requests(tmp_path):
    app = _make_app(
        tmp_path,
        runner_path=SAFE_RUNNER_PATH.replace("*.request", "*.ignored"),
    )

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "runner path must watch /opt request files" in result.stderr


def test_preflight_fails_when_claude_shim_service_lacks_hermes_group(tmp_path):
    app = _make_app(
        tmp_path,
        claude_shim_service=SAFE_CLAUDE_SHIM_SERVICE.replace("SupplementaryGroups=hermes\n", ""),
    )

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "claude shim service must include hermes supplementary group" in result.stderr


def test_preflight_fails_when_admin_service_runs_as_root(tmp_path):
    app = _make_app(
        tmp_path,
        admin_service=SAFE_ADMIN_SERVICE.replace("User=cios\nGroup=cios\n", ""),
    )

    result = _run_preflight(app)

    assert result.returncode == 2
    assert "admin service must run as cios user" in result.stderr
    assert "admin service must run as cios group" in result.stderr


def test_preflight_can_require_scout_binary_for_product_market_runs(tmp_path):
    app = _make_app(tmp_path)

    result = _run_preflight_with_scout(app, "missing-scout-bin")

    assert result.returncode == 2
    assert "missing required Scout binary: missing-scout-bin" in result.stderr


def test_preflight_accepts_configured_scout_binary(tmp_path):
    app = _make_app(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    scout = bin_dir / "scout"
    scout.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    scout.chmod(0o755)

    result = _run_preflight_with_scout(app, "scout", path=str(bin_dir))

    assert result.returncode == 0, result.stderr + result.stdout


def test_preflight_can_require_async_pytest_plugin_for_remote_full_suite(tmp_path):
    app = _make_app(tmp_path)
    python_bin = app / ".venv" / "bin" / "python"
    python_bin.parent.mkdir(parents=True)
    python_bin.write_text(
        "#!/bin/sh\n"
        "echo 'ModuleNotFoundError: No module named pytest_asyncio' >&2\n"
        "exit 1\n",
        encoding="utf-8",
    )
    python_bin.chmod(0o755)

    result = _run_preflight_with_test_deps(app)

    assert result.returncode == 2
    assert "missing required test dependency: pytest_asyncio" in result.stderr
