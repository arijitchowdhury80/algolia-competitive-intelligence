"""Landing page generator: turns a Prescription into a complete,
self-contained marketing landing page HTML document.

Pipeline: injected BrainModel produces structured content JSON (hero, proof
points, CTA) -> deterministic vetting against the prescription's evidence
URLs -> deterministic HTML assembly from the vetted JSON. The model never
touches HTML; it only ever returns content, so injection and layout are
fully controlled here (stdlib only, html.escape everything, brand tokens
applied via CSS custom properties, no external JS/CSS).

Evidence rule (same invariant as brain/prescribe): any claim that names a
specific entity (a competitor, a proper noun) without a matching evidence
URL drawn from the prescription's own grounding is unverifiable. Rather than
silently ship it or silently drop it, the asset is flagged
review_status=needs_verification so a human decides -- never auto-published,
never silently shipped (Addendum 2 point 4).
"""

from __future__ import annotations

import html
import re
from typing import Any, Optional

from pydantic import ValidationError

from cios.brain.quality import extract_json_object
from cios.brain.types import BrainModel
from cios.platform.models.types import ModelRequest

from .prompts import LANDING_PAGE_SYSTEM, build_landing_page_prompt
from .types import BrandTokens, CollateralAsset, CollateralKind, CollateralRequest, ReviewStatus

TASK_PROFILE = "collateral.landing_page"

# Heuristic for "names a specific entity" that stays domain-agnostic: any
# capitalized word that isn't a generic sentence-starting pronoun/determiner.
# This catches company/product/brand names without any fixed vendor
# vocabulary. Not a substitute for evidence -- only a trigger for the
# evidence-or-flag check below.
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9']*")
_GENERIC_CAPITALIZED_WORDS = {
    "we", "our", "you", "your", "this", "that", "it", "they", "i", "the",
    "a", "an", "no", "see", "return", "learn", "get", "start", "why",
    "how", "what", "when", "where",
}


class MalformedLandingPageOutput(RuntimeError):
    """Raised when the model returns unparseable/invalid JSON twice. Fail
    loud rather than fabricate landing page copy."""


def _looks_entity_named(claim: str) -> bool:
    """True if `claim` contains what looks like a named entity (domain-
    agnostic proxy for 'names a competitor/company/product'): a capitalized
    word that is not a generic sentence-starting pronoun or determiner."""
    for match in _WORD.finditer(claim):
        word = match.group(0)
        if word[0].isupper() and word.lower() not in _GENERIC_CAPITALIZED_WORDS:
            return True
    return False


def _build_data_block(prescription: Any, brand: BrandTokens) -> str:
    g = prescription.grounding
    lines = [
        f"COMPANY: {brand.company_name}",
        f"PLAY: {prescription.title}",
        "STEPS:",
    ]
    lines.extend(f"  - {step}" for step in prescription.play)
    lines.append(f"EXPECTED EFFECT: {prescription.expected_effect}")
    lines.append(f"URGENCY: {prescription.urgency_window.value}")
    urls = sorted(set(g.evidence_urls))
    lines.append("\nEVIDENCE URLS (only cite from this list):")
    lines.extend(f"  - {u}" for u in urls) if urls else lines.append("  (none)")
    return "\n".join(lines)


def _e(value: Optional[object]) -> str:
    if value is None:
        return ""
    return html.escape(str(value))


def _render_html(content: dict[str, Any], brand: BrandTokens, prescription: Any) -> str:
    proof_html = "".join(
        f"""<div class="proof-point"><p>{_e(p.get("claim"))}</p>{
            f'<a class="proof-source" href="{_e(p.get("evidence_url"))}">Source</a>' if p.get("evidence_url") else ""
        }</div>"""
        for p in content.get("proof_points", [])
    )
    logo_html = (
        f'<img class="logo" src="{_e(brand.logo_url)}" alt="{_e(brand.company_name)} logo">'
        if brand.logo_url
        else f'<div class="logo-text">{_e(brand.company_name)}</div>'
    )
    style = f"""
    :root {{
      --brand-primary: {_e(brand.primary_color)};
      --brand-secondary: {_e(brand.secondary_color)};
      --brand-accent: {_e(brand.accent_color)};
      font-family: {_e(brand.font_family)};
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #f6f8fc; color: var(--brand-secondary); font-family: inherit; }}
    .shell {{ max-width: 960px; margin: 0 auto; padding: 32px 24px; }}
    .brand-bar {{ display: flex; align-items: center; margin-bottom: 32px; }}
    .logo {{ max-height: 32px; }}
    .logo-text {{ font-weight: 900; font-size: 20px; color: var(--brand-primary); }}
    .hero {{ padding: 40px 32px; border-radius: 12px; background: white; border-top: 5px solid var(--brand-primary); box-shadow: 0 12px 30px rgba(6,19,63,.08); }}
    .hero h1 {{ margin: 0 0 12px; font-size: clamp(28px, 4vw, 46px); color: var(--brand-secondary); }}
    .hero p {{ font-size: 18px; line-height: 1.5; }}
    .proof-grid {{ display: grid; gap: 16px; margin: 32px 0; }}
    .proof-point {{ padding: 16px; border-radius: 8px; background: white; border: 1px solid #d9e1ef; }}
    .proof-source {{ font-size: 12px; color: var(--brand-primary); }}
    .cta {{ text-align: center; padding: 32px; border-radius: 12px; background: var(--brand-primary); color: white; }}
    .cta .label {{ display: inline-block; padding: 12px 28px; border-radius: 999px; background: white; color: var(--brand-primary); font-weight: 850; }}
    .cta .subtext {{ margin-top: 12px; opacity: .9; }}
    """
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_e(content.get("hero_headline")) or _e(prescription.title)}</title>
  <style>{style}</style>
</head>
<body>
  <main class="shell">
    <div class="brand-bar">{logo_html}</div>
    <section class="hero">
      <h1>{_e(content.get("hero_headline"))}</h1>
      <p>{_e(content.get("hero_subheadline"))}</p>
    </section>
    <section class="proof-grid">
      {proof_html}
    </section>
    <section class="cta">
      <div class="label">{_e(content.get("cta_label")) or "Learn more"}</div>
      <div class="subtext">{_e(content.get("cta_subtext"))}</div>
    </section>
  </main>
</body>
</html>
"""


def _parse(response: Any) -> Optional[dict[str, Any]]:
    if getattr(response, "parsed_json", None):
        obj = response.parsed_json
        return obj if isinstance(obj, dict) else None
    text = (getattr(response, "text", "") or "").strip()
    if not text:
        return None
    return extract_json_object(text)


class LandingPageGenerator:
    """Generates a self-contained marketing landing page executing a
    Prescription, via an injected BrainModel."""

    def __init__(self, model: BrainModel) -> None:
        self._model = model

    async def generate(self, request: CollateralRequest) -> CollateralAsset:
        if request.kind is not CollateralKind.LANDING_PAGE:
            raise ValueError(
                f"LandingPageGenerator only handles {CollateralKind.LANDING_PAGE}, "
                f"got {request.kind}"
            )
        prescription = request.prescription
        brand = request.brand
        allowed_urls = set(prescription.grounding.evidence_urls)

        data_block = _build_data_block(prescription, brand)
        content = await self._call_model_with_retry(request.tenant_id, data_block)

        proof_points = content.get("proof_points") or []
        needs_verification = False
        for point in proof_points:
            if not isinstance(point, dict):
                needs_verification = True
                continue
            claim = str(point.get("claim") or "")
            evidence_url = str(point.get("evidence_url") or "")
            if evidence_url and evidence_url not in allowed_urls:
                # Fabricated evidence -- cited a URL never supplied.
                needs_verification = True
            if _looks_entity_named(claim) and evidence_url not in allowed_urls:
                # Names something specific but cites no evidence we can
                # trace back to this prescription's grounding.
                needs_verification = True

        rendered = _render_html(content, brand, prescription)

        try:
            return CollateralAsset(
                tenant_id=request.tenant_id,
                kind=CollateralKind.LANDING_PAGE,
                html=rendered,
                sources=sorted(allowed_urls),
                prescription_title=prescription.title,
                review_status=ReviewStatus.NEEDS_VERIFICATION if needs_verification else ReviewStatus.DRAFT,
            )
        except ValidationError as exc:
            raise MalformedLandingPageOutput(str(exc)) from exc

    async def _call_model_with_retry(self, tenant_id: int, data_block: str) -> dict[str, Any]:
        prompt = build_landing_page_prompt(data_block)
        for attempt in (1, 2):
            request = ModelRequest(
                task_profile=TASK_PROFILE,
                capability_needs=["needs_json_mode"],
                tenant_id=str(tenant_id),
                messages=[
                    {"role": "system", "content": LANDING_PAGE_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
            )
            response = await self._model.generate(request)
            parsed = _parse(response)
            if parsed is not None:
                return parsed
            prompt = (
                "Your previous reply was not valid JSON. Return ONLY the JSON "
                "object described, nothing else.\n\n" + build_landing_page_prompt(data_block)
            )
        raise MalformedLandingPageOutput(
            "model returned invalid JSON on both the initial call and the retry"
        )
