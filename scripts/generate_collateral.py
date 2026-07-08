"""CLI: generate a draft collateral asset (landing page or marketing
dashboard) from an already-persisted action_items row, for human review.

Doctrine (docs/planning/CI-OS-product-doctrine-2026-07-08.md, Addendum 2
point 4): collateral is NOT auto-generated in the daily production run
(scripts/daily_production_run.py) -- prescriptions are persisted as
action_items there, and a human runs this script on demand against a
specific action_item id to produce a draft asset for review. Nothing this
script writes is ever auto-published (src/cios/collateral/types.py:
CollateralAsset.review_status always starts at draft/needs_verification).

Usage:
  .venv/bin/python scripts/generate_collateral.py \\
      --action-item-id 42 \\
      --kind landing_page \\
      --brand-tokens config/brand-tokens/algolia.yaml \\
      [--out-dir out/collateral]

Env vars (read-only, never printed):
  CIOS_DATABASE_URL    - Postgres DSN (required)
  CIOS_APP_PASSWORD    - cios_app role password (optional, has a dev default)
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg
import yaml
from psycopg.rows import dict_row

from cios.collateral.landing_page import LandingPageGenerator
from cios.collateral.marketing_dashboard import MarketingDashboardGenerator
from cios.collateral.types import BrandTokens, CollateralKind, CollateralRequest
from cios.db.session import get_dsn, tenant_context
from cios.platform.models.providers.claude_cli import ClaudeCliShimProvider
from cios.prescribe.types import Effort, Grounding, Prescription, Team, UrgencyWindow

# Mirrors scripts/daily_production_run.py's app_dsn -- kept local (not
# imported from there) so this script has no runtime dependency on the
# production runner module.


def app_dsn(superuser_dsn: str) -> str:
    import os

    info = psycopg.conninfo.conninfo_to_dict(superuser_dsn)
    info["user"] = "cios_app"
    info["password"] = os.environ.get("CIOS_APP_PASSWORD", "cios_app_dev_local_only_not_secret")
    return psycopg.conninfo.make_conninfo(**info)


def load_action_item(conn, action_item_id: int) -> dict:
    """Action items are tenant-scoped (RLS via tenant_context), so we first
    look the row up tenant-agnostically to learn its tenant_id, then re-read
    it inside the correct tenant_context -- same two-step pattern RLS forces
    on any by-id lookup where the caller doesn't already know the tenant."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT tenant_id FROM action_items WHERE id = %s", (action_item_id,))
        row = cur.fetchone()
    if row is None:
        raise SystemExit(f"action_item id={action_item_id} not found")
    tenant_id = row["tenant_id"]
    with tenant_context(conn, tenant_id):
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM action_items WHERE id = %s AND tenant_id = %s",
                        (action_item_id, tenant_id))
            return cur.fetchone()


# Doctrine's action_items schema has no per-field play/team/urgency columns
# of its own (see prescription_to_action_item() in daily_production_run.py
# for the mapping the daily run uses when writing these rows) -- title and
# play steps are folded together into `recommendation` as "<title>: <s1>; <s2>".
# Reconstructing a Prescription for collateral generation from that row is
# therefore a best-effort unpack, not a lossless round-trip; documented here
# rather than silently treated as exact.
_TITLE_STEPS_RE = re.compile(r"^(?P<title>[^:]+):\s*(?P<steps>.+)$")


def action_item_to_prescription(row: dict) -> Prescription:
    recommendation = row["recommendation"] or ""
    match = _TITLE_STEPS_RE.match(recommendation)
    if match:
        title = match.group("title").strip()
        play = [s.strip() for s in match.group("steps").split(";") if s.strip()]
    else:
        title = recommendation.strip() or f"Action item {row['id']}"
        play = [title]

    evidence_urls = list(row.get("evidence_ids") or [])
    if not evidence_urls:
        raise SystemExit(
            f"action_item id={row['id']} has no evidence_ids; cannot generate collateral "
            "without grounding (evidence-or-silence)"
        )

    team_raw = row.get("owner") or Team.MARKETING.value
    try:
        team = Team(team_raw)
    except ValueError:
        team = Team.MARKETING

    urgency_raw = row.get("due_window") or row.get("priority") or UrgencyWindow.THIS_WEEK.value
    try:
        urgency = UrgencyWindow(urgency_raw)
    except ValueError:
        urgency = UrgencyWindow.THIS_WEEK

    grounding = Grounding(
        signal_evidence_urls=evidence_urls,
        evidence_urls=evidence_urls,
    )
    return Prescription(
        tenant_id=row["tenant_id"],
        title=title,
        play=play,
        team=team,
        urgency_window=urgency,
        grounding=grounding,
        expected_effect=f"Executes action item {row['id']} ({title}).",
        effort=Effort.M,
        materiality_score=float(row.get("confidence") or 0.5),
    )


async def generate(kind: CollateralKind, prescription: Prescription, brand: BrandTokens) -> str:
    request = CollateralRequest(tenant_id=prescription.tenant_id, kind=kind,
                                 prescription=prescription, brand=brand)
    if kind is CollateralKind.MARKETING_DASHBOARD:
        asset = MarketingDashboardGenerator().generate(request)
        return asset.html
    if kind is CollateralKind.LANDING_PAGE:
        provider = ClaudeCliShimProvider(model_alias="opus", timeout_s=90.0)
        health = await provider.health_check()
        if not health.healthy:
            raise SystemExit(f"ABORT: claude-shim not healthy ({health.detail}); "
                              "landing_page generation needs a live model.")
        asset = await LandingPageGenerator(model=provider).generate(request)
        return asset.html
    raise SystemExit(f"unknown kind: {kind}")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "collateral"


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action-item-id", type=int, required=True)
    parser.add_argument("--kind", choices=[k.value for k in CollateralKind], required=True)
    parser.add_argument("--brand-tokens", type=Path, required=True,
                         help="YAML file with BrandTokens fields (company_name required)")
    parser.add_argument("--out-dir", type=Path, default=Path("out/collateral"))
    args = parser.parse_args()

    superuser_dsn = get_dsn()
    conninfo = app_dsn(superuser_dsn)

    with open(args.brand_tokens, encoding="utf-8") as f:
        brand_data = yaml.safe_load(f) or {}
    brand = BrandTokens(**brand_data)

    with psycopg.connect(conninfo, autocommit=True) as conn:
        row = load_action_item(conn, args.action_item_id)

    prescription = action_item_to_prescription(row)
    kind = CollateralKind(args.kind)
    html = await generate(kind, prescription, brand)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = args.out_dir / f"{_slug(prescription.title)}-{kind.value}-{timestamp}.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"Draft collateral written: {out_path} (review_status is never auto-approved; "
          "a human must review before this asset ships)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
