import importlib
import json
import sys
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_ROOT / "scripts"


def load_review():
    sys.path.insert(0, str(SCRIPTS_DIR))
    sys.modules.pop("ci_run_review", None)
    return importlib.import_module("ci_run_review")


def write_audit(path: Path, *, status: str, checks: dict | None = None) -> None:
    path.parent.mkdir(parents=True)
    payload = {
        "cadence": "daily",
        "date": "2026-06-29",
        "generated_at": "2026-06-29T09:05:00-04:00",
        "status": status,
        "checks": checks or {
            "markdown_artifact": {"status": "pass", "details": "brief.md"},
            "html_artifact": {"status": "pass", "details": "report.html"},
            "ledger": {"status": "pass", "details": "ci.sqlite"},
            "dashboard_publish": {"status": "pass", "details": "dashboard log"},
            "weak_language_gate": {"status": "pass", "details": "no raw-change language found"},
        },
        "semantic_delta_counts": {"publish": 1, "suppressed": 2},
        "artifacts": {"markdown": "brief.md", "html": "report.html", "ledger": "ci.sqlite"},
        "run_output_tail": "Quality score: 0.91",
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")


def test_review_writes_argus_learning_artifacts_for_clean_run(tmp_path):
    mod = load_review()
    output_root = tmp_path / "competitive-research"
    audit = output_root / "run-audits" / "2026-06-29-daily.json"
    write_audit(audit, status="pass")

    result = mod.run_review(
        cadence="daily",
        output_root=output_root,
        audit_json_path=audit,
        run_output="Quality score: 0.91\n",
        date="2026-06-29",
        generated_at="2026-06-29T09:06:00-04:00",
    )

    assert result["status"] == "healthy"
    assert result["discrepancies"] == []
    assert result["improvement_actions"] == []
    assert Path(result["json_path"]).exists()
    assert Path(result["markdown_path"]).exists()
    assert (output_root / "run-reviews" / "argus-learning-log.md").exists()
    assert "Argus run review - daily - 2026-06-29" in Path(result["markdown_path"]).read_text()


def test_review_records_discrepancies_and_actions_for_warn_run(tmp_path):
    mod = load_review()
    output_root = tmp_path / "competitive-research"
    audit = output_root / "run-audits" / "2026-06-29-daily.json"
    write_audit(
        audit,
        status="warn",
        checks={
            "markdown_artifact": {"status": "pass", "details": "brief.md"},
            "html_artifact": {"status": "pass", "details": "report.html"},
            "ledger": {"status": "pass", "details": "ci.sqlite"},
            "dashboard_publish": {"status": "warn", "details": "dashboard log contains: Traceback"},
            "weak_language_gate": {"status": "pass", "details": "no raw-change language found"},
        },
    )

    result = mod.run_review(
        cadence="daily",
        output_root=output_root,
        audit_json_path=audit,
        run_output="[WARN] Output quality issues: missing_links\nQuality score: 0.75\n",
        date="2026-06-29",
        generated_at="2026-06-29T09:06:00-04:00",
    )

    assert result["status"] == "needs_attention"
    assert any(item["source"] == "dashboard_publish" for item in result["discrepancies"])
    assert any(item["source"] == "output_quality" for item in result["discrepancies"])
    assert any("Repair dashboard publishing" in item["action"] for item in result["improvement_actions"])
    assert any("missing evidence links" in item["action"] for item in result["improvement_actions"])
    learning_log = output_root / "run-reviews" / "argus-learning-log.md"
    assert "needs_attention" in learning_log.read_text()


def test_review_fails_when_audit_json_is_missing(tmp_path):
    mod = load_review()
    output_root = tmp_path / "competitive-research"

    result = mod.run_review(
        cadence="weekly",
        output_root=output_root,
        audit_json_path=output_root / "run-audits" / "missing.json",
        run_output="",
        date="2026-06-29",
        generated_at="2026-06-29T09:06:00-04:00",
    )

    assert result["status"] == "failed"
    assert result["discrepancies"][0]["source"] == "audit_json"


def test_cron_wrappers_call_argus_review_after_self_check():
    daily = (SCRIPTS_DIR / "competitive-research-daily.sh").read_text()
    weekly = (SCRIPTS_DIR / "competitive-research-weekly.sh").read_text()

    assert "run_post_review" in daily
    assert "ci_run_review.py" in daily
    assert "run_post_review" in weekly
    assert "ci_run_review.py" in weekly
