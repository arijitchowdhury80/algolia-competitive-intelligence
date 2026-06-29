import importlib
import sys
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_ROOT / "scripts"
REPO_ROOT = SKILL_ROOT.parents[1]


DAILY = """**Competitive pulse - 2026-06-28**

**What changed**

Constructor added customer proof for [Petco](https://constructor.com/customers).

**Why it matters to Algolia**

Constructor is adding customer proof in AI search. Algolia should check whether the proof weakens current sales claims or battlecards.

**Recommended action**

Sales Enablement owns the first move. Review the source evidence today and log the validation result.

**Evidence**

- [Constructor](https://constructor.com/customers) - named customer proof with outcome evidence.
"""


WEEKLY = """**Weekly competitive synthesis - 2026-06-22 to 2026-06-28**

**What changed**

Constructor added customer proof for Petco.

**Customer proof movement**

- **Constructor:** [Constructor added customer proof for Petco.](https://constructor.com/customers) - review for playbook impact.

**Content/narrative movement**

- **Google Vertex AI Search:** [Google Cloud published an agentic search narrative.](https://cloud.google.com/blog/products/ai-machine-learning) - review for content response.

**Campaign opportunities**

- Product Marketing should create an Algolia POV on agentic search and commerce discovery.

**Recommended actions by owner**

- **Sales Enablement:** Validate whether Constructor customer proof changes objection handling.
- **Product Marketing:** Compare Google agentic search language against Algolia AI search messaging.

**Battlecard updates**

- Candidate: Constructor customer proof for Petco.

**Suppressed weak signals**

3 weak or ambiguous source changes were kept out of the executive brief.

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
    assert "Constructor added customer proof for Petco." in html
    assert "What happened" in html
    assert "Why it matters" in html
    assert "Recommended response" in html
    assert "Customer Proof Radar" in html
    assert "Narrative And Content Radar" in html
    assert "Decision Queue" in html
    assert "Suppressed Signals" in html
    assert "Data limits" in html
    assert "Show collection details" in html
    assert "Attention queue" not in html
    assert "Mock findings" not in html
    assert "case_study" not in html


def test_cron_wrappers_call_dashboard_publisher_after_successful_runs():
    daily = (SCRIPTS_DIR / "competitive-research-daily.sh").read_text()
    weekly = (SCRIPTS_DIR / "competitive-research-weekly.sh").read_text()

    assert "publish_dashboard" in daily
    assert "publish-dashboard.py" in daily
    assert "publish_dashboard" in weekly
    assert "publish-dashboard.py" in weekly


def test_cron_wrappers_fail_closed_on_provider_credit_or_synthesis_failure():
    daily = (SCRIPTS_DIR / "competitive-research-daily.sh").read_text()
    weekly = (SCRIPTS_DIR / "competitive-research-weekly.sh").read_text()

    assert "ci-provider-preflight.py" in daily
    assert "ci-provider-preflight.py" in weekly
    assert 'PYTHON_BIN="${PYTHON_BIN:-/opt/hermes/.venv/bin/python}"' in daily
    assert 'PYTHON_BIN="${PYTHON_BIN:-/opt/hermes/.venv/bin/python}"' in weekly
    assert "/opt/data/.env" in daily
    assert "/opt/data/.env" in weekly
    assert 'CI_MODEL_PROVIDER="${CI_MODEL_PROVIDER:-gemini}"' in daily
    assert 'CI_MODEL_PROVIDER="${CI_MODEL_PROVIDER:-gemini}"' in weekly
    assert 'COMPETITIVE_RESEARCH_PROVIDER="${COMPETITIVE_RESEARCH_PROVIDER:-gemini}"' in daily
    assert 'COMPETITIVE_RESEARCH_PROVIDER="${COMPETITIVE_RESEARCH_PROVIDER:-gemini}"' in weekly
    assert 'COMPETITIVE_RESEARCH_MODEL="${COMPETITIVE_RESEARCH_MODEL:-gemini-2.5-flash}"' in daily
    assert 'COMPETITIVE_RESEARCH_MODEL="${COMPETITIVE_RESEARCH_MODEL:-gemini-2.5-flash}"' in weekly
    assert "--fail-on-synthesis-error" in daily
    assert "--fail-on-synthesis-error" in weekly


def test_dashboard_publish_rebases_before_push(monkeypatch, tmp_path):
    publish = load_publish_module()
    repo_root = tmp_path / "repo"
    (repo_root / "apps" / "dashboard" / "public").mkdir(parents=True)
    calls = []

    def fake_run_git(root, args, check=True):
        calls.append(tuple(args))
        if args[:3] == ["status", "--porcelain", "--"]:
            return publish.subprocess.CompletedProcess(["git", *args], 0, stdout=" M apps/dashboard/public/index.html\n")
        return publish.subprocess.CompletedProcess(["git", *args], 0, stdout="")

    def fake_subprocess_run(args, **kwargs):
        calls.append(tuple(args[1:]))
        return publish.subprocess.CompletedProcess(args, 0, stdout="[main abc123] Update\n")

    monkeypatch.setattr(publish, "run_git", fake_run_git)
    monkeypatch.setattr(publish.subprocess, "run", fake_subprocess_run)

    assert publish.publish_git(repo_root, "Update dashboard") is True
    assert ("pull", "--rebase", "origin", "main") in calls
    assert calls.index(("pull", "--rebase", "origin", "main")) < calls.index(("push", "origin", "main"))
