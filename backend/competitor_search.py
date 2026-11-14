"""
Kilpailijasiirtymien haku Exa + Context.dev -APIeilla.

Etsii, näkyykö kadonnut asiakas kilpailijoiden customer case / reference -sivuilla.
Pelkkä maininta EI ole todiste toimittajan vaihtumisesta — arvioidaan erikseen.
"""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()

SEARCH_TEMPLATES = (
    "{customer} customer case study supplier",
    "{customer} customer reference company",
    "{customer} customer partnership",
)


def _get_exa_client():
    api_key = os.getenv("EXA_API_KEY")
    if not api_key:
        return None
    try:
        from exa_py import Exa
    except ImportError:
        return None
    return Exa(api_key=api_key)


def _get_context_client():
    api_key = os.getenv("CONTEXT_DEV_API_KEY") or os.getenv("CONTEXT_API_KEY")
    if not api_key:
        return None
    try:
        from context.dev import ContextDev
    except ImportError:
        return None
    return ContextDev(api_key=api_key)


def _dedupe_hits(hits: list[dict]) -> list[dict]:
    seen: set[str] = set()
    unique: list[dict] = []
    for hit in hits:
        url = (hit.get("url") or "").strip()
        key = url.lower() if url else f"{hit.get('title')}|{hit.get('snippet')}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(hit)
    return unique


def _search_exa(customer: str, num_results: int = 5) -> list[dict]:
    client = _get_exa_client()
    if client is None:
        return []

    hits: list[dict] = []
    for template in SEARCH_TEMPLATES:
        query = template.format(customer=customer)
        try:
            result = client.search(
                query,
                type="auto",
                num_results=num_results,
                contents={"highlights": True, "text": {"max_characters": 800}},
            )
        except Exception:
            continue

        for item in getattr(result, "results", []) or []:
            highlights = getattr(item, "highlights", None) or []
            text = getattr(item, "text", None) or ""
            snippet = " ".join(highlights) if highlights else text[:400]
            hits.append(
                {
                    "source": "exa",
                    "query": query,
                    "title": getattr(item, "title", None),
                    "url": getattr(item, "url", None),
                    "snippet": snippet,
                }
            )
    return hits


def _search_context(customer: str, num_results: int = 5) -> list[dict]:
    client = _get_context_client()
    if client is None:
        return []

    hits: list[dict] = []
    for template in SEARCH_TEMPLATES:
        query = template.format(customer=customer)
        try:
            result = client.web.search(query=query, num_results=num_results)
        except Exception:
            continue

        for item in getattr(result, "results", []) or []:
            if isinstance(item, dict):
                title = item.get("title")
                url = item.get("url")
                snippet = item.get("description") or item.get("snippet") or ""
                relevance = item.get("relevance")
            else:
                title = getattr(item, "title", None)
                url = getattr(item, "url", None)
                snippet = (
                    getattr(item, "description", None)
                    or getattr(item, "snippet", None)
                    or ""
                )
                relevance = getattr(item, "relevance", None)

            hits.append(
                {
                    "source": "context.dev",
                    "query": query,
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                    "relevance": relevance,
                }
            )
    return hits


def _looks_like_customer_page(hit: dict, customer: str) -> bool:
    blob = " ".join(
        str(hit.get(k) or "") for k in ("title", "url", "snippet", "query")
    ).lower()
    customer_l = customer.lower()
    if customer_l not in blob:
        return False

    signals = (
        "customer",
        "case study",
        "case-study",
        "success story",
        "reference",
        "clients",
        "partners",
        "testimonial",
        "logo",
    )
    return any(signal in blob for signal in signals)


def search_competitor_mentions(
    customer_name: str,
    *,
    exclude_domains: list[str] | None = None,
    num_results: int = 5,
) -> list[dict]:
    """
    Hakee webistä viitteitä, joissa customer_name esiintyy asiakasreferenssinä.

    Palauttaa listan hittejä:
    {
      "source": "exa" | "context.dev",
      "query": "...",
      "title": "...",
      "url": "...",
      "snippet": "...",
      "likely_customer_page": bool
    }
    """
    customer = customer_name.strip()
    if not customer:
        return []

    hits = _dedupe_hits(
        _search_exa(customer, num_results=num_results)
        + _search_context(customer, num_results=num_results)
    )

    excluded = {d.lower().lstrip("www.") for d in (exclude_domains or [])}
    filtered: list[dict] = []
    for hit in hits:
        url = (hit.get("url") or "").lower()
        domain = url.split("/")[2] if "://" in url else ""
        domain = domain.lstrip("www.")
        if domain and domain in excluded:
            continue
        hit["likely_customer_page"] = _looks_like_customer_page(hit, customer)
        filtered.append(hit)

    return filtered


def evaluate_competitor_evidence(
    customer_name: str,
    hits: list[dict],
    *,
    known_competitors: list[str] | None = None,
) -> dict[str, Any]:
    """
    Arvioi Context.dev Answers -API:lla (tai heuristiikalla), onko näyttö
    riittävä mahdolliselle toimittajan vaihtumiselle.
    """
    customer = customer_name.strip()
    competitor_hits = [h for h in hits if h.get("likely_customer_page")]
    client = _get_context_client()

    if client is not None and hits:
        competitors_hint = ", ".join(known_competitors or []) or "unknown"
        evidence_blob = "\n\n".join(
            f"title={h.get('title')}\nurl={h.get('url')}\nsnippet={h.get('snippet')}"
            for h in hits[:12]
        )
        try:
            response = client.web.answers(
                mode="fast",
                task=(
                    f"Customer '{customer}' disappeared from a supplier's customer list. "
                    f"Known competitors (if any): {competitors_hint}. "
                    "Based ONLY on the evidence snippets below, decide whether the customer "
                    "appears as a real customer/reference/case study of a competing supplier. "
                    "A bare name mention on a competitor page is NOT enough. "
                    "Require clear customer-case / logo wall / reference language.\n\n"
                    f"Evidence:\n{evidence_blob}"
                ),
                json_format={
                    "competitor_found": False,
                    "competitor_name": "",
                    "evidence_urls": [""],
                    "evidence_summary": [""],
                    "confidence": "low",
                    "is_supplier_switch_proven": False,
                    "reason": "",
                },
                timeout_opts={"milliseconds": 30000, "behavior": "return-partial"},
            )
            content = getattr(response, "json_content", None) or {}
            if isinstance(content, dict):
                return {
                    "competitor_found": bool(content.get("competitor_found")),
                    "competitor_name": content.get("competitor_name") or None,
                    "evidence": [
                        e
                        for e in (content.get("evidence_summary") or [])
                        if isinstance(e, str) and e.strip()
                    ],
                    "evidence_urls": [
                        u
                        for u in (content.get("evidence_urls") or [])
                        if isinstance(u, str) and u.strip()
                    ],
                    "confidence": content.get("confidence") or "low",
                    "is_supplier_switch_proven": bool(
                        content.get("is_supplier_switch_proven")
                    ),
                    "reason": content.get("reason") or "",
                    "raw_hits": hits,
                }
        except Exception:
            pass

    # Heuristinen fallback ilman Answers-API:a
    if competitor_hits:
        urls = [h.get("url") for h in competitor_hits if h.get("url")]
        return {
            "competitor_found": True,
            "competitor_name": None,
            "evidence": [
                f"{h.get('title') or 'Untitled'}: {(h.get('snippet') or '')[:180]}"
                for h in competitor_hits[:5]
            ],
            "evidence_urls": urls[:5],
            "confidence": "medium" if len(competitor_hits) >= 2 else "low",
            "is_supplier_switch_proven": False,
            "reason": (
                "Customer appears on pages that look like competitor case/"
                "reference pages, but a mention alone does not prove a switch."
            ),
            "raw_hits": hits,
        }

    return {
        "competitor_found": False,
        "competitor_name": None,
        "evidence": [],
        "evidence_urls": [],
        "confidence": "low",
        "is_supplier_switch_proven": False,
        "reason": "No strong competitor customer-reference pages found.",
        "raw_hits": hits,
    }


def find_competitor_transitions(
    lost_customers: list[str],
    *,
    exclude_domains: list[str] | None = None,
    known_competitors: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Tutkii jokaisen kadonneen asiakkaan mahdolliset kilpailijasiirtymät."""
    results: dict[str, dict[str, Any]] = {}
    for customer in lost_customers:
        hits = search_competitor_mentions(
            customer,
            exclude_domains=exclude_domains,
        )
        results[customer] = evaluate_competitor_evidence(
            customer,
            hits,
            known_competitors=known_competitors,
        )
    return results
