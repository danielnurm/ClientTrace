"""Consent check: which trackers load before the visitor answers the cookie banner?

Under GDPR and the ePrivacy rules (in Finland, Traficom's guidance), cookies and trackers that aren't strictly
necessary, analytics included, need consent first. This opens a site in a fresh headless browser, never touches
the banner, and records every request and cookie in the first seconds:

  tracks_before_consent  a tracker sent data (a beacon or pixel) or set its cookie
  loads_before_consent   tracker scripts loaded (the vendor gets the visitor's IP), but no data call seen
  clean                  no tracker activity before consent
  unknown                the site couldn't be loaded

Google requests sent with Consent Mode "denied" (gcs=G100) are shown as cookieless pings, not counted: whether
they're allowed is debated. Matomo is shown but not counted: it can be configured to run without consent.

CLI:
  python -m backend.consent check verkkokauppa.com yle.fi
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

from backend import site_tech as st
from backend import trackers as tr

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "consent"
WAIT_MS = 5000
NOT_COUNTED = {"Matomo"}
SKIP_LINK = re.compile(r"privacy|tietosuoja|cookie|evaste|login|kirjaudu|cart|ostoskori|\.pdf$", re.I)


def _short(url: str) -> str:
    """Scheme, host and path only: enough to prove the call without copying identifiers."""
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}{p.path}"[:160]


def analyse(requests: list[dict], cookies: list[dict]) -> dict:
    """Findings per tracker from recorded requests [{"ms", "url"}] and cookies [{"name", "domain"}]."""
    found: dict[str, dict] = {}
    pings: list[dict] = []
    consent = None
    timeline = []
    for r in sorted(requests, key=lambda r: r["ms"]):
        hit = tr.classify_request(r["url"])
        tool = tr.consent_tool(r["url"])
        if tool and consent is None:
            consent = {"name": tool, "ms": r["ms"]}
        timeline.append({"ms": r["ms"], "host": urlsplit(r["url"]).netloc,
                         "type": "tracker" if hit and hit["kind"] != "ping" else "consent" if tool else "other",
                         **({"tracker": hit["tracker"], "kind": hit["kind"]} if hit else {})})
        if not hit:
            continue
        if hit["kind"] == "ping":
            pings.append({"tracker": hit["tracker"], "ms": r["ms"], "url": _short(r["url"])})
            continue
        f = found.setdefault(hit["tracker"], {"tracker": hit["tracker"], "category": hit["category"],
                                              "sent": False, "first_ms": r["ms"], "evidence": [], "cookies": [],
                                              "own_domain": False})
        f["sent"] = f["sent"] or hit["kind"] == "send"
        f["own_domain"] = f["own_domain"] or hit["own_domain"]
        if len(f["evidence"]) < 3:
            f["evidence"].append({"ms": r["ms"], "kind": hit["kind"], "url": _short(r["url"])})
    for c in cookies:
        name = tr.classify_cookie(c["name"])
        if name:
            f = found.setdefault(name, {"tracker": name, "category": tr.TRACKERS[name]["category"], "sent": False,
                                        "first_ms": None, "evidence": [], "cookies": [], "own_domain": False})
            if c["name"] not in f["cookies"]:
                f["cookies"].append(c["name"])
    for f in found.values():
        if "note" in tr.TRACKERS[f["tracker"]]:
            f["note"] = tr.TRACKERS[f["tracker"]]["note"]
        f["counted"] = f["tracker"] not in NOT_COUNTED
    return {"trackers": sorted(found.values(), key=lambda f: (f["first_ms"] is None, f["first_ms"] or 0)),
            "pings": pings, "consent_tool": consent, "timeline": timeline}


def verdict(trackers: list[dict]) -> str:
    counted = [t for t in trackers if t["counted"]]
    if any(t["sent"] or t["cookies"] for t in counted):
        return "tracks_before_consent"
    if counted:
        return "loads_before_consent"
    return "clean"


def _internal_link(page, host: str) -> Optional[str]:
    links = page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
    for href in links:
        p = urlsplit(href)
        if p.netloc == host and p.path.strip("/") and not SKIP_LINK.search(href):
            return href.split("#")[0]
    return None


def check_consent(site: str, pages: int = 2, wait_ms: int = WAIT_MS) -> dict:
    """Open the site in a fresh browser, never answer the banner, and analyse the first seconds of each page."""
    from playwright.sync_api import sync_playwright  # imported here so the module loads without Playwright

    url = st._site_url(site)
    row = {"site": st._site_key(site), "url": url,
           "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    requests: list[dict] = []
    visited = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            # Chromium's own user agent, minus "Headless": a hand-written one made a site skip its tracking
            ua = browser.new_page().evaluate("navigator.userAgent").replace("HeadlessChrome", "Chrome")
            ctx = browser.new_context(locale="fi-FI", user_agent=ua)
            page = ctx.new_page()
            start = [0.0]
            page.on("request", lambda r: requests.append(
                {"ms": round((time.monotonic() - start[0]) * 1000), "url": r.url, "page": len(visited)}))
            target: Optional[str] = url
            while target and len(visited) < pages:
                start[0] = time.monotonic()
                page.goto(target, wait_until="domcontentloaded", timeout=25000)
                page.wait_for_timeout(wait_ms)
                visited.append(page.url)
                target = _internal_link(page, urlsplit(page.url).netloc) if len(visited) < pages else None
            cookies = [{"name": c["name"], "domain": c["domain"]} for c in ctx.cookies()]
            browser.close()
    except Exception as e:
        return {**row, "verdict": "unknown", "error": f"{type(e).__name__}: {str(e).splitlines()[0]}"[:200]}

    first = [r for r in requests if r["page"] == 0 and r["ms"] <= wait_ms]
    a = analyse(requests, cookies)
    a["timeline"] = analyse(first, [])["timeline"]  # the strip shows the home page's first seconds
    return {**row, "pages": visited, "requests": len(requests), **a, "verdict": verdict(a["trackers"])}


def consent_report(sites: list[str], refresh: bool = False) -> dict:
    """Check each site (cached in data/consent/<site>.json unless refresh). Sequential: one browser at a time."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for s in sites:
        path = CACHE_DIR / f"{st._site_key(s)}.json"
        if path.exists() and not refresh:
            rows.append(json.loads(path.read_text(encoding="utf-8")))
            continue
        r = check_consent(s)
        if r["verdict"] != "unknown":
            path.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
        rows.append(r)
    order = {"tracks_before_consent": 0, "loads_before_consent": 1, "clean": 2, "unknown": 3}
    rows.sort(key=lambda r: order[r["verdict"]])
    summary: dict[str, int] = {}
    for r in rows:
        summary[r["verdict"]] = summary.get(r["verdict"], 0) + 1
    return {"checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "summary": summary, "sites": rows}


DEMO_SNAPSHOT = CACHE_DIR.parent / "consent_demo.json"

if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["snapshot"] and len(args) >= 2:  # demo data for the API, from cached checks only
        rep = consent_report(args[1:])
        DEMO_SNAPSHOT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
        sys.exit(f"Saved {len(rep['sites'])} sites to {DEMO_SNAPSHOT}: {rep['summary']}")
    if args[:1] != ["check"] or len(args) < 2:
        sys.exit("usage: python -m backend.consent check|snapshot <site> [site ...]")
    rep = consent_report(args[1:], refresh=True)
    print(rep["summary"])
    for r in rep["sites"]:
        tool = (r.get("consent_tool") or {}).get("name", "no consent tool")
        print(f"\n{r['site']}: {r['verdict']} ({tool}) {r.get('error', '')}")
        for t in r.get("trackers", []):
            ev = t["evidence"][0] if t["evidence"] else None
            print(f"  {t['tracker']:<18} {'sent' if t['sent'] else 'loaded':<6} "
                  f"{(str(t['first_ms']) + ' ms') if t['first_ms'] is not None else '':>8} "
                  f"cookies={t['cookies']} {ev['url'] if ev else ''}{'' if t['counted'] else '  (not counted)'}")
        for pg in r.get("pings", [])[:2]:
            print(f"  ping: {pg['tracker']} {pg['ms']} ms {pg['url']}")
