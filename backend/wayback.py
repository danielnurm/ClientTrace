"""Role 2 – historical customers from the Wayback Machine.

Finds archived customer/reference pages of a company for a given year via the
Wayback CDX API, and extracts customer names + logos from them.

Results are cached per company and year in data/historical/<domain>_<year>.json;
get_historical_customers() reads the cache first, so Wayback is only hit once.

CLI:  python -m backend.wayback kone.com 2023   → (re)fetches and writes data/historical/kone.com_2023.json
      python -m backend.wayback kone.com 2023 --timeline   → half-yearly timeline, data/timeline/
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

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "historical"

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

CTA = re.compile(r"(?i)^(learn|read|see|view|find out)( more)?$|^(case study|read the story)$")


def _listing_dir(path: str) -> str:
    """Directory whose sub-pages are the customers:
    /customers/ → /customers/, /references.html → /references/, /refs/index.html → /refs/."""
    path = path or "/"
    if path.endswith("/"):
        return path
    parent, last = path.rsplit("/", 1)
    if "." not in last:
        return path + "/"
    stem = last.split(".", 1)[0]
    return parent + "/" if stem in ("index", "default") else f"{parent}/{stem}/"


def _link_name(link: dict, path: str) -> str:
    """Customer name for a card/link: image alt, else short link text, else the URL slug.
    Skips "Learn more"-style texts and long title+description texts."""
    img = link["img"]
    alt = _clean(re.sub(r"(?i)\blogo\b", "", img["alt"])) if img else ""
    text = _clean(link["text"])
    if CTA.match(text) or len(text.split()) > 6:
        text = ""
    return alt or text or _name_from_slug(path)


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


FILLER_WORDS = {"the", "a", "an", "of", "for", "on", "in", "to", "is", "are", "and",
                "with", "how", "why", "what", "our", "your", "no", "one"}


def _strip_location(name: str) -> str:
    """'Edificio Bronce, Madrid, Spain' → 'Edificio Bronce' (location suffix off),
    so the same project matches its current name."""
    return name.split(", ", 1)[0].strip() or name


def _is_headline(name: str) -> bool:
    """Article titles, e.g. 'Keeping people on the move for one of the world's
    biggest events': 5+ words with 2+ filler words. Short names are kept."""
    words = re.findall(r"[\w'’@-]+", name.lower())
    return len(words) >= 5 and sum(w in FILLER_WORDS for w in words) >= 2


def _clean_customers(customers: list[dict]) -> list[dict]:
    """Strip location suffixes, drop headline-like names, then de-duplicate."""
    cleaned = [{**c, "name": _strip_location(c["name"])} for c in customers]
    return _dedupe([c for c in cleaned if not _is_headline(c["name"])])


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
    return {"company": company, "domain": domain, "year": year, "customers": _clean_customers(customers)}


def _cache_path(url: str, year: int) -> Path:
    """One file per company and year, so fetching a new company never replaces another."""
    return CACHE_DIR / f"{_domain(url)}_{year}.json"


def _load_cache(url: str, year: int, path: Optional[Path] = None) -> Optional[dict]:
    """Cached result if it is for the same domain and year, else None."""
    path = path or _cache_path(url, year)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if data.get("domain") == _domain(url) and data.get("year") == year:
        return {**data, "customers": _clean_customers(data["customers"])}
    return None


def get_historical_customers(url: str, year: int) -> list[dict]:
    """Agreed interface (CONTRIBUTING.md): customers found in the Wayback Machine for `year`.
    Uses data/historical/<domain>_<year>.json when it exists."""
    cached = _load_cache(url, year)
    if cached is not None:
        return cached["customers"]
    return save_historical(url, year)["customers"]


def save_historical(url: str, year: int, path: Optional[Path] = None) -> dict:
    """Fetches from Wayback (ignoring the cache) and writes the result to `path`
    (default: this company's cache file)."""
    path = path or _cache_path(url, year)
    result = fetch_historical(url, year)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


# ---------- timeline: when each customer appeared and disappeared ----------

TIMELINE_DIR = Path(__file__).resolve().parent.parent / "data" / "timeline"
TIMELINE_YEARS_BEFORE = 2   # start this many years before the chosen year
TIMELINE_STEP_MONTHS = 6    # one snapshot per half-year
# When a site moves its pages, the archive stops capturing the old ones over a few weeks.
# Pages last archived within this many months of the section's last capture are treated
# as "still there when the section was last archived", not as removed.
SECTION_END_MONTHS = 3
SLUG = re.compile(r"^[\w\-.%]+$")


def _cdx_range(url: str, from_year: int, to_year: int) -> list[tuple[str, str]]:
    """[(timestamp, original)] of 200-OK captures of exactly `url`, at most one per month."""
    params = {
        "url": url,
        "from": str(from_year), "to": str(to_year),
        "filter": ["statuscode:200", "mimetype:text/html"],
        "collapse": "timestamp:6",
        "fl": "timestamp,original",
        "output": "json",
    }
    resp = _get(CDX_URL, params)
    if resp.status_code != 200 or not resp.text.strip():
        return []
    return [(r[0], r[1]) for r in resp.json()[1:]]


def _listing_snapshot(ts: str, original: str, own: str) -> list[dict]:
    """Customers on one archived listing page, from that page alone (no detail-page
    fetches), so a whole timeline stays at one request per snapshot."""
    page = _parse(_fetch(ts, original, retries=2))
    source = _snapshot_url(ts, original)
    customers = _logo_wall(page, ts, original, source, own)
    for path, link in _detail_links(page, original, _listing_dir(urlparse(original).path)).items():
        logo = _archived_img(ts, original, link["img"]["src"]) if link["img"] else ""
        if own in logo.rsplit("/", 1)[-1].lower():  # company's own logo
            logo = ""
        customers.append({"name": _link_name(link, path), "logo_url": logo,
                          "source_url": _snapshot_url(ts, urljoin(original, link["href"]))})
    return _clean_customers(customers)


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _cdx_prefix_monthly(prefix_url: str, from_year: int, to_year: int) -> list[tuple[str, str]]:
    """[(timestamp, original)] of 200-OK captures under `prefix_url`, at most one per page
    per month. Rows come sorted by page, then time."""
    params = {
        "url": prefix_url + "*",
        "from": str(from_year), "to": str(to_year),
        "filter": ["statuscode:200", "mimetype:text/html"],
        "collapse": "timestamp:6",
        "fl": "timestamp,original",
        "limit": "20000",
        "output": "json",
    }
    resp = _get(CDX_URL, params)
    if resp.status_code != 200 or not resp.text.strip():
        return []
    return [(r[0], r[1]) for r in resp.json()[1:]]


def _date(ts: str) -> str:
    return f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"


def _page_path(url: str) -> str:
    return urlparse(url).path.lower().rstrip("/")


def _subpage_history(listing: str, from_year: int, to_year: int, names: dict[str, str]) -> dict:
    """When each page directly below the listing page was archived, from the archive index
    alone (one request, no page fetches). A page that was archived regularly and then
    stopped was most likely removed; `section_last_archived` tells whether the whole
    section stopped being archived at that point (e.g. the site moved), in which case the
    last capture says nothing about the page itself."""
    base = urljoin(listing, _listing_dir(urlparse(listing).path))
    base_path = _page_path(base)
    pages: dict[str, dict] = {}
    for ts, original in _cdx_prefix_monthly(base, from_year, to_year):
        path = _page_path(original)
        rest = path[len(base_path):].strip("/")
        if not rest or "/" in rest or not SLUG.match(rest) or SKIP_LINK.search(original):
            continue  # the listing itself, deeper pages, files, query and malformed URLs
        page = pages.setdefault(path, {"path": path, "url": original, "first": ts, "last": ts, "captures": 0})
        page["first"], page["last"] = min(page["first"], ts), max(page["last"], ts)
        page["captures"] += 1

    section_last = max((p["last"] for p in pages.values()), default="")
    section_end_from = _months_before(section_last, SECTION_END_MONTHS)
    out = []
    for p in pages.values():
        name = names.get(p["path"]) or _name_from_slug(p["path"])
        if _is_headline(name):
            continue  # article pages, not customers
        out.append({
            "name": name,
            "path": p["path"],
            "url": p["url"],
            # when the archive first/last captured the page; "first" is NOT a publication
            # date (archive coverage is uneven), "last" estimates removal
            "first_archived": _date(p["first"]),
            "last_archived": _date(p["last"]),
            "captures": p["captures"],
            # still there when the section stopped being archived → no removal date known
            "until_section_end": p["last"][:6] >= section_end_from,
        })
    out.sort(key=lambda p: (p["last_archived"], p["name"]))
    return {"listing_dir": base,
            "section_last_archived": _date(section_last) if section_last else None,
            "section_end_from": f"{section_end_from[:4]}-{section_end_from[4:6]}" if section_end_from else None,
            "pages": out}


def _months_before(ts: str, n: int) -> str:
    """"202505…", 3 → "202502"."""
    if not ts:
        return ""
    months = int(ts[:4]) * 12 + int(ts[4:6]) - 1 - n
    return f"{months // 12}{months % 12 + 1:02d}"


def _names_by_path(url: str, year: int) -> dict[str, str]:
    """Customer names from the cached historical result, keyed by their page path, so
    sub-page history uses exactly the names the comparison uses."""
    cached = _load_cache(url, year)
    out = {}
    for c in (cached or {}).get("customers", []):
        m = re.match(r"https?://web\.archive\.org/web/\d+[a-z_]*/(.+)$", c.get("source_url") or "")
        if m:
            out[_page_path(m.group(1))] = c["name"]
    return out


def fetch_timeline(url: str, year: int) -> dict:
    """When customers appeared on and disappeared from the company's customer page,
    from TIMELINE_YEARS_BEFORE years before `year` until today. Two sources:
    - snapshots: the listing page every TIMELINE_STEP_MONTHS (good for logo walls)
    - subpages: archive dates of every page below the listing (good for reference
      pages, whose listing often shows only a few at a time)
    The customer page is found the same way as in fetch_historical(), using `year`."""
    domain = _domain(url)
    own = domain.split(".")[0]
    listings = [original for _, original, _ in _find_listing_pages(domain, year)]
    to_year = time.gmtime().tm_year

    # One capture per half-year bucket (the last one in it), across all listing pages
    buckets: dict[str, dict[str, str]] = {}  # "2023-1" → {listing: timestamp}
    for listing in listings:
        for ts, original in _cdx_range(listing, year - TIMELINE_YEARS_BEFORE, to_year):
            part = (int(ts[4:6]) - 1) // TIMELINE_STEP_MONTHS + 1  # 1 = Jan–Jun, 2 = Jul–Dec
            buckets.setdefault(f"{ts[:4]}-{part:02d}", {})[original] = ts

    snapshots, seen = [], {}
    for bucket in sorted(buckets):
        names, latest = [], ""
        for original, ts in buckets[bucket].items():
            try:
                found = _listing_snapshot(ts, original, own)
            except Exception:
                continue  # an unreadable snapshot just leaves a gap
            latest = max(latest, ts)
            for c in found:
                seen.setdefault(_key(c["name"]), c)
                names.append(c["name"])
        if latest:
            snapshots.append({"timestamp": latest,
                              "date": f"{latest[:4]}-{latest[4:6]}-{latest[6:8]}",
                              "names": sorted(set(names))})

    customers = []
    for key, c in seen.items():
        present = [i for i, s in enumerate(snapshots) if key in {_key(n) for n in s["names"]}]
        last = present[-1]
        customers.append({
            **c,
            "first_seen": snapshots[present[0]]["date"],
            "last_seen": snapshots[last]["date"],
            # first archived snapshot after the last sighting; None = still there at the end
            "missing_since": snapshots[last + 1]["date"] if last + 1 < len(snapshots) else None,
            "snapshots_present": len(present),
        })
    # Sub-page archive history: sees every reference page, not just what the listing
    # page shows (often only a few featured ones; the rest load with JavaScript).
    names = _names_by_path(url, year)
    subpages = []
    for listing in listings:
        try:
            subpages.append(_subpage_history(listing, year - TIMELINE_YEARS_BEFORE, to_year, names))
        except Exception:
            continue
    return {"domain": domain, "year": year, "listings": listings,
            "snapshots": snapshots, "customers": customers, "subpages": subpages}


def get_customer_timeline(url: str, year: int, refresh: bool = False,
                          cached_only: bool = False) -> Optional[dict]:
    """Cached fetch_timeline(): data/timeline/<domain>_<year>.json. The first fetch takes
    a few minutes (one throttled Wayback request per snapshot). cached_only=True returns
    None instead of fetching, for callers that can't wait."""
    path = TIMELINE_DIR / f"{_domain(url)}_{year}.json"
    if not refresh and path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    if cached_only:
        return None
    result = fetch_timeline(url, year)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "kone.com"
    yr = int(sys.argv[2]) if len(sys.argv) > 2 else 2023
    if "--timeline" in sys.argv:
        tl = get_customer_timeline(target, yr, refresh=True)
        print(f"{tl['domain']}: {len(tl['snapshots'])} snapshots, {len(tl['customers'])} customers "
              f"→ data/timeline/{tl['domain']}_{yr}.json")
    else:
        res = save_historical(target, yr)
        print(f"{res['company']} ({res['domain']}) {res['year']}: {len(res['customers'])} customers → {_cache_path(target, yr).relative_to(CACHE_DIR.parent.parent)}")
