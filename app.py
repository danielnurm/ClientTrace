import streamlit as st
from dotenv import load_dotenv

load_dotenv()  # API keys from .env for the backend/analysis modules

from frontend.dashboard import render
from frontend.data_source import run_analysis
from frontend.switches import render_switches

st.set_page_config(page_title="ClientTrace", page_icon="🔎", layout="wide")

st.title("🔎 ClientTrace")
st.caption("Which customers quietly left? Compare a company's customer logos over time.")

tab_pages, tab_switches = st.tabs(["Customer pages", "Tool switches (live)"])

with tab_pages:
    with st.form("analyze"):
        col1, col2 = st.columns([4, 1])
        url = col1.text_input("Company website", placeholder="https://example.com")
        year = col2.selectbox("Compare with", [2023, 2024, 2025])
        submitted = st.form_submit_button("Analyze", type="primary")


    @st.cache_data(show_spinner=False, ttl=3600)
    def cached_analysis(url, year):
        # Cache: same URL + year is not fetched again → saves API credits
        return run_analysis(url, year)


    if submitted:
        if not url:
            st.error("Please enter a website URL.")
        else:
            if not url.startswith("http"):
                url = "https://" + url
            with st.spinner("Fetching current and archived customer pages..."):
                result = cached_analysis(url, year)
            if result["notes"]:
                # Something fell back → don't keep it cached, retry for real next time
                cached_analysis.clear()
            st.session_state["result"] = result

    if "result" in st.session_state:
        render(st.session_state["result"])

with tab_switches:
    render_switches()
