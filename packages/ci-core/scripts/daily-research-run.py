#!/usr/bin/env python3
"""
Daily Competitive Research Runner v2
====================================

Orchestrates the public-source CI engine:
1. Load sources and ensure SQLite ledger schema
2. Collect direct public-source snapshots and diffs
3. Ingest Parallel monitor/search results when available
4. Normalize signals into the ledger
5. Synthesize from the signal ledger, not raw search dumps
6. Save Markdown, HTML, raw collection metadata, and Telegram output

Usage:
  python3 scripts/daily-research-run.py
  python3 scripts/daily-research-run.py --date 2026-06-17
  python3 scripts/daily-research-run.py --dry-run
  python3 scripts/daily-research-run.py --fixture "$COMPETITIVE_RESEARCH_OUTPUT_ROOT/raw/2026-06-17.json" --local-synthesis
  python3 scripts/daily-research-run.py --direct-limit 5 --skip-search --local-synthesis
  python3 scripts/daily-research-run.py --resume --local-synthesis
"""

import argparse
import json
import sys
from pathlib import Path

from ci_core import (
    DB_PATH,
    build_daily_prompt,
    build_synthesis_packet,
    check_monitors,
    check_parallel_cli,
    collect_direct_sources,
    collect_parallel_searches,
    connect_db,
    date_today,
    date_window,
    flatten_sources,
    monitor_events_to_signals,
    quality_score,
    record_synthesis_run,
    render_html_report,
    render_telegram,
    save_html,
    save_markdown,
    seed_fixture,
    synthesize_local,
    synthesize_with_hermes,
    upsert_sources,
    validate_output,
    write_collection_raw,
    load_sources,
)


def parse_args():
    parser = argparse.ArgumentParser(description="Daily Competitive Research Runner v2")
    parser.add_argument("--date", help="Date override (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="Collect/store signals but skip synthesis")
    parser.add_argument("--resume", action="store_true", help="Skip collection and synthesize from existing ledger")
    parser.add_argument("--fixture", help="Replay a raw JSON fixture into the signal ledger")
    parser.add_argument("--local-synthesis", action="store_true", help="Use deterministic local synthesis for UX testing")
    parser.add_argument("--skip-direct", action="store_true", help="Skip direct public URL fetching")
    parser.add_argument("--skip-search", action="store_true", help="Skip Parallel search ingestion")
    parser.add_argument("--skip-monitors", action="store_true", help="Skip Parallel monitor ingestion")
    parser.add_argument("--direct-limit", type=int, help="Limit direct public-source fetches")
    parser.add_argument("--search-results", type=int, default=5, help="Max results per Parallel search query")
    parser.add_argument("--min-score", type=float, default=0.3, help="Minimum signal score for synthesis packet")
    parser.add_argument("--fail-on-synthesis-error", action="store_true", help="Exit nonzero instead of falling back when Hermes synthesis fails")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    date_str = args.date or date_today()
    print("=== Competitive research v2: %s ===" % date_str)
    print("SQLite ledger: %s" % DB_PATH)

    conn = connect_db()
    config = load_sources()
    source_records = flatten_sources(config)
    upsert_sources(conn, source_records)
    print("Sources loaded: %d" % len(source_records))

    collection = {
        "date": date_str,
        "db_path": str(DB_PATH),
        "sources_loaded": len(source_records),
        "fixture_signal_ids": [],
        "direct": {},
        "monitors": {},
        "search": {},
        "errors": [],
    }

    if not args.resume:
        if args.fixture:
            fixture_path = Path(args.fixture)
            if not fixture_path.exists():
                print("[FATAL] Fixture not found: %s" % fixture_path)
                return 2
            ids = seed_fixture(conn, fixture_path, detected_date=date_str)
            collection["fixture_signal_ids"] = ids
            print("Fixture replay inserted signals: %d" % len(ids))

        if not args.skip_direct:
            print("[1/3] Fetching direct public sources...")
            collection["direct"] = collect_direct_sources(conn, limit=args.direct_limit)
            print("  snapshots=%s signals=%s errors=%s" % (
                collection["direct"].get("snapshots", 0),
                collection["direct"].get("signals", 0),
                len(collection["direct"].get("errors", [])),
            ))

        parallel_ready = check_parallel_cli()
        if parallel_ready and not args.skip_monitors:
            print("[2/3] Checking Parallel monitors...")
            events = check_monitors()
            collection["monitors"] = monitor_events_to_signals(conn, events, detected_date=date_str)
            collection["monitors"]["events_seen"] = len(events)
            print("  events=%s signals=%s" % (len(events), collection["monitors"].get("signals", 0)))
        elif not args.skip_monitors:
            collection["errors"].append("parallel_cli_not_authenticated_for_monitors")
            print("[2/3] Parallel monitors skipped: CLI not authenticated")

        if parallel_ready and not args.skip_search:
            print("[3/3] Running Parallel search ingestion...")
            collection["search"] = collect_parallel_searches(conn, config, max_results=args.search_results)
            print("  signals=%s errors=%s" % (
                collection["search"].get("signals", 0),
                len(collection["search"].get("errors", [])),
            ))
        elif not args.skip_search:
            collection["errors"].append("parallel_cli_not_authenticated_for_search")
            print("[3/3] Parallel search skipped: CLI not authenticated")

        raw_path = write_collection_raw(collection, date_str)
        print("Raw collection metadata: %s" % raw_path)
    else:
        print("Resume mode: collection skipped")

    if args.dry_run:
        print("Dry run complete. Ledger is updated; synthesis skipped.")
        return 0

    date_start, date_end = date_window(date_str, 1)
    packet = build_synthesis_packet(conn, "daily", date_start, date_end)
    print("Synthesis packet: %d signals, %d ledger sources" % (
        len(packet.get("signals", [])),
        len(packet.get("source_ledger", [])),
    ))

    if not packet.get("signals"):
        print("No material daily signals; using deterministic quiet-day synthesis.")
        markdown = synthesize_local(packet, cadence="daily")
    elif args.local_synthesis:
        markdown = synthesize_local(packet, cadence="daily")
    else:
        prompt = build_daily_prompt(packet)
        try:
            markdown = synthesize_with_hermes(prompt)
        except Exception as exc:
            if args.fail_on_synthesis_error:
                print("[FATAL] Hermes synthesis failed: %s" % str(exc)[:500])
                print("[FATAL] Production CI will not publish a fallback report. Fix provider/model availability and rerun.")
                return 75
            print("[WARN] Hermes synthesis failed: %s" % str(exc)[:500])
            print("[WARN] Falling back to local synthesis so artifacts are still reviewable.")
            markdown = synthesize_local(packet, cadence="daily")

    errors = validate_output(markdown, surface="telegram")
    if errors:
        print("[WARN] Output quality issues: %s" % ", ".join(errors))

    html_text = render_html_report(markdown, packet, cadence="daily")
    markdown_path = save_markdown(markdown, date_str, cadence="daily")
    html_path = save_html(html_text, date_str, cadence="daily")
    score = quality_score(markdown)
    signal_ids = [s["id"] for s in packet.get("signals", [])]
    record_synthesis_run(conn, "daily", date_start, date_end, signal_ids, markdown_path, html_path, score)

    print("Markdown saved: %s" % markdown_path)
    print("HTML saved: %s" % html_path)
    print("Quality score: %.2f" % score)
    print("")
    print("=" * 60)
    print(render_telegram(markdown, date_str, markdown_path, html_path))
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
