"""Role 2 – historical customers from the Wayback Machine.

Finds archived customer/reference pages of a company for a given year via the
Wayback CDX API, and extracts customer names + logos from them.

Results are cached in data/historical.json; get_historical_customers() reads
the cache when it matches the domain + year, so Wayback is only hit once.

CLI:  python -m backend.wayback kone.com 2023   → (re)fetches and writes data/historical.json
"""
from __future__ import annotations

import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests

CDX_URL = "https://web.archive.org/cdx/search/cdx"
TIMEOUT = 40
HEADERS = {"User-Agent": "ClientTrace/0.1 (historical customer research)"}

CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "historical.json"

# Paths where companies typically list their customers.
# Full-domain CDX queries time out on big sites, so we probe these one by one:
# the most common slugs first, the rest only if those find nothing.
LANG_PREFIXES = ["", "en/", "fi/"]
PRIMARY_SLUGS = ["customers", "references", "case-studies"]
SECONDARY_SLUGS = [
    "our-customers", "clients", "customer-stories", "success-stories",
    "asiakkaat", "referenssit", "asiakastarinat",
]
MAX_DETAIL_PAGES = 30  # cap on archived detail pages fetched per company
MIN_INTERVAL = 5.0     # seconds between Wayback requests (it blocks fast clients)
BLOCK_WAIT = 60        # first wait after a refusal; doubles on each retry
LOGO_HINT = re.compile(r"logo|customer|client|partner|brand", re.I)
SKIP_LINK = re.compile(r"\.(pdf|jpg|png|zip)$|[?#]", re.I)


# ---------- Wayback helpers ----------

_lock = threading.Lock()
_last_call = [0.0]


def _throttle():
    with _lock:
        wait = _last_call[0] + MIN_INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.monotonic()


def _get(url: str, params: Optional[dict] = None, retries: int = 3) -> requests.Response:
    """GET with timeout, throttling and retry on Wayback's frequent 5xx/429/refusals.
    A refused connection means Wayback has blocked us for a while, so wait minutes."""
    last = None
    for attempt in range(retries):
        _throttle()
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
            if resp.status_code < 500 and resp.status_code != 429:
                return resp
            last = f"HTTP {resp.status_code}"
        except requests.ConnectionError as e:
            last = f"connection refused, Wayback is rate-limiting this IP ({e})"
            if attempt < retries - 1:
                time.sleep(BLOCK_WAIT * 2 ** attempt)
            continue
        except requests.RequestException as e:
            last = str(e)
        if attempt < retries - 1:
            time.sleep(10 * 2 ** attempt)
    raise RuntimeError(f"Wayback request failed ({last}): {url}")


def _cdx(url: str, year: int, prefix: bool = False, limit: int = 200) -> list[tuple[str, str]]:
    """Returns [(timestamp, original_url)] of 200-OK HTML captures in `year`."""
    params = {
        "url": url + ("*" if prefix else ""),
        "from": str(year), "to": str(year),
        "filter": ["statuscode:200", "mimetype:text/html"],
        "collapse": "urlkey",
        "fl": "timestamp,original",
        "limit": str(limit),
        "output": "json",
    }
    resp = _get(CDX_URL, params)
    if resp.status_code != 200 or not resp.text.strip():
        return []
    rows = resp.json()
    return [(r[0], r[1]) for r in rows[1:]]  # first row is the header


def _snapshot_url(timestamp: str, original: str, raw: bool = False) -> str:
    """Archived URL. raw=True gives the original HTML without Wayback's toolbar."""
    return f"https://web.archive.org/web/{timestamp}{'id_' if raw else ''}/{original}"


def _fetch(timestamp: str, original: str, retries: int = 3) -> str:
    resp = _get(_snapshot_url(timestamp, original, raw=True), retries=retries)
    resp.raise_for_status()
    return resp.text


# ---------- HTML parsing ----------

class _PageParser(HTMLParser):
    """Collects title, og tags, images and links (with their text/img)."""

    def __init__(self):
        super().__init__()
        self.title, self.meta = "", {}
        self.images: list[dict] = []   # {src, alt, cls}
        self.links: list[dict] = []    # {href, text, img}
        self._in_title = False
        self._link: Optional[dict] = None

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "title":
            self._in_title = True
        elif tag == "meta" and a.get("property", a.get("name")):
            self.meta[a.get("property") or a.get("name")] = a.get("content", "")
        elif tag == "a" and a.get("href"):
            self._link = {"href": a["href"], "text": "", "img": None}
            self.links.append(self._link)
        elif tag == "img":
            src = a.get("data-src") or a.get("src") or ""
            img = {"src": src, "alt": a.get("alt") or a.get("title", ""), "cls": a.get("class", "")}
            if src:
                self.images.append(img)
                if self._link is not None and self._link["img"] is None:
                    self._link["img"] = img

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "a":
            self._link = None

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._link is not None:
            self._link["text"] += data


def _parse(html: str) -> _PageParser:
    p = _PageParser()
    p.feed(html)
    return p


def _clean(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return re.sub(r"(?i)\s*(read more|lue lisää)$", "", text)


def _archived_img(ts: str, page_url: str, src: str) -> str:
    """Absolute archived image URL (im_ = raw image as captured), '' if no src."""
    if not src:
        return ""
    if src.startswith("https://web.archive.org/") or src.startswith("http://web.archive.org/"):
        return src
    return f"https://web.archive.org/web/{ts}im_/{urljoin(page_url, src)}"


def _name_from_slug(url: str) -> str:
    slug = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
    slug = re.sub(r"\.(aspx|html?|php)$", "", slug)
    return slug.replace("-", " ").replace("_", " ").strip().title()


def _page_name(page: _PageParser) -> str:
    """Customer/project name from a detail page: og:title or <title> before ' - '/' | '."""
    title = _clean(page.meta.get("og:title") or page.title)
    return _clean(re.split(r"\s[-|–]\s", title)[0])


def _company_name(page: _PageParser, domain: str) -> str:
    site = _clean(page.meta.get("og:site_name", ""))
    if site:
        return site
    parts = re.split(r"\s[-|–]\s", _clean(page.title))
    return parts[-1] if len(parts) > 1 else domain.split(".")[0].title()


# ---------- extraction ----------

def _logo_wall(page: _PageParser, ts: str, base: str, source: str, own: str) -> list[dict]:
    """Logos shown directly on a listing page (e.g. a customer logo wall)."""
    out = []
    for img in page.images:
        hint = f"{img['src']} {img['cls']} {img['alt']}"
        if not LOGO_HINT.search(hint) or own in hint.lower():
            continue
        name = _clean(re.sub(r"(?i)\blogo\b", "", img["alt"])) or _name_from_slug(img["src"])
        if name:
            out.append({"name": name, "logo_url": _archived_img(ts, base, img["src"]), "source_url": source})
    return out


def _detail_links(page: _PageParser, base: str, listing_path: str) -> dict[str, dict]:
    """Links pointing *below* the listing page, e.g. /references/the-shard.aspx."""
    out = {}
    for link in page.links:
        url = urljoin(base, link["href"])
        path = urlparse(url).path
        if path.startswith(listing_path) and path.rstrip("/") != listing_path.rstrip("/") \
                and not SKIP_LINK.search(url):
            out.setdefault(path, link)
    return out


def _find_listing_pages(domain: str, year: int) -> list[tuple[str, str, list]]:
    """Probes the usual customer-page paths with one prefix query each.
    Returns [(timestamp, listing_url, captures_below_it)]. Common slugs first,
    and stops at the first language prefix with hits, to keep requests low."""
    found = []
    for slugs in (PRIMARY_SLUGS, SECONDARY_SLUGS):
        for lang in LANG_PREFIXES:
            found += _probe(domain, year, lang, slugs)
            if found:
                return found
    return found


def _probe(domain: str, year: int, lang: str, slugs: list[str]) -> list[tuple[str, str, list]]:
    """One CDX prefix query per slug. Listing page = /<lang><slug>[/][index|default.*]."""
    found = []
    for slug in slugs:
        root = f"/{lang}{slug}"
        listing_re = re.compile(rf"^{re.escape(root)}/?((index|default)\.\w+)?$")
        caps = [(t, o) for t, o in _cdx(domain + root, year, prefix=True)
                if re.match(rf"^{re.escape(root)}(/|\.|$)", urlparse(o).path)]
        listing = [c for c in caps if listing_re.match(urlparse(c[1]).path)]
        if listing:
            found.append((*listing[0], [c for c in caps if c not in listing]))
    return found


def _customers_from_listing(ts: str, original: str, below: list, own: str) -> tuple[list[dict], str]:
    """Customers from one listing page + its archived detail pages."""
    html = _fetch(ts, original)
    page = _parse(html)
    source = _snapshot_url(ts, original)
    customers = _logo_wall(page, ts, original, source, own)

    # Detail pages: those linked from the listing + any other captures under the same path.
    listing_path = urlparse(original).path
    if not listing_path.endswith("/"):
        listing_path = listing_path.rsplit("/", 1)[0] + "/"
    links = _detail_links(page, original, listing_path)
    captures = {urlparse(o).path: (t, o) for t, o in below}
    blocked = threading.Event()  # set once Wayback refuses: skip remaining detail fetches

    def build(path: str) -> Optional[dict]:
        link, cap = links.get(path), captures.get(path)
        name = _clean(link["text"]) if link else ""
        logo = _archived_img(ts, original, link["img"]["src"]) if link and link["img"] else ""
        if link and link["img"] and not name:
            name = _clean(link["img"]["alt"])
        src = _snapshot_url(*cap) if cap else source
        if cap and (not name or not logo) and not blocked.is_set():
            try:  # fetch the archived detail page for a proper name / image
                detail = _parse(_fetch(*cap, retries=1))
                name = name or _page_name(detail)
                logo = logo or _archived_img(cap[0], cap[1], detail.meta.get("og:image", ""))
            except Exception:
                blocked.set()  # fall back to slug names, don't hammer a blocking Wayback
        name = name or _name_from_slug(path)
        if own in logo.rsplit("/", 1)[-1].lower():  # company's own logo, not the customer's
            logo = ""
        return {"name": name, "logo_url": logo, "source_url": src} if name else None

    paths = sorted(set(links) | set(captures))[:MAX_DETAIL_PAGES]
    with ThreadPoolExecutor(max_workers=2) as pool:
        customers += [c for c in pool.map(build, paths) if c]
    return customers, _company_name(page, own)


def _dedupe(customers: list[dict]) -> list[dict]:
    seen, out = set(), []
    for c in customers:
        key = re.sub(r"[^a-z0-9]", "", c["name"].lower())
        if key and key not in seen:
            seen.add(key)
            out.append(c)
    return out


def _domain(url: str) -> str:
    host = urlparse(url if "//" in url else f"https://{url}").netloc.lower()
    return host[4:] if host.startswith("www.") else host


def fetch_historical(url: str, year: int) -> dict:
    """Full result: {company, domain, year, customers:[{name, logo_url, source_url}]}."""
    domain = _domain(url)
    own = domain.split(".")[0]
    company, customers = domain.split(".")[0].title(), []
    for ts, original, below in _find_listing_pages(domain, year):
        found, company = _customers_from_listing(ts, original, below, own)
        customers += found
    return {"company": company, "domain": domain, "year": year, "customers": _dedupe(customers)}


def _load_cache(url: str, year: int, path: Path = CACHE_PATH) -> Optional[dict]:
    """Cached result if it is for the same domain and year, else None."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if data.get("domain") == _domain(url) and data.get("year") == year:
        return data
    return None


def get_historical_customers(url: str, year: int) -> list[dict]:
    """Agreed interface (CONTRIBUTING.md): customers found in the Wayback Machine for `year`.
    Uses data/historical.json when it already holds this domain + year."""
    cached = _load_cache(url, year)
    if cached is not None:
        return cached["customers"]
    return save_historical(url, year)["customers"]


def save_historical(url: str, year: int, path: Path = CACHE_PATH) -> dict:
    """Fetches from Wayback (ignoring the cache) and writes the result to `path`."""
    result = fetch_historical(url, year)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "kone.com"
    yr = int(sys.argv[2]) if len(sys.argv) > 2 else 2023
    res = save_historical(target, yr)
    print(f"{res['company']} ({res['domain']}) {res['year']}: {len(res['customers'])} customers → data/historical.json")
