import streamlit as st
from dotenv import load_dotenv

load_dotenv()  # API keys from .env for the backend/analysis modules

from frontend.dashboard import render
from frontend.data_source import run_analysis
from frontend.switches import render_switches

st.set_page_config(page_title="ClientTrace", page_icon="🔎", layout="wide")

st.title("🔎 ClientTrace")
st.caption("Which of your customers are moving to a competitor? Checked live on their own websites, "
           "with proof for every alert.")

tab_switches, tab_pages = st.tabs(["Competitor alerts", "Why logo pages mislead"])

with tab_switches:
    render_switches()

with tab_pages:
    st.markdown(
        "#### Why we don't use logo pages\n"
        "The obvious way to spot a lost customer is to compare a company's customer or reference page "
        "with the same page in the Wayback Machine. We built that first, and measured it:\n\n"
        "- **kone.com:** 19 references disappeared since 2023. The archive history showed all of them "
        "were still on the site until spring 2026, when KONE moved its references to a new site. "
        "**Lost customers: 0.**\n"
        "- **zendesk.com:** 4 customers whose stories disappeared all still run Zendesk's help centre "
        "today. **Lost customers: 0.**\n\n"
        "Logos leave marketing pages for many reasons: redesigns, rotation, expired permissions, "
        "finished projects. That's why *Competitor alerts* checks what runs on the customer's own "
        "website instead. The comparison is kept here to show the difference: try `kone.com` and 2023."
    )
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
