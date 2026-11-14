
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from dotenv import load_dotenv

# Same HTML parsing as the historical side → names come out in the same form
# and compare well against backend/wayback.py's results.
from backend.wayback import (
    LOGO_HINT, _clean, _dedupe, _detail_links, _domain, _name_from_slug, _parse,
)

load_dotenv()

API_KEY = os.getenv("CONTEXT_DEV_API_KEY")

BASE_URL = "https://api.context.dev/v1"


def search_web(query, num_results=5):
    """Search the web using Context.dev."""

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
            "enabled": True
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


# ---------- Agreed interface (README) ----------

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

    path = urlparse(page_url).path or "/"
    if not path.endswith("/"):
        last = path.rsplit("/", 1)[-1]
        path = path.rsplit("/", 1)[0] + "/" if "." in last else path + "/"
    if path != "/":  # "/" would make every link on the page a "customer"
        for detail_path, link in _detail_links(page, page_url, path).items():
            img = link["img"]
            name = _clean(link["text"]) or (_clean(img["alt"]) if img else "") \
                or _name_from_slug(detail_path)
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
    """Agreed interface (README): customers listed on the company's site today.
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
