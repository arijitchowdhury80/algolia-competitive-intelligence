"""Competitor thesis engine (argus-competitor-thesis-engine) -- maintains a
living strategic thesis per competitor.

Rules:
  - A thesis updates ONLY when backed by new evidence ids (evidence-backed
    claims / deltas). An update attempt with no evidence is refused.
  - Every update is non-destructive: the prior thesis state is appended to
    history before the new text/confidence/status is written. History is never
    rewritten.
  - The thesis carries its confidence and the evidence ids that support it.

In-memory registry keyed by competitor id. No DB; caller persists via repos.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from cios.common.dedup import DEFAULT_SIMILARITY_THRESHOLD, token_set_similarity

from .types import Thesis, ThesisHistoryEntry


class ThesisEvidenceError(ValueError):
    """Raised when a thesis update carries no supporting evidence."""


def find_similar_active_thesis(
    active_theses: list[dict],
    *,
    competitor_id: int,
    candidate_thesis: str,
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> Optional[dict]:
    """Root-cause fix for "N near-identical theses per competitor": a
    competitor's living thesis should read as ONE evolving hypothesis, not a
    new row every time a repeat signal restates it. Given the tenant's
    currently active theses and a freshly drafted thesis sentence for
    `competitor_id`, returns the existing row a caller should attach new
    evidence to instead of spawning a duplicate -- or None if this is
    genuinely a new hypothesis for that competitor. Conservative by design
    (DEFAULT_SIMILARITY_THRESHOLD): only merges when the sentences are
    clearly paraphrases of the same claim, never across competitors."""
    for row in active_theses:
        if row.get("competitor_id") != competitor_id:
            continue
        if token_set_similarity(row.get("thesis", ""), candidate_thesis) >= threshold:
            return row
    return None


class ThesisEngine:
    def __init__(self) -> None:
        self._theses: dict[int, Thesis] = {}
        self._next_id = 1

    def get(self, competitor_id: int) -> Optional[Thesis]:
        return self._theses.get(competitor_id)

    def open_thesis(
        self,
        *,
        tenant_id: int,
        competitor_id: int,
        thesis: str,
        confidence: Optional[float],
        evidence_ids: list[str],
        open_questions: Optional[list[str]] = None,
    ) -> Thesis:
        """Create the first thesis for a competitor. Requires evidence."""
        if competitor_id in self._theses:
            raise ValueError(f"thesis already exists for competitor {competitor_id}; use update")
        self._require_evidence(evidence_ids)
        t = Thesis(
            id=self._next_id,
            tenant_id=tenant_id,
            competitor_id=competitor_id,
            thesis=thesis,
            confidence=confidence,
            evidence_ids=list(evidence_ids),
            open_questions=list(open_questions or []),
        )
        self._theses[competitor_id] = t
        self._next_id += 1
        return t

    def update(
        self,
        *,
        competitor_id: int,
        thesis: str,
        confidence: Optional[float],
        new_evidence_ids: list[str],
        status: Optional[str] = None,
        open_questions: Optional[list[str]] = None,
    ) -> Thesis:
        """Update a living thesis. Only proceeds with new evidence. Appends the
        prior state to history (non-destructive) and merges evidence ids."""
        current = self._theses.get(competitor_id)
        if current is None:
            raise KeyError(f"no thesis for competitor {competitor_id}; open one first")
        self._require_evidence(new_evidence_ids)

        # snapshot the prior state into history before mutating.
        current.history.append(
            ThesisHistoryEntry(
                thesis=current.thesis,
                confidence=current.confidence,
                status=current.status,
                evidence_ids=list(current.evidence_ids),
            )
        )

        current.thesis = thesis
        current.confidence = confidence
        if status is not None:
            current.status = status
        if open_questions is not None:
            current.open_questions = list(open_questions)
        for eid in new_evidence_ids:
            if eid not in current.evidence_ids:
                current.evidence_ids.append(eid)
        current.updated_at = datetime.now(timezone.utc)
        return current

    @staticmethod
    def _require_evidence(evidence_ids: list[str]) -> None:
        if not [e for e in (evidence_ids or []) if e]:
            raise ThesisEvidenceError(
                "a thesis update requires at least one supporting evidence id"
            )
