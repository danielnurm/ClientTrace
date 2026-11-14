"""Which third-party products (chat, analytics, consent, ...) a website runs right now.

Reads two live sources per site:
  1. the homepage HTML
  2. every Google Tag Manager container it loads (gtm.js?id=GTM-...), because many
     sites inject their chat widget through GTM, so it never shows up in the HTML

Detection is a plain substring match on script hosts / loader calls only (no
brand names in text), so a page that merely *mentions* a product doesn't count.

Live checks are stored per site in data/sites/<site>_live.json, so every check
can be compared with the previous one ("what changed since last time").

CLI:
  python -m backend.site_tech check tokmanni.fi fennia.fi
  python -m backend.site_tech watch http://localhost:8765 --interval 5
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
from urllib.parse import urlparse

import requests

from backend.wayback import SITES_DIR as HISTORY_DIR, _domain as _host

TIMEOUT = 20
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ClientTrace/0.1; +site-check)"}
SITES_DIR = Path(__file__).resolve().parent.parent / "data" / "sites"
GTM_RE = re.compile(r"GTM-[A-Z0-9]{4,9}")
MAX_GTM = 3  # containers read per site

# product → category + patterns (lower-case substrings of script hosts / loader calls).
# "verified": seen on a real site in our experiment (14.11.2026), the rest are the
# vendors' documented embed hosts.
SIGNATURES: dict[str, dict] = {
    # customer-service chat
    "Giosg":           {"category": "chat", "patterns": ["service.giosg.com"], "verified": True},
    "Salesforce chat": {"category": "chat", "patterns": ["embeddedservice_bootstrap", "salesforceliveagent.com"], "verified": True},
    "Genesys":         {"category": "chat", "patterns": ["apps.mypurecloud.", "window.genesys(",
                                                     "-genesys-prod."],  # self-hosted widget (omasp.fi)
                        "verified": True},
    # Nordic chat / AI bot vendors, each verified on real bank and insurer sites (14.11.2026)
    "Boost.ai":        {"category": "chat", "patterns": ["boost.ai/chatpanel"], "verified": True},  # aktia.fi, tryg.no, almbrand.dk
    "Puzzel":          {"category": "chat", "patterns": ["app-cdn.puzzel.com"], "verified": True},  # danskebank.fi/.dk, if.se, if.no
    "Humany":          {"category": "chat", "patterns": [".humany.net"], "verified": True},         # folksam.se
    "Zendesk":         {"category": "chat", "patterns": ["static.zdassets.com/ekr", "v2.zopim.com"], "verified": True},
    "Intercom":        {"category": "chat", "patterns": ["widget.intercom.io", "js.intercomcdn.com"]},
    "HubSpot chat":    {"category": "chat", "patterns": ["js.usemessages.com"]},
    "Drift":           {"category": "chat", "patterns": ["js.driftt.com"]},
    "LiveChat":        {"category": "chat", "patterns": ["cdn.livechatinc.com"]},
    "Leadoo":          {"category": "chat", "patterns": ["bot.leadoo.com"]},
    "Tidio":           {"category": "chat", "patterns": ["code.tidio.co"]},
    "Crisp":           {"category": "chat", "patterns": ["client.crisp.chat"]},
    "Freshchat":       {"category": "chat", "patterns": ["wchat.freshchat.com"]},
    "LivePerson":      {"category": "chat", "patterns": ["lpsnmedia.net"]},
    # analytics / session recording
    "Google Analytics": {"category": "analytics", "patterns": ["googletagmanager.com/gtag/js", "google-analytics.com/analytics.js"]},
    "Matomo":          {"category": "analytics", "patterns": ["matomo.js", "piwik.js"]},
    "Hotjar":          {"category": "analytics", "patterns": ["static.hotjar.com"]},
    "Microsoft Clarity": {"category": "analytics", "patterns": ["clarity.ms/tag"]},
    # marketing automation
    "HubSpot":         {"category": "marketing", "patterns": ["js.hs-scripts.com"], "verified": True},
    "Marketo":         {"category": "marketing", "patterns": ["munchkin.marketo.net"]},
    "Pardot":          {"category": "marketing", "patterns": ["pi.pardot.com"]},
    # cookie consent
    "Cookiebot":       {"category": "consent", "patterns": ["consent.cookiebot.com"]},
    "OneTrust":        {"category": "consent", "patterns": ["cdn.cookielaw.org"]},
    "Usercentrics":    {"category": "consent", "patterns": ["app.usercentrics.eu", "web.cmp.usercentrics.eu"]},
    # A/B testing
    "Optimizely":      {"category": "ab-testing", "patterns": ["cdn.optimizely.com"]},
    "VWO":             {"category": "ab-testing", "patterns": ["dev.visualwebsiteoptimizer.com"]},
}


# ---------- detection ----------

def detect_products(text: str, signatures: Optional[dict] = None) -> list[str]:
    """Product names whose patterns occur in `text` (HTML or a GTM container)."""
    low = (text or "").lower().replace("\\/", "/")  # GTM containers escape slashes as \/
    sigs = signatures or SIGNATURES
    return sorted(name for name, s in sigs.items() if any(p in low for p in s["patterns"]))


def category_of(product: str, signatures: Optional[dict] = None) -> str:
    return (signatures or SIGNATURES).get(product, {}).get("category", "other")


def _site_url(site: str) -> str:
    """'tokmanni.fi' → 'https://www.tokmanni.fi/', full URLs (incl. localhost) kept as is."""
    if "//" in site:
        return site
    return f"https://{site if site.count('.') > 1 else 'www.' + site}/"


def _site_key(site: str) -> str:
    """File-safe id: 'https://www.tokmanni.fi/' → 'tokmanni.fi', 'http://localhost:8765' → 'localhost_8765'."""
    return re.sub(r"[^a-z0-9.\-]", "_", _host(_site_url(site)))


def check_site(site: str, signatures: Optional[dict] = None) -> dict:
    """One live check: homepage HTML + its GTM containers.

    Returns {"site", "url", "checked_at", "latency_ms", "products": [...],
             "found_in": {product: "html" | "gtm"}, "gtm_ids": [...], "error"?}.
    A failed homepage fetch raises; a failed GTM fetch is noted in "gtm_errors".
    """
    url = _site_url(site)
    start = time.monotonic()
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    html = resp.text
    found_in = {p: "html" for p in detect_products(html, signatures)}

    gtm_ids = sorted(set(GTM_RE.findall(html)))[:MAX_GTM]
    gtm_errors = []

    def fetch_gtm(gid):
        r = requests.get(f"https://www.googletagmanager.com/gtm.js?id={gid}", headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        return r.text

    with ThreadPoolExecutor(max_workers=MAX_GTM) as pool:
        futures = {gid: pool.submit(fetch_gtm, gid) for gid in gtm_ids}
    for gid, fut in futures.items():
        try:
            for p in detect_products(fut.result(), signatures):
                found_in.setdefault(p, "gtm")
        except requests.RequestException as e:
            gtm_errors.append(f"{gid}: {e}")

    result = {
        "site": _site_key(site),
        "url": url,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "latency_ms": round((time.monotonic() - start) * 1000),
        "products": sorted(found_in),
        "found_in": found_in,
        "gtm_ids": gtm_ids,
    }
    if gtm_errors:
        result["gtm_errors"] = gtm_errors
    return result


def check_sites(sites: list[str], signatures: Optional[dict] = None, workers: int = 8) -> dict[str, dict]:
    """Checks many sites in parallel. Failed sites get {"site", "error"} instead of raising."""
    def one(site):
        try:
            return check_site(site, signatures)
        except Exception as e:  # one unreachable site must not stop the rest
            return {"site": _site_key(site), "url": _site_url(site), "error": f"{type(e).__name__}: {e}"}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return {s: r for s, r in zip(sites, pool.map(one, sites))}


# ---------- change over time ----------

def diff_products(before: list[str], after: list[str], signatures: Optional[dict] = None) -> dict:
    """{"added": [...], "removed": [...], "switches": [{"from", "to", "category"}]}.
    A switch = one product of a category removed and another of the same category added."""
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    switches = [
        {"from": r, "to": a, "category": category_of(r, signatures)}
        for r in removed for a in added
        if category_of(r, signatures) == category_of(a, signatures)
    ]
    return {"added": added, "removed": removed, "switches": switches}


def _live_path(site: str) -> Path:
    return SITES_DIR / f"{_site_key(site)}_live.json"


def load_live_checks(site: str) -> list[dict]:
    try:
        return json.loads(_live_path(site).read_text(encoding="utf-8"))["checks"]
    except (OSError, ValueError, KeyError):
        return []


def record_live_check(site: str, signatures: Optional[dict] = None) -> dict:
    """Checks the site now, stores the check and compares it with the previous stored one.

    Returns {"check": {...}, "previous": {...} | None, "changes": diff_products(...) | None}.
    """
    return store_check(site, check_site(site, signatures), signatures)


def store_check(site: str, check: dict, signatures: Optional[dict] = None) -> dict:
    """Appends an existing live check to the site's history; same return as record_live_check."""
    checks = load_live_checks(site)
    previous = checks[-1] if checks else None
    changes = diff_products(previous["products"], check["products"], signatures) if previous else None
    checks.append(check)
    path = _live_path(site)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"site": check["site"], "checks": checks[-200:]}, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    return {"check": check, "previous": previous, "changes": changes}


def watch(site: str, interval: float = 5.0, rounds: Optional[int] = None, on_change=None) -> None:
    """Re-checks `site` every `interval` seconds and reports changes (in memory, nothing stored)."""
    previous, n = None, 0
    while rounds is None or n < rounds:
        n += 1
        try:
            check = check_site(site)
        except Exception as e:
            print(f"{time.strftime('%H:%M:%S')}  {site}: check failed ({e})", flush=True)
        else:
            stamp = f"{time.strftime('%H:%M:%S')}  {check['site']} ({check['latency_ms']} ms)"
            if previous is None:
                print(f"{stamp}  now running: {', '.join(check['products']) or 'nothing detected'}", flush=True)
            else:
                changes = diff_products(previous["products"], check["products"])
                if changes["added"] or changes["removed"]:
                    for s in changes["switches"]:
                        print(f"\a{stamp}  ⚠ SWITCH ({s['category']}): {s['from']} → {s['to']}", flush=True)
                    if not changes["switches"]:
                        print(f"\a{stamp}  ⚠ CHANGE: +{changes['added']} -{changes['removed']}", flush=True)
                    if on_change:
                        on_change(check, changes)
            previous = check
        if rounds is None or n < rounds:
            time.sleep(interval)


# ---------- live + archive combined ----------

def site_report(site: str, from_year: int = 2021, live: Optional[dict] = None,
                history: Optional[dict] = None) -> dict:
    """Combines the live check (HTML + GTM) with the Wayback history (archived HTML).

    Returns {"site", "live", "history_captures", "products": {name: {...}}, "signals": [...]}
    where each product has "status" (running | removed), "confidence" (high | medium | low),
    "since"/"missing_since" when known and "evidence" links. Signals are the
    sales-relevant conclusions: switches and new competitors in a category.
    Pass `live`/`history` to reuse results; otherwise they are fetched (history from cache).
    """
    from backend.wayback import get_site_history
    live = live or check_site(site)
    history = history or get_site_history(site, from_year=from_year)
    arch = history.get("products", {})
    caps = [c for c in history.get("captures", []) if "error" not in c]

    def first_url(p):
        return next((c["url"] for c in caps if p in c["products"]), None)

    def last_url(p):
        return next((c["url"] for c in reversed(caps) if p in c["products"]), None)

    products = {}
    for p in sorted(set(live["products"]) | set(arch)):
        a, where = arch.get(p), live["found_in"].get(p)
        info = {"category": category_of(p), "live": where, "archive": a}
        if where:
            info["status"] = "running"
            info["confidence"] = "high" if a or where == "html" else "medium"
            info["since"] = a["first_seen"] if a else None  # None: loaded via GTM, not archived
            info["evidence"] = [u for u in (first_url(p), live["url"]) if u]
        else:
            info["status"] = "removed"
            info["confidence"] = "high" if a["status"] == "removed" else "medium"
            info["last_seen"] = a["last_seen"]
            info["missing_since"] = a.get("missing_since")
            info["evidence"] = [u for u in (last_url(p), live["url"]) if u]
        products[p] = info

    signals = []
    by_cat: dict[str, list[str]] = {}
    for p, i in products.items():
        by_cat.setdefault(i["category"], []).append(p)
    for cat, names in by_cat.items():
        gone = [p for p in names if products[p]["status"] == "removed"]
        running = [p for p in names if products[p]["status"] == "running"]
        for g in gone:
            for r in running:
                g_first, r_since = products[g]["archive"]["first_seen"], products[r]["since"]
                if r_since and r_since <= g_first:
                    continue  # both ran side by side from the start: consolidation, not a switch
                if not r_since:
                    conf = "low"  # new tool only visible live (GTM): when it arrived is unknown
                elif products[g]["confidence"] == products[r]["confidence"] == "high":
                    conf = "high"
                else:
                    conf = "medium"
                signals.append({"type": "switch", "category": cat, "from": g, "to": r, "confidence": conf,
                                "between": [products[g]["last_seen"], products[g].get("missing_since") or live["checked_at"][:10]]})
        # two tools in one category, one of them new in the archive → switch probably in progress
        if len(running) > 1 and not gone:
            dated = sorted((products[p]["since"], p) for p in running if products[p]["since"])
            year_ago = f"{int(live['checked_at'][:4]) - 1}{live['checked_at'][4:10]}"
            if dated and dated[-1][0] >= year_ago and (len(dated) == 1 or dated[-1][0] > dated[-2][0]):
                since, newest = dated[-1]
                others = [p for p in running if p != newest]
                signals.append({"type": "new_competitor", "category": cat, "new": newest, "since": since,
                                "alongside": others, "confidence": "low"})
    return {"site": live["site"], "live": live, "history_captures": len(caps),
            "products": products, "signals": signals}


# ---------- supplier view: which of a vendor's showcased customers still run it ----------

DOMAINS_CACHE = SITES_DIR / "domains.json"
SKIP_HOSTS = re.compile(r"linkedin|facebook|twitter|x\.com|instagram|youtube|wikipedia|crunchbase|bloomberg|"
                        r"glassdoor|finder\.fi|asiakastieto|kauppalehti|google\.", re.I)


def _urls_in(obj) -> list[str]:
    """Every 'url' string in a nested API response, in order."""
    if isinstance(obj, dict):
        out = [obj["url"]] if isinstance(obj.get("url"), str) else []
        for v in obj.values():
            out += _urls_in(v)
        return out
    if isinstance(obj, list):
        return [u for v in obj for u in _urls_in(v)]
    return []


def find_customer_domain(name: str, supplier_host: str = "", search=None) -> Optional[str]:
    """Customer's own website domain via a web search (1 Context.dev credit), cached in data/sites/domains.json."""
    try:
        known = json.loads(DOMAINS_CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        known = {}
    if name in known:
        return known[name]
    if search is None:
        from backend.context_api import search_web as search
    result = search(f"{name} official website", num_results=5, markdown=False)
    domain = next((_host(u) for u in _urls_in(result)
                   if not SKIP_HOSTS.search(u) and (not supplier_host or supplier_host not in _host(u))), None)
    known[name] = domain
    DOMAINS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    DOMAINS_CACHE.write_text(json.dumps(known, ensure_ascii=False, indent=1), encoding="utf-8")
    return domain


def _cached_history(domain: str) -> Optional[dict]:
    """Wayback history only if already cached, whatever its from_year: never fetches
    (a fresh crawl takes minutes per site and would block the dashboard)."""
    try:
        return json.loads((HISTORY_DIR / f"{_host(domain)}_history.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _verdict(report: dict, product: str) -> tuple[str, str]:
    """(verdict, confidence) for one customer site and the supplier's product."""
    p = report["products"].get(product)
    for s in report["signals"]:
        if s["type"] == "switch" and s["to"] == product:
            return "won", s["confidence"]
        if s["type"] == "switch" and s["from"] == product:
            return "switched_away", s["confidence"]
        if s["type"] == "new_competitor" and product in s["alongside"]:
            return "competitor_added", s["confidence"]
    if p and p["status"] == "running":
        return "still_running", p["confidence"]
    if p and p["status"] == "removed":
        return "removed", p["confidence"]
    if competitors_running(report, product):
        return "runs_competitor", "medium"  # the supplier's product isn't there, a rival's is
    return "not_detected", "low"


def competitors_running(report: dict, product: str) -> list[str]:
    """Products of the same category as `product` that the site runs now (not `product` itself)."""
    cat = category_of(product)
    return sorted(p for p, i in report["products"].items()
                  if p != product and i["status"] == "running" and i["category"] == cat)


def resolve_customers(supplier_url: str, customers: Optional[list[dict]] = None, search=None) -> list[dict]:
    """[{"name", "domain"}] or [{"name", "domain": None, "verdict": "error", "error"}] per customer.
    customers=None reads them from the supplier's customer page (Context.dev, cached)."""
    supplier_host = _host(supplier_url)
    if customers is None:
        from backend.context_api import get_current_customers
        customers = get_current_customers(supplier_url)
    rows = []
    for c in customers:
        domain = c.get("domain")
        src = c.get("source_url") or ""
        if not domain and src and supplier_host not in _host(src) and "web.archive.org" not in src \
                and not SKIP_HOSTS.search(src):
            domain = _host(src)  # the supplier linked straight to the customer's site
        if not domain:
            try:
                domain = find_customer_domain(c["name"], supplier_host, search)
            except Exception as e:
                rows.append({"name": c["name"], "domain": None, "verdict": "error", "error": f"domain lookup: {e}"})
                continue
        if not domain:
            rows.append({"name": c["name"], "domain": None, "verdict": "error",
                         "error": "no website found for this customer"})
            continue
        rows.append({"name": c["name"], "domain": domain})
    return rows


def supplier_report(supplier_url: str, product: str, customers: Optional[list[dict]] = None,
                    search=None, record: bool = False) -> dict:
    """One input → full result. Combines five sources:
      1. the supplier's customer page (Context.dev, cached)  2. each customer's homepage live
      3. its GTM containers live  4. its Wayback history (if cached)  5. a web search for its domain.

    `customers`: optional [{"name", "domain"?}] to skip step 1. record=True stores each live
    check and adds "changes" (diff vs. the previous stored check) and "previous_check". Returns
    {"supplier", "product", "elapsed_ms", "summary": {verdict: n}, "customers": [{"name", "domain",
     "verdict", "confidence", "signals", "products", "evidence", "history": bool, "error"?}]}.
    """
    start = time.monotonic()
    supplier_host = _host(supplier_url)
    rows = resolve_customers(supplier_url, customers, search)

    todo = [r for r in rows if r.get("domain") and "error" not in r]
    live = check_sites([r["domain"] for r in todo])
    for r in todo:
        lv = live[r["domain"]]
        if "error" in lv:
            r.update(verdict="error", error=lv["error"])
            continue
        hist = _cached_history(r["domain"])
        rep = site_report(r["domain"], live=lv, history=hist or {"captures": [], "products": {}})
        verdict, conf = _verdict(rep, product)
        if record:
            stored = store_check(r["domain"], lv)
            r["changes"] = stored["changes"]
            r["previous_check"] = (stored["previous"] or {}).get("checked_at")
        info = rep["products"].get(product, {})
        r.update(verdict=verdict, confidence=conf, history=hist is not None,
                 competitors=competitors_running(rep, product),
                 signals=[s for s in rep["signals"] if product in (s.get("from"), s.get("to"), s.get("new"), *s.get("alongside", []))],
                 products={p: {k: i.get(k) for k in ("category", "status", "live", "since", "confidence")}
                           for p, i in rep["products"].items()},
                 evidence=info.get("evidence", [lv["url"]]), latency_ms=lv["latency_ms"])

    summary: dict[str, int] = {}
    for r in rows:
        summary[r["verdict"]] = summary.get(r["verdict"], 0) + 1
    return {"supplier": supplier_host, "product": product, "elapsed_ms": round((time.monotonic() - start) * 1000),
            "summary": summary, "customers": rows}


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["watch"] and len(args) >= 2:
        every = float(args[args.index("--interval") + 1]) if "--interval" in args else 5.0
        watch(args[1], interval=every)
    elif args[:1] == ["supplier"] and len(args) >= 4:
        # python -m backend.site_tech supplier giosg.com Giosg tokmanni.fi fennia.fi ...
        rep = supplier_report(args[1], args[2], customers=[{"name": d, "domain": d} for d in args[3:]])
        print(f"{rep['product']} customers ({rep['elapsed_ms']} ms): {rep['summary']}")
        for r in rep["customers"]:
            extra = r.get("error") or "; ".join(
                f"switch {s['from']} → {s['to']} ({s['between'][0]} … {s['between'][1]})" if s["type"] == "switch"
                else f"{s['new']} added {s['since']}, {', '.join(s['alongside'])} still loaded"
                for s in r.get("signals", []))
            print(f"  {r['name']:20} {r['verdict']:17} {r.get('confidence', ''):7} {extra}")
    elif args[:1] == ["check"] and len(args) >= 2:
        for site, r in check_sites(args[1:]).items():
            if "error" in r:
                print(f"{site:22} ERROR {r['error'][:80]}")
            else:
                where = ", ".join(f"{p} [{r['found_in'][p]}]" for p in r["products"]) or "-"
                print(f"{site:22} {r['latency_ms']:5} ms  {where}")
    else:
        print(__doc__)
