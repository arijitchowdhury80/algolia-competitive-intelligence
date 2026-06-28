#!/usr/bin/env python3
"""Run the CI collector benchmark and write durable comparison artifacts."""

import argparse
import sys

from ci_core import CI_COLLECTOR_BENCHMARK_TARGETS, date_today, run_collector_benchmark


def parse_args():
    parser = argparse.ArgumentParser(description="Run CI collector benchmark")
    parser.add_argument("--date", help="Benchmark date (YYYY-MM-DD)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    date_str = args.date or date_today()
    out_dir = run_collector_benchmark(CI_COLLECTOR_BENCHMARK_TARGETS, date_str=date_str)
    print("Benchmark saved: %s" % out_dir)
    print("Comparison: %s" % (out_dir / "comparison.md"))
    print("JSON: %s" % (out_dir / "benchmark.json"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
