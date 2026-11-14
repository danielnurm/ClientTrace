"""Draws the results. Gets a ready-made dict from data_source.run_analysis."""
from html import escape
from urllib.parse import urlparse

import altair as alt
import pandas as pd
import streamlit as st

STATUS_COLORS = {
    "Gone from site": "#e5484d",    # red
    "Lost": "#e5484d",
    "Still mentioned": "#d97706",   # amber
    "Retained": "#30a46c",          # green
    "New": "#3e63dd",               # blue
}
TIMELINE_EMPHASIS = "#2a78d6"   # removed: the point of the chart
TIMELINE_CONTEXT = "#898781"    # still there: context, drawn at reduced opacity
MUTED_INK = "#898781"


def _month(date):
    """"2024-12-07" → "Dec 2024"."""
    try:
        return pd.Timestamp(date).strftime("%b %Y")
    except (ValueError, TypeError):
        return date or ""


def _timeline_chart(tl, domain):
    """One bar per page/customer from first to last archive capture. Removed ones in the
    emphasis hue on top; the rest in gray. A vertical rule marks when the section
    stopped being archived (a site move), where bars ending there say nothing."""
    removed_label = "Removed"
    other_label = ("Still there when the section stopped being archived"
                   if tl.get("section_end") else "Still there at the last capture")
    df = pd.DataFrame(tl["rows"])
    df["start"], df["end"] = pd.to_datetime(df["start"]), pd.to_datetime(df["end"])
    df["status"] = df["removed"].map({True: removed_label, False: other_label})
    df["from_label"] = df["start"].dt.strftime("%b %Y")
    df["until_label"] = df["end"].dt.strftime("%b %Y")
    order = list(df["name"])

    bars = alt.Chart(df).mark_bar(height=10, cornerRadius=4).encode(
        x=alt.X("start:T", title=None, axis=alt.Axis(format="%Y", grid=True, tickCount=6)),
        x2="end:T",
        y=alt.Y("name:N", sort=order, title=None, axis=alt.Axis(labelLimit=240, ticks=False, domain=False)),
        color=alt.Color("status:N", title=None,
                        scale=alt.Scale(domain=[removed_label, other_label],
                                        range=[TIMELINE_EMPHASIS, TIMELINE_CONTEXT]),
                        legend=alt.Legend(orient="top", direction="horizontal", symbolType="square")),
        opacity=alt.condition("datum.removed", alt.value(1.0), alt.value(0.45)),
        tooltip=[alt.Tooltip("name:N", title="Customer"),
                 alt.Tooltip("from_label:N", title="Archived from"),
                 alt.Tooltip("until_label:N", title="Archived until"),
                 alt.Tooltip("status:N", title="Status")],
    )
    chart = bars
    if tl.get("section_end"):
        mark = pd.DataFrame({"x": [pd.to_datetime(tl["section_end"] + "-01")],
                             "label": [f"Section stopped being archived ({_month(tl['section_end'] + '-01')})"]})
        rule = alt.Chart(mark).mark_rule(color=MUTED_INK, strokeWidth=1).encode(x="x:T")
        text = alt.Chart(mark).mark_text(align="right", dx=-4, dy=6, baseline="top",
                                         color=MUTED_INK, fontSize=11).encode(x="x:T", y=alt.value(0), text="label:N")
        chart = bars + rule + text
    st.altair_chart(chart.properties(height=24 * len(df) + 40).configure_view(stroke=None),
                    use_container_width=True)


def _link(url, text):
    """HTML link, only for http(s) URLs; plain text otherwise."""
    if not (url or "").startswith(("http://", "https://")):
        return escape(text)
    return f'<a href="{escape(url, quote=True)}" target="_blank">{escape(text)}</a>'


def _logo(c, size):
    logo = c.get("logo_url") or ""
    box = (f"width:{size}px;height:{size}px;flex:none;border-radius:6px;display:flex;"
           "align-items:center;justify-content:center;border:1px solid rgba(128,128,128,.25)")
    if logo.startswith(("http://", "https://")):
        return (f'<div style="{box}"><img src="{escape(logo, quote=True)}" alt="" '
                'style="max-width:90%;max-height:90%;object-fit:contain"></div>')
    initial = escape(c["name"][:1].upper())
    return f'<div style="{box};font-weight:700;opacity:.6">{initial}</div>'


def _badge(text, color):
    return (f'<span style="font-size:.75em;font-weight:600;padding:2px 8px;border-radius:999px;'
            f'color:{color};border:1px solid {color}">{escape(text)}</span>')


def _rows(customers, domain, current_source, numbered):
    """Full-width rows, one per lost customer: who, when last seen, what the site check found."""
    html = []
    for i, c in enumerate(customers, 1):
        mention = c.get("mention")
        if mention and mention["mentioned"]:
            badge = _badge("Still mentioned", STATUS_COLORS["Still mentioned"])
            found = "Still on the site: " + _link(mention.get("url"), (mention.get("title") or "page") + " ↗")
        elif mention:
            badge = _badge("Strong signal", STATUS_COLORS["Gone from site"])
            found = f"Not found elsewhere on {escape(domain)} (site search)"
        elif "mention" in c:
            badge = _badge("Not checked", "gray")
            found = "Rest of the site not checked"
        else:
            badge, found = "", ""

        seen = f"Last on {escape(domain)}: " + _link(
            c["source_url"], (c.get("snapshot_date") or "archived page") + " ↗")
        archive = c.get("archive")
        if archive and archive["removed"]:
            seen = f"Removed around {_month(archive['until'])} · " + _link(c["source_url"], "archived page ↗")
        elif archive:
            seen = (f"On {escape(domain)} until the section stopped being archived "
                    f"({_month(archive['until'])}) · " + _link(c["source_url"], "archived page ↗"))
        now = _link(current_source, "not on the current page ↗") if current_source else "not on the current page"
        number = f'<div style="width:1.6em;flex:none;opacity:.5;font-weight:700">{i}</div>' if numbered else ""
        html.append(
            '<div style="display:flex;gap:12px;align-items:center;padding:10px 4px;'
            'border-bottom:1px solid rgba(128,128,128,.2)">'
            f'{number}{_logo(c, 44)}'
            '<div style="display:flex;flex-direction:column;gap:2px;min-width:0">'
            f'<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">'
            f'<strong>{escape(c["name"])}</strong>{badge}</div>'
            f'<small>{seen} → {now}</small>'
            + (f"<small style='opacity:.8'>{found}</small>" if found else "")
            + "</div></div>"
        )
    st.markdown("".join(html), unsafe_allow_html=True)


def render(data):
    if data.get("demo"):
        st.warning(
            "**Demo data – these results are not real.**\n\n"
            + "\n".join(f"- {n}" for n in data["notes"])
        )
    elif data["notes"]:
        st.info("\n".join(f"- {n}" for n in data["notes"]))

    domain = urlparse(data["url"]).netloc.lower().removeprefix("www.") or data["url"]
    year, old, lost = data["year"], data["old"], data["lost"]
    checked = data.get("mentions_checked")
    current_source = data.get("current_source")

    still = [c for c in lost if (c.get("mention") or {}).get("mentioned")]
    # Leads: everything not explained by "still on the site". Ranked by (stable sorts,
    # last one is the primary key): site check → known removal date → most recent first.
    leads = sorted([c for c in lost if c not in still],
                   key=lambda c: (c.get("archive") or {}).get("until") or c.get("snapshot_key") or "",
                   reverse=True)
    leads.sort(key=lambda c: 0 if (c.get("archive") or {}).get("removed") else 1 if c.get("archive") else 2)
    leads.sort(key=lambda c: 0 if (c.get("mention") or {}).get("mentioned") is False else 1)
    share = round(100 * len(leads) / len(old)) if old else 0
    tl = data.get("timeline")
    moved = [c for c in leads if c.get("archive") and not c["archive"]["removed"]]

    # --- Headline ---
    st.markdown(f"### {escape(domain)} dropped {len(leads)} of its {len(old)} "
                f"showcased customers since {year} ({share} %)")
    detail = []
    if checked:
        detail.append("A search of the rest of the site found none of them either.")
        if still:
            detail.append(f"{len(still)} more {'was' if len(still) == 1 else 'were'} only dropped from "
                          "the customer page and are still mentioned elsewhere, probably rotation.")
    if tl and tl.get("section_end") and moved and len(moved) * 2 >= len(leads):
        count = f"all {len(leads)}" if len(moved) == len(leads) else f"{len(moved)} of the {len(leads)}"
        detail.append(f"**But {count} were still on the site when its "
                      f"reference section stopped being archived ({_month(tl['section_end'] + '-01')}), "
                      "which points to a site redesign rather than lost customers.**")
    detail.append(f"{len(data['retained'])} still listed, {len(data['added'])} new since {year}.")
    st.markdown(" ".join(detail))

    # --- Number cards ---
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(f"Showcased in {year}", len(old))
    c2.metric("Showcased now", len(data["new"]))
    c3.metric("Leads", len(leads))
    c4.metric("Share lost", f"{share} %")

    # --- Timeline ---
    if tl and tl["rows"]:
        st.markdown("#### When they disappeared")
        st.caption(f"Each bar runs from the first to the last time the archive captured the page on "
                   f"{domain}. The archive's start dates depend on its coverage, not on when the "
                   "relationship began."
                   + (f" {tl['not_shown']} more pages that were never removed are not shown."
                      if tl["not_shown"] else ""))
        _timeline_chart(tl, domain)
        with st.expander(f"Timeline data ({len(tl['rows'])} rows)"):
            st.dataframe(pd.DataFrame([{
                "Customer": r["name"], "Archived from": r["start"], "Archived until": r["end"],
                "Status": "Removed" if r["removed"] else "Still there at the end",
                "In this comparison": "yes" if r["in_comparison"] else "",
            } for r in tl["rows"]]), width="stretch", hide_index=True)
    elif not data.get("demo") and lost:
        st.markdown("#### When they disappeared")
        st.caption("No timeline yet. It reads the archive back to "
                   f"{year - 2} to show when each customer disappeared. Free, takes a few minutes.")
        if st.button("Build timeline"):
            from backend.wayback import get_customer_timeline
            from frontend.data_source import run_analysis
            with st.spinner("Reading the archive… one request every few seconds, so this takes a few minutes."):
                get_customer_timeline(data["url"], year)
            st.session_state["result"] = run_analysis(data["url"], year)
            st.rerun()

    # --- Ranked leads ---
    if leads:
        st.markdown("#### Leads, strongest first")
        _rows(leads, domain, current_source, numbered=True)
    else:
        st.success(f"No lost customers: everyone {domain} showcased in {year} is still on the site.")
    st.write("")

    # --- Weaker signals and the rest ---
    if still:
        with st.expander(f"Dropped from the list but still mentioned ({len(still)}) – probably rotation"):
            _rows(still, domain, current_source, numbered=False)
    if data["added"]:
        with st.expander(f"New since {year} ({len(data['added'])})"):
            st.markdown(" · ".join(_link(c["source_url"], c["name"]) for c in data["added"]),
                        unsafe_allow_html=True)

    def status(c):
        if c in still:
            return "Still mentioned"
        return "Gone from site" if (c.get("mention") or {}).get("mentioned") is False else "Lost"

    rows = (
        [{"Status": status(c), **c} for c in lost]
        + [{"Status": "Retained", **c} for c in data["retained"]]
        + [{"Status": "New", **c} for c in data["added"]]
    )
    if rows:
        df = pd.DataFrame(rows)[["Status", "logo_url", "name", "source_url"]]
        df.columns = ["Status", "Logo", "Customer", "Source"]

        def color(val):
            return f"color: {STATUS_COLORS.get(val, 'inherit')}; font-weight: 600"

        with st.expander(f"All customers ({len(rows)})"):
            st.dataframe(
                df.style.map(color, subset=["Status"]),
                width="stretch",
                hide_index=True,
                column_config={
                    "Logo": st.column_config.ImageColumn("Logo"),
                    "Source": st.column_config.LinkColumn("Source"),
                },
            )

    st.caption("A disappeared logo does not prove a lost customer – "
               "the site may simply have been redesigned. Treat results as signals.")
