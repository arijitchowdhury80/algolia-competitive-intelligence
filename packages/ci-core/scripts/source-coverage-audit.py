#!/usr/bin/env python3
"""Source coverage audit for the competitive intelligence ledger."""

import argparse
import json
import sys

from ci_core import (
    DB_PATH,
    connect_db,
    date_today,
    date_window,
    flatten_sources,
    get_source_coverage,
    load_sources,
    upsert_sources,
)


def parse_args():
    parser = argparse.ArgumentParser(description="Audit competitive research source coverage")
    parser.add_argument("--date", help="End date for audit window (YYYY-MM-DD)")
    parser.add_argument("--days", type=int, default=7, help="Window length")
    parser.add_argument("--json", action="store_true", help="Print full JSON audit")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    end_date = args.date or date_today()
    start_date, end_date = date_window(end_date, args.days)
    conn = connect_db()
    source_records = flatten_sources(load_sources())
    upsert_sources(conn, source_records)
    coverage = get_source_coverage(conn, start_date, end_date)
    totals = coverage["totals"]
    print("=== Source coverage audit: %s to %s ===" % (start_date, end_date))
    print("SQLite ledger: %s" % DB_PATH)
    print(
        "enabled={enabled_sources} checked={checked_sources} ok={successful_sources} "
        "failed={failed_sources} missing={missing_sources} snapshots={snapshots_in_window} "
        "signal_sources={signal_sources} changed_sources={changed_signal_sources}".format(**totals)
    )
    if args.json:
        print(json.dumps(coverage, indent=2, default=str))
        return 0
    problem_rows = [
        row for row in coverage["sources"]
        if row["status"] != "ok" or int(row.get("changed_signal_count") or 0) > 0
    ]
    if problem_rows:
        print("")
        print("Sources needing attention:")
        for row in problem_rows[:25]:
            reason = row.get("error") or (
                "changed signal stored" if int(row.get("changed_signal_count") or 0) > 0 else "not checked in this window"
            )
            print("- {competitor} [{status}] {url} - {reason}".format(
                competitor=row["competitor"],
                status=row["status"],
                url=row["url"],
                reason=str(reason)[:220],
            ))
    else:
        print("All enabled sources were checked successfully; no changed-source alerts in this window.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
