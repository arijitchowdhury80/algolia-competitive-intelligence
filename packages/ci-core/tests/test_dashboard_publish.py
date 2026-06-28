import importlib
import sys
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_ROOT / "scripts"
REPO_ROOT = SKILL_ROOT.parents[1]


DAILY = """**Competitive pulse - 2026-06-28**

**Bottom line**

Constructor produced the highest-scored public signal: [Constructor changed case_study](https://constructor.com/customers). Treat this as actionable only after validation.

**Recommended action**

Sales Enablement owns the first move. Review the source evidence today and log the validation result.

**Evidence**

- **Constructor, 2026-06-28:** [Constructor changed case_study](https://constructor.com/customers) - Constructor public case_study source changed.
"""


WEEKLY = """**Weekly competitive synthesis - 2026-06-22 to 2026-06-28**

**What changed**

The ledger captured 12 public signals. The strongest source-backed signal is from Constructor.

**Strategic pattern**

AI search packaging remains the repeated market pattern.

**Recommended actions by owner**

- **Sales Enablement:** Validate whether Constructor customer proof changes objection handling.

**Coverage gaps**

This v1 run uses public sources only.
"""


def load_publish_module():
    sys.path.insert(0, str(SCRIPTS_DIR))
    sys.modules.pop("ci_dashboard_publish", None)
    return importlib.import_module("ci_dashboard_publish")


def test_export_dashboard_assets_uses_latest_real_reports(tmp_path):
    publish = load_publish_module()
    output_root = tmp_path / "competitive-research"
    repo_root = tmp_path / "repo"
    (output_root / "briefs").mkdir(parents=True)
    (output_root / "reports").mkdir(parents=True)
    (repo_root / "apps" / "dashboard" / "public").mkdir(parents=True)

    (output_root / "briefs" / "2026-06-28.md").write_text(DAILY)
    (output_root / "briefs" / "2026-06-28-weekly.md").write_text(WEEKLY)
    (output_root / "reports" / "2026-06-28.html").write_text("<!doctype html><title>Daily</title>")
    (output_root / "reports" / "2026-06-28-weekly.html").write_text("<!doctype html><title>Weekly</title>")

    result = publish.export_dashboard_assets(
        output_root=output_root,
        repo_root=repo_root,
        generated_at="2026-06-28T09:05:00-04:00",
    )

    public = repo_root / "apps" / "dashboard" / "public"
    html = (public / "index.html").read_text()

    assert result["latest_daily"]["date"] == "2026-06-28"
    assert result["latest_weekly"]["date"] == "2026-06-28"
    assert (public / "latest-daily.md").read_text() == DAILY
    assert (public / "latest-weekly.md").read_text() == WEEKLY
    assert (public / "archive" / "2026-06-28.md").read_text() == DAILY
    assert (public / "archive" / "2026-06-28-weekly.md").read_text() == WEEKLY
    assert (public / "data" / "latest.json").exists()
    assert "Competitive Brief" in html
    assert "Generated from archived CI briefs, not mock data" in html
    assert "Constructor customer proof changed needs validation." in html
    assert "What happened" in html
    assert "Why it matters" in html
    assert "Recommended response" in html
    assert "Data limits" in html
    assert "Show collection details" in html
    assert "Attention queue" not in html
    assert "Mock findings" not in html


def test_cron_wrappers_call_dashboard_publisher_after_successful_runs():
    daily = (SCRIPTS_DIR / "competitive-research-daily.sh").read_text()
    weekly = (SCRIPTS_DIR / "competitive-research-weekly.sh").read_text()

    assert "publish_dashboard" in daily
    assert "publish-dashboard.py" in daily
    assert "publish_dashboard" in weekly
    assert "publish-dashboard.py" in weekly
