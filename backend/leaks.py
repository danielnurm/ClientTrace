"""Search check: who receives what a visitor types into a site's search box?

Opens the site in a fresh headless browser, runs a site search for a term (for example "pregnancy test" on a
pharmacy) and records every request in the seconds after it. A request "carries the term" when the term appears
in its URL or body, decoded (backend/payload.py). Two phases, each in a fresh browser:

  before   the cookie banner is never touched
  after    the banner's accept button is clicked first

Each phase runs twice and a recipient counts only if it shows up in both runs, because tracker calls vary from
load to load. Requests to the site itself (the search) aren't recipients, except tracker endpoints on the site's
own domain (server-side tagging), which forward the data on.

CLI:
  python -m backend.leaks check shop-apotheke.com schwangerschaftstest
  python -m backend.leaks survey                 # every site in data/leaks_sites.json
"""
from __future__ import annotations

import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus, urlencode, urljoin, urlsplit

from backend import payload
from backend import trackers as tr

DATA = Path(__file__).resolve().parent.parent / "data"
SITES_FILE = DATA / "leaks_sites.json"
SURVEY_FILE = DATA / "leaks_survey.json"
CACHE_DIR = DATA / "leaks"
RUNS = 2
WAIT_MS = 6000  # recorded after the search starts
# Categories that count: companies that don't need the term to run the search. Unidentified companies are shown
# but not counted, since they may be the site's own services on another domain.
SENSITIVE = {"advertising", "analytics", "session recording", "marketing", "personalisation"}

ACCEPT_SELECTORS = [
    "#onetrust-accept-btn-handler",                                  # OneTrust
    "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",        # Cookiebot
    "#CybotCookiebotDialogBodyButtonAccept",
    "[data-testid=uc-accept-all-button]",                            # Usercentrics
    "#coiPage-1 .coi-banner__accept", "button.coi-banner__accept",   # CookieInformation
    "#didomi-notice-agree-button",                                   # Didomi
    ".cmpboxbtnyes",                                                 # consentmanager
    "button.sp_choice_type_11",                                      # Sourcepoint
    "#gravitoCMP-accept-all", "[data-cky-tag=accept-button]",        # Gravito, CookieYes
]
ACCEPT_TEXT = re.compile(
    r"^\s*(hyväksy( kaikki)?( evästeet)?|salli kaikki( evästeet)?|accept( all)?( cookies)?|allow all( cookies)?|"
    r"i accept|agree|godkänn( alla)?( cookies)?|acceptera( alla)?( cookies)?|jag godkänner|godta( alle)?|"
    r"tillåt alla( cookies)?|tillat alle|aksepter( alle)?|acceptér alle|accepter( alle)?|tillad alle|"
    r"alles? akzeptieren|alle cookies akzeptieren|akzeptieren|zustimmen|allen zustimmen)\s*$", re.I)
# Last resort when no button is found: the consent tool's own "accept all" call, as its button would make it
ACCEPT_JS = """() => {
  if (window.Cookiebot && Cookiebot.submitCustomConsent) { Cookiebot.submitCustomConsent(true, true, true); return true }
  if (window.UC_UI && UC_UI.acceptAllConsents) { UC_UI.acceptAllConsents(); return true }
  if (window.__ucCmp && __ucCmp.acceptAllConsents) { __ucCmp.acceptAllConsents(); return true }
  if (window.CookieInformation && CookieInformation.submitAllCategories) { CookieInformation.submitAllCategories(); return true }
  if (window.OneTrust && OneTrust.AllowAll) { OneTrust.AllowAll(); return true }
  if (window.Didomi && Didomi.setUserAgreeToAll) { Didomi.setUserAgreeToAll(); return true }
  return false
}"""
# A bot wall instead of the site (Cloudflare, Akamai): reported as blocked, never worked around
BLOCK_TITLE = re.compile(r"just a moment|access denied|attention required|are you a robot|pardon our interruption", re.I)
SEARCH_INPUT = ("input[type=search], input[name=q], input[name=query], input[name=search], input[name=s], "
                "input[name=text], input[name=searchTerm], input[name=term], input[name=k], input[name=keyword], "
                "input[name=sok], input[name=haku], input[role=combobox], input[name=Search], "
                "input[placeholder*='search' i], input[placeholder*='sök' i], input[placeholder*='søk' i], "
                "input[placeholder*='søg' i], input[placeholder*='such' i], input[placeholder*='hae' i]")
# Tried last, in order, when the page shows no usable search form; one counts only if its page shows the term
SEARCH_PATHS = ["/search?q={}", "/search?query={}", "/search?text={}", "/sok?q={}", "/haku?q={}", "/suche?q={}",
                "/soeg?q={}", "/catalogsearch/result/?q={}", "/?s={}"]
SEARCH_OPENER = re.compile(r"search|hae|haku|sök|søk|søg|suche", re.I)


def _base(host: str) -> str:
    host = host.lower().split(":")[0]
    return host[4:] if host.startswith("www.") else host


def _is_site(host: str, site: str) -> bool:
    host = _base(host)
    return host == site or host.endswith("." + site)


def _short(url: str) -> str:
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}{p.path}"[:160]


def carriers(site: str, requests: list[dict], term: str) -> dict[str, dict]:
    """Recipients whose requests carry the term: {name: {"name", "category", "own_domain", "fields", "evidence",
    "first_ms"}}. `requests` are [{"ms", "url", "body"}] recorded after the search started."""
    found: dict[str, dict] = {}
    for r in sorted(requests, key=lambda r: r["ms"]):
        hits = payload.find_term(r["url"], r.get("body", ""), term)
        if not hits:
            continue
        who = tr.recipient(r["url"])
        if _is_site(urlsplit(r["url"]).netloc, site) and not who["own_domain"]:
            continue  # the site's own search request, not a recipient
        f = found.setdefault(who["name"], {**who, "fields": [], "evidence": [], "first_ms": r["ms"]})
        for h in hits:
            if h["field"] not in f["fields"]:
                f["fields"].append(h["field"])
            if len(f["evidence"]) < 3:
                f["evidence"].append({"ms": r["ms"], "url": _short(r["url"]), **h})
    return found


def merge_runs(runs: list[dict[str, dict]]) -> tuple[list[dict], list[str]]:
    """Recipients seen in every run (stable), and the names seen in only some (left out of the counts)."""
    if not runs:
        return [], []
    stable = [runs[0][n] for n in runs[0] if all(n in r for r in runs[1:])]
    once = sorted({n for r in runs for n in r} - {s["name"] for s in stable})
    stable.sort(key=lambda f: f["first_ms"])
    return stable, once


def search_url(page, term: str) -> Optional[str]:
    """A URL that runs the site's search: from its OpenSearch description, else from a GET search form."""
    href = page.eval_on_selector_all(
        "link[rel=search][type*=opensearch]", "els => els.length ? els[0].href : null")
    if href:
        try:
            xml = page.request.get(href, timeout=10000).text()
            m = re.search(r'<Url[^>]*type="text/html"[^>]*template="([^"]+)"', xml) or \
                re.search(r'<Url[^>]*template="([^"]+)"[^>]*type="text/html"', xml)
            if m and "{searchTerms}" in m.group(1):
                return m.group(1).replace("&amp;", "&").replace("{searchTerms}", term.replace(" ", "+"))
        except Exception as e:  # a broken description just means we try the form next
            print(f"  opensearch failed: {type(e).__name__}", file=sys.stderr)
    form = page.evaluate("""sel => {
        for (const input of document.querySelectorAll(sel)) {
            const f = input.form;
            if (f && input.name && (f.method || 'get').toLowerCase() === 'get') return [f.action, input.name];
        }
        return null;
    }""", SEARCH_INPUT)
    if form and form[0]:
        action = form[0] if form[0].startswith("http") else urljoin(page.url, form[0])
        return f"{action.split('?')[0]}?{urlencode({form[1]: term})}"
    return None


def type_search(page, term: str) -> bool:
    """Fallback: open the search (some sites hide it behind an icon), type the term and press Enter.
    No click on the box itself: before consent the cookie banner often covers it, and fill() doesn't need one."""
    for attempt in range(2):
        loc = page.locator(SEARCH_INPUT)
        for i in range(min(loc.count(), 6)):
            box = loc.nth(i)
            try:
                if box.is_visible():
                    box.fill(term, timeout=3000)
                    box.press("Enter", timeout=3000)
                    return True
            except Exception:  # covered or read-only: try the next box
                continue
        if attempt == 0:
            opener = page.get_by_role("button", name=SEARCH_OPENER)
            try:
                if not opener.count() or not opener.first.is_visible():
                    return False
                opener.first.click(timeout=3000, force=True)
            except Exception:
                return False
            page.wait_for_timeout(800)
    return False


def guess_search(page, site: str, term: str) -> Optional[str]:
    """Last resort: common search addresses. Kept only if the page loads on the site and shows the term."""
    for path in SEARCH_PATHS:
        url = f"https://{site}{path.format(quote_plus(term))}"
        try:
            res = page.request.get(url, timeout=10000)
            if res.ok and _is_site(urlsplit(res.url).netloc, site) and term.lower() in res.text().lower():
                return url
        except Exception:  # unreachable address: try the next pattern
            continue
    return None


def accept_banner(page) -> bool:
    """Click the consent banner's accept button: known consent tools first, then button text, in every frame."""
    for frame in page.frames:
        for sel in ACCEPT_SELECTORS:
            try:
                btn = frame.locator(sel)
                if btn.count() and btn.first.is_visible():
                    btn.first.click(timeout=3000)
                    return True
            except Exception:  # detached frame or a covered button: try the next way
                continue
    for frame in page.frames:
        try:
            btn = frame.get_by_role("button", name=ACCEPT_TEXT)
            if btn.count() and btn.first.is_visible():
                btn.first.click(timeout=3000)
                return True
        except Exception:
            continue
    try:
        return bool(page.evaluate(ACCEPT_JS))
    except Exception:  # the page navigated away mid-call
        return False


def blocked(status, title: str, text: str) -> bool:
    """The response is a bot wall rather than the site."""
    return (status is not None and status in (401, 403, 429, 503)) or bool(BLOCK_TITLE.search(title)) or not text.strip()


def _run(browser, ua: str, site: str, term: str, accept: bool) -> dict:
    """One fresh browser context: load, optionally accept, search, and record what follows."""
    ctx = browser.new_context(user_agent=ua, viewport={"width": 1366, "height": 900})
    page = ctx.new_page()
    reqs: list[dict] = []
    start = [0.0]

    def on_request(r):
        try:
            body = r.post_data or ""
        except Exception:  # binary bodies can't be decoded as text; the URL still counts
            body = ""
        reqs.append({"t": time.monotonic(), "url": r.url, "body": body})

    page.on("request", on_request)
    out = {"accepted": None, "searched": None, "error": None, "blocked": False}
    try:
        res = page.goto(f"https://{site}/", wait_until="commit", timeout=30000)
        try:
            page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass  # slow pages still get the fixed wait below
        page.wait_for_timeout(3500)
        if blocked(res.status if res else None, page.title(), page.inner_text("body", timeout=3000)):
            out["blocked"] = True
            ctx.close()
            return {**out, "carriers": {}, "requests": 0}
        if accept:
            out["accepted"] = accept_banner(page)
            page.wait_for_timeout(2000)
        url = search_url(page, term)
        start[0] = time.monotonic()
        if url:
            page.goto(url, wait_until="commit", timeout=30000)
            out["searched"] = "url"
        elif type_search(page, term):
            out["searched"] = "typed"
        else:
            url = guess_search(page, site, term)
            start[0] = time.monotonic()  # the probes above aren't part of the visit
            if url:
                page.goto(url, wait_until="commit", timeout=30000)
            out["searched"] = "guessed" if url else False
        if out["searched"]:
            page.wait_for_timeout(WAIT_MS)
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {str(e).splitlines()[0]}"[:160]
    ctx.close()
    after = [{"ms": round((r["t"] - start[0]) * 1000), "url": r["url"], "body": r["body"]}
             for r in reqs if start[0] and r["t"] >= start[0]]
    out["carriers"] = carriers(site, after, term) if out["searched"] else {}
    out["requests"] = len(after)
    return out


def _phase(runs: list[dict], accept: bool) -> dict:
    ok = [r for r in runs if r["searched"] and not r["error"] and (r["accepted"] if accept else True)]
    if len(ok) < len(runs):
        first = runs[0]
        status = ("blocked" if first.get("blocked") else "error" if first["error"] else "no_search" if not first["searched"]
                  else "no_accept" if accept and not first["accepted"] else "unstable")
        return {"status": status, "error": first["error"], "recipients": [], "seen_once": []}
    stable, once = merge_runs([r["carriers"] for r in ok])
    return {"status": "ok", "searched": ok[0]["searched"], "recipients": stable, "seen_once": once}


def check_search(site: str, term: str, runs: int = RUNS) -> dict:
    """Both phases for one site and term, each run `runs` times in a fresh context."""
    from playwright.sync_api import sync_playwright  # imported here so the module loads without Playwright

    site = _base(urlsplit(site if "//" in site else f"//{site}").netloc)
    row = {"site": site, "term": term, "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        # Chromium's own user agent minus "Headless": consent tools auto-accept for headless bots
        ua = browser.new_page().evaluate("navigator.userAgent").replace("HeadlessChrome", "Chrome")
        before = [_run(browser, ua, site, term, accept=False) for _ in range(runs)]
        after = [_run(browser, ua, site, term, accept=True) for _ in range(runs)]
        browser.close()
    row["before"], row["after"] = _phase(before, False), _phase(after, True)
    row["verdict"] = verdict(row)
    return row


def sensitive(recipients: list[dict]) -> list[dict]:
    """Recipients that aren't needed to run the search (site search providers, consent and chat tools are)."""
    return [r for r in recipients if r["category"] in SENSITIVE]


def verdict(row: dict) -> str:
    before, after = row["before"], row["after"]
    if before["status"] != "ok" and after["status"] != "ok":
        return "unknown"
    if before["status"] == "ok" and sensitive(before["recipients"]):
        return "sent_before_consent"
    if after["status"] == "ok" and sensitive(after["recipients"]):
        return "sent_after_consent"
    if before["status"] == "ok" and after["status"] == "ok":
        return "not_sent"
    return "unknown"


VERDICT_ORDER = {"sent_before_consent": 0, "sent_after_consent": 1, "not_sent": 2, "unknown": 3}


def survey(sites: Optional[list[dict]] = None, workers: int = 3, refresh: bool = False) -> dict:
    """Check every site (cached per site in data/leaks/) and summarise. Sites are {"site", "term", ...}."""
    spec = json.loads(SITES_FILE.read_text(encoding="utf-8"))
    sites = sites or spec["sites"]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def one(s: dict) -> dict:
        path = CACHE_DIR / f"{s['site']}.json"
        if path.exists() and not refresh:
            return json.loads(path.read_text(encoding="utf-8"))
        r = {**check_search(s["site"], s["term"]), **{k: v for k, v in s.items() if k not in ("site", "term")}}
        if r["verdict"] != "unknown":
            path.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{r['site']}: {r['verdict']}", file=sys.stderr)
        return r

    with ThreadPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(one, sites))
    rows.sort(key=lambda r: (VERDICT_ORDER[r["verdict"]], r["site"]))
    return {"method": {**spec["method"], "runs": RUNS, "wait_ms": WAIT_MS,
                       "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
            "summary": summarise(rows), "sites": rows}


def summarise(rows: list[dict]) -> dict:
    verdicts: dict[str, int] = {}
    companies: dict[str, dict] = {}
    own_domain = set()
    for r in rows:
        verdicts[r["verdict"]] = verdicts.get(r["verdict"], 0) + 1
        for phase in ("before", "after"):
            for rec in sensitive(r[phase]["recipients"]):
                c = companies.setdefault(rec["name"], {"name": rec["name"], "category": rec["category"],
                                                       "before": set(), "after": set()})
                c[phase].add(r["site"])
                if rec["own_domain"]:
                    own_domain.add(r["site"])
    top = sorted(({**c, "before": len(c["before"]), "after": len(c["after"]), "total": len(c["before"] | c["after"])}
                  for c in companies.values()), key=lambda c: (-c["total"], -c["before"], c["name"]))
    return {"sites": len(rows), "verdicts": verdicts, "own_domain": sorted(own_domain), "companies": top}


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["check"] and len(args) >= 3:
        print(json.dumps(check_search(args[1], " ".join(args[2:])), ensure_ascii=False, indent=1))
    elif args[:1] == ["survey"]:
        rep = survey(refresh="--refresh" in args)
        SURVEY_FILE.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"Saved {rep['summary']['sites']} sites to {SURVEY_FILE}: {rep['summary']['verdicts']}")
    else:
        sys.exit("usage: python -m backend.leaks check <site> <term> | survey [--refresh]")
