"""'Competitor alerts' tab: which of our customers have a competitor's chat tool next to ours,
and how sure we can be. Built for a vendor's customer-success / sales team.

Calls backend.churn_watch.churn_report (live homepage + Tag Manager + service pages,
privacy policy, help centre, cached archive) and draws: one status bar for the whole
customer base, the competitors showing up, and one card per customer with the evidence.
"""
import time
from html import escape

import altair as alt
import pandas as pd
import streamlit as st

# status → (icon, label, colour, what it means, what to do). Colours: the fixed status
# palette (good / warning / serious / critical) plus neutrals, always with icon + label.
STATUSES = {
    "likely_switching":   ("🔴", "Likely switching", "#d03b3b",
                           "A competitor's chat is on the same page as ours, and another source points to it too.",
                           "Contact the customer this week."),
    "possibly_trialling": ("🟠", "Possibly trialling", "#ec835a",
                           "A competitor's chat is on the same page as ours, or the privacy policy names it.",
                           "Check in with the customer soon."),
    "worth_a_look":       ("🟡", "Worth a look", "#fab219",
                           "A competitor's chat is only on other pages than ours, often a different part of "
                           "the business (e.g. the shop vs. customer service).",
                           "Usually no action. Keep an eye on it."),
    "on_competitor":      ("⚫", "Already on a competitor", "#52514e",
                           "Our chat isn't on the site, a competitor's is.",
                           "Win-back: find out when and why they moved."),
    "healthy":            ("🟢", "Healthy", "#0ca30c",
                           "Only our chat runs on the site.", ""),
    "unknown":            ("⚪", "Can't tell", "#898781",
                           "No chat tool detected. It may load only for logged-in users or after consent.",
                           "Check the site by hand."),
    "unreachable":        ("⚪", "Site not reachable", "#898781",
                           "The site blocked or failed the check.", "Try again later or check by hand."),
}
ORDER = list(STATUSES)
DEMO_SITES = "tokmanni.fi\nfennia.fi\nlahitapiola.fi\nelisa.fi\nhttp://localhost:8765"


def _link(url, text):
    if not (url or "").startswith(("http://", "https://")):
        return escape(text)
    return f'<a href="{escape(url, quote=True)}" target="_blank">{escape(text)}</a>'


def _chip(status):
    icon, label, color, *_ = STATUSES[status]
    return (f'<span style="font-size:.8em;font-weight:600;padding:2px 9px;border-radius:999px;'
            f'border:1px solid {color};white-space:nowrap">{icon} {escape(label)}</span>')


def _month(date):
    try:
        return pd.Timestamp(date).strftime("%b %Y")
    except (ValueError, TypeError):
        return date or ""


def _pages(paths):
    return ", ".join("home page" if p == "/" else p for p in paths)


# ---------- charts ----------

def _ink(hex_color):
    """Label colour inside a fill: dark ink on light fills, white on dark ones."""
    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return "#0b0b0b" if 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.5 else "#ffffff"


def _status_chart(summary):
    rows = [{"status": s, "label": f"{STATUSES[s][0]} {STATUSES[s][1]}", "n": summary.get(s, 0),
             "meaning": STATUSES[s][3], "order": i} for i, s in enumerate(ORDER) if summary.get(s)]
    df = pd.DataFrame(rows)
    total = df["n"].sum()
    df["share"] = (100 * df["n"] / total).round().astype(int).astype(str) + " %"
    df["mid"] = df["n"].cumsum() - df["n"] / 2  # label sits in the middle of its segment
    df["ink"] = [_ink(STATUSES[s][2]) for s in df["status"]]
    color = alt.Color("label:N", title=None, sort=[r["label"] for r in rows],
                      scale=alt.Scale(domain=[r["label"] for r in rows],
                                      range=[STATUSES[r["status"]][2] for r in rows]),
                      legend=alt.Legend(orient="bottom", direction="horizontal", columns=4))
    base = alt.Chart(df).encode(
        x=alt.X("n:Q", stack="zero", axis=None, scale=alt.Scale(domain=[0, total])),
        order=alt.Order("order:Q"),
    )
    bar = base.mark_bar(height=28, cornerRadius=4).encode(
        color=color,
        tooltip=[alt.Tooltip("label:N", title="Status"), alt.Tooltip("n:Q", title="Customers"),
                 alt.Tooltip("share:N", title="Share"), alt.Tooltip("meaning:N", title="Means")])
    text = alt.Chart(df).mark_text(fontWeight="bold", align="center").encode(
        x=alt.X("mid:Q", scale=alt.Scale(domain=[0, total])), text=alt.Text("n:Q"),
        color=alt.Color("ink:N", scale=None),
        opacity=alt.condition(f"datum.n / {total} > 0.06", alt.value(1), alt.value(0)))
    st.altair_chart((bar + text).properties(height=70).configure_view(stroke=None), use_container_width=True)


def _competitor_chart(customers):
    rows = []
    for c in customers:
        for r in c.get("rivals", []):
            rows.append({"competitor": r["name"], "status": c["status"], "rank": ORDER.index(c["status"]),
                         "label": f"{STATUSES[c['status']][0]} {STATUSES[c['status']][1]}", "site": c["site"]})
    if not rows:
        st.caption("No competitor chat tools found on these customer sites.")
        return
    df = pd.DataFrame(rows)
    order_comp = df.groupby("competitor").size().sort_values(ascending=False).index.tolist()
    labels = [f"{STATUSES[s][0]} {STATUSES[s][1]}" for s in ORDER if s in set(df["status"])]
    chart = alt.Chart(df).mark_bar(cornerRadius=4, height=18).encode(
        y=alt.Y("competitor:N", sort=order_comp, title=None, axis=alt.Axis(labelLimit=200, ticks=False, domain=False)),
        x=alt.X("count():Q", title="Customer sites", axis=alt.Axis(tickMinStep=1, format="d", grid=True)),
        color=alt.Color("label:N", title=None, sort=labels,
                        scale=alt.Scale(domain=labels, range=[STATUSES[s][2] for s in ORDER if s in set(df["status"])]),
                        legend=alt.Legend(orient="bottom", direction="horizontal")),
        order=alt.Order("rank:Q"),
        tooltip=[alt.Tooltip("competitor:N", title="Competitor"), alt.Tooltip("label:N", title="Status"),
                 alt.Tooltip("count():Q", title="Customer sites")],
    )
    st.altair_chart(chart.properties(height=34 * len(order_comp) + 50).configure_view(stroke=None),
                    use_container_width=True)


# ---------- how customers switch (archive timeline) ----------

def _swatch(cls, product):
    from frontend.switch_chart import STYLE, label
    _, _, color, hatch = STYLE[cls]
    bg = (f"repeating-linear-gradient(45deg, {color} 0 3px, #52514e 3px 4px)" if hatch else color)
    return (f"<span style='display:inline-flex;align-items:center;gap:6px;margin:2px 14px 2px 0'>"
            f"<span style='display:inline-block;width:22px;height:12px;border-radius:3px;background:{bg}'></span>"
            f"{escape(label(cls, product))}</span>")


def _switch_section(customers, product):
    from frontend import switch_chart as sc
    with_tl = [c for c in customers if c.get("timeline")]
    without = [c["site"] for c in customers if not c.get("timeline")]
    if not with_tl:
        st.caption("No archive history built yet for these customers. Build it once (a few minutes per site): "
                   f"`python -m backend.switch_timeline build {product} " + " ".join(without) + "`")
        return
    quiet = [c for c in with_tl if c["status"] == "healthy" and not c["timeline"]["summary"]["changed"]]
    shown = [c for c in with_tl if c not in quiet]
    entries = [{"site": c["site"] + (" · demo" if c["timeline"].get("demo") else ""), "status": c["status"],
                "timeline": c["timeline"]} for c in shown]

    real_switch = any(e["timeline"]["summary"].get("switch") for e in entries if not e["timeline"].get("demo"))
    text = sc.headline(entries, product)
    st.markdown(f"**{escape(text)}**" if real_switch else escape(text))
    hidden = [e["site"] for e in entries if e["timeline"]["summary"].get("ours_hidden")]
    if hidden:
        st.caption(f"On {', '.join(hidden)} a chat tool loads through Google Tag Manager, which the archive "
                   "doesn't store, so those months can't show whether it was there.")
    if entries:
        icons = {k: v[0] for k, v in STATUSES.items()}
        st.plotly_chart(sc.figure(entries, product, icons), use_container_width=True,
                        config={"displayModeBar": False})
        st.markdown("".join(_swatch(c, product) for c in sc.legend_classes(entries))
                    + "<span style='display:inline-flex;align-items:center;gap:6px;margin:2px 14px 2px 0'>"
                      "◆ switch (last month with " + escape(product) + " → first month without)</span>",
                    unsafe_allow_html=True)
    if quiet:
        with st.expander(f"🟢 {len(quiet)} healthy customer{'s' if len(quiet) != 1 else ''} with no change "
                         "in the archived period"):
            st.markdown(", ".join(escape(c["site"]) for c in quiet))
    if without:
        st.caption("No archive history yet for: " + ", ".join(without) +
                   f". Build it with `python -m backend.switch_timeline build {product} " + " ".join(without) + "`.")
    with st.expander("Archive snapshots behind the chart (proof)"):
        rows = []
        for e in entries + [{"site": c["site"], "timeline": c["timeline"]} for c in quiet]:
            for m in e["timeline"]["months"]:
                for snap in m.get("snapshots", []):
                    rows.append({"Customer": e["site"], "Month": m["month"], "Page": snap["page"],
                                 "Status": sc.label(m["class"], product),
                                 "Detected": ", ".join(snap.get("products", [])) or "–", "Snapshot": snap["url"]})
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                         column_config={"Snapshot": st.column_config.LinkColumn("Snapshot", display_text="open")})
        else:
            st.caption("No archive snapshots.")


# ---------- customer cards ----------

def _evidence(r, product):
    """Plain-language checklist for one competitor found on the site."""
    lines = []
    if r["same_page"]:
        lines.append(f"✓ On the same page as {escape(product)}: {escape(_pages(r['same_page']))}")
    elif r["other_pages"]:
        lines.append(f"– Only on other pages than {escape(product)}: {escape(_pages(r['other_pages']))}")
    lines.append(f"✓ Named in the {_link(r['in_privacy_policy'], 'privacy policy')}"
                 if r["in_privacy_policy"] else "– Not named in the privacy policy")
    lines.append("✓ The help centre runs on it" if r["help_centre"] else "– Help centre doesn't point to it")
    if r.get("since"):
        lines.append(f"In the archive since {escape(_month(r['since']))}")
    return lines


def _card(c, product):
    status = c["status"]
    icon, label, color, meaning, todo = STATUSES[status]
    head = f"<b style='font-size:1.05em'>{escape(c['site'])}</b> {_chip(status)}"
    body = [f"<span>{escape(meaning)}</span>"]
    if c.get("dropped_since_last_check"):
        body.insert(0, f"<b style='color:{STATUSES['likely_switching'][2]}'>{escape(product)} disappeared "
                       "since the last check.</b>")
    if status == "unreachable":
        body.append(f"<span style='opacity:.65'>{escape(c.get('error', ''))}</span>")
    for r in c.get("rivals", []):
        body.append(f"<b>{escape(r['name'])}</b><br>" + "<br>".join(_evidence(r, product)))
    if todo:
        body.append(f"<b>What to do:</b> {escape(todo)}")
    if status != "unreachable":
        proof = [_link(c["url"], "live site")]
        if c.get("help_center"):
            proof.append(_link(c["help_center"]["url"], f"help centre ({c['help_center']['platform']})"))
        proof += [_link(u, "privacy policy") for u in dict.fromkeys(c.get("disclosed", {}).values())]
        changes = c.get("changes")
        if c.get("previous_check"):
            if changes and (changes["added"] or changes["removed"]):
                diff = [f"+{p}" for p in changes["added"]] + [f"−{p}" for p in changes["removed"]]
                proof.append(f"<b>changed since last check:</b> {escape(' '.join(diff))}")
            else:
                proof.append(f"no change since {escape(c['previous_check'][:16].replace('T', ' '))}")
        else:
            proof.append("first check")
        body.append("<span style='opacity:.8;font-size:.9em'>" + " · ".join(proof) + "</span>")
    return (f"<div style='border-left:4px solid {color};padding:10px 14px;margin:10px 0;line-height:1.55'>"
            f"{head}<div style='display:flex;flex-direction:column;gap:6px;margin-top:6px'>"
            + "".join(f"<div>{b}</div>" for b in body) + "</div></div>")


def _headline(summary, product):
    n = sum(summary.values())
    at_risk = summary.get("likely_switching", 0) + summary.get("possibly_trialling", 0)
    parts = []
    if at_risk:
        parts.append(f"**{at_risk}** may be moving to a competitor")
    if summary.get("on_competitor"):
        k = summary["on_competitor"]
        parts.append(f"**{k}** already {'runs' if k == 1 else 'run'} a competitor's chat")
    if summary.get("worth_a_look"):
        k = summary["worth_a_look"]
        parts.append(f"**{k}** {'has' if k == 1 else 'have'} a competitor elsewhere on the site")
    if summary.get("healthy"):
        k = summary["healthy"]
        parts.append(f"**{k}** {'runs' if k == 1 else 'run'} only {product}")
    unknown = summary.get("unknown", 0) + summary.get("unreachable", 0)
    if unknown:
        parts.append(f"**{unknown}** couldn't be checked")
    title = (f"### {at_risk} of {n} customers may be moving to a competitor" if at_risk
             else f"### None of {n} customers shows signs of moving to a competitor")
    return title + "\n" + "; ".join(parts) + "."


def render_switches():
    try:  # imported lazily: a broken backend must not take the whole dashboard down
        from backend.churn_watch import churn_report
        from backend.site_tech import SIGNATURES, resolve_customers
    except Exception as e:
        st.error(f"Competitor alerts are unavailable: {type(e).__name__}: {e}")
        return

    st.caption("Which of your customers have started running a competitor's chat next to yours? "
               "Each customer's own website is checked live, and every alert is tested against "
               "more evidence before it counts, because most competitor sightings are harmless.")
    chat = sorted(p for p, s in SIGNATURES.items() if s["category"] == "chat")
    with st.form("switches"):
        c1, c2 = st.columns([2, 3])
        product = c1.selectbox("Your product", chat, index=chat.index("Giosg"))
        supplier = c2.text_input("Your website (only needed to read customers from your customer page)",
                                 value="giosg.com")
        sites = st.text_area("Your customers' websites, one per line. Leave empty to read them from your "
                             "customer page (uses Context.dev credits).", value=DEMO_SITES, height=130)
        submitted = st.form_submit_button("Check now", type="primary")

    if submitted:
        lines = [s.strip() for s in sites.splitlines() if s.strip()]
        with st.spinner("Checking each customer's website live…"):
            try:
                if not lines:
                    resolved = resolve_customers(supplier)
                    lines = [r["domain"] for r in resolved if r.get("domain")]
                t0 = time.monotonic()
                rep = churn_report(lines, product, record=True)
                rep["elapsed_s"] = time.monotonic() - t0
                st.session_state["churn_report"] = rep
            except Exception as e:
                st.session_state.pop("churn_report", None)
                st.error(f"Check failed: {type(e).__name__}: {e}")

    rep = st.session_state.get("churn_report")
    if not rep:
        return
    s, product = rep["summary"], rep["product"]
    st.markdown(_headline(s, product))
    st.caption(f"Checked live {rep['checked_at'][:16].replace('T', ' ')} UTC · "
               f"{sum(s.values())} sites in {rep.get('elapsed_s', 0):.1f} s")

    st.markdown("#### Your customer base")
    _status_chart(s)

    st.markdown(f"#### Competitors on your customers' sites")
    _competitor_chart(rep["customers"])

    st.markdown("#### How customers switch")
    st.caption("Which chat ran on each customer's own site, month by month, from the Wayback Machine. "
               "Orange is the warning time: both chats on the site at once.")
    _switch_section(rep["customers"], product)

    st.markdown("#### Customers, most urgent first")
    st.markdown("".join(_card(c, product) for c in rep["customers"]), unsafe_allow_html=True)

    with st.expander("How to read this, and how reliable it is"):
        st.markdown("\n".join(f"- {STATUSES[k][0]} **{STATUSES[k][1]}**: {STATUSES[k][3]}" for k in ORDER))
        st.markdown(
            "\n**Why the extra checks:** a competitor's tool on a customer's site is often harmless, for "
            "example a different tool in the online shop than in customer service. Commercial tools alert "
            "on every sighting; by HG Insights' own figure only about one in three such signals turns out "
            "to be a real evaluation. So an alert here only escalates when the tools share a page, and "
            "more when a second, independent source (privacy policy or help centre) points to the same "
            "competitor.\n\n"
            "**What is checked:** the home page and up to two customer-service pages, tools loaded through "
            "Google Tag Manager, the privacy or cookie policy, the help centre's hosting, and the archive "
            "history where it's cached.\n\n"
            "**Limits:** logged-in areas and tools that load only after cookie consent can't be seen, so "
            "*can't tell* never means *doesn't use*. A tool loaded through Tag Manager counts on every page "
            "that loads the same container.")
