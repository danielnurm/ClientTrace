"""'Tool switches' tab: which of a vendor's customers still run its product, live.

Calls backend.site_tech.supplier_report (live homepage + GTM, cached Wayback history,
optional Context.dev customer page / domain search) and draws the result.
"""
from html import escape

import streamlit as st

VERDICTS = {  # verdict → (label, color, sort order)
    "switched_away":    ("Switched away", "#e5484d", 0),
    "competitor_added": ("Competitor added", "#d97706", 1),
    "removed":          ("Removed", "#e5484d", 2),
    "still_running":    ("Still running", "#30a46c", 3),
    "not_detected":     ("Not detected", "#898781", 4),
    "error":            ("Not reachable", "#898781", 5),
}
DEMO_SITES = "tokmanni.fi\nfennia.fi\nlahitapiola.fi\nelisa.fi\nhttp://localhost:8765"


def _badge(text, color):
    return (f'<span style="font-size:.75em;font-weight:600;padding:2px 8px;border-radius:999px;'
            f'color:{color};border:1px solid {color}">{escape(text)}</span>')


def _link(url, text):
    if not (url or "").startswith(("http://", "https://")):
        return escape(text)
    return f'<a href="{escape(url, quote=True)}" target="_blank">{escape(text)}</a>'


def _signal_text(s):
    if s["type"] == "switch":
        return f"{s['from']} → {s['to']} (between {s['between'][0]} and {s['between'][1]})"
    return f"{s['new']} added {s['since']}, {', '.join(s['alongside'])} still loaded"


def _products_text(products):
    parts = []
    for p, i in sorted(products.items(), key=lambda x: x[1]["category"]):
        if i["status"] != "running":
            continue
        where = "page" if i["live"] == "html" else "tag manager"
        since = f", since {i['since']}" if i.get("since") else ""
        parts.append(f"{escape(p)} <span style='opacity:.6'>({escape(i['category'])}, {where}{since})</span>")
    return ", ".join(parts) or "<span style='opacity:.6'>nothing detected</span>"


def _changes_text(r):
    ch = r.get("changes")
    if not r.get("previous_check"):
        return "<span style='opacity:.6'>first check</span>"
    if not ch or not (ch["added"] or ch["removed"]):
        return f"<span style='opacity:.6'>no change since {escape(r['previous_check'][:16].replace('T', ' '))}</span>"
    parts = [f"{s['from']} → {s['to']}" for s in ch["switches"]]
    if not parts:
        parts = [f"+{p}" for p in ch["added"]] + [f"−{p}" for p in ch["removed"]]
    txt = "; ".join(parts)
    return f"<b style='color:#e5484d'>⚠ changed since last check: {escape(txt)}</b>"


def _row(r, product):
    label, color, _ = VERDICTS.get(r["verdict"], VERDICTS["error"])
    conf = f" · {r['confidence']} confidence" if r.get("confidence") and r["verdict"] != "error" else ""
    lines = [f"<b>{escape(r['name'])}</b> {_badge(label, color)}"
             f"<span style='opacity:.6;font-size:.85em'>{conf}</span>"]
    if r["verdict"] == "error":
        lines.append(f"<span style='opacity:.6'>{escape(r.get('error', ''))[:120]}</span>")
    else:
        lines.append(f"Runs now: {_products_text(r['products'])}")
        for s in r.get("signals", []):
            lines.append(f"Signal: {escape(_signal_text(s))}")
        ev = r.get("evidence") or []
        links = [_link(u, "archived page" if "web.archive.org" in u else "live page") for u in ev]
        hist = "" if r.get("history") else " · <span style='opacity:.6'>no archive history cached</span>"
        lines.append(f"Evidence: {' · '.join(links)}{hist} · {r.get('latency_ms', '?')} ms")
        lines.append(_changes_text(r))
    return ("<div style='padding:10px 0;border-bottom:1px solid rgba(128,128,128,.2);line-height:1.6'>"
            + "<br>".join(lines) + "</div>")


def render_switches():
    try:  # imported lazily: a broken backend must not take the whole dashboard down
        from backend.site_tech import SIGNATURES, supplier_report
    except Exception as e:
        st.error(f"Tool switch check is unavailable: {type(e).__name__}: {e}")
        return

    st.caption("Did the customers move to a competitor? We read each customer's own website "
               "live (page + Google Tag Manager) and compare it with the Wayback Machine.")
    chat = sorted(p for p, s in SIGNATURES.items() if s["category"] == "chat")
    with st.form("switches"):
        c1, c2 = st.columns([3, 2])
        supplier = c1.text_input("Supplier website", value="giosg.com")
        product = c2.selectbox("Supplier's product", chat, index=chat.index("Giosg"))
        sites = st.text_area("Customer sites to check, one per line. Leave empty to read them from the "
                             "supplier's customer page (uses Context.dev credits).", value=DEMO_SITES, height=130)
        submitted = st.form_submit_button("Check now", type="primary")

    if submitted:
        customers = [{"name": s.strip(), "domain": s.strip()} for s in sites.splitlines() if s.strip()] or None
        with st.spinner("Checking the customer sites live..."):
            try:
                st.session_state["switch_report"] = supplier_report(supplier, product, customers=customers, record=True)
            except Exception as e:
                st.session_state.pop("switch_report", None)
                st.error(f"Check failed: {type(e).__name__}: {e}")

    rep = st.session_state.get("switch_report")
    if not rep:
        return
    s = rep["summary"]
    n = sum(s.values())
    lost = s.get("switched_away", 0) + s.get("removed", 0)
    st.markdown(f"### Of {n} customer sites, {s.get('still_running', 0)} still run {escape(rep['product'])}, "
                f"{lost} dropped it and {s.get('competitor_added', 0)} added a competitor")
    m = st.columns(4)
    m[0].metric("Still running", s.get("still_running", 0))
    m[1].metric("Dropped / switched", lost)
    m[2].metric("Competitor added", s.get("competitor_added", 0))
    m[3].metric("Checked in", f"{rep['elapsed_ms'] / 1000:.1f} s")

    rows = sorted(rep["customers"], key=lambda r: VERDICTS.get(r["verdict"], VERDICTS["error"])[2])
    st.markdown("".join(_row(r, rep["product"]) for r in rows), unsafe_allow_html=True)

    with st.expander("How reliable is this?"):
        st.markdown(
            "- **Five sources:** supplier's customer page (Context.dev), customer homepage live, its Google "
            "Tag Manager containers live, the homepage in the Wayback Machine (one capture per quarter), "
            "and a web search for the customer's domain.\n"
            "- **Strict signatures:** only script hosts and loader calls count, never a product name in text.\n"
            "- **No false switches from one odd capture:** a product counts as removed only after two "
            "consecutive archive captures without it.\n"
            "- **Measured on 17 Finnish sites (14.11.2026):** a chat widget was visible in the page HTML on 3, "
            "and only inside Google Tag Manager on 1–3 more. Tag Manager containers are almost never "
            "archived, so for those sites we see the switch from now on, not its history.\n"
            "- **Confidence:** high = seen in both archive and live page, medium = one source, "
            "low = two tools side by side (switch probably in progress).")
