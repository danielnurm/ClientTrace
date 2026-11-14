"""
Yritysnimien normalisointi AI:lla.

Tarkoitus: tunnistaa, että esim. "Nokia Oyj", "Nokia Corporation" ja "Nokia"
viittaavat samaan yritykseen — ilman että eri firmia yhdistetään virheellisesti.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field

load_dotenv()

_LEGAL_SUFFIXES = re.compile(
    r"""
    \b(
        oyj|oy|ab|ltd|llc|llp|inc|corp|corporation|company|co|
        plc|gmbh|ag|sa|sas|bv|nv|pty|limited|holdings?
    )\b\.?
    """,
    re.IGNORECASE | re.VERBOSE,
)


class NormalizedName(BaseModel):
    original: str
    canonical: str
    confidence: str = Field(description="high | medium | low")
    notes: str = ""


class NormalizationResult(BaseModel):
    names: list[NormalizedName]


def _get_openai_client() -> OpenAI | None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    return OpenAI(api_key=api_key)


def customer_names(customers: list[Any]) -> list[str]:
    """Poimii nimet listasta, joka voi olla merkkijonoja tai {"name": ...}-dictjä."""
    names: list[str] = []
    for item in customers:
        if isinstance(item, dict):
            name = item.get("name")
            if isinstance(name, str) and name.strip():
                names.append(name.strip())
        elif isinstance(item, str) and item.strip():
            names.append(item.strip())
    return names


def rough_normalize(name: str) -> str:
    """Kevyt, sääntöpohjainen normalisointi fallbackiksi ilman AI:ta."""
    cleaned = name.strip().lower()
    cleaned = _LEGAL_SUFFIXES.sub(" ", cleaned)
    cleaned = re.sub(r"[^\w\s&+-]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or name.strip().lower()


def normalize_company_names(names: list[str]) -> dict[str, str]:
    """
    Palauttaa mappingin original -> canonical.

    AI saa yhdistää vain selvästi saman juridisen entiteetin / brändin.
    Epävarmoissa tapauksissa canonical = original.
    """
    unique = list(dict.fromkeys(n.strip() for n in names if n and n.strip()))
    if not unique:
        return {}

    client = _get_openai_client()
    if client is None:
        return {name: rough_normalize(name).title() for name in unique}

    response = client.responses.parse(
        model="gpt-4o-mini",
        input=[
            {
                "role": "system",
                "content": """
You normalize company names for customer-list matching.

Goal: map each input name to a short canonical brand form.

Safe merges (same company):
- Nokia / Nokia Oyj / Nokia Corporation → Nokia
- Microsoft / Microsoft Corp. / Microsoft Corporation → Microsoft
- Case and punctuation differences

Do NOT merge different companies, even if names look similar:
- Meta ≠ Meta Platforms only if clearly the same; keep separate if unsure
- SoftBank ≠ SoftBank Robotics if they are distinct
- Apple ≠ Apple Hospitality
- When uncertain, keep the original spelling as canonical

Rules:
- Return exactly one entry per input name (original must match input exactly).
- Prefer the shortest well-known brand name when confident.
- confidence must be high, medium, or low.
""",
            },
            {
                "role": "user",
                "content": json.dumps({"names": unique}),
            },
        ],
        text_format=NormalizationResult,
    )

    result = response.output_parsed
    if result is None:
        return {name: rough_normalize(name).title() for name in unique}

    mapping: dict[str, str] = {}
    for item in result.names:
        canonical = (item.canonical or item.original).strip()
        if item.confidence == "low":
            mapping[item.original] = item.original.strip()
        else:
            mapping[item.original] = canonical

    for name in unique:
        mapping.setdefault(name, name)

    return mapping


def apply_normalization(
    customers: list[Any],
    mapping: dict[str, str] | None = None,
) -> list[dict]:
    """
    Palauttaa asiakkaat dict-muodossa canonical-nimellä.
    Alkuperäinen nimi säilytetään kentässä original_name.
    """
    names = customer_names(customers)
    mapping = mapping or normalize_company_names(names)

    normalized: list[dict] = []
    for item in customers:
        if isinstance(item, dict):
            original = str(item.get("name", "")).strip()
            if not original:
                continue
            row = dict(item)
            row["original_name"] = original
            row["name"] = mapping.get(original, original)
            normalized.append(row)
        elif isinstance(item, str) and item.strip():
            original = item.strip()
            normalized.append(
                {
                    "name": mapping.get(original, original),
                    "original_name": original,
                    "logo_url": None,
                    "source_url": None,
                }
            )
    return normalized
