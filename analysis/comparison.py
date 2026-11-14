"""
Compares an old and a new customer list.

Accepts README customer dicts ({"name", "logo_url", "source_url"})
or plain names, and returns the same type it was given.

OPENAI_API_KEY in .env is optional:
- with a key, names are matched by AI (gpt-4o-mini)
- without one (or if the AI call fails), a free rule-based comparison
  is used: legal suffixes removed + small spelling differences allowed
"""

from __future__ import annotations

import json
import os
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Optional

from dotenv import load_dotenv
from pydantic import BaseModel

from analysis.customer_extraction import rough_normalize

load_dotenv()

# How similar normalized names must be to match (0–1)
FUZZY_THRESHOLD = 0.9
# Short names only match exactly: "Neste" ≠ "Nestle"
FUZZY_MIN_LENGTH = 8


class CustomerMatch(BaseModel):
    old_customer: str
    new_customer: Optional[str]  # Optional, not "str | None": Python 3.9 + pydantic
    is_match: bool
    reason: str


class ComparisonResult(BaseModel):
    matches: list[CustomerMatch]


def _get_client():
    """OpenAI client created on use, not on import → importing works without a key."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    from openai import OpenAI

    return OpenAI(api_key=api_key)


def _name(item: Any) -> str:
    return (item.get("name") or "") if isinstance(item, dict) else str(item)


def _normalize(name: str) -> str:
    """rough_normalize + accents removed: "Wärtsilä Oyj" → "wartsila"."""
    folded = unicodedata.normalize("NFKD", rough_normalize(name))
    return "".join(ch for ch in folded if not unicodedata.combining(ch))


def _rule_based_matches(old_names: list[str], new_names: list[str]) -> dict[str, str]:
    """Free matching: {old name: new name}. Each name is used at most once."""
    new_norm = {n: _normalize(n) for n in new_names}
    matches: dict[str, str] = {}
    used: set[str] = set()

    for old in old_names:
        old_norm = _normalize(old)
        best, best_score = None, 0.0
        for new, norm in new_norm.items():
            if new in used:
                continue
            if norm == old_norm:
                score = 1.0
            elif min(len(norm), len(old_norm)) >= FUZZY_MIN_LENGTH:
                score = SequenceMatcher(None, old_norm, norm).ratio()
            else:
                score = 0.0
            if score > best_score:
                best, best_score = new, score
        if best is not None and best_score >= FUZZY_THRESHOLD:
            matches[old] = best
            used.add(best)

    return matches


def _ai_matches(client, old_names: list[str], new_names: list[str]) -> dict[str, str]:
    """AI matching: {old name: new name}."""
    response = client.responses.parse(
        model="gpt-4o-mini",
        input=[
            {
                "role": "system",
                "content": """
                You are an expert at matching company names.

                Determine whether companies in old_customers and
                new_customers refer to the same company.

                Consider:
                - Capitalization differences
                - Legal suffixes (Oy, Oyj, Ltd, Inc, Corporation)
                - Minor spelling differences
                - Known company aliases

                Examples:
                - Nokia = Nokia Oyj
                - Teboil = TeboiL
                - Microsoft = Microsoft Corporation

                Rules:
                - Each old customer must be matched at most once.
                - Each new customer must be matched at most once.
                - Only match companies that are genuinely the same entity.
                - If uncertain, do not match.
                - Return every old customer exactly once.
                - Use null as new_customer if no match exists.
                """
            },
            {
                "role": "user",
                "content": json.dumps({
                    "old_customers": old_names,
                    "new_customers": new_names
                })
            }
        ],
        text_format=ComparisonResult
    )

    result = response.output_parsed
    if result is None:
        raise ValueError("AI could not compare the customer lists.")

    # Only accept names that are really in the lists (the AI can invent names)
    old_set, new_set = set(old_names), set(new_names)
    matches: dict[str, str] = {}
    used: set[str] = set()
    for m in result.matches:
        if (m.is_match and m.old_customer in old_set and m.new_customer in new_set
                and m.old_customer not in matches and m.new_customer not in used):
            matches[m.old_customer] = m.new_customer
            used.add(m.new_customer)
    return matches


def compare_customers(old_customers: list[Any], new_customers: list[Any]) -> dict[str, list[Any]]:
    """Returns {"lost": [...], "retained": [...], "added": [...]}.
    retained holds the new list's version of each customer."""
    # Name → original item (dict or str); first one wins for duplicate names
    old_by = {}
    for item in old_customers:
        old_by.setdefault(_name(item).strip(), item)
    new_by = {}
    for item in new_customers:
        new_by.setdefault(_name(item).strip(), item)
    old_by.pop("", None)
    new_by.pop("", None)

    old_names, new_names = list(old_by), list(new_by)

    matches: dict[str, str] = {}
    if old_names and new_names:
        client = _get_client()
        if client is not None:
            try:
                matches = _ai_matches(client, old_names, new_names)
            except Exception:
                matches = _rule_based_matches(old_names, new_names)
        else:
            matches = _rule_based_matches(old_names, new_names)

    matched_new = set(matches.values())
    return {
        "lost": [old_by[n] for n in old_names if n not in matches],
        "retained": [new_by[matches[n]] for n in old_names if n in matches],
        "added": [new_by[n] for n in new_names if n not in matched_new],
    }


if __name__ == "__main__":
    old = ["Nokia", "Teboil", "Apple"]
    new = ["Nokia Oyj", "TeboiL", "Google"]
    print(compare_customers(old, new))
