
import json
import os
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from dotenv import load_dotenv

# Same HTML parsing as the historical side → names come out in the same form
# and compare well against backend/wayback.py's results.
from backend.wayback import (
    LOGO_HINT, _clean, _dedupe, _detail_links, _domain, _link_name, _listing_dir,
    _name_from_slug, _parse,
)

load_dotenv()

API_KEY = os.getenv("CONTEXT_DEV_API_KEY")

BASE_URL = "https://api.context.dev/v1"


def search_web(query, num_results=5, markdown=True):
    """Search the web using Context.dev. markdown=False skips page contents (cheaper)."""

    if not API_KEY:
        raise ValueError("Context.dev API key is missing from .env")

    url = f"{BASE_URL}/web/search"

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "query": query,
        "numResults": num_results,
        "markdownOptions": {
            "enabled": markdown
        }
    }

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=90
    )

    response.raise_for_status()
    return response.json()


def scrape_page(url, html=False):
    """Retrieve webpage content as Markdown (or raw HTML with html=True)."""

    if not API_KEY:
        raise ValueError("Context.dev API key is missing from .env")

    endpoint = f"{BASE_URL}/web/scrape"

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "url": url,
        "formats": {"html": True} if html else {
            "markdown": True
        }
    }

    response = requests.post(
        endpoint,
        headers=headers,
        json=payload,
        timeout=90
    )

    response.raise_for_status()
    return response.json()


# ---------- Agreed interface (CONTRIBUTING.md) ----------

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "current"
# Customer-page paths to try, most common first. Each try costs 1 credit.
PROBE_PATHS = ["customers", "references", "case-studies", "en/customers", "en/references"]
MAX_SCRAPES = 4  # credit cap per company
SOCIAL = re.compile(r"linkedin|twitter|facebook|instagram|youtube|tiktok|github|x-logo", re.I)


def _customers_from_html(html, page_url, own):
    """Customers from a live listing page: logo wall + links to detail pages below it."""
    page = _parse(html)
    customers = []

    for img in page.images:
        hint = f"{img['src']} {img['cls']} {img['alt']}"
        if not LOGO_HINT.search(hint) or own in hint.lower() or SOCIAL.search(hint):
            continue
        name = _clean(re.sub(r"(?i)\blogo\b", "", img["alt"])) or _name_from_slug(img["src"])
        if name:
            customers.append({"name": name, "logo_url": urljoin(page_url, img["src"]),
                              "source_url": page_url})

    path = _listing_dir(urlparse(page_url).path)
    if path != "/":  # "/" would make every link on the page a "customer"
        for detail_path, link in _detail_links(page, page_url, path).items():
            img = link["img"]
            name = _link_name(link, detail_path)
            logo = urljoin(page_url, img["src"]) if img else ""
            if own in logo.rsplit("/", 1)[-1].lower():  # company's own logo
                logo = ""
            customers.append({"name": name, "logo_url": logo,
                              "source_url": urljoin(page_url, link["href"])})

    return _dedupe(customers)


def _candidate_pages(url):
    parsed = urlparse(url if "//" in url else f"https://{url}")
    base = f"{parsed.scheme or 'https'}://{parsed.netloc}"
    pages = [f"{base}/{p}/" for p in PROBE_PATHS]
    if parsed.path.strip("/"):  # user gave the customer page itself → try it first
        pages.insert(0, f"{base}{parsed.path}")
    return pages


def get_current_customers(url, refresh=False):
    """Agreed interface (CONTRIBUTING.md): customers listed on the company's site today.
    Tries the usual customer-page paths (max MAX_SCRAPES credits) and caches the
    result in data/current/<domain>.json, so each company costs credits once.
    refresh=True ignores the cache. Returns [] if no customer page was found."""
    domain = _domain(url)
    cache = CACHE_DIR / f"{domain}.json"
    if not refresh and cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))["customers"]

    own = domain.split(".")[0]
    customers, source = [], None
    for page_url in _candidate_pages(url)[:MAX_SCRAPES]:
        try:
            result = scrape_page(page_url, html=True)
        except requests.HTTPError:
            continue  # page doesn't exist → try the next path
        html = (result.get("html") or {}).get("data") or ""
        customers = _customers_from_html(html, result.get("url") or page_url, own)
        if customers:
            source = page_url
            break

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({
        "domain": domain,
        "source": source,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "customers": customers,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return customers


def get_current_source(url):
    """The customer page get_current_customers() used for this company, if cached."""
    cache = CACHE_DIR / f"{_domain(url)}.json"
    if not cache.exists():
        return None
    return json.loads(cache.read_text(encoding="utf-8")).get("source")


# ---------- Is a lost customer still mentioned on the company's site? ----------

MENTIONS_DIR = Path(__file__).resolve().parent.parent / "data" / "mentions"
# Parallel searches. Default plan allows 2 concurrent requests; raise it via .env if yours allows more.
MENTION_WORKERS = int(os.getenv("CONTEXT_DEV_CONCURRENCY") or 2)
RATE_LIMIT_RETRIES = 3


def _plain(text):
    """Lowercase, accents and punctuation removed: "Wärtsilä Oyj" → "wartsila oyj"."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    return " ".join(re.sub(r"[^\w]+", " ", text).split())


def _with_retry(func, *args, **kwargs):
    """Calls a Context.dev function, waiting and retrying when it answers 429 (rate limit)."""
    for attempt in range(RATE_LIMIT_RETRIES + 1):
        try:
            return func(*args, **kwargs)
        except requests.HTTPError as e:
            response = e.response
            if response is None or response.status_code != 429 or attempt == RATE_LIMIT_RETRIES:
                raise
            try:  # wait as long as the API asks
                wait = float(response.headers.get("Retry-After") or 1)
            except ValueError:
                wait = 1.0
            time.sleep(min(wait, 10))


def _page_names(url, name):
    """True/False: is the page live and does it name the customer? None if it can't be fetched.
    Search indexes keep dead pages, so every hit is checked before it counts."""
    wanted = f" {_plain(name)} "
    try:  # plain request first: free and fast
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0 (ClientTrace)"})
        if r.ok and "html" in r.headers.get("Content-Type", ""):
            if wanted in f" {_plain(r.text)} ":
                return True
            if urlparse(r.url).path.rstrip("/") != urlparse(url).path.rstrip("/"):
                return False  # redirected elsewhere: the page is gone
    except requests.RequestException:
        pass
    try:  # blocked, failed or JS-rendered → let Context.dev fetch it (1 credit)
        page = _with_retry(scrape_page, url)
    except requests.RequestException:
        return None
    return wanted in f" {_plain((page.get('markdown') or {}).get('data'))} "


def _site_mention(domain, name):
    """First live page on the company's main site that names the customer, or None.
    1 Context.dev search, plus a scrape for hits a plain request can't verify."""
    result = _with_retry(search_web, f'site:{domain} "{name}"', num_results=5, markdown=False)
    wanted = f" {_plain(name)} "
    main_site = {domain, f"www.{domain}"}  # not qa-, cms- or distributor subdomains
    hits = [
        h for h in result.get("results") or []
        if urlparse(h.get("url") or "").netloc.lower() in main_site
        and not (h.get("url") or "").lower().endswith(".pdf")  # old brochures aren't evidence
        and wanted in f" {_plain(h.get('title'))} {_plain(h.get('description'))} {_plain(h.get('url'))} "
    ]
    unverified = False
    for hit in hits:
        named = _page_names(hit["url"], name)
        if named:
            return {"url": hit["url"], "title": _clean(hit.get("title") or "")}
        unverified = unverified or named is None
    if unverified:
        raise requests.ConnectionError(f"couldn't verify search hits for {name}")
    return None


def find_site_mentions(url, names, refresh=False):
    """For each customer name: {"mentioned": bool, "url", "title", "checked_at"}.
    Searches the company's own site (1 credit per name, run in parallel) and caches
    the answers in data/mentions/<domain>.json. Names whose search failed are left
    out of the result, so the caller can show them as unchecked."""
    domain = _domain(url)
    cache = MENTIONS_DIR / f"{domain}.json"
    known = {} if refresh or not cache.exists() else json.loads(cache.read_text(encoding="utf-8"))
    todo = [n for n in dict.fromkeys(names) if n not in known]

    if todo:
        if not API_KEY:
            raise ValueError("Context.dev API key is missing from .env")

        def check(name):
            try:
                return name, _site_mention(domain, name)
            except Exception:  # one failed name must not stop the others
                return name, False  # failed → not cached, shown as unchecked

        now = datetime.now(timezone.utc).isoformat()
        with ThreadPoolExecutor(max_workers=MENTION_WORKERS) as pool:
            for name, hit in pool.map(check, todo):
                if hit is False:
                    continue
                known[name] = {"mentioned": hit is not None, **(hit or {}), "checked_at": now}

        MENTIONS_DIR.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(known, ensure_ascii=False, indent=2), encoding="utf-8")

    return {n: known[n] for n in names if n in known}
