"""Churn early warning with precision checks, built on backend.site_tech.

The question for a vendor's customer-success team: which of *our* customers have
started running a competitor's tool next to ours? Two chat tools on one site is
often a trial or a migration in progress, months before the customer cancels.
But many such alerts are noise (a different tool in another part of the business),
so every competitor found is checked before it raises an alarm.

Per customer site (all live, plain requests, no credits):
  1. homepage + Google Tag Manager containers   (site_tech.check_site)
  2. up to two customer-service pages            → same page as ours, or another section?
  3. the help centre's hosting platform          → help.<site> / support.<site>
  4. the privacy policy / cookie page            → does it name the competitor?
  5. the archive history, if cached              → since when has each tool been there?

Statuses (see assess()): likely_switching, possibly_trialling, worth_a_look,
on_competitor, healthy, unknown, unreachable.

CLI:
  python -m backend.churn_watch customers Giosg tokmanni.fi fennia.fi elisa.fi
"""
from __future__ import annotations

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests

from backend import site_tech as st

MAX_SERVICE_PAGES = 2
MAX_PRIVACY_PAGES = 2

# Customer-service pages, most specific first (Finnish and English)
SERVICE_PATHS = [re.compile(p, re.I) for p in (
    r"asiakaspalvelu|customer-?service",
    r"yhteystied|contact|ota-?yhteytt",
    r"/(support|help|tuki|apua)(/|$)",
)]
PRIVACY_PATH = re.compile(r"tietosuoja|privacy|rekisteriseloste|evaste|cookie", re.I)

# Help-centre platforms, recognised from the address or hosting of the page itself,
# never from links on it (an Intercom help centre can still link to old Zendesk articles).
HELP_PLATFORMS = {
    "Zendesk": {"url": r"\.zendesk\.com|/hc/[a-z]{2}(-[a-z]{2})?(/|$)", "page": r"theme\.zdassets\.com|static\.zdassets\.com/hc/"},
    "Intercom": {"url": r"intercom\.help", "page": r"static\.intercomassets\.com|intercom-interblocks"},
    "Freshdesk": {"url": r"\.freshdesk\.com|/support/solutions", "page": r"assets\.freshdesk\.com"},
    "Help Scout": {"url": r"helpscoutdocs\.com", "page": r"helpscout-docs|docs\.helpscout\.net"},
    "Salesforce": {"url": r"\.my\.site\.com|/s/(article|topic)?", "page": r"\bforce\.com/sfsites|sfsites/"},
}
# Words a privacy policy uses for each product (brand names are fine in a legal text,
# unlike on a marketing page)
DISCLOSURE_NAMES = {
    "Giosg": r"\bgiosg\b", "Salesforce chat": r"\bsalesforce\b", "Genesys": r"\bgenesys\b",
    "Zendesk": r"\bzendesk\b", "Intercom": r"\bintercom\b", "HubSpot chat": r"\bhubspot\b",
    "Drift": r"\bdrift\b", "LiveChat": r"\blivechat\b", "Leadoo": r"\bleadoo\b", "Tidio": r"\btidio\b",
    "Crisp": r"\bcrisp\b", "Freshchat": r"\bfresh(chat|works)\b", "LivePerson": r"\bliveperson\b",
}


def _get(url: str) -> Optional[requests.Response]:
    try:
        r = requests.get(url, headers=st.HEADERS, timeout=st.TIMEOUT, allow_redirects=True)
        return r if r.ok and len(r.text) > 200 else None
    except requests.RequestException:
        return None


def _links(html: str, base: str) -> list[tuple[str, str]]:
    """(absolute url, link text) for links on the same site."""
    root = st._site_key(base).split("_")[0]
    out = []
    for href, text in re.findall(r'<a[^>]+href="([^"#]+)"[^>]*>(.*?)</a>', html, re.I | re.S):
        url = urljoin(base, href)
        if urlparse(url).netloc.lower().removeprefix("www.").endswith(root):
            out.append((url.split("?")[0], re.sub(r"<[^>]+>|\s+", " ", text).strip()))
    return out


def service_pages(html: str, base: str) -> list[str]:
    """Up to MAX_SERVICE_PAGES customer-service pages linked from the homepage, by URL path."""
    picked = []
    for rx in SERVICE_PATHS:
        for url in sorted({u for u, _ in _links(html, base) if rx.search(urlparse(u).path)}, key=len):
            if url not in picked and urlparse(url).path.strip("/"):
                picked.append(url)
    return picked[:MAX_SERVICE_PAGES]


def privacy_pages(html: str, base: str) -> list[str]:
    urls = {u for u, text in _links(html, base) if PRIVACY_PATH.search(urlparse(u).path + " " + text)}
    return sorted(urls, key=lambda u: (0 if re.search(r"tietosuoja|privacy", u, re.I) else 1, len(u)))[:MAX_PRIVACY_PAGES]


def help_platform(final_url: str, html: str) -> Optional[str]:
    for name, rx in HELP_PLATFORMS.items():
        if re.search(rx["url"], final_url, re.I) or re.search(rx["page"], html[:400000], re.I):
            return name
    return None


def help_center(site: str) -> Optional[dict]:
    """{"url", "platform"} of the site's hosted help centre, or None."""
    root = st._site_key(site).split("_")[0]
    for host in (f"help.{root}", f"support.{root}"):
        r = _get(f"https://{host}")
        if r is not None:
            platform = help_platform(r.url, r.text)
            if platform:
                return {"url": r.url, "platform": platform}
    return None


def disclosures(urls: list[str], products: list[str]) -> dict[str, str]:
    """{product: privacy page url} for products the privacy/cookie pages name."""
    found = {}
    for url in urls:
        r = _get(url)
        if r is None:
            continue
        text = re.sub(r"<script.*?</script>|<style.*?</style>|<[^>]+>", " ", r.text, flags=re.S | re.I)
        for p in products:
            rx = DISCLOSURE_NAMES.get(p)
            if rx and p not in found and re.search(rx, text, re.I):
                found[p] = r.url
    return found


def page_products(live: dict, home_html: str, pages: list[str]) -> dict[str, list[str]]:
    """{product: [page paths]} for the homepage and service pages. A product loaded
    through Tag Manager counts on every page that loads the same container."""
    gtm_products = {p for p, where in live["found_in"].items() if where == "gtm"}
    html_by_page = {"/": home_html}
    for url in pages:
        r = _get(url)
        if r is not None:
            html_by_page[urlparse(url).path or "/"] = r.text
    on = {}
    for path, html in html_by_page.items():
        here = set(st.detect_products(html))
        if any(gid in html for gid in live.get("gtm_ids", [])):
            here |= gtm_products
        for p in here:
            on.setdefault(p, []).append(path)
    return {p: sorted(v) for p, v in on.items()}


def assess(product: str, live: dict, on_pages: dict, help: Optional[dict], disclosed: dict,
           since: Optional[dict] = None) -> dict:
    """Status for one customer, with the evidence for each competitor found.

    status: likely_switching | possibly_trialling | worth_a_look | on_competitor | healthy | unknown
    Each competitor gets {"name", "same_page": [paths], "other_pages": [paths], "in_privacy_policy": url,
    "help_centre": bool, "since": date}. The rules are deliberately simple so they can be explained:
      likely_switching   = shares a page with our product AND privacy policy or help centre points to it
      possibly_trialling = shares a page with our product OR the privacy policy names it
      worth_a_look       = only on other pages than ours (often a different part of the business)
    """
    cat = st.category_of(product)
    running = set(live["products"])
    ours = product in running
    since = since or {}
    our_pages = set(on_pages.get(product, []))
    rivals = []
    for name in sorted(p for p in running if p != product and st.category_of(p) == cat):
        pages = set(on_pages.get(name, []))
        rivals.append({
            "name": name,
            "same_page": sorted(pages & our_pages),
            "other_pages": sorted(pages - our_pages),
            "in_privacy_policy": disclosed.get(name),
            "help_centre": bool(help) and (help["platform"] == name or name.startswith(help["platform"])),
            "since": since.get(name),
        })
    if not ours and not rivals:
        status = "unknown"
    elif not ours:
        status = "on_competitor"
    elif not rivals:
        status = "healthy"
    elif any(r["same_page"] and (r["in_privacy_policy"] or r["help_centre"]) for r in rivals):
        status = "likely_switching"
    elif any(r["same_page"] or r["in_privacy_policy"] for r in rivals):
        status = "possibly_trialling"
    else:
        status = "worth_a_look"
    return {"status": status, "ours": ours, "our_pages": sorted(our_pages), "rivals": rivals}


STATUS_ORDER = {"likely_switching": 0, "possibly_trialling": 1, "on_competitor": 2, "worth_a_look": 3,
                "unknown": 4, "unreachable": 5, "healthy": 6}


def check_customer(site: str, product: str, record: bool = True) -> dict:
    """Full early-warning check for one customer site (live, plain requests)."""
    row = {"site": st._site_key(site)}
    try:
        live = st.check_site(site)
    except Exception as e:
        return {**row, "status": "unreachable", "error": f"{type(e).__name__}: {e}"[:160]}
    home = _get(live["url"])
    html = home.text if home is not None else ""
    with ThreadPoolExecutor(3) as pool:
        f_pages = pool.submit(lambda: page_products(live, html, service_pages(html, live["url"])))
        f_help = pool.submit(help_center, site)
        f_disc = pool.submit(disclosures, privacy_pages(html, live["url"]),
                             [p for p in live["products"] if st.category_of(p) == st.category_of(product)])
        on_pages, help, disclosed = f_pages.result(), f_help.result(), f_disc.result()

    # When each tool first appeared in the archive (cached only; never fetches)
    hist = st._cached_history(site)
    since = {}
    if hist:
        rep = st.site_report(site, live=live, history=hist)
        since = {p: i.get("since") for p, i in rep["products"].items() if i.get("since")}

    a = assess(product, live, on_pages, help, disclosed, since)
    a["dropped_since_last_check"] = False
    if record:
        stored = st.store_check(site, live)
        row["changes"], row["previous_check"] = stored["changes"], (stored["previous"] or {}).get("checked_at")
        if stored["changes"] and product in stored["changes"]["removed"]:
            a["dropped_since_last_check"] = True  # our tool vanished since the last check
            a["status"] = "likely_switching" if a["rivals"] else a["status"]
    return {**row, **a, "products": live["products"], "found_in": live["found_in"], "on_pages": on_pages,
            "help_center": help, "disclosed": disclosed, "url": live["url"], "latency_ms": live["latency_ms"],
            "history": hist is not None}


def churn_report(sites: list[str], product: str, record: bool = True) -> dict:
    with ThreadPoolExecutor(6) as pool:
        rows = list(pool.map(lambda s: check_customer(s, product, record), sites))
    rows.sort(key=lambda r: STATUS_ORDER.get(r["status"], 9))
    summary: dict[str, int] = {}
    for r in rows:
        summary[r["status"]] = summary.get(r["status"], 0) + 1
    return {"product": product, "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "summary": summary, "customers": rows}


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["customers"] and len(args) >= 3:
        rep = churn_report(args[2:], args[1])
        print(f"{rep['product']}: {rep['summary']}")
        for r in rep["customers"]:
            ev = "; ".join(f"{x['name']}: same page {x['same_page'] or '-'}, other pages {x['other_pages'] or '-'}, "
                           f"privacy {'yes' if x['in_privacy_policy'] else '-'}, help centre {'yes' if x['help_centre'] else '-'}"
                           for x in r.get("rivals", []))
            print(f"  {r['site']:<20} {r['status']:<19} {ev or r.get('error', '')}")
    else:
        print(__doc__)
