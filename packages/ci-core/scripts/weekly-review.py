#!/usr/bin/env python3
"""
Weekly Competitive Research Synthesis v2
=======================================

Reads the SQLite signal ledger and produces a pattern-first weekly synthesis.
This script also keeps a small operational audit: source count, signal count,
coverage gaps, and output quality.

Usage:
  python3 scripts/weekly-review.py
  python3 scripts/weekly-review.py --date 2026-06-22
  python3 scripts/weekly-review.py --local-synthesis
  python3 scripts/weekly-review.py --fixture "$COMPETITIVE_RESEARCH_OUTPUT_ROOT/raw/2026-06-17.json" --local-synthesis
"""

import argparse
import json
import sys
from pathlib import Path

from ci_core import (
    DB_PATH,
    build_synthesis_packet,
    build_weekly_prompt,
    connect_db,
    create_action_items_from_semantic_deltas,
    date_today,
    date_window,
    flatten_sources,
    get_signal_counts,
    load_sources,
    quality_score,
    record_synthesis_run,
    render_html_report,
    save_html,
    save_markdown,
    seed_fixture,
    source_ledger,
    synthesize_local,
    synthesize_with_hermes,
    upsert_sources,
    validate_output,
)


def parse_args():
    parser = argparse.ArgumentParser(description="Weekly Competitive Research Synthesis v2")
    parser.add_argument("--date", help="End date for review window (YYYY-MM-DD)")
    parser.add_argument("--days", type=int, default=7, help="Window length")
    parser.add_argument("--fixture", help="Replay fixture before synthesis")
    parser.add_argument("--local-synthesis", action="store_true", help="Use deterministic local synthesis for UX testing")
    parser.add_argument("--dry-run", action="store_true", help="Build packet and audit only")
    parser.add_argument("--fail-on-synthesis-error", action="store_true", help="Exit nonzero instead of falling back when Hermes synthesis fails")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    end_date = args.date or date_today()
    start_date, end_date = date_window(end_date, args.days)
    print("=== Weekly competitive synthesis v2: %s to %s ===" % (start_date, end_date))
    print("SQLite ledger: %s" % DB_PATH)

    conn = connect_db()
    config = load_sources()
    source_records = flatten_sources(config)
    upsert_sources(conn, source_records)
    print("Sources loaded: %d" % len(source_records))

    if args.fixture:
        fixture_path = Path(args.fixture)
        if not fixture_path.exists():
            print("[FATAL] Fixture not found: %s" % fixture_path)
            return 2
        ids = seed_fixture(conn, fixture_path, detected_date=end_date)
        print("Fixture replay inserted signals: %d" % len(ids))

    packet = build_synthesis_packet(conn, "weekly", start_date, end_date, limit=40)
    counts = get_signal_counts(conn, start_date, end_date)
    audit = {
        "date_start": start_date,
        "date_end": end_date,
        "db_path": str(DB_PATH),
        "sources_loaded": len(source_records),
        "signals": counts,
        "source_coverage": packet.get("source_coverage", {}),
        "ledger_sources": source_ledger(packet.get("signals", []), limit=25),
    }
    print("Signals in window: %d" % counts["total"])
    print("Action-owner coverage: %s" % json.dumps(counts["by_owner"], sort_keys=True))
    print("Category coverage: %s" % json.dumps(counts["by_category"], sort_keys=True))
    coverage_totals = packet.get("source_coverage", {}).get("totals", {})
    if coverage_totals:
        print("Source coverage: enabled={enabled_sources} checked={checked_sources} ok={successful_sources} failed={failed_sources} missing={missing_sources} changed_sources={changed_signal_sources}".format(**coverage_totals))

    if args.dry_run:
        print(json.dumps(audit, indent=2, default=str))
        return 0

    if args.local_synthesis:
        markdown = synthesize_local(packet, cadence="weekly")
    else:
        prompt = build_weekly_prompt(packet)
        try:
            markdown = synthesize_with_hermes(prompt)
        except Exception as exc:
            if args.fail_on_synthesis_error:
                print("[FATAL] Hermes synthesis failed: %s" % str(exc)[:500])
                print("[FATAL] Production CI will not publish a fallback report. Fix provider/model availability and rerun.")
                return 75
            print("[WARN] Hermes synthesis failed: %s" % str(exc)[:500])
            print("[WARN] Falling back to local synthesis so artifacts are still reviewable.")
            markdown = synthesize_local(packet, cadence="weekly")

    errors = validate_output(markdown, surface="weekly")
    if errors:
        print("[WARN] Output quality issues: %s" % ", ".join(errors))

    html_text = render_html_report(markdown, packet, cadence="weekly")
    markdown_path = save_markdown(markdown, end_date, cadence="weekly")
    html_path = save_html(html_text, end_date, cadence="weekly")
    score = quality_score(markdown)
    signal_ids = [s["id"] for s in packet.get("signals", [])]
    report_id = record_synthesis_run(conn, "weekly", start_date, end_date, signal_ids, markdown_path, html_path, score)
    create_action_items_from_semantic_deltas(conn, report_id, packet.get("semantic_deltas", []))

    print("Markdown saved: %s" % markdown_path)
    print("HTML saved: %s" % html_path)
    print("Quality score: %.2f" % score)
    print("")
    print(markdown)
    return 0


if __name__ == "__main__":
    sys.exit(main())
