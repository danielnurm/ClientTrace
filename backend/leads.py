"""Sales leads: which of a competitor's customers are switching away right now?

The same checks as backend.churn_watch, seen from the other side. churn_watch asks a
vendor "which of OUR customers run a competitor next to us?". Run it with the
competitor as the product and the answer is a seller's lead list: the competitor's
customers that have started running another tool next to it, or have already left it.

Lead statuses, hottest first (mapped from churn_watch statuses):
  leaving    competitor shares a page with another tool AND the privacy policy or help
             centre points to that tool, or the competitor vanished since the last check
  trialling  another tool on the same page as the competitor, or named in the privacy policy
  switched   the competitor is gone and another tool runs (who they chose, and since when)
  weak       another tool only on other pages than the competitor (often another business unit)
  locked_in  only the competitor runs, or it arrived recently (the archive shows a move to it)
  unknown    nothing detected, or the site isn't reachable

CLI:
  python -m backend.leads Giosg tokmanni.fi fennia.fi elisa.fi
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import Optional

from backend import churn_watch as cw
from backend import site_tech as st

LEAD_STATUS = {
    "likely_switching": "leaving",
    "possibly_trialling": "trialling",
    "on_competitor": "switched",
    "worth_a_look": "weak",
    "healthy": "locked_in",
    "moving_to_us": "locked_in",  # from the competitor's side: it's the one arriving
    "unknown": "unknown",
    "unreachable": "unknown",
}
LEAD_ORDER = {s: i for i, s in enumerate(["leaving", "trialling", "switched", "weak", "locked_in", "unknown"])}


def _alternatives(row: dict) -> list[dict]:
    """Other tools of the same kind on the site, strongest evidence first."""
    def strength(r: dict) -> int:
        return 2 * bool(r["same_page"]) + bool(r["in_privacy_policy"]) + bool(r["help_centre"])
    rivals = sorted(row.get("rivals", []), key=lambda r: -strength(r))
    return [{"name": r["name"], "same_page": r["same_page"], "other_pages": r["other_pages"],
             "in_privacy_policy": r["in_privacy_policy"], "help_centre": r["help_centre"],
             "since": r["since"]} for r in rivals]


def to_lead(row: dict, competitor: str) -> dict:
    """One churn_watch row (checked with the competitor as product) as a sales lead."""
    status = LEAD_STATUS.get(row["status"], "unknown")
    if row.get("dropped_since_last_check"):
        status = "leaving"
    alts = _alternatives(row)
    tl = row.get("timeline")
    timeline = tl if tl and tl.get("product") == competitor else None  # built for another product: not ours to read
    return {
        "site": row["site"], "url": row.get("url"), "status": status, "competitor": competitor,
        "competitor_running": row.get("ours", False), "competitor_pages": row.get("our_pages", []),
        "switching_to": alts[0]["name"] if alts and status in ("leaving", "trialling", "switched") else None,
        "alternatives": alts, "dropped_since_last_check": row.get("dropped_since_last_check", False),
        "help_center": row.get("help_center"), "products": row.get("products", []),
        "timeline": timeline, "error": row.get("error"),
    }


def find_leads(competitor: str, sites: list[str], record: bool = False) -> dict:
    """Leads among `sites` (the competitor's customers), hottest first. Live, plain requests, no credits."""
    rep = cw.churn_report(sites, competitor, record=record)
    leads = sorted((to_lead(r, competitor) for r in rep["customers"]), key=lambda l: LEAD_ORDER[l["status"]])
    summary: dict[str, int] = {}
    for l in leads:
        summary[l["status"]] = summary.get(l["status"], 0) + 1
    return {"competitor": competitor, "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "summary": summary, "leads": leads}


def competitor_customers(competitor_url: str, customers: Optional[list[dict]] = None) -> list[dict]:
    """The competitor's customers with their own domains: [{"name", "domain"}].

    Read from the competitor's customer page (Context.dev, cached), unless `customers` is given.
    Customers whose website couldn't be found are left out.
    """
    return [{"name": r["name"], "domain": r["domain"]}
            for r in st.resolve_customers(competitor_url, customers) if r.get("domain")]


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) < 2:
        sys.exit("usage: python -m backend.leads <competitor product> <site> [site ...]")
    rep = find_leads(args[0], args[1:])
    print(f"Leads among {args[0]} customers: {rep['summary']}")
    for l in rep["leads"]:
        to = f" → {l['switching_to']}" if l["switching_to"] else ""
        print(f"  {l['status']:<10} {l['site']}{to}{'  (' + l['error'] + ')' if l['error'] else ''}")
