"""Semantic extraction: content hashing, semantic-line segmentation, and
narrative/customer-proof fact + delta extraction.

Ported faithfully from docs/workspace/v0-reference/ci_core.py, which was
prod-hotfixed (semantic_lines long-line segmentation, expanded
infer_content_topic/is_content_source, multi-fact extraction up to 8/source,
GENERIC_NARRATIVE_TITLE filter) and is proven live. Do not "improve" this
logic without a corresponding V0 change -- behavior parity is the contract.

One intentional adaptation: V0 emitted a bare "publish" quality_status string
into its own sqlite schema. Our schema.sql semantic_deltas CHECK constraint
requires 'published' (not 'publish') and enforces evidence_ids on publish.
This module scores and stages a delta as "review" when V0 would have said
"publish"; the runner promotes it to "published" once real evidence_ids are
attached at persistence. Materiality scoring itself is unchanged.
"""

from __future__ import annotations

import difflib
import html
import hashlib
import json
import re
from urllib.parse import urlparse

from cios.collect.types import Delta, ExtractedFact, SourceContext

# ---------------------------------------------------------------------------
# Text normalization + hashing
# ---------------------------------------------------------------------------


def clean_generated_text(text: str) -> str:
    return (
        (text or "")
        .replace("—", "-")
        .replace("–", "-")
        .replace("→", "->")
        .replace(" ", " ")
    )


def normalize_text(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return clean_generated_text(text).strip()


def content_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def canonical_url(url: str) -> str:
    url = (url or "").strip()
    if url and not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.rstrip("/")


def normalize_identity(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def infer_competitor_from_url(url: str) -> str:
    host = urlparse(url).netloc.lower().replace("www.", "")
    labels = {
        "coveo": "Coveo",
        "bloomreach": "Bloomreach",
        "constructor": "Constructor",
        "google": "Google Vertex AI Search",
        "elastic": "Elastic",
        "meilisearch": "Meilisearch",
        "typesense": "Typesense",
        "perplexity": "Perplexity AI",
        "openai": "OpenAI / ChatGPT",
        "algolia": "Algolia",
    }
    for key, label in labels.items():
        if key in host:
            return label
    return host or "Unknown"


# ---------------------------------------------------------------------------
# Boilerplate / diff filtering
# ---------------------------------------------------------------------------


def is_boilerplate_diff(text: str) -> bool:
    lower = normalize_text(text).lower()
    if not lower:
        return True
    nav_markers = [
        "contact us login",
        "login apac eu us uk canada",
        "partners rfp/rfi company",
        "facebook instagram linkedin",
        "privacy at",
        "schedule a demo",
        "product tours",
        "toggle navigation",
        "sign in appearance settings",
    ]
    marker_count = sum(1 for marker in nav_markers if marker in lower)
    if marker_count >= 2:
        return True
    if re.search(r"\bcareers?\s+\d+\b", lower) and marker_count >= 1:
        return True
    if len(lower) > 500 and marker_count >= 1:
        return True
    return False


def split_signal_lines(text: str) -> list[str]:
    chunks = re.split(r"(?<=[.!?])\s+|\s{2,}", normalize_text(text))
    return [c.strip() for c in chunks if len(c.strip()) > 20][:800]


def diff_summary(old_text: str, new_text: str, max_lines: int = 14) -> str:
    old_lines = split_signal_lines(old_text)
    new_lines = split_signal_lines(new_text)
    diff = []
    for line in difflib.unified_diff(old_lines, new_lines, n=1, lineterm=""):
        if line.startswith("+") and not line.startswith("+++"):
            cleaned = line[1:].strip()
            if is_boilerplate_diff(cleaned):
                continue
            if cleaned and len(cleaned) > 20:
                diff.append(cleaned)
        if len(diff) >= max_lines:
            break
    return " | ".join(diff)[:1200]


def mostly_boilerplate_delta(old_text: str, new_text: str) -> bool:
    summary = diff_summary(old_text, new_text)
    if not summary:
        return True
    useful_keywords = [
        "customer", "case study", "ai", "search", "agent", "launch",
        "announce", "product discovery", "conversion", "revenue",
    ]
    return not any(keyword in summary.lower() for keyword in useful_keywords)


# ---------------------------------------------------------------------------
# Semantic line segmentation (patched: segments >240-char blob lines)
# ---------------------------------------------------------------------------


def semantic_lines(text: str) -> list[str]:
    lines: list[str] = []
    # Many collectors store page text as a single whitespace-collapsed blob with
    # no newlines. A line-oriented extractor sees one giant "line" and finds no
    # facts. Segment long blobs on visual separators and sentence boundaries so
    # headlines/sentences are recoverable.
    raw_segments: list[str] = []
    for raw in (text or "").splitlines():
        norm = normalize_text(raw)
        if len(norm) > 240:
            raw_segments.extend(re.split(r"\s*[•·|]\s*|(?<=[.!?])\s+(?=[A-Z0-9])", norm))
        else:
            raw_segments.append(raw)
    for raw in raw_segments:
        line = normalize_text(raw).strip(" -*\t")
        if not line or is_boilerplate_diff(line):
            continue
        lower = line.lower()
        if any(marker in lower for marker in [
            "cookie preferences",
            "accept all",
            "decline all",
            "privacy policy",
            "terms of use",
            "navigation products",
            "subscribe to newsletter",
        ]):
            continue
        if len(line) >= 4:
            lines.append(line)
    return lines[:500]


def surrounding_evidence(lines: list[str], idx: int) -> str:
    window = " ".join(lines[idx: idx + 5])
    return normalize_text(window)[:900]


# ---------------------------------------------------------------------------
# Source classification (patched: expanded is_content_source)
# ---------------------------------------------------------------------------


def is_customer_source(source: SourceContext) -> bool:
    source_type = (source.source_type or "").lower()
    url = (source.url or "").lower()
    return any(marker in f"{source_type} {url}" for marker in ["case", "customer", "story"])


def is_content_source(source: SourceContext) -> bool:
    source_type = (source.source_type or "").lower()
    url = (source.url or "").lower()
    return any(marker in f"{source_type} {url}" for marker in [
        "blog", "press", "news", "ai", "rss", "content",
        "changelog", "release", "roadmap", "product", "docs", "protocol", "announc",
    ])


# ---------------------------------------------------------------------------
# Field inference helpers
# ---------------------------------------------------------------------------


def infer_product_area(text: str) -> str:
    lower = text.lower()
    if "ai search" in lower or ("ai" in lower and "search" in lower):
        return "AI search"
    if "product discovery" in lower:
        return "product discovery"
    if "personalization" in lower or "personalized" in lower:
        return "personalization"
    if "recommendation" in lower:
        return "recommendations"
    if "commerce search" in lower or "ecommerce search" in lower:
        return "commerce search"
    if "search" in lower:
        return "search"
    return "unknown"


def infer_industry(text: str) -> str:
    lower = text.lower()
    if any(k in lower for k in ["ecommerce", "commerce", "retail", "shopper", "product discovery"]):
        return "retail/ecommerce"
    if any(k in lower for k in ["health", "pharma", "clinic"]):
        return "healthcare"
    if any(k in lower for k in ["bank", "finance", "insurance"]):
        return "financial services"
    if any(k in lower for k in ["media", "publisher", "content"]):
        return "media"
    return "unknown"


def extract_metric(text: str) -> str:
    match = re.search(r"\b\d+(?:\.\d+)?\s?%|\b\d+(?:\.\d+)?x\b|\$\s?\d+(?:\.\d+)?[mMkK]?", text)
    return normalize_text(match.group(0)).replace(" ", "") if match else ""


def customer_candidate_name(line: str) -> str:
    candidate = re.sub(r"^#+\s*", "", line).strip()
    candidate = re.split(
        r"\s+(?:uses|selected|chooses|is using|announced|launches)\s+", candidate, maxsplit=1, flags=re.I
    )[0]
    if " - " in candidate:
        candidate = candidate.split(" - ", 1)[0]
    elif ": " in candidate:
        candidate = candidate.split(": ", 1)[0]
    words = candidate.split()
    if len(words) > 4:
        candidate = " ".join(words[:3])
    if not re.match(r"^[A-Z][A-Za-z0-9&.' -]{1,60}$", candidate):
        return ""
    if candidate.lower() in {"customers", "customer stories", "case studies", "constructor customers"}:
        return ""
    return candidate.strip()


def infer_content_topic(text: str) -> str:
    lower = text.lower()
    if ("agent" in lower or "agentic" in lower) and any(
        k in lower for k in ["search", "discovery", "retrieval", "mcp", "commerce", "shopping"]
    ):
        return "agentic_search"
    if (
        "ai search" in lower
        or "ai-powered search" in lower
        or "semantic search" in lower
        or "vector search" in lower
        or "neural search" in lower
        or " rag " in lower
        or ("ai" in lower and "retrieval" in lower)
        or ("llm" in lower and "search" in lower)
    ):
        return "ai_search"
    if any(
        k in lower
        for k in [
            "product discovery", "merchandising", "recommendation", "personaliz",
            "relevance", "site search", "ecommerce search", "e-commerce search",
            "faceted", "autocomplete",
        ]
    ):
        return "product_discovery"
    if "personalization" in lower:
        return "personalization"
    if "customer" in lower or "case study" in lower:
        return "customer_proof"
    return "market_narrative"


def infer_narrative_angle(text: str) -> str:
    topic = infer_content_topic(text)
    if topic == "agentic_search":
        return "Agentic search and retrieval are being packaged as enterprise workflow infrastructure."
    if topic == "ai_search":
        return "AI search is being positioned as a platform-level capability."
    if topic == "product_discovery":
        return "Product discovery is being framed around commerce outcomes and personalization."
    if topic == "customer_proof":
        return "Customer proof is being used to validate competitive claims."
    return "Competitor narrative movement needs classification."


def infer_target_audience(text: str) -> str:
    lower = text.lower()
    if any(k in lower for k in ["developer", "api", "build", "workflow"]):
        return "developers"
    if any(k in lower for k in ["commerce", "merchandising", "shopper", "retail"]):
        return "commerce teams"
    if any(k in lower for k in ["enterprise", "leader", "cto", "cio"]):
        return "enterprise AI leaders"
    return "go-to-market teams"


def infer_content_opportunity(topic: str, competitor: str) -> str:
    if topic == "agentic_search":
        return "Algolia should explain where its AI search and MCP story fits into agentic discovery workflows."
    if topic == "ai_search":
        return "Algolia should produce evidence-backed AI search comparison content for buyers evaluating retrieval quality."
    if topic == "product_discovery":
        return "Algolia should connect product discovery content to measurable ecommerce outcomes and proof."
    if topic == "customer_proof":
        return "Algolia should counter with comparable customer proof and vertical-specific stories."
    return "Algolia should decide whether this narrative deserves a response or only monitoring."


def content_candidate_title(line: str) -> str:
    title = re.sub(r"^#+\s*", "", line).strip()
    title = re.sub(r"\s+", " ", title)
    lower = title.lower()
    if not title or len(title) < 12:
        return ""
    if any(k in lower for k in ["cookie", "privacy", "navigation", "contact", "subscribe"]):
        return ""
    if len(title.split()) > 18:
        title = " ".join(title.split()[:18])
    return title


# Stable page-section headers that recur day-over-day (never a real "new" narrative).
GENERIC_NARRATIVE_TITLE = re.compile(
    r"^(ai & machine learning|roadmap & product updates|insights and innovations|"
    r"elastic blog.*|.*stories,?\s*tutorials.*|[^ ]+/[^ ]+|feed:.*|top stories)$",
    re.I,
)


# ---------------------------------------------------------------------------
# Fact extraction (patched: extract_content_narrative_facts multi-fact up to
# 8/source + GENERIC_NARRATIVE_TITLE filter + dedup)
# ---------------------------------------------------------------------------


def extract_customer_proof_facts(text: str, source: SourceContext, detected_date: str) -> list[ExtractedFact]:
    lines = semantic_lines(text)
    facts: list[ExtractedFact] = []
    source_url = canonical_url(source.url)
    seen: set[str] = set()
    for idx, line in enumerate(lines):
        name = customer_candidate_name(line)
        evidence = surrounding_evidence(lines, idx)
        if not name and any(k in line.lower() for k in ["uses", "selected", "chooses", "customer", "case study"]):
            name = customer_candidate_name(line)
        if not name or normalize_identity(name) in seen:
            continue
        target = evidence or line
        metric = extract_metric(target)
        product_area = infer_product_area(target)
        proof_strength = (
            "high" if metric
            else ("medium" if any(k in target.lower() for k in ["uses", "selected", "case study", "customer"]) else "low")
        )
        fact_json = {
            "customer_name": name,
            "industry": infer_industry(target),
            "use_case": product_area if product_area != "unknown" else "unknown",
            "product_area": product_area,
            "claimed_outcome": target if any(
                k in target.lower() for k in ["increase", "improve", "conversion", "revenue", "personalized", "uses"]
            ) else "",
            "metric": metric,
            "quote": "",
            "asset_title": line,
            "asset_url": source_url,
            "proof_strength": proof_strength,
        }
        facts.append(ExtractedFact(
            competitor_id=source.competitor_id,
            fact_type="customer_proof",
            statement=f"{name} customer proof observed on {source_url}",
            fact_json=fact_json,
            evidence_text=target,
            evidence_url=source_url,
            confidence=0.82 if proof_strength == "high" else 0.7,
        ))
        seen.add(normalize_identity(name))
    return facts


def extract_content_narrative_facts(text: str, source: SourceContext, detected_date: str) -> list[ExtractedFact]:
    lines = semantic_lines(text)
    facts: list[ExtractedFact] = []
    competitor = source.competitor_name
    source_url = canonical_url(source.url)
    source_type = source.source_type or "blog"
    seen_titles: set[str] = set()
    for idx, line in enumerate(lines):
        target = surrounding_evidence(lines, idx)
        title = content_candidate_title(line)
        lower_target = target.lower()
        if not title or len(title) < 15 or len(title.split()) < 3:
            continue
        if not any(k in lower_target for k in [
            "ai", "agent", "search", "retrieval", "product discovery", "launch",
            "announce", "introducing", "mcp", "vector", "semantic", "recommendation",
            "personaliz", "merchandis", "relevance",
        ]):
            continue
        if GENERIC_NARRATIVE_TITLE.match(title.strip()):
            continue
        title_identity = normalize_identity(title)
        if title_identity in seen_titles:
            continue
        seen_titles.add(title_identity)
        topic = infer_content_topic(target)
        publish_match = re.search(
            r"\b20\d{2}-\d{2}-\d{2}\b|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},\s+20\d{2}\b"
            r"|\bJune\s+\d{1,2},\s+20\d{2}\b",
            target,
        )
        fact_json = {
            "title": title,
            "publish_date": publish_match.group(0) if publish_match else "",
            "asset_type": "press" if source_type in {"press", "news"} else "blog",
            "topic": topic,
            "narrative_angle": infer_narrative_angle(target),
            "target_audience": infer_target_audience(target),
            "strategic_claim": target,
            "product_claims": [
                claim for claim in ["AI search", "agentic discovery", "retrieval workflows", "product discovery"]
                if claim.lower() in lower_target
            ],
            "proof_points": [extract_metric(target)] if extract_metric(target) else [],
            "cta": "Learn more" if "learn more" in lower_target else "",
            "algolia_content_opportunity": infer_content_opportunity(topic, competitor),
        }
        facts.append(ExtractedFact(
            competitor_id=source.competitor_id,
            fact_type="content_narrative",
            statement=f"{competitor} published or surfaced: {title}",
            fact_json=fact_json,
            evidence_text=target,
            evidence_url=source_url,
            confidence=0.78 if topic in {"agentic_search", "ai_search", "product_discovery"} else 0.62,
        ))
        if len(facts) >= 8:
            break
    return facts


def extract_semantic_facts(text: str, source: SourceContext, detected_date: str) -> list[ExtractedFact]:
    if is_customer_source(source):
        return extract_customer_proof_facts(text, source, detected_date)
    if is_content_source(source):
        return extract_content_narrative_facts(text, source, detected_date)
    return []


def semantic_fact_identity(fact: ExtractedFact) -> str:
    if fact.fact_type == "customer_proof":
        return "customer:%s" % normalize_identity(fact.fact_json.get("customer_name", ""))
    if fact.fact_type == "content_narrative":
        return "content:%s" % normalize_identity(fact.fact_json.get("title", ""))
    return normalize_identity(json.dumps(fact.fact_json, sort_keys=True, default=str))


# ---------------------------------------------------------------------------
# Delta scoring (materiality)
# ---------------------------------------------------------------------------


def materiality_for_delta(delta: Delta, source: SourceContext, collector_changed: bool = False) -> Delta:
    after = delta.metadata.get("after_json") or {}
    score = 0.0
    reasons: list[str] = []
    if delta.delta_type == "new_customer_proof":
        score = 0.42
        reasons.append("named customer proof")
        if after.get("customer_name"):
            score += 0.15
        if after.get("metric") or after.get("claimed_outcome"):
            score += 0.16
            reasons.append("outcome evidence")
        if after.get("product_area") in {"AI search", "product discovery", "commerce search", "search"}:
            score += 0.12
            reasons.append("Algolia-relevant product area")
        if int(source.priority or 3) <= 2:
            score += 0.08
            reasons.append("priority source")
        if after.get("proof_strength") == "high":
            score += 0.08
        delta.implication = (
            "%s is adding customer proof in %s. Algolia should check whether the proof weakens current sales claims or battlecards."
            % (source.competitor_name, after.get("product_area") or "search/product discovery")
        )
        delta.recommended_action = "Validate the customer proof, compare it against Algolia proof points, and decide whether the competitive playbook needs an update."
        delta.metadata["action_owner"] = "Sales Enablement"
    elif delta.delta_type == "new_content_narrative":
        score = 0.35
        reasons.append("new content narrative")
        if after.get("topic") in {"agentic_search", "ai_search", "product_discovery"}:
            score += 0.2
            reasons.append("Algolia-relevant topic")
        if after.get("strategic_claim"):
            score += 0.1
        if after.get("product_claims"):
            score += 0.1
            reasons.append("product claim present")
        if int(source.priority or 3) <= 2:
            score += 0.06
        delta.implication = after.get("algolia_content_opportunity") or "Algolia should decide whether this narrative requires a response."
        delta.recommended_action = "Review the narrative, compare it with Algolia messaging, and decide whether to create or update content."
        delta.metadata["action_owner"] = "Product Marketing"
    else:
        reasons.append("no semantic delta")

    if collector_changed:
        score -= 0.25
        reasons.append("collector method changed, so confidence is penalized")
    if not delta.evidence_urls:
        score -= 0.2
        reasons.append("missing evidence URL")

    score = max(0.0, min(0.98, round(score, 3)))
    delta.materiality_score = score
    delta.metadata["materiality_reason"] = "; ".join(reasons)
    # V0 said "publish" here; our schema's semantic_deltas CHECK requires
    # 'published' plus non-empty evidence_ids. We stage as "review" and let
    # the runner promote to "published" once real evidence_ids are attached.
    delta.quality_status = (
        "review" if score >= 0.65 and delta.delta_type in {"new_customer_proof", "new_content_narrative"}
        else "suppressed"
    )
    return delta


def make_suppressed_delta(source: SourceContext, detected_date: str, reason: str) -> Delta:
    source_url = canonical_url(source.url)
    return Delta(
        competitor_id=source.competitor_id,
        delta_type="suppressed_non_semantic_change",
        materiality_score=0.0,
        what_changed="Suppressed source change: %s." % reason,
        implication="No Algolia action. The change did not produce a validated semantic delta.",
        recommended_action="Keep for diagnostics only.",
        evidence_urls=[source_url] if source_url else [],
        quality_status="suppressed",
        metadata={"materiality_reason": reason, "action_owner": "Competitive Intelligence", "after_json": {}},
    )


def semantic_diff(
    source: SourceContext,
    old_text: str,
    new_text: str,
    detected_date: str,
    collector_changed: bool = False,
) -> tuple[list[ExtractedFact], list[Delta]]:
    """Diff two snapshots' extracted facts into scored deltas.

    Ported from V0 semantic_diff(): a delta fires only for a *new* fact
    identity not present in the prior snapshot's facts; a change that
    produces no new fact identity is recorded as a suppressed diagnostic
    delta rather than silently dropped (evidence-or-silence doctrine).
    """
    old_facts = extract_semantic_facts(old_text, source, detected_date) if old_text else []
    new_facts = extract_semantic_facts(new_text, source, detected_date)
    old_identities = {semantic_fact_identity(fact) for fact in old_facts}
    deltas: list[Delta] = []
    for fact in new_facts:
        identity = semantic_fact_identity(fact)
        if not identity or identity in old_identities:
            continue
        after = fact.fact_json
        if fact.fact_type == "customer_proof":
            delta_type = "new_customer_proof"
            summary = "%s added customer proof for %s." % (source.competitor_name, after.get("customer_name", "a named customer"))
        elif fact.fact_type == "content_narrative":
            delta_type = "new_content_narrative"
            summary = "%s published or surfaced a narrative asset: %s." % (source.competitor_name, after.get("title", "Untitled asset"))
        else:
            continue
        delta = Delta(
            competitor_id=source.competitor_id,
            delta_type=delta_type,
            what_changed=summary,
            evidence_urls=[fact.evidence_url],
            quality_status="suppressed",
            confidence=fact.confidence,
            metadata={"after_json": after},
        )
        deltas.append(materiality_for_delta(delta, source, collector_changed=collector_changed))
    if not deltas and (old_text or new_text):
        reason = "only boilerplate, collector, or hash-level movement detected"
        if not mostly_boilerplate_delta(old_text, new_text):
            reason = "changed text did not map to a supported semantic schema"
        deltas.append(make_suppressed_delta(source, detected_date, reason))
    return new_facts, deltas
