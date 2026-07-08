"""Claim ledger (argus-claim-ledger) -- tracks competitor claims over time.

Invariants:
  - A claim cannot be registered without at least one evidence URL
    (evidence-or-silence). Attempting it raises.
  - Registering a claim that matches an existing one bumps its repetition
    count and merges evidence, rather than duplicating.
  - Supersedence is tracked, never destructive: superseding a claim links both
    directions and marks the old one inactive but keeps it.
  - Contradiction detection is deterministic first (same subject, incompatible
    assertion). An optional injected BrainModel enables an LLM contradiction
    check as an extension, used only when the deterministic check is
    inconclusive.

In-memory registry. No DB; the caller persists via injected repositories.
"""

from __future__ import annotations

import json
import re
from typing import Optional

from cios.platform.models.types import ModelRequest

from .prompts import CONTRADICTION_SYSTEM
from .types import BrainModel, Claim, Contradiction

# crude negation / polarity markers for the deterministic contradiction check.
_NEGATIONS = ("not", "no longer", "never", "without", "dropped", "removed", "discontinued")


class ClaimEvidenceError(ValueError):
    """Raised when a claim is registered with no evidence URL."""


class ClaimLedger:
    def __init__(self, model: Optional[BrainModel] = None) -> None:
        self._claims: dict[int, Claim] = {}
        self._next_id = 1
        self._model = model

    # -- registration ------------------------------------------------------

    def register(
        self,
        *,
        tenant_id: int,
        competitor_id: int,
        claim_text: str,
        evidence_urls: list[str],
        claim_type: Optional[str] = None,
        subject: Optional[str] = None,
        assertion: Optional[str] = None,
    ) -> Claim:
        urls = [u for u in (evidence_urls or []) if u]
        if not urls:
            raise ClaimEvidenceError(
                "a claim requires at least one evidence URL (evidence-or-silence)"
            )

        # merge into an existing identical claim instead of duplicating.
        existing = self._find_same(tenant_id, competitor_id, claim_text)
        if existing is not None:
            existing.repetition_count += 1
            existing.last_seen_at = _now()
            for u in urls:
                if u not in existing.evidence_urls:
                    existing.evidence_urls.append(u)
            return existing

        claim = Claim(
            id=self._next_id,
            tenant_id=tenant_id,
            competitor_id=competitor_id,
            claim_text=claim_text,
            claim_type=claim_type,
            subject=subject,
            assertion=assertion,
            evidence_urls=urls,
        )
        self._claims[self._next_id] = claim
        self._next_id += 1
        return claim

    def supersede(self, old_claim_id: int, new_claim: Claim) -> Claim:
        """Record that new_claim supersedes old_claim_id. Non-destructive: the
        old claim stays, marked inactive and linked."""
        old = self._claims.get(old_claim_id)
        if old is None:
            raise KeyError(f"no claim with id {old_claim_id}")
        old.active = False
        old.superseded_by_id = new_claim.id
        new_claim.supersedes_id = old_claim_id
        return new_claim

    # -- contradiction detection -------------------------------------------

    def find_contradictions(self) -> list[Contradiction]:
        """Deterministic pass over active claims sharing a subject."""
        found: list[Contradiction] = []
        active = [c for c in self._claims.values() if c.active and c.subject]
        for i in range(len(active)):
            for j in range(i + 1, len(active)):
                a, b = active[i], active[j]
                if a.competitor_id != b.competitor_id or a.subject != b.subject:
                    continue
                if self._deterministic_contradicts(a, b):
                    found.append(
                        Contradiction(
                            tenant_id=a.tenant_id,
                            competitor_id=a.competitor_id,
                            subject=a.subject or "",
                            claim_a_id=a.id or 0,
                            claim_b_id=b.id or 0,
                            detail=(
                                f"assertions differ on same subject: "
                                f"'{a.assertion or a.claim_text}' vs '{b.assertion or b.claim_text}'"
                            ),
                        )
                    )
        return found

    @staticmethod
    def _deterministic_contradicts(a: Claim, b: Claim) -> bool:
        # explicit assertion values that differ -> contradiction.
        if a.assertion is not None and b.assertion is not None:
            return a.assertion.strip().lower() != b.assertion.strip().lower()
        # else: polarity flip on otherwise similar claim text.
        a_neg = _has_negation(a.claim_text)
        b_neg = _has_negation(b.claim_text)
        return a_neg != b_neg

    async def llm_contradicts(self, a: Claim, b: Claim) -> Optional[Contradiction]:
        """Extension: ask the injected model whether two claims contradict.
        Returns a Contradiction (method='llm') or None. Requires a model."""
        if self._model is None:
            return None
        request = ModelRequest(
            task_profile="brain.contradiction",
            capability_needs=["needs_json_mode"],
            tenant_id=str(a.tenant_id),
            messages=[
                {"role": "system", "content": CONTRADICTION_SYSTEM},
                {
                    "role": "user",
                    "content": f"Claim A: {a.claim_text}\nClaim B: {b.claim_text}",
                },
            ],
        )
        response = await self._model.generate(request)
        parsed = None
        if getattr(response, "parsed_json", None):
            parsed = response.parsed_json
        else:
            try:
                parsed = json.loads((response.text or "").strip())
            except (json.JSONDecodeError, ValueError):
                return None
        if not isinstance(parsed, dict) or not parsed.get("contradicts"):
            return None
        return Contradiction(
            tenant_id=a.tenant_id,
            competitor_id=a.competitor_id,
            subject=a.subject or "",
            claim_a_id=a.id or 0,
            claim_b_id=b.id or 0,
            detail=str(parsed.get("reason") or "model flagged contradiction"),
            method="llm",
        )

    # -- lookups -----------------------------------------------------------

    def all_claims(self) -> list[Claim]:
        return list(self._claims.values())

    def active_claims(self) -> list[Claim]:
        return [c for c in self._claims.values() if c.active]

    def _find_same(self, tenant_id: int, competitor_id: int, claim_text: str) -> Optional[Claim]:
        norm = _normalize(claim_text)
        for c in self._claims.values():
            if (
                c.active
                and c.tenant_id == tenant_id
                and c.competitor_id == competitor_id
                and _normalize(c.claim_text) == norm
            ):
                return c
        return None


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _has_negation(text: str) -> bool:
    lowered = f" {text.lower()} "
    return any(f" {n} " in lowered for n in _NEGATIONS)


def _now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)
