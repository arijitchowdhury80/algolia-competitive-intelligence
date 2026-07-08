"""Compiles BrandObservations into a BrandPositionRead via an injected
BrainModel -- same Protocol as src/cios/brain (BrainModel.generate), so a
router-backed adapter or an in-memory fake is interchangeable across brain
and ownbrand callers.

Prompt lives in this module and is domain-agnostic: the tenant name and all
observation text are supplied only through the DATA block built at runtime,
never as literals in the template strings (same rule as brain/prompts.py).

Evidence-or-silence, extended to the tenant's own position: every theme must
cite the observation URL(s) it is grounded in. A theme the model proposes
with no matching observation is dropped, not repaired -- the deterministic
guard in BrandTheme's validator (types.py) makes this impossible to
construct silently, so this module treats a validation failure as "drop and
log," never as "coerce and ship."
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from pydantic import ValidationError

from cios.platform.models.types import ModelRequest
from cios.brain.quality import extract_json_object
from cios.brain.types import BrainModel
from cios.ownbrand.types import BrandObservation, BrandPositionRead, BrandTheme

logger = logging.getLogger("cios.ownbrand.position")

POSITION_TASK_PROFILE = "ownbrand.position"

POSITION_SYSTEM = """\
You compile how a company is currently positioning its own brand, based ONLY
on statements pulled from that company's own sources (blog, newsroom,
changelog, press releases) and third-party mentions (review sites, analyst
coverage). You have no fixed domain of your own -- the company and its
observations are whatever the DATA block tells you.

Hard rules:
1. Evidence or silence. Every theme you name MUST cite at least one
   observation URL from the OBSERVATION URLS list you are given. If you
   cannot ground a theme in a supplied observation, do not name it.
2. No invention. Do not infer a positioning theme that is not actually
   stated or clearly shown in the supplied observations.
3. Gaps must also be evidence-grounded: a "gap versus competitors" claim
   must reference what the tenant's own observations show (or conspicuously
   do not show) -- never a general market assumption.
4. No em dashes in any text you write. Use plain sentences.
"""

POSITION_OUTPUT_CONTRACT = """\
Return ONLY a single JSON object, no prose before or after, matching exactly:

{
  "themes": [
    {
      "label": "<short theme name, e.g. 'AI-native positioning'>",
      "summary": "<what the company is saying about itself on this theme>",
      "observation_urls": ["<url from OBSERVATION URLS>", "..."]
    }
  ],
  "gaps_vs_competitors": ["<short gap statement grounded in the observations>"]
}

If there is not enough evidence for any theme, return {"themes": [], "gaps_vs_competitors": []}.
"""


def _build_data_block(tenant_company_name: str, observations: list[BrandObservation]) -> str:
    lines = [f"TENANT COMPANY: {tenant_company_name}", "", "OBSERVATIONS:"]
    for obs in observations:
        lines.append(f"- ({obs.source_type.value}) \"{obs.quote}\" -- {obs.source_url}")
    lines.append("")
    lines.append("OBSERVATION URLS:")
    for url in sorted({obs.source_url for obs in observations}):
        lines.append(f"- {url}")
    return "\n".join(lines)


class MalformedPositionOutput(RuntimeError):
    """Raised when the model returns unparseable JSON twice. Fail loud rather
    than fabricate a position read (evidence-or-silence extends here too)."""


class BrandPositionCompiler:
    def __init__(self, model: BrainModel) -> None:
        self._model = model

    async def compile(
        self, tenant_id: int, tenant_company_name: str, observations: list[BrandObservation]
    ) -> BrandPositionRead:
        if not observations:
            # No evidence at all: an empty, honest read -- never a
            # fabricated "here's how the brand is positioned" narrative.
            return BrandPositionRead(
                tenant_id=tenant_id,
                tenant_company_name=tenant_company_name,
                observations_considered=0,
            )

        allowed_urls = {obs.source_url for obs in observations}
        raw = await self._call_model_with_retry(tenant_company_name, observations)

        themes: list[BrandTheme] = []
        for cand in raw.get("themes", []):
            theme = self._vet_theme(cand, allowed_urls)
            if theme is not None:
                themes.append(theme)

        gaps = [g for g in raw.get("gaps_vs_competitors", []) if isinstance(g, str) and g.strip()]

        return BrandPositionRead(
            tenant_id=tenant_id,
            tenant_company_name=tenant_company_name,
            themes=themes,
            gaps_vs_competitors=gaps,
            observations_considered=len(observations),
        )

    async def _call_model_with_retry(
        self, tenant_company_name: str, observations: list[BrandObservation]
    ) -> dict[str, Any]:
        data_block = _build_data_block(tenant_company_name, observations)
        prompt = POSITION_OUTPUT_CONTRACT + "\n\n=== INPUT ===\n" + data_block

        for _attempt in (1, 2):
            request = ModelRequest(
                task_profile=POSITION_TASK_PROFILE,
                capability_needs=["needs_json_mode"],
                messages=[
                    {"role": "system", "content": POSITION_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
            )
            response = await self._model.generate(request)
            if getattr(response, "parsed_json", None) and isinstance(response.parsed_json, dict):
                return response.parsed_json
            parsed = extract_json_object(getattr(response, "text", "") or "")
            if parsed is not None:
                return parsed
            prompt = prompt + "\n\nReturn ONLY the JSON object, nothing else."

        raise MalformedPositionOutput("BrainModel returned unparseable output twice")

    @staticmethod
    def _vet_theme(cand: Any, allowed_urls: set[str]) -> Optional[BrandTheme]:
        if not isinstance(cand, dict):
            return None
        urls = [u for u in cand.get("observation_urls", []) if u in allowed_urls]
        if not urls:
            logger.info("ownbrand: dropping theme with no valid observation URL: %r", cand)
            return None
        try:
            return BrandTheme(
                label=cand.get("label", ""),
                summary=cand.get("summary", ""),
                observation_urls=urls,
            )
        except ValidationError:
            logger.info("ownbrand: dropping malformed theme candidate: %r", cand)
            return None
