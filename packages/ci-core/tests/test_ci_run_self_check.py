import importlib
import json
import sqlite3
import sys
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_ROOT / "scripts"


def load_self_check():
    sys.path.insert(0, str(SCRIPTS_DIR))
    sys.modules.pop("ci_run_self_check", None)
    return importlib.import_module("ci_run_self_check")


def create_ledger(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        create table semantic_deltas (
            id integer primary key,
            detected_date text,
            quality_status text
        )
        """
    )
    conn.execute(
        "insert into semantic_deltas (detected_date, quality_status) values (?, ?)",
        ("2026-06-29", "publish"),
    )
    conn.execute(
        "insert into semantic_deltas (detected_date, quality_status) values (?, ?)",
        ("2026-06-29", "suppressed"),
    )
    conn.commit()
    conn.close()


def test_self_check_passes_and_writes_audit_artifacts(tmp_path):
    mod = load_self_check()
    output_root = tmp_path / "competitive-research"
    markdown = output_root / "briefs" / "2026-06-29.md"
    html = output_root / "reports" / "2026-06-29.html"
    dashboard_log = output_root / "raw" / "dashboard-publish-latest.log"
    ledger = output_root / "ci.sqlite"
    markdown.parent.mkdir(parents=True)
    html.parent.mkdir(parents=True)
    dashboard_log.parent.mkdir(parents=True)
    markdown.write_text(
        "**Competitive pulse - 2026-06-29**\n\n"
        "**What changed**\n\nConstructor published named customer proof.\n\n"
        "**Evidence**\n\n- https://constructor.com/customers\n"
    )
    html.write_text("<!doctype html><title>CI</title>")
    dashboard_log.write_text("Dashboard assets exported: 8 reports\n")
    create_ledger(ledger)

    result = mod.run_self_check(
        cadence="daily",
        output_root=output_root,
        markdown_path=markdown,
        html_path=html,
        dashboard_log_path=dashboard_log,
        run_output="Markdown saved: %s\nHTML saved: %s\n" % (markdown, html),
        date="2026-06-29",
        generated_at="2026-06-29T09:05:00-04:00",
    )

    assert result["status"] == "pass"
    assert result["checks"]["markdown_artifact"]["status"] == "pass"
    assert result["checks"]["html_artifact"]["status"] == "pass"
    assert result["checks"]["ledger"]["status"] == "pass"
    assert result["checks"]["dashboard_publish"]["status"] == "pass"
    assert result["semantic_delta_counts"] == {"publish": 1, "suppressed": 1}
    assert Path(result["json_path"]).exists()
    assert Path(result["markdown_path"]).exists()
    payload = json.loads(Path(result["json_path"]).read_text())
    assert payload["cadence"] == "daily"
    assert "planned_vs_actual" in Path(result["markdown_path"]).read_text()


def test_self_check_fails_when_required_report_artifacts_are_missing(tmp_path):
    mod = load_self_check()
    output_root = tmp_path / "competitive-research"
    output_root.mkdir()

    result = mod.run_self_check(
        cadence="weekly",
        output_root=output_root,
        markdown_path=output_root / "briefs" / "missing-weekly.md",
        html_path=output_root / "reports" / "missing-weekly.html",
        dashboard_log_path=output_root / "raw" / "dashboard-publish-latest.log",
        run_output="weekly wrapper output",
        date="2026-06-29",
        generated_at="2026-06-29T09:05:00-04:00",
    )

    assert result["status"] == "fail"
    assert result["checks"]["markdown_artifact"]["status"] == "fail"
    assert result["checks"]["html_artifact"]["status"] == "fail"
    assert result["checks"]["ledger"]["status"] == "fail"


def test_self_check_warns_on_raw_change_language(tmp_path):
    mod = load_self_check()
    output_root = tmp_path / "competitive-research"
    markdown = output_root / "briefs" / "2026-06-29.md"
    html = output_root / "reports" / "2026-06-29.html"
    dashboard_log = output_root / "raw" / "dashboard-publish-latest.log"
    ledger = output_root / "ci.sqlite"
    markdown.parent.mkdir(parents=True)
    html.parent.mkdir(parents=True)
    dashboard_log.parent.mkdir(parents=True)
    markdown.write_text("Constructor page changed since previous snapshot.")
    html.write_text("<!doctype html><title>CI</title>")
    dashboard_log.write_text("Dashboard assets exported: 8 reports\n")
    create_ledger(ledger)

    result = mod.run_self_check(
        cadence="daily",
        output_root=output_root,
        markdown_path=markdown,
        html_path=html,
        dashboard_log_path=dashboard_log,
        run_output="",
        date="2026-06-29",
        generated_at="2026-06-29T09:05:00-04:00",
    )

    assert result["status"] == "warn"
    assert result["checks"]["weak_language_gate"]["status"] == "warn"
    assert "page changed" in result["checks"]["weak_language_gate"]["details"]


def test_cron_wrappers_call_self_check_after_dashboard_publish():
    daily = (SCRIPTS_DIR / "competitive-research-daily.sh").read_text()
    weekly = (SCRIPTS_DIR / "competitive-research-weekly.sh").read_text()

    assert "run_self_check" in daily
    assert "ci_run_self_check.py" in daily
    assert "run_self_check" in weekly
    assert "ci_run_self_check.py" in weekly
