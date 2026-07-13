from __future__ import annotations

from tests.integration.conftest import _schema_reset_safety_error


def test_schema_reset_requires_explicit_test_opt_in() -> None:
    reason = _schema_reset_safety_error(
        "postgresql://postgres:secret@127.0.0.1:5433/cios",
        env={},
    )

    assert reason is not None
    assert "CIOS_ALLOW_SCHEMA_RESET_FOR_TESTS=1" in reason


def test_schema_reset_refuses_non_loopback_hosts_even_with_opt_in() -> None:
    reason = _schema_reset_safety_error(
        "postgresql://postgres:secret@prod.example.com:5432/cios",
        env={"CIOS_ALLOW_SCHEMA_RESET_FOR_TESTS": "1"},
    )

    assert reason is not None
    assert "loopback" in reason


def test_schema_reset_allows_explicit_loopback_test_dsn() -> None:
    reason = _schema_reset_safety_error(
        "postgresql://postgres:secret@127.0.0.1:5433/cios",
        env={"CIOS_ALLOW_SCHEMA_RESET_FOR_TESTS": "1"},
    )

    assert reason is None
