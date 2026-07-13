"""Tests for the Scout command adapter."""

from __future__ import annotations

import json
import sys

import pytest

from cios.intelligence.scout_adapter import (
    ScoutCommandSpec,
    ScoutExecutionError,
    run_scout_export,
)


def test_run_scout_export_executes_command_and_loads_output_rows(tmp_path) -> None:
    output_path = tmp_path / "scout-output.json"
    command = [
        sys.executable,
        "-c",
        (
            "import json, sys; "
            "path = sys.argv[1]; "
            "open(path, 'w', encoding='utf-8').write(json.dumps(["
            "{'company_name':'Constructor','capability':'AI Shopping Agent'}"
            "]))"
        ),
        str(output_path),
    ]

    rows = run_scout_export(
        ScoutCommandSpec(command=command, output_path=output_path, timeout_seconds=5)
    )

    assert rows == [{"company_name": "Constructor", "capability": "AI Shopping Agent"}]


def test_run_scout_export_raises_when_command_exits_nonzero(tmp_path) -> None:
    output_path = tmp_path / "missing.json"
    command = [sys.executable, "-c", "import sys; sys.stderr.write('bad scout run'); sys.exit(7)"]

    with pytest.raises(ScoutExecutionError, match="failed with exit code 7"):
        run_scout_export(
            ScoutCommandSpec(command=command, output_path=output_path, timeout_seconds=5)
        )


def test_run_scout_export_raises_when_output_file_is_missing(tmp_path) -> None:
    output_path = tmp_path / "missing.json"
    command = [sys.executable, "-c", "print('completed without artifact')"]

    with pytest.raises(ScoutExecutionError, match="did not create expected output"):
        run_scout_export(
            ScoutCommandSpec(command=command, output_path=output_path, timeout_seconds=5)
        )


def test_run_scout_export_raises_when_command_times_out(tmp_path) -> None:
    output_path = tmp_path / "late.json"
    command = [sys.executable, "-c", "import time; time.sleep(1)"]

    with pytest.raises(ScoutExecutionError, match="timed out"):
        run_scout_export(
            ScoutCommandSpec(command=command, output_path=output_path, timeout_seconds=0.01)
        )
