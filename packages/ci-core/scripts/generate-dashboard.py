#!/usr/bin/env python3
"""Generate the static CI Command Center dashboard from the SQLite ledger."""

import argparse
import sys

from ci_core import connect_db, date_today, date_window, render_dashboard_html, save_dashboard_html


def parse_args():
    parser = argparse.ArgumentParser(description="Generate CI dashboard HTML")
    parser.add_argument("--date", help="End date for dashboard window (YYYY-MM-DD)")
    parser.add_argument("--days", type=int, default=7, help="Dashboard source-health/signal window")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    end_date = args.date or date_today()
    start_date, end_date = date_window(end_date, args.days)
    conn = connect_db()
    html = render_dashboard_html(conn, start_date, end_date)
    path = save_dashboard_html(html)
    print("Dashboard saved: %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
