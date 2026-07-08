"""Competitor research: company + domain in, evidence-grounded competitor
candidates out.

The LLM proposes candidates; a deterministic vetting pass (dedup by domain,
exclude the tenant's own domain, cap the set) is the actual gate -- the model
never gets to decide the final list size or duplicate entries. Rule 1 (no
vendor literals): the prompt below carries no fixed vendor/vertical
vocabulary, only the request's own company_name/domain/vertical_hint.
"""

from __future__ import annotations

import json
import re
from typing import Optional, Protocol
from urllib.parse import urlsplit

from cios.brain.types import BrainModel
from cios.onboard.types import CompetitorCandidate, OnboardRequest
from cios.platform.models.types import ModelRequest

DEFAULT_CANDIDATE_CAP = 8

RESEARCH_SYSTEM = """\
You are a competitive-intelligence researcher. Given a company's name and
domain, propose its REAL head-to-head competitors -- companies that
genuinely compete for the same buyers, not adjacent or aspirational names.
For each competitor give a one-line evidence-grounded reason ("why"): a
concrete, checkable fact about why they compete (same buyer, same category,
documented rivalry, market overlap), never a generic platitude. Never
propose the company itself as its own competitor.

Return ONLY strict JSON, no prose, no markdown fences:
{"competitors": [{"name": str, "domain": str | null, "why": str}, ...]}
"""


def _domain_of(url_or_domain: Optional[str]) -> Optional[str]:
    if not url_or_domain:
        return None
    candidate = url_or_domain.strip()
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    host = urlsplit(candidate).netloc.lower()
    return host[4:] if host.startswith("www.") else host or None


class WebEvidence(Protocol):
    """Optional injected grounding source for competitor claims. Not
    implemented here (no network in this core module) -- a real
    implementation lives outside src/cios/onboard and is supplied by the
    caller when stronger evidence-backing than the model's own knowledge is
    required."""

    def search(self, query: str) -> list[str]: ...  # returns evidence snippets/URLs


class CompetitorResearcher:
    """Proposes and deterministically vets a competitor set for one company."""

    def __init__(self, model: BrainModel, web_evidence: Optional[WebEvidence] = None) -> None:
        self._model = model
        self._web_evidence = web_evidence  # reserved for future grounding; unused today

    async def research(
        self, request: OnboardRequest, cap: int = DEFAULT_CANDIDATE_CAP
    ) -> list[CompetitorCandidate]:
        raw = await self._propose(request)
        return self.vet(raw, own_domain=request.domain, cap=cap)

    async def _propose(self, request: OnboardRequest) -> list[CompetitorCandidate]:
        data_lines = [f"Company: {request.company_name}", f"Domain: {request.domain}"]
        if request.vertical_hint:
            data_lines.append(f"Vertical hint: {request.vertical_hint}")
        if request.seed_competitors:
            data_lines.append(
                "Known competitors to confirm/extend (do not drop these without a "
                f"better reason): {', '.join(request.seed_competitors)}"
            )
        prompt = RESEARCH_SYSTEM + "\n\nDATA:\n" + "\n".join(data_lines)
        response = await self._model.generate(
            ModelRequest(
                task_profile="onboard_competitor_research",
                capability_needs=["needs_json_mode"],
                prompt=prompt,
            )
        )
        obj = _extract_json_object(response.parsed_json if response.parsed_json else response.text)
        if not isinstance(obj, dict):
            return []
        raw_list = obj.get("competitors")
        if not isinstance(raw_list, list):
            return []
        out: list[CompetitorCandidate] = []
        for item in raw_list:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            why = item.get("why")
            if not name or not why:
                continue
            out.append(CompetitorCandidate(name=str(name), domain=item.get("domain"), why=str(why)))
        return out

    def vet(
        self, raw: list[CompetitorCandidate], own_domain: str, cap: int = DEFAULT_CANDIDATE_CAP
    ) -> list[CompetitorCandidate]:
        """Deterministic gate: dedup by domain (falls back to lowercased name
        when a candidate has no domain), drop the tenant's own domain, cap
        the set. Order is preserved (first proposal wins a dedup collision)."""
        own = _domain_of(own_domain)
        seen: set[str] = set()
        vetted: list[CompetitorCandidate] = []
        for candidate in raw:
            key = _domain_of(candidate.domain) or candidate.name.strip().lower()
            if not key:
                continue
            if own and key == own:
                continue
            if key in seen:
                continue
            seen.add(key)
            vetted.append(candidate)
            if len(vetted) >= cap:
                break
        return vetted


def _extract_json_object(text_or_obj) -> Optional[dict]:
    if isinstance(text_or_obj, dict):
        return text_or_obj
    text = text_or_obj or ""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
