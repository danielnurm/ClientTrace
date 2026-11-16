"""HTTP API for the web frontend: the search check (who receives a visitor's search term), the consent check, and
sales leads among a competitor's customers.

Run:   .venv/bin/uvicorn api.main:app --reload --port 8000
Demo:  DEMO_MODE=1 serves the saved snapshot in data/leads_demo.json (no network at all).
Save a new snapshot (live, plain requests, no credits):
       .venv/bin/python -m api.main snapshot Giosg tokmanni.fi fennia.fi elisa.fi

Endpoints:
  GET  /api/survey                                  the saved search-check survey (data/leaks_survey.json)
  GET  /api/site/{site}                             one site from the survey: recipients before and after consent
  POST /api/check?site=a.fi&term=raskaustesti       live search check of any site (about a minute; not in demo mode)
  GET /api/consent?sites=a.fi,b.fi                  trackers before consent per site (cached checks; demo list by default)
  GET /api/consent/{site}                           one site's findings, evidence and first-seconds timeline
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

from backend import consent, leads
from backend import leaks as search_leaks

load_dotenv()

SNAPSHOT = Path(__file__).resolve().parent.parent / "data" / "leads_demo.json"
DEMO_SITES = ["tokmanni.fi", "fennia.fi", "elisa.fi", "lahitapiola.fi", "omasp.fi", "s-pankki.fi"]

app = FastAPI(title="Firstbite API")


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


def load_consent_snapshot() -> dict:
    try:
        return json.loads(consent.DEMO_SNAPSHOT.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise HTTPException(503, f"consent snapshot missing or broken ({consent.DEMO_SNAPSHOT.name}): {e}")


@app.get("/api/consent")
def get_consent(sites: Optional[str] = None) -> dict:
    if demo_mode() or not sites:
        return {**load_consent_snapshot(), "demo": demo_mode() or not sites}
    try:
        return {**consent.consent_report(_sites(sites)), "demo": False}
    except Exception as e:
        raise HTTPException(502, f"consent check failed: {type(e).__name__}: {e}")


@app.get("/api/consent/{site}")
def get_consent_site(site: str) -> dict:
    if demo_mode():
        match = next((s for s in load_consent_snapshot()["sites"] if s["site"] == site), None)
        if match is None:
            raise HTTPException(404, f"{site} is not in the demo snapshot")
        return {**match, "demo": True}
    return {**get_consent(site)["sites"][0], "demo": False}


def load_survey() -> dict:
    try:
        return json.loads(search_leaks.SURVEY_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise HTTPException(503, f"survey missing or broken ({search_leaks.SURVEY_FILE.name}): {e}")


@app.get("/api/survey")
def get_survey() -> dict:
    return {**load_survey(), "demo": demo_mode()}


@app.get("/api/site/{site}")
def get_site(site: str) -> dict:
    match = next((s for s in load_survey()["sites"] if s["site"] == site), None)
    if match is None:
        raise HTTPException(404, f"{site} is not in the survey; check it live with POST /api/check")
    return {**match, "demo": demo_mode()}


@app.post("/api/check")
def post_check(site: str, term: str) -> dict:
    if demo_mode():
        raise HTTPException(503, "live checks need the API without DEMO_MODE=1")
    if not site.strip() or not term.strip():
        raise HTTPException(422, "both site and term are needed")
    try:
        return {**search_leaks.check_search(site.strip(), term.strip()), "demo": False}
    except Exception as e:
        raise HTTPException(502, f"search check failed: {type(e).__name__}: {e}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] != ["snapshot"] or len(args) < 3:
        sys.exit("usage: python -m api.main snapshot <competitor product> <site> [site ...]")
    rep = leads.find_leads(args[1], args[2:])
    SNAPSHOT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Saved {len(rep['leads'])} leads to {SNAPSHOT}: {rep['summary']}")
