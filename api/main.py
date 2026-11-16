"""HTTP API for the web frontend: who receives what a visitor searches for on a site.

Run:   .venv/bin/uvicorn api.main:app --reload --port 8000
Demo:  DEMO_MODE=1 serves the saved, anonymised survey only (no network at all).
Live:  ALLOW_LIVE=1 enables POST /api/check, which opens a real browser on the given site. Off by default:
       run it only on your own machine.

Endpoints:
  GET  /api/survey                                  the saved survey (data/leaks_survey.json, anonymised)
  GET  /api/site/{id}                               one surveyed site: recipients before consent, after accept/reject
  POST /api/check?site=a.fi&term=raskaustesti       live check of one public site (about two minutes)
"""
from __future__ import annotations

import ipaddress
import json
import logging
import os
import socket
from urllib.parse import urlsplit

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException

from backend import leaks as search_leaks

load_dotenv()
log = logging.getLogger("firstbite")
app = FastAPI(title="Firstbite API")


def demo_mode() -> bool:
    return os.getenv("DEMO_MODE") == "1"


def live_allowed() -> bool:
    return os.getenv("ALLOW_LIVE") == "1" and not demo_mode()


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def public_host(site: str) -> str:
    """The bare host of `site` if it's a public internet name, else ValueError. Blocks what a browser on the
    server must never be pointed at: localhost, private and link-local ranges (cloud metadata at 169.254.169.254),
    bare IPs and non-https URLs."""
    site = site.strip().lower()
    parts = urlsplit(site if "//" in site else f"https://{site}")
    if parts.scheme != "https":
        raise ValueError("only https sites can be checked")
    host = parts.hostname or ""
    if not host or "." not in host or host.endswith((".local", ".internal", ".localhost")):
        raise ValueError("not a public site name")
    if _is_ip(host):
        raise ValueError("give a site name, not an IP address")
    try:
        addrs = {info[4][0] for info in socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)}
    except socket.gaierror:
        raise ValueError("the site name doesn't resolve")
    if any(not ipaddress.ip_address(a).is_global for a in addrs):
        raise ValueError("the site resolves to a private or reserved address")
    return host


def load_survey() -> dict:
    try:
        return json.loads(search_leaks.SURVEY_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        log.error("survey unreadable: %s", e)
        raise HTTPException(503, "the saved survey is missing or broken")


@app.get("/api/survey")
def get_survey() -> dict:
    return {**load_survey(), "demo": demo_mode(), "live": live_allowed()}


@app.get("/api/site/{site_id}")
def get_site(site_id: str) -> dict:
    match = next((s for s in load_survey()["sites"] if s["site"] == site_id), None)
    if match is None:
        raise HTTPException(404, "not in the survey")
    return {**match, "demo": demo_mode()}


@app.post("/api/check")
def post_check(site: str, term: str) -> dict:
    if not live_allowed():
        raise HTTPException(403, "live checks are off; run the API with ALLOW_LIVE=1 on your own machine")
    term = term.strip()
    if not term or len(term) > 60:
        raise HTTPException(422, "give a search term of 1-60 characters")
    try:
        host = public_host(site)
    except ValueError as e:
        raise HTTPException(422, str(e))
    try:
        return {**search_leaks.check_search(host, term), "demo": False}
    except Exception:
        log.exception("search check failed for %s", host)
        raise HTTPException(502, "the check failed; see the API log")
