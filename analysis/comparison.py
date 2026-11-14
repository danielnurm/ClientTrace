"""
Vertaa vanhan ja uuden asiakaslistan.

Hyväksyy README:n customer-dictit ({"name", "logo_url", "source_url"})
tai pelkät nimet, ja palauttaa samaa tyyppiä kuin sai.

OPENAI_API_KEY .env-tiedostossa on vapaaehtoinen:
- avaimen kanssa nimet matchataan AI:lla (gpt-4o-mini)
- ilman avainta (tai jos AI-kutsu epäonnistuu) käytetään ilmaista
  sääntöpohjaista vertailua: yhtiömuodot pois + pienet kirjoitusvirheet
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

# Kuinka samankaltaisten normalisoitujen nimien pitää olla (0–1)
FUZZY_THRESHOLD = 0.9
# Lyhyet nimet vain tarkalla osumalla: "Neste" ≠ "Nestle"
FUZZY_MIN_LENGTH = 8


class CustomerMatch(BaseModel):
    old_customer: str
    new_customer: Optional[str]  # Optional eikä "str | None": Python 3.9 + pydantic
    is_match: bool
    reason: str


class ComparisonResult(BaseModel):
    matches: list[CustomerMatch]


def _get_client():
    """OpenAI-client vasta käytössä, ei importissa → import ei kaadu ilman avainta."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    from openai import OpenAI

    return OpenAI(api_key=api_key)


def _name(item: Any) -> str:
    return (item.get("name") or "") if isinstance(item, dict) else str(item)


def _normalize(name: str) -> str:
    """rough_normalize + ääkköset/aksentit pois: "Wärtsilä Oyj" → "wartsila"."""
    folded = unicodedata.normalize("NFKD", rough_normalize(name))
    return "".join(ch for ch in folded if not unicodedata.combining(ch))


def _rule_based_matches(old_names: list[str], new_names: list[str]) -> dict[str, str]:
    """Ilmainen matchaus: {vanha nimi: uusi nimi}. Jokainen nimi käytetään kerran."""
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
    """AI-matchaus: {vanha nimi: uusi nimi}."""
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

    # Hyväksytään vain nimet, jotka oikeasti ovat listoissa (AI voi keksiä nimiä)
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
    """Palauttaa {"lost": [...], "retained": [...], "added": [...]}.
    retained sisältää uuden listan version asiakkaasta."""
    # Nimi → alkuperäinen alkio (dict tai str); tuplanimistä ensimmäinen
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
