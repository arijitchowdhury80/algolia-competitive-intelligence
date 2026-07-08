"""LLM half: synthesize a HorizonRead per horizon from ledger observations
plus optional external industry observations.

No DB, no network. The BrainModel Protocol (cios.brain.types.BrainModel) is
injected, same convention as cios.brain.cadence. External retrieval (news
RSS, analyst notes, ...) lives behind the IndustryFeed Protocol below --
implementations are NOT built in this module; it exists purely as the seam
a future feed plugs into without touching synthesis or connector logic.

Evidence rule: a theme is only ever labeled CONFIRMED when the model's own
proposed evidence_urls resolve to at least two distinct URLs drawn from the
input observations -- this is decided deterministically here, never taken
on the model's say-so.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Optional, Protocol

from pydantic import ValidationError

from cios.brain.quality import extract_json_object
from cios.brain.types import BrainModel
from cios.horizon.prompts import HORIZON_READ_SYSTEM, build_horizon_read_prompt
from cios.horizon.types import (
    Horizon,
    IndustryObservation,
    IndustryTheme,
    HorizonRead,
    RelevanceScore,
    ThemeConfidence,
)
from cios.platform.models.types import ModelRequest

logger = logging.getLogger("cios.horizon.industry")

TASK_PROFILE = "horizon.industry_read"
CONFIRMED_MIN_DISTINCT_SOURCES = 2


class MalformedHorizonOutput(RuntimeError):
    """Raised when the model returns unparseable/invalid JSON twice. Fail
    loud rather than fabricate a horizon read."""


class IndustryFeed(Protocol):
    """Injected external observation source (news RSS, analyst notes, ...).
    Not implemented in this module -- only the seam is defined here so the
    synthesizer does not need to change when a real feed is wired in."""

    def observations_in_window(
        self, tenant_id: int, start: date, end: date
    ) -> list[IndustryObservation]: ...


def _parse(response: Any) -> Optional[dict[str, Any]]:
    if getattr(response, "parsed_json", None):
        obj = response.parsed_json
        return obj if isinstance(obj, dict) else None
    text = (getattr(response, "text", "") or "").strip()
    if not text:
        return None
    return extract_json_object(text)


def _vet_theme(cand: Any, allowed_urls: set[str]) -> Optional[IndustryTheme]:
    if not isinstance(cand, dict):
        return None
    theme_text = (cand.get("theme") or "").strip()
    if not theme_text:
        return None
    urls = [u for u in (cand.get("evidence_urls") or []) if isinstance(u, str) and u]
    urls = [u for u in urls if u in allowed_urls]
    if not urls:
        # Evidence-or-silence: a theme with no grounded evidence is dropped
        # outright, not demoted to unconfirmed.
        return None
    confidence = (
        ThemeConfidence.CONFIRMED
        if len(set(urls)) >= CONFIRMED_MIN_DISTINCT_SOURCES
        else ThemeConfidence.SINGLE_SOURCE_UNCONFIRMED
    )
    try:
        return IndustryTheme(theme=theme_text, confidence=confidence, evidence_urls=urls)
    except ValidationError:
        return None


def _vet_movements(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [m.strip() for m in raw if isinstance(m, str) and m.strip()]


def _vet_relevance(raw: Any) -> Optional[RelevanceScore]:
    if not isinstance(raw, dict):
        return None
    try:
        score = float(raw.get("score"))
    except (TypeError, ValueError):
        return None
    score = max(0.0, min(1.0, score))
    rationale = (raw.get("rationale") or "").strip()
    if not rationale:
        return None
    try:
        return RelevanceScore(score=score, rationale=rationale)
    except ValidationError:
        return None


class HorizonSynthesizer:
    """Produces a HorizonRead for one horizon from ledger observations plus
    optional external IndustryFeed observations."""

    def __init__(self, model: BrainModel, feed: Optional[IndustryFeed] = None) -> None:
        self._model = model
        self._feed = feed

    async def synthesize(
        self,
        tenant_id: int,
        horizon: Horizon,
        as_of: date,
        ledger_observations: list[IndustryObservation],
        window: tuple[date, date],
    ) -> HorizonRead:
        external: list[IndustryObservation] = []
        if self._feed is not None:
            start, end = window
            external = self._feed.observations_in_window(tenant_id, start, end)

        observations = ledger_observations + external
        allowed_urls = {o.source_url for o in observations if o.source_url}

        if not observations:
            # Nothing to reason over -- an honest empty read, no model call.
            return HorizonRead(tenant_id=tenant_id, horizon=horizon, as_of=as_of)

        data_block = self._build_data_block(horizon, as_of, observations)
        raw = await self._call_model_with_retry(tenant_id, data_block)

        themes = [
            t for cand in raw.get("themes", []) if (t := _vet_theme(cand, allowed_urls)) is not None
        ]
        movements = _vet_movements(raw.get("notable_movements"))
        relevance = _vet_relevance(raw.get("relevance"))

        return HorizonRead(
            tenant_id=tenant_id,
            horizon=horizon,
            as_of=as_of,
            notable_movements=movements,
            themes=themes,
            relevance=relevance,
        )

    async def _call_model_with_retry(self, tenant_id: int, data_block: str) -> dict[str, Any]:
        prompt = build_horizon_read_prompt(data_block)
        for attempt in (1, 2):
            request = ModelRequest(
                task_profile=TASK_PROFILE,
                capability_needs=["needs_json_mode"],
                tenant_id=str(tenant_id),
                messages=[
                    {"role": "system", "content": HORIZON_READ_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
            )
            response = await self._model.generate(request)
            parsed = _parse(response)
            if parsed is not None:
                return parsed
            logger.warning("horizon read attempt %d returned unparseable JSON", attempt)
            prompt = (
                "Your previous reply was not valid JSON. Return ONLY the JSON "
                "object described, nothing else.\n\n" + build_horizon_read_prompt(data_block)
            )
        raise MalformedHorizonOutput(
            "model returned invalid JSON on both the initial call and the retry"
        )

    @staticmethod
    def _build_data_block(
        horizon: Horizon, as_of: date, observations: list[IndustryObservation]
    ) -> str:
        lines = [
            f"HORIZON: {horizon.value} ({horizon.days} days)",
            f"AS OF: {as_of.isoformat()}",
            "\nOBSERVATIONS THIS WINDOW:",
        ]
        for obs in observations:
            lines.append(
                f"  - [{obs.observed_at.isoformat()}] ({obs.kind}) {obs.summary}"
                f" (source={obs.source_url}; origin={obs.origin.value})"
            )
        urls = sorted({o.source_url for o in observations if o.source_url})
        lines.append("\nEVIDENCE URLS (only cite from this list):")
        lines.extend(f"  - {u}" for u in urls) if urls else lines.append("  (none)")
        return "\n".join(lines)
