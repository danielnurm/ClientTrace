"""Fetches the data for the dashboard.

Uses the teammates' real functions (roles 1-3) when they work.
If a function is missing, unfinished or crashes, falls back to demo data,
so the dashboard can always be run and shown.
"""
from frontend.mock_data import MOCK_NEW, MOCK_OLD


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


def run_analysis(url, year):
    """Returns a dict the dashboard can draw directly."""
    notes = []

    new, err = _try("backend.context_api:get_current_customers", url)
    if new is None:
        notes.append(f"Current customers → demo data ({err})")
        new = MOCK_NEW

    old, err = _try("backend.wayback:get_historical_customers", url, year)
    if old is None:
        notes.append(f"Historical customers → demo data ({err})")
        old = MOCK_OLD

    result, err = _try("analysis.comparison:compare_customers", old, new)
    if result is None:
        notes.append(f"Comparison → simple fallback ({err})")
        result = _simple_compare(old, new)

    return {
        "url": url,
        "year": year,
        "old": old,
        "new": new,
        "lost": result.get("lost", []),
        "retained": result.get("retained", []),
        "added": result.get("added", []),
        "notes": notes,
    }
