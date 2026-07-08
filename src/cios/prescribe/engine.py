"""The prescription engine: turns gathered intel into specific, gradeable
plays -- the Addendum 2 point 3 bar ("Not observations. Prescriptions.").

No DB, no network. BrainModel is injected (cios.brain.types.BrainModel).
Every deterministic guard here runs unconditionally, never trusting the
model's own claim about what it grounded a prescription in -- same
convention as cios.horizon.connector and cios.brain.cadence:
  - evidence-or-silence: a candidate citing any URL outside the caller-
    supplied allowed set, or a thesis id outside the supplied theses, is
    rejected outright (not trimmed or repaired).
  - materiality-before-urgency: candidates below the materiality floor are
    dropped before ranking.
  - no generic-AI-slop: a candidate whose title/play/expected_effect
    contains a banned platitude is rejected regardless of its evidence.
  - cap ~5/cycle: after vetting, candidates are ranked by
    urgency_window.weight * materiality_score and truncated.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from pydantic import ValidationError

from cios.brain.types import BrainModel, Signal, Thesis
from cios.horizon.types import DotConnection
from cios.ownbrand.types import BrandPositionRead
from cios.platform.models.types import ModelRequest

from .prompts import BANNED_PLATITUDES, PRESCRIPTION_SYSTEM, build_prescription_prompt
from .types import Effort, Grounding, Prescription, Team, UrgencyWindow

logger = logging.getLogger("cios.prescribe.engine")

TASK_PROFILE = "prescribe.engine"
DEFAULT_MATERIALITY_FLOOR = 0.35
DEFAULT_MAX_PER_CYCLE = 5


class MalformedPrescriptionOutput(RuntimeError):
    """Raised when the model returns unparseable/invalid JSON twice. Fail
    loud rather than fabricate a prescription."""


def _parse(response: Any) -> Optional[dict[str, Any]]:
    if getattr(response, "parsed_json", None):
        obj = response.parsed_json
        return obj if isinstance(obj, dict) else None
    text = (getattr(response, "text", "") or "").strip()
    if not text:
        return None
    from cios.brain.quality import extract_json_object

    return extract_json_object(text)


def _contains_platitude(text: str) -> Optional[str]:
    lowered = text.lower()
    for phrase in BANNED_PLATITUDES:
        if phrase in lowered:
            return phrase
    return None


def _vet_prescription(
    cand: Any,
    tenant_id: int,
    allowed_urls: set[str],
    valid_thesis_ids: set[int],
    floor: float,
) -> Optional[Prescription]:
    if not isinstance(cand, dict):
        return None

    try:
        team = Team(cand.get("team"))
    except ValueError:
        logger.info("prescription rejected: invalid team %r", cand.get("team"))
        return None
    try:
        urgency = UrgencyWindow(cand.get("urgency_window"))
    except ValueError:
        logger.info("prescription rejected: invalid urgency_window %r", cand.get("urgency_window"))
        return None
    try:
        effort = Effort(cand.get("effort"))
    except ValueError:
        logger.info("prescription rejected: invalid effort %r", cand.get("effort"))
        return None

    title = (cand.get("title") or "").strip()
    play = [s.strip() for s in (cand.get("play") or []) if isinstance(s, str) and s.strip()]
    expected_effect = (cand.get("expected_effect") or "").strip()
    if not title or not play or not expected_effect:
        logger.info("prescription rejected: missing title/play/expected_effect")
        return None

    # Banned-platitude check: run over everything reader-facing, regardless
    # of what evidence the candidate cites -- a specific-looking source
    # attached to a generic play is still a generic play.
    platitude = _contains_platitude(" ".join([title, *play, expected_effect]))
    if platitude:
        logger.info("prescription rejected: banned platitude %r", platitude)
        return None

    try:
        materiality_score = float(cand.get("materiality_score"))
    except (TypeError, ValueError):
        materiality_score = 0.0
    if materiality_score < floor:
        logger.info("prescription rejected: materiality %.3f below floor %.3f", materiality_score, floor)
        return None

    signal_urls = [u for u in (cand.get("signal_evidence_urls") or []) if isinstance(u, str) and u]
    connection_urls = [
        u for u in (cand.get("connection_evidence_urls") or []) if isinstance(u, str) and u
    ]
    evidence_urls = [u for u in (cand.get("evidence_urls") or []) if isinstance(u, str) and u]
    thesis_ids = [t for t in (cand.get("thesis_ids") or []) if isinstance(t, int)]

    # Zero-tolerance fabrication guard: any proposed URL/id outside the
    # caller-supplied allowed sets voids the whole candidate rather than
    # being silently trimmed.
    for urls in (signal_urls, connection_urls, evidence_urls):
        if any(u not in allowed_urls for u in urls):
            logger.info("prescription rejected: cited evidence URL not in allowed set")
            return None
    if any(t not in valid_thesis_ids for t in thesis_ids):
        logger.info("prescription rejected: cited thesis id not in supplied theses")
        return None

    try:
        grounding = Grounding(
            signal_evidence_urls=signal_urls,
            connection_evidence_urls=connection_urls,
            thesis_ids=thesis_ids,
            evidence_urls=evidence_urls,
        )
        return Prescription(
            tenant_id=tenant_id,
            title=title,
            play=play,
            team=team,
            urgency_window=urgency,
            grounding=grounding,
            expected_effect=expected_effect,
            effort=effort,
            materiality_score=materiality_score,
        )
    except ValidationError as exc:
        logger.info("prescription rejected: schema validation failed: %s", exc)
        return None


class PrescriptionEngine:
    """Given this cycle's signals, horizon connections, own-brand position,
    and standing theses, produces a ranked, capped list of Prescriptions."""

    def __init__(
        self,
        model: BrainModel,
        materiality_floor: float = DEFAULT_MATERIALITY_FLOOR,
        max_per_cycle: int = DEFAULT_MAX_PER_CYCLE,
    ) -> None:
        self._model = model
        self._floor = materiality_floor
        self._max_per_cycle = max_per_cycle

    async def prescribe(
        self,
        tenant_id: int,
        signals: list[Signal],
        connections: Optional[list[DotConnection]] = None,
        theses: Optional[list[Thesis]] = None,
        brand_position: Optional[BrandPositionRead] = None,
    ) -> list[Prescription]:
        connections = connections or []
        theses = theses or []

        allowed_urls = self._allowed_urls(signals, connections, brand_position)
        valid_thesis_ids = {t.id for t in theses if t.id is not None}

        if not allowed_urls and not valid_thesis_ids:
            return []

        data_block = self._build_data_block(signals, connections, theses, brand_position)
        raw = await self._call_model_with_retry(tenant_id, data_block)

        candidates = [
            p
            for cand in raw.get("prescriptions", [])
            if (p := _vet_prescription(cand, tenant_id, allowed_urls, valid_thesis_ids, self._floor))
            is not None
        ]
        candidates.sort(key=lambda p: p.rank_score, reverse=True)
        return candidates[: self._max_per_cycle]

    @staticmethod
    def _allowed_urls(
        signals: list[Signal],
        connections: list[DotConnection],
        brand_position: Optional[BrandPositionRead],
    ) -> set[str]:
        urls: set[str] = set()
        urls.update(u for s in signals for u in s.evidence_urls if u)
        for c in connections:
            urls.update(u for u in c.signal_evidence_urls if u)
            urls.update(u for u in c.horizon_evidence_urls if u)
        if brand_position is not None:
            for theme in brand_position.themes:
                urls.update(u for u in theme.observation_urls if u)
        return urls

    async def _call_model_with_retry(self, tenant_id: int, data_block: str) -> dict[str, Any]:
        prompt = build_prescription_prompt(data_block)
        for attempt in (1, 2):
            request = ModelRequest(
                task_profile=TASK_PROFILE,
                capability_needs=["needs_json_mode"],
                tenant_id=str(tenant_id),
                messages=[
                    {"role": "system", "content": PRESCRIPTION_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
            )
            response = await self._model.generate(request)
            parsed = _parse(response)
            if parsed is not None:
                return parsed
            logger.warning("prescription engine attempt %d returned unparseable JSON", attempt)
            prompt = (
                "Your previous reply was not valid JSON. Return ONLY the JSON "
                "object described, nothing else.\n\n" + build_prescription_prompt(data_block)
            )
        raise MalformedPrescriptionOutput(
            "model returned invalid JSON on both the initial call and the retry"
        )

    @staticmethod
    def _build_data_block(
        signals: list[Signal],
        connections: list[DotConnection],
        theses: list[Thesis],
        brand_position: Optional[BrandPositionRead],
    ) -> str:
        lines: list[str] = ["THIS CYCLE'S SIGNALS:"]
        if signals:
            for s in signals:
                lines.append(
                    f"  - [{s.signal_type}] {s.headline}: {s.what_changed}"
                    f" (team={s.team_to_involve}; evidence={s.evidence_urls})"
                )
        else:
            lines.append("  (none)")

        lines.append("\nHORIZON CONNECTIONS:")
        if connections:
            for c in connections:
                lines.append(
                    f"  - [{c.horizon.value}] {c.connection}"
                    f" (signal_evidence={c.signal_evidence_urls};"
                    f" horizon_evidence={c.horizon_evidence_urls})"
                )
        else:
            lines.append("  (none)")

        lines.append("\nSTANDING THESES:")
        if theses:
            for t in theses:
                lines.append(f"  - id={t.id}: {t.thesis} (status={t.status})")
        else:
            lines.append("  (none)")

        lines.append("\nOWN-BRAND POSITION:")
        if brand_position is not None and brand_position.themes:
            for theme in brand_position.themes:
                lines.append(
                    f"  - {theme.label}: {theme.summary} (evidence={theme.observation_urls})"
                )
            if brand_position.gaps_vs_competitors:
                lines.append("  Gaps vs competitors:")
                lines.extend(f"    - {g}" for g in brand_position.gaps_vs_competitors)
        else:
            lines.append("  (none)")

        allowed = sorted(
            {u for s in signals for u in s.evidence_urls if u}
            | {u for c in connections for u in c.signal_evidence_urls if u}
            | {u for c in connections for u in c.horizon_evidence_urls if u}
            | (
                {u for theme in brand_position.themes for u in theme.observation_urls if u}
                if brand_position is not None
                else set()
            )
        )
        lines.append("\nEVIDENCE URLS (only cite from this list):")
        lines.extend(f"  - {u}" for u in allowed) if allowed else lines.append("  (none)")

        valid_thesis_ids = sorted(t.id for t in theses if t.id is not None)
        lines.append("\nTHESIS IDS (only cite from this list):")
        lines.extend(f"  - {i}" for i in valid_thesis_ids) if valid_thesis_ids else lines.append(
            "  (none)"
        )
        return "\n".join(lines)
