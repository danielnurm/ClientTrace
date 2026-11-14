"""Draws the results. Gets a ready-made dict from data_source.run_analysis."""
from html import escape
from urllib.parse import urlparse

import pandas as pd
import streamlit as st

STATUS_COLORS = {
    "Gone from site": "#e5484d",    # red
    "Lost": "#e5484d",
    "Still mentioned": "#d97706",   # amber
    "Retained": "#30a46c",          # green
    "New": "#3e63dd",               # blue
}


def _link(url, text):
    """HTML link, only for http(s) URLs; plain text otherwise."""
    if not (url or "").startswith(("http://", "https://")):
        return escape(text)
    return f'<a href="{escape(url, quote=True)}" target="_blank">{escape(text)}</a>'


def _card(c, current_source, domain):
    """Evidence card for one lost customer: then (archived) → now (current page / rest of site)."""
    logo = c.get("logo_url") or ""
    top = (f'<img src="{escape(logo, quote=True)}" alt="" '
           'style="max-width:100%;max-height:40px;object-fit:contain">'
           if logo.startswith(("http://", "https://")) else "")
    listed = f"Listed {c['snapshot_date']}" if c.get("snapshot_date") else "Listed before"
    lines = [
        _link(c["source_url"], f"{listed} ↗"),
        _link(current_source, "Not on the current page ↗") if current_source else "Not on the current page",
    ]
    mention = c.get("mention")
    if mention is None and "mention" in c:
        lines.append('<span style="opacity:.7">Rest of site not checked</span>')
    elif mention and mention["mentioned"]:
        lines.append("Still on site: " + _link(mention.get("url"), (mention.get("title") or "page") + " ↗"))
    elif mention:
        lines.append(f"<strong>Not found anywhere on {escape(domain)}</strong>")
    return (
        '<div style="display:flex;flex-direction:column;gap:6px;padding:12px;'
        'border:1px solid rgba(128,128,128,.3);border-radius:8px">'
        f"{top}<strong>{escape(c['name'])}</strong>"
        + "".join(f"<small>{line}</small>" for line in lines)
        + "</div>"
    )


def _cards(customers, current_source, domain):
    st.markdown(
        '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:10px">'
        + "".join(_card(c, current_source, domain) for c in customers) + "</div>",
        unsafe_allow_html=True,
    )


def render(data):
    if data.get("demo"):
        st.warning(
            "**Demo data – these results are not real.**\n\n"
            + "\n".join(f"- {n}" for n in data["notes"])
        )
    elif data["notes"]:
        st.info("\n".join(f"- {n}" for n in data["notes"]))

    domain = urlparse(data["url"]).netloc.lower().removeprefix("www.") or data["url"]
    lost, year = data["lost"], data["year"]
    checked = data.get("mentions_checked")
    gone = [c for c in lost if (c.get("mention") or {}).get("mentioned") is False]
    still = [c for c in lost if (c.get("mention") or {}).get("mentioned")]
    unchecked = [c for c in lost if c not in gone and c not in still]

    # --- Headline ---
    st.subheader(domain)
    if checked:
        text = (f"Listed **{len(data['old'])}** customers in {year}. "
                f"**{len(gone)}** of them are gone from the whole site, "
                f"**{len(still)}** {'was' if len(still) == 1 else 'were'} dropped from the customer "
                f"page but {'is' if len(still) == 1 else 'are'} still mentioned elsewhere, and "
                f"**{len(data['retained'])}** {'is' if len(data['retained']) == 1 else 'are'} still listed.")
        if unchecked:
            text += f" {len(unchecked)} couldn't be checked."
    else:
        text = (f"Listed **{len(data['old'])}** customers in {year}. "
                f"**{len(lost)}** {'is' if len(lost) == 1 else 'are'} no longer on the customer page and "
                f"**{len(data['retained'])}** {'is' if len(data['retained']) == 1 else 'are'} still listed.")
    st.markdown(text)

    # --- Number cards ---
    cols = st.columns(5 if checked else 4)
    cols[0].metric(f"Customers in {year}", len(data["old"]))
    cols[1].metric("Customers now", len(data["new"]))
    if checked:
        cols[2].metric("Gone from site", len(gone))
        cols[3].metric("Still mentioned", len(still))
    else:
        cols[2].metric("Disappeared", len(lost))
    cols[-1].metric("New", len(data["added"]))

    # --- Evidence for the lost customers ---
    current_source = data.get("current_source")
    if checked:
        if gone:
            st.markdown(f"#### Gone from {domain}")
            st.caption("Removed from the customer page and not found anywhere else on the site. "
                       "The strongest signal.")
            _cards(gone, current_source, domain)
        if unchecked:
            st.markdown("#### Not checked")
            _cards(unchecked, current_source, domain)
        if still:
            with st.expander(f"Dropped from the customer page but still mentioned ({len(still)})"):
                st.caption("Probably a redesign or rotation rather than a lost customer.")
                _cards(still, current_source, domain)
    elif lost:
        st.markdown(f"#### Disappeared since {year}")
        _cards(lost, current_source, domain)
    st.write("")

    # --- Table of all customers ---
    def status(c):
        if c in gone:
            return "Gone from site"
        return "Still mentioned" if c in still else "Lost"

    rows = (
        [{"Status": status(c), **c} for c in lost]
        + [{"Status": "Retained", **c} for c in data["retained"]]
        + [{"Status": "New", **c} for c in data["added"]]
    )
    if not rows:
        st.info("No customers found.")
        return

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
