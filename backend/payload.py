"""Find a search term inside a recorded request: which field of the URL or body carried it.

Trackers rarely send the term as is. Google Analytics puts the page address in `dl` (so `?q=pregnancy+test` rides
along, encoded twice), Meta sends `dl` and custom data in a form body, others post JSON, and GA4 batches several
hits as separate lines. This decodes all of those and reports each field that contains the term.

Evidence keeps only a short window around the term, so client IDs and other identifiers in the same request
are never stored.
"""
from __future__ import annotations

import json
from typing import Iterator
from urllib.parse import parse_qsl, unquote_plus, urlsplit

WINDOW = 40  # characters kept on each side of the term in evidence


def _decode(value: str) -> str:
    """Undo up to three layers of URL encoding (a page URL inside a tracker URL is encoded twice)."""
    for _ in range(3):
        decoded = unquote_plus(value)
        if decoded == value:
            break
        value = decoded
    return value


def _variants(term: str) -> set[str]:
    t = term.lower().strip()
    return {t, t.replace(" ", "-"), t.replace(" ", "_")}


def _json_fields(obj, prefix: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _json_fields(v, f"{prefix}.{k}" if prefix else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _json_fields(v, f"{prefix}[{i}]")
    elif obj is not None:
        yield prefix or "body", str(obj)


def fields(url: str, body: str = "") -> Iterator[tuple[str, str]]:
    """(field, value) pairs from the URL path, its query string and the request body."""
    parts = urlsplit(url)
    yield "path", parts.path
    yield from parse_qsl(parts.query, keep_blank_values=True)
    body = (body or "").strip()
    if not body:
        return
    if body[:1] in "[{":
        try:
            yield from _json_fields(json.loads(body))
            return
        except ValueError:
            pass  # not JSON after all: fall through to form or raw text
    lines = body.splitlines()
    if all("=" in ln for ln in lines if ln):
        for ln in lines:  # GA4 batches one hit per line, each a query string
            yield from parse_qsl(ln, keep_blank_values=True)
    else:
        yield "body", body


def snippet(text: str, term: str) -> str:
    """The term with a little context on each side, so a reader sees where it sat."""
    low = text.lower()
    hit = next((v for v in _variants(term) if v in low), None)
    if hit is None:
        return ""
    i = low.index(hit)
    start, end = max(0, i - WINDOW), min(len(text), i + len(hit) + WINDOW)
    return ("…" if start else "") + text[start:end] + ("…" if end < len(text) else "")


def find_term(url: str, body: str, term: str) -> list[dict]:
    """Every field of the request that contains the term: [{"field", "snippet"}], first occurrence per field."""
    found, seen = [], set()
    variants = _variants(term)
    for name, value in fields(url, body):
        text = _decode(value)
        if name in seen or not any(v in text.lower() for v in variants):
            continue
        seen.add(name)
        found.append({"field": name, "snippet": snippet(text, term)})
    return found
