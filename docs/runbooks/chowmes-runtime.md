# Chowmes Runtime Runbook

## Role

Chowmes/Hermes is the operator and scheduler for CI. It runs daily and weekly workers, sends delivery messages, and can supervise quality through Athena.

## Required Environment

```bash
COMPETITIVE_RESEARCH_OUTPUT_ROOT=/path/to/artifacts/competitive-research
SCOUT_BASE_URL=http://127.0.0.1:8421
SCOUT_API_KEY=...
```

Do not print secrets in logs or reports.

## Commands

```bash
workers/daily-runner/run.sh --local-synthesis
workers/weekly-runner/run.sh --local-synthesis
workers/dashboard-runner/run.sh
python3 packages/ci-core/scripts/collector-benchmark.py
```

## Verification

```bash
python3 -m pytest packages/ci-core/tests -q
```

After changing live Chowmes env/config/session/gateway state, run the Chowmes health check from the ChowMes repository.

