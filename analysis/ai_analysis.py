"""
Asiakaslistojen vertailu + kilpailijaevidenssi → perusteltu tilannearvio.

Hyväksyy sekä merkkijonolistat että README:n customer-dictit:
{"name": "...", "logo_url": "...", "source_url": "..."}
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from analysis.customer_extraction import customer_names, normalize_company_names
from backend.competitor_search import find_competitor_transitions


def _domain_from_url(url: str | None) -> str | None:
    if not url:
        return None
    try:
        host = urlparse(url).netloc.lower().lstrip("www.")
        return host or None
    except Exception:
        return None


def _supplier_domains(customers: list[Any]) -> list[str]:
    domains: list[str] = []
    for item in customers:
        if not isinstance(item, dict):
            continue
        for key in ("source_url", "logo_url"):
            domain = _domain_from_url(item.get(key))
            if domain and domain not in domains:
                domains.append(domain)
    return domains


def _status_for_lost(competitor_found: bool, confidence: str) -> str:
    if competitor_found and confidence in {"high", "medium"}:
        return "possibly_lost"
    if competitor_found:
        return "possibly_lost"
    return "unlisted"


def _build_customer_report(
    *,
    name: str,
    previously_listed: bool,
    currently_listed: bool,
    competitor: dict[str, Any] | None = None,
) -> dict[str, Any]:
    competitor = competitor or {}
    competitor_found = bool(competitor.get("competitor_found"))
    confidence = competitor.get("confidence") or (
        "high" if previously_listed and currently_listed else "medium"
    )

    if previously_listed and currently_listed:
        status = "retained"
        evidence = ["Old customer page", "Current customer page"]
        competitor_found = False
        confidence = "high"
    elif previously_listed and not currently_listed:
        status = _status_for_lost(competitor_found, confidence)
        evidence = ["Old customer page"]
        if competitor_found:
            evidence.append("Competitor customer page")
            evidence.extend(
                e for e in (competitor.get("evidence") or []) if e not in evidence
            )
        else:
            evidence.append("Missing from current customer page")
            confidence = "medium"
    elif not previously_listed and currently_listed:
        status = "added"
        evidence = ["Current customer page"]
        competitor_found = False
        confidence = "high"
    else:
        status = "unknown"
        evidence = []
        confidence = "low"

    report: dict[str, Any] = {
        "customer": name,
        "status": status,
        "previously_listed": previously_listed,
        "currently_listed": currently_listed,
        "competitor_found": competitor_found,
        "confidence": confidence,
        "evidence": evidence,
    }

    if competitor.get("competitor_name"):
        report["competitor_name"] = competitor["competitor_name"]
    if competitor.get("evidence_urls"):
        report["evidence_urls"] = competitor["evidence_urls"]
    if competitor.get("reason"):
        report["reason"] = competitor["reason"]
    if competitor.get("is_supplier_switch_proven") is not None and status.startswith(
        "possibly"
    ):
        report["is_supplier_switch_proven"] = bool(
            competitor.get("is_supplier_switch_proven")
        )

    return report


def analyze_customers(
    old_customers: list[Any],
    new_customers: list[Any],
    *,
    known_competitors: list[str] | None = None,
    search_competitors: bool = True,
) -> dict[str, Any]:
    """
    Vertaa asiakaslistat, normalisoi nimet AI:lla ja tuottaa tilannearvion.

    Palauttaa:
    {
      "comparison": {"lost": [...], "retained": [...], "added": [...]},
      "normalization": {"Nokia Oyj": "Nokia", ...},
      "analysis": [ {customer, status, ...}, ... ]
    }
    """
    # comparison.py alustaa OpenAI-clientin importissa → ladataan vasta täällä
    from analysis.comparison import compare_customers

    old_names = customer_names(old_customers)
    new_names = customer_names(new_customers)

    normalization = normalize_company_names(old_names + new_names)
    old_normalized = [normalization.get(n, n) for n in old_names]
    new_normalized = [normalization.get(n, n) for n in new_names]

    # comparison.py odottaa list[str] ja tekee AI-matchauksen itsekin
    comparison = compare_customers(old_normalized, new_normalized)

    lost = list(comparison.get("lost", []))
    retained = list(comparison.get("retained", []))
    added = list(comparison.get("added", []))

    competitor_map: dict[str, dict[str, Any]] = {}
    if search_competitors and lost:
        exclude_domains = _supplier_domains(old_customers + new_customers)
        competitor_map = find_competitor_transitions(
            lost,
            exclude_domains=exclude_domains,
            known_competitors=known_competitors,
        )

    analysis: list[dict[str, Any]] = []

    for name in retained:
        analysis.append(
            _build_customer_report(
                name=name,
                previously_listed=True,
                currently_listed=True,
            )
        )

    for name in lost:
        analysis.append(
            _build_customer_report(
                name=name,
                previously_listed=True,
                currently_listed=False,
                competitor=competitor_map.get(name),
            )
        )

    for name in added:
        analysis.append(
            _build_customer_report(
                name=name,
                previously_listed=False,
                currently_listed=True,
            )
        )

    return {
        "comparison": {
            "lost": lost,
            "retained": retained,
            "added": added,
            "old_count": len(dict.fromkeys(old_normalized)),
            "new_count": len(dict.fromkeys(new_normalized)),
        },
        "normalization": normalization,
        "analysis": analysis,
    }


if __name__ == "__main__":
    old = [
        {"name": "Nokia Oyj", "logo_url": None, "source_url": "https://supplier.example/customers"},
        {"name": "Kone", "logo_url": None, "source_url": "https://supplier.example/customers"},
        {"name": "Wärtsilä", "logo_url": None, "source_url": "https://supplier.example/customers"},
        {"name": "Elisa", "logo_url": None, "source_url": "https://supplier.example/customers"},
    ]
    new = [
        {"name": "Nokia Corporation", "logo_url": None, "source_url": "https://supplier.example/customers"},
        {"name": "Kone", "logo_url": None, "source_url": "https://supplier.example/customers"},
        {"name": "Valmet", "logo_url": None, "source_url": "https://supplier.example/customers"},
    ]

    # Kilpailijahaku pois demoajossa (tarvitsee EXA/CONTEXT-avaimet)
    result = analyze_customers(old, new, search_competitors=False)
    from pprint import pprint

    pprint(result)
