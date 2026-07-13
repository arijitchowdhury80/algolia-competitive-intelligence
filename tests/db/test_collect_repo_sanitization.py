from __future__ import annotations

import json

from cios.collect.types import ExtractedFact
from cios.db.repos.collect import _postgres_safe, _safe_fact_evidence_ids


def test_postgres_safe_removes_nul_characters_recursively() -> None:
    payload = {
        "text": "bad\x00text",
        "items": ["ok", "no\x00pe"],
        "nested": {"key\x00with-nul": "value\x00with-nul"},
    }

    safe = _postgres_safe(payload)

    assert "\x00" not in json.dumps(safe)
    assert safe["text"] == "badtext"
    assert safe["items"] == ["ok", "nope"]
    assert safe["nested"]["keywith-nul"] == "valuewith-nul"


def test_fact_evidence_payload_is_postgres_safe() -> None:
    fact = ExtractedFact(
        competitor_id=1,
        fact_type="positioning",
        statement="Constructor says\x00 agentic commerce.",
        fact_json={"raw": "Constructor\x00 raw payload"},
        evidence_text="Evidence has a NUL\x00 byte.",
        evidence_url="https://constructor.example/post",
    )

    evidence_ids = _safe_fact_evidence_ids(fact)

    assert "\x00" not in json.dumps(evidence_ids)
    assert evidence_ids[0]["text"] == "Evidence has a NUL byte."
