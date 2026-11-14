"""Month-by-month chat-vendor history of a customer's site, from the Wayback Machine.

Answers "how did the switch unfold, and how much warning time was there?" for the
Competitor alerts view. Reuses the existing pieces instead of new detection:
  - backend.wayback._cdx_range / _fetch  (monthly captures, raw archived HTML)
  - backend.site_tech.detect_products     (the same strict signatures as the live check)
  - backend.churn_watch.service_pages     (which contact page to follow)

Requests: the archive allows about one request every 5 s, so not every month is
fetched. One capture per quarter is read first; months are only filled in where
the class changes between two quarters, which gives monthly precision exactly
where a switch happens. Everything is cached in data/switch_timeline/<site>.json,
so the dashboard never waits for the archive.

Tag Manager: tools loaded through Google Tag Manager aren't in the archived HTML,
and the containers themselves are almost never archived (0 captures for fennia.fi
and elisa.fi, 2 for tokmanni.fi in 2023-2026). When our product loads through Tag
Manager today and never shows up in the archive, its past presence is unknown,
so those months get their own classes instead of a false "competitor only".

CLI:
  python -m backend.switch_timeline build Giosg tokmanni.fi fennia.fi lahitapiola.fi elisa.fi
  python -m backend.switch_timeline demo          # writes the offline demo timeline
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from backend import site_tech as st
from backend import wayback as w

TIMELINE_DIR = Path(__file__).resolve().parent.parent / "data" / "switch_timeline"
MONTHS = 36          # how far back
SAMPLE_EVERY = 3     # first pass: one capture per quarter
DEMO_SITE = "localhost_8765"  # the fake customer site of demo/switch_chat.py

# Snapshot classes, in the order the legend shows them
OURS_ONLY, BOTH, COMPETITOR_ONLY = "ours_only", "both", "competitor_only"
NONE_DETECTED, NO_SNAPSHOT = "none_detected", "no_snapshot"
OURS_HIDDEN, COMPETITOR_OURS_HIDDEN = "ours_hidden", "competitor_ours_hidden"
CLASSES = [OURS_ONLY, BOTH, COMPETITOR_ONLY, COMPETITOR_OURS_HIDDEN, NONE_DETECTED, OURS_HIDDEN, NO_SNAPSHOT]
OURS_SEEN = {OURS_ONLY, BOTH}
COMPETITOR_SEEN = {BOTH, COMPETITOR_ONLY, COMPETITOR_OURS_HIDDEN}


# ---------- months ----------

def _ym(date: str) -> str:
    return date[:7]


def month_range(end_ym: str, months: int = MONTHS) -> list[str]:
    """The `months` months up to and including end_ym ("2026-11"), oldest first."""
    y, m = int(end_ym[:4]), int(end_ym[5:7])
    out = []
    for _ in range(months):
        out.append(f"{y}-{m:02d}")
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    return out[::-1]


def months_between(a: str, b: str) -> int:
    return (int(b[:4]) - int(a[:4])) * 12 + int(b[5:7]) - int(a[5:7])


# ---------- classification ----------

def classify(products: Optional[list[str]], product: str, ours_hidden: bool) -> str:
    """Class of one month from the products seen in that month's snapshots (None = no snapshot)."""
    if products is None:
        return NO_SNAPSHOT
    cat = st.category_of(product)
    ours = product in products
    rival = any(p != product and st.category_of(p) == cat for p in products)
    if ours and rival:
        return BOTH
    if ours:
        return OURS_ONLY
    if rival:
        return COMPETITOR_OURS_HIDDEN if ours_hidden else COMPETITOR_ONLY
    return OURS_HIDDEN if ours_hidden else NONE_DETECTED


def months_to_refine(sampled: dict[str, str], available: list[str]) -> list[str]:
    """Months with a capture that lie between two sampled months of different class."""
    done = sorted(sampled)
    out = []
    for a, b in zip(done, done[1:]):
        if sampled[a] != sampled[b]:
            out += [m for m in available if a < m < b and m not in sampled]
    return out


def derive(months: list[dict], product: str) -> dict:
    """Per-customer summary: first competitor sighting, our last sighting, the switch window
    and the warning time. A switch only counts as completed when the archive actually saw our
    product before and only a competitor after; nothing is inferred from hidden months."""
    seen = [m for m in months if m["class"] != NO_SNAPSHOT and not m.get("inferred")]  # real captures only
    first_comp = next((m for m in seen if m["class"] in COMPETITOR_SEEN), None)
    ours = [m for m in seen if m["class"] in OURS_SEEN]
    ours_last = ours[-1] if ours else None
    switch = None
    if ours_last:
        after = [m for m in seen if m["month"] > ours_last["month"]]
        first_only = next((m for m in after if m["class"] == COMPETITOR_ONLY), None)
        if first_only:
            switch = {"from": product, "to": sorted({v for v in first_only["vendors"] if v != product}),
                      "window": [ours_last["month"], first_only["month"]]}
    warning = None
    if switch and first_comp and first_comp["month"] <= ours_last["month"]:
        warning = months_between(first_comp["month"], ours_last["month"])
    hidden = any(m["class"] in (OURS_HIDDEN, COMPETITOR_OURS_HIDDEN) for m in months)
    current = seen[-1]["class"] if seen else None
    return {
        "first_competitor_seen": first_comp["month"] if first_comp else None,
        "ours_last_seen": ours_last["month"] if ours_last else None,
        "switch": switch,
        "warning_months": warning,
        "ours_hidden": hidden,
        "changed": len({m["class"] for m in seen}) > 1,
        "latest_archived_class": current,
    }


# ---------- building from the archive ----------

def _captures_by_month(url: str, window: list[str]) -> dict[str, tuple[str, str]]:
    """Latest capture per month of exactly `url`, limited to the window."""
    rows = w._cdx_range(url, int(window[0][:4]), int(window[-1][:4]))
    by_month = {}
    for ts, orig in rows:
        m = f"{ts[:4]}-{ts[4:6]}"
        if window[0] <= m <= window[-1]:
            by_month[m] = (ts, orig)
    return by_month


def build(site: str, product: str, months: int = MONTHS, refresh: bool = False) -> dict:
    """Fetches (or reads from cache) the month-by-month history of one customer site."""
    path = TIMELINE_DIR / f"{st._site_key(site)}.json"
    if not refresh and path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    from backend.churn_watch import _get, service_pages

    live = st.check_site(site)
    home = _get(live["url"])
    pages = [live["url"]] + service_pages(home.text if home is not None else "", live["url"])[:1]
    window = month_range(live["checked_at"][:7], months)
    caps = {p: _captures_by_month(p, window) for p in pages}
    available = sorted({m for c in caps.values() for m in c})

    fetched: dict[str, list[dict]] = {}

    def fetch_month(m):
        snaps = []
        for p in pages:
            if m in caps[p]:
                ts, orig = caps[p][m]
                snap = {"page": urlparse(p).path or "/", "date": w._date(ts), "url": w._snapshot_url(ts, orig)}
                try:
                    snap["products"] = st.detect_products(w._fetch(ts, orig, retries=2))
                except Exception as e:  # one failed capture is just a gap
                    snap["error"] = str(e)[:120]
                snaps.append(snap)
        fetched[m] = snaps

    def products_of(m):
        ok = [s for s in fetched.get(m, []) if "error" not in s]
        return sorted({p for s in ok for p in s["products"]}) if ok else None

    for m in available[::SAMPLE_EVERY] + available[-1:]:
        if m not in fetched:
            fetch_month(m)
    ever = {p for m in fetched for p in (products_of(m) or [])}
    ours_hidden = live["found_in"].get(product) == "gtm" and product not in ever
    while True:  # fill in months only where the class changes
        sampled = {m: classify(products_of(m), product, ours_hidden) for m in fetched if products_of(m) is not None}
        todo = months_to_refine(sampled, available)
        if not todo:
            break
        for m in todo:
            fetch_month(m)
        ever = {p for m in fetched for p in (products_of(m) or [])}
        ours_hidden = live["found_in"].get(product) == "gtm" and product not in ever

    result = assemble(site, product, window, fetched, live, ours_hidden, pages)
    TIMELINE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


def assemble(site, product, window, fetched, live, ours_hidden, pages, demo=False) -> dict:
    """Months between fetched snapshots inherit the class of the previous fetched month
    when the classes on both sides agree (that's what the refinement guarantees)."""
    months, last = [], None
    known = {m: s for m, s in fetched.items() if any("error" not in x for x in s)}
    for m in window:
        if m in known:
            ok = [s for s in known[m] if "error" not in s]
            prods = sorted({p for s in ok for p in s["products"]})
            last = {"month": m, "class": classify(prods, product, ours_hidden), "vendors": prods,
                    "snapshots": ok, "inferred": False}
            months.append(last)
        elif last is not None and any(k > m for k in known):
            months.append({**last, "month": m, "snapshots": [], "inferred": True})
        else:
            months.append({"month": m, "class": NO_SNAPSHOT, "vendors": [], "snapshots": [], "inferred": False})
    return {"site": st._site_key(site), "product": product, "demo": demo,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "pages": [urlparse(p).path or "/" for p in pages],
            "live": {"checked_at": live["checked_at"], "products": live["products"], "found_in": live["found_in"]},
            "months": months, "summary": derive(months, product)}


def cached(site: str) -> Optional[dict]:
    """Cached timeline only; never touches the archive."""
    try:
        return json.loads((TIMELINE_DIR / f"{st._site_key(site)}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_demo() -> dict:
    """Offline demo for the fake customer site (demo/switch_chat.py): Giosg for two years,
    an Intercom trial next to it for four months, then Intercom only. Marked demo=True."""
    end = datetime.now(timezone.utc).strftime("%Y-%m")
    window = month_range(end)
    fetched = {}
    for i, m in enumerate(window):
        if i < 3:
            continue  # the archive started later
        prods = ["Giosg"] if i < 24 else ["Giosg", "Intercom"] if i < 28 else ["Intercom"]
        fetched[m] = [{"page": "/", "date": f"{m}-15", "url": f"https://web.archive.org/web/{m.replace('-', '')}15000000/http://localhost:8765/",
                       "products": prods}]
    live = {"checked_at": f"{end}-14T12:00:00+00:00", "products": ["Intercom"], "found_in": {"Intercom": "html"}}
    result = assemble("http://localhost:8765", "Giosg", window, fetched, live, False, ["http://localhost:8765/"], demo=True)
    TIMELINE_DIR.mkdir(parents=True, exist_ok=True)
    (TIMELINE_DIR / f"{DEMO_SITE}.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["build"] and len(args) >= 3:
        for s in args[2:]:
            t0 = time.monotonic()
            try:
                tl = build(s, args[1], refresh=True)
            except Exception as e:
                print(f"{s:<18} FAILED {type(e).__name__}: {e}", flush=True)
                continue
            sm = tl["summary"]
            print(f"{tl['site']:<18} {time.monotonic() - t0:5.0f} s  first rival {sm['first_competitor_seen']}  "
                  f"ours last {sm['ours_last_seen']}  switch {sm['switch']}  warning {sm['warning_months']} mo  "
                  f"ours hidden {sm['ours_hidden']}", flush=True)
    elif args[:1] == ["demo"]:
        print(write_demo()["summary"])
    else:
        print(__doc__)
