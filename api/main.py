"""HTTP API for the web frontend: sales leads among a competitor's customers.

Run:   .venv/bin/uvicorn api.main:app --reload --port 8000
Demo:  DEMO_MODE=1 serves the saved snapshot in data/leads_demo.json (no network at all).
Save a new snapshot (live, plain requests, no credits):
       .venv/bin/python -m api.main snapshot Giosg tokmanni.fi fennia.fi elisa.fi

Endpoints:
  GET /api/leads?competitor=Giosg&sites=a.fi,b.fi   leads, hottest first (sites default to the demo list)
  GET /api/leads/{site}?competitor=Giosg            one lead with its evidence and archive timeline
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException

from backend import leads

load_dotenv()

SNAPSHOT = Path(__file__).resolve().parent.parent / "data" / "leads_demo.json"
DEMO_SITES = ["tokmanni.fi", "fennia.fi", "elisa.fi", "lahitapiola.fi", "omasp.fi", "s-pankki.fi"]

app = FastAPI(title="ClientTrace API")


def demo_mode() -> bool:
    return os.getenv("DEMO_MODE") == "1"


def load_snapshot() -> dict:
    try:
        return json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise HTTPException(503, f"demo snapshot missing or broken ({SNAPSHOT.name}): {e}")


def _sites(sites: Optional[str]) -> list[str]:
    return [s.strip() for s in sites.split(",") if s.strip()] if sites else DEMO_SITES


@app.get("/api/leads")
def get_leads(competitor: str = "Giosg", sites: Optional[str] = None) -> dict:
    if demo_mode():
        return {**load_snapshot(), "demo": True}
    try:
        return {**leads.find_leads(competitor, _sites(sites)), "demo": False}
    except Exception as e:
        raise HTTPException(502, f"lead check failed: {type(e).__name__}: {e}")


@app.get("/api/leads/{site}")
def get_lead(site: str, competitor: str = "Giosg") -> dict:
    if demo_mode():
        match = next((l for l in load_snapshot()["leads"] if l["site"] == site), None)
        if match is None:
            raise HTTPException(404, f"{site} is not in the demo snapshot")
        return {**match, "demo": True}
    rep = get_leads(competitor, site)
    return {**rep["leads"][0], "demo": False}


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] != ["snapshot"] or len(args) < 3:
        sys.exit("usage: python -m api.main snapshot <competitor product> <site> [site ...]")
    rep = leads.find_leads(args[1], args[2:])
    SNAPSHOT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Saved {len(rep['leads'])} leads to {SNAPSHOT}: {rep['summary']}")
