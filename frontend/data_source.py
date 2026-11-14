"""Fetches the data for the dashboard.

Uses the teammates' real functions (roles 1-3) when they work.
If a function is missing, unfinished, crashes or returns the wrong format,
falls back to demo data, so the dashboard can always be run and shown.
Real and demo customers are never mixed: if either list is missing,
both come from demo data.
"""
import re
from datetime import datetime

from frontend.mock_data import MOCK_NEW, MOCK_OLD


def _snapshot_date(source_url):
    """Wayback snapshot date from its URL: .../web/20230324201307/... → "24 Mar 2023"."""
    m = re.search(r"/web/(\d{4})(\d{2})?(\d{2})?", source_url or "")
    if not m:
        return ""
    year, month, day = m.groups()
    if not month:
        return year
    try:
        return datetime(int(year), int(month), int(day or 1)).strftime("%-d %b %Y" if day else "%b %Y")
    except ValueError:
        return year


def _as_customer(item):
    """Customer dict (CONTRIBUTING.md) (or a plain name) → clean customer dict, or None if unusable."""
    if isinstance(item, str):
        item = {"name": item}
    if not isinstance(item, dict):
        return None
    name = str(item.get("name") or "").strip()
    if not name:
        return None
    return {
        "name": name,
        "logo_url": item.get("logo_url") or "",
        "source_url": item.get("source_url") or "",
    }


def _customer_list(items):
    if not isinstance(items, list):
        raise TypeError(f"expected a list, got {type(items).__name__}")
    return [c for c in map(_as_customer, items) if c is not None]


def _simple_compare(old, new):
    """Fallback comparison if role 3's compare_customers is not ready."""
    def key(c):
        return c["name"].strip().lower()

    old_by = {key(c): c for c in old}
    new_by = {key(c): c for c in new}
    return {
        "lost": [old_by[k] for k in old_by.keys() - new_by.keys()],
        "retained": [new_by[k] for k in old_by.keys() & new_by.keys()],
        "added": [new_by[k] for k in new_by.keys() - old_by.keys()],
    }


def _comparison(result, old, new):
    """Checks compare_customers output. Accepts customer dicts or plain names."""
    if not isinstance(result, dict):
        raise TypeError(f"expected a dict, got {type(result).__name__}")
    by_name = {c["name"]: c for c in old + new}

    def lookup(item):
        # A plain name → the full customer (with logo) from the input lists
        if isinstance(item, str) and item.strip() in by_name:
            return by_name[item.strip()]
        return _as_customer(item)

    out = {}
    for key in ("lost", "retained", "added"):
        items = result.get(key, [])
        if not isinstance(items, list):
            raise TypeError(f"'{key}' should be a list, got {type(items).__name__}")
        out[key] = [c for c in map(lookup, items) if c is not None]
    return out


def _try(func_path, *args):
    """Calls e.g. 'backend.wayback:get_historical_customers'.
    Returns (result, error_text). Result is None if it failed."""
    module_name, func_name = func_path.split(":")
    try:
        module = __import__(module_name, fromlist=[func_name])
        func = getattr(module, func_name)
        result = func(*args)
        if result is None:
            return None, f"{func_name} returned None"
        return result, None
    except Exception as e:  # anything goes wrong → use demo data
        return None, f"{func_name}: {type(e).__name__}: {e}"


def _fetch_customers(func_path, *args):
    result, err = _try(func_path, *args)
    if result is None:
        return None, err
    try:
        return _customer_list(result), None
    except Exception as e:
        return None, f"{func_path.split(':')[1]}: wrong format ({e})"


def run_analysis(url, year):
    """Returns a dict the dashboard can draw directly."""
    notes = []

    new, new_err = _fetch_customers("backend.context_api:get_current_customers", url)
    old, old_err = _fetch_customers("backend.wayback:get_historical_customers", url, year)

    demo = new is None or old is None
    if demo:
        if new is None:
            notes.append(f"Current customers failed → {new_err}")
        if old is None:
            notes.append(f"Historical customers failed → {old_err}")
        if new is not None or old is not None:
            notes.append("The list that did work is not shown, so real and demo data are not mixed.")
        old, new = MOCK_OLD, MOCK_NEW

    result, err = _try("analysis.comparison:compare_customers", old, new)
    try:
        if result is None:
            raise RuntimeError(err)
        result = _comparison(result, old, new)
    except Exception as e:
        notes.append(f"Comparison → simple fallback ({e})")
        result = _simple_compare(old, new)

    # Lost customers: copies with evidence attached, so cached lists aren't changed
    lost = [{**c, "snapshot_date": _snapshot_date(c["source_url"])} for c in result["lost"]]
    mentions_checked = False
    if lost and not demo:
        mentions, err = _try("backend.context_api:find_site_mentions", url, [c["name"] for c in lost])
        if mentions is None:
            notes.append(f"Site-mention check skipped ({err})")
        else:
            mentions_checked = True
            for c in lost:
                c["mention"] = mentions.get(c["name"])  # None = this one couldn't be checked

    current_source, _ = (None, None) if demo else _try("backend.context_api:get_current_source", url)

    return {
        "url": url,
        "year": year,
        "demo": demo,
        "old": old,
        "new": new,
        "lost": lost,
        "retained": result["retained"],
        "added": result["added"],
        "mentions_checked": mentions_checked,
        "current_source": current_source,
        "notes": notes,
    }
