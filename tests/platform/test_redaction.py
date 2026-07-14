"""Tests for process-output secret redaction."""

from cios.platform.redaction import redact_sensitive_text


def test_redact_sensitive_text_replaces_sensitive_values_only() -> None:
    text = "token=secret-token dsn=postgresql://user:password@db.local/cios status=failed"

    redacted = redact_sensitive_text(
        text,
        {
            "GEMINI_API_KEY": "secret-token",
            "CIOS_DATABASE_URL": "postgresql://user:password@db.local/cios",
            "CIOS_DELIVER_TENANT": "algolia",
        },
    )

    assert redacted == "token=[redacted] dsn=[redacted] status=failed"
