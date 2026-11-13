"""Draws the results. Gets a ready-made dict from data_source.run_analysis."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

STATUS_COLORS = {
    "Lost": "#e5484d",       # red
    "Retained": "#30a46c",   # green
    "New": "#3e63dd",        # blue
}


def render(data):
    if data["notes"]:
        with st.expander("⚠️ Some parts use demo data", expanded=False):
            for n in data["notes"]:
                st.write("•", n)

    st.subheader(f"Results: {data['url']}")
    st.caption(f"Compared {data['year']} with today")

    # --- Number cards ---
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(f"Customers in {data['year']}", len(data["old"]))
    c2.metric("Customers now", len(data["new"]))
    c3.metric("Disappeared", len(data["lost"]))
    c4.metric("New", len(data["added"]))

    # --- Bar chart ---
    fig = go.Figure(go.Bar(
        x=["Retained", "Lost", "New"],
        y=[len(data["retained"]), len(data["lost"]), len(data["added"])],
        marker_color=[STATUS_COLORS["Retained"], STATUS_COLORS["Lost"], STATUS_COLORS["New"]],
        text=[len(data["retained"]), len(data["lost"]), len(data["added"])],
        textposition="outside",
    ))
    fig.update_layout(height=300, margin=dict(t=20, b=20), yaxis_title="Customers")
    st.plotly_chart(fig)

    # --- Table of all customers ---
    rows = (
        [{"Status": "Lost", **c} for c in data["lost"]]
        + [{"Status": "Retained", **c} for c in data["retained"]]
        + [{"Status": "New", **c} for c in data["added"]]
    )
    if not rows:
        st.info("No customers found.")
        return

    df = pd.DataFrame(rows)[["Status", "name", "source_url"]]
    df.columns = ["Status", "Customer", "Source"]

    def color(val):
        return f"color: {STATUS_COLORS.get(val, 'inherit')}; font-weight: 600"

    st.dataframe(
        df.style.map(color, subset=["Status"]),
        width="stretch",
        hide_index=True,
        column_config={"Source": st.column_config.LinkColumn("Source")},
    )

    st.caption("A disappeared logo does not prove a lost customer – "
               "the site may simply have been redesigned. Treat results as signals.")
