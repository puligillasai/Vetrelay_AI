"""VetRelay AI — MVP 2 Clinic Console Streamlit app (staff-facing capacity dashboard)."""

import httpx
import streamlit as st

API_BASE = "http://localhost:8000"

st.set_page_config(page_title="VetRelay AI — Clinic Console", layout="wide")
st.title("🏥 VetRelay AI — Clinic Console")
st.caption("Staff-facing dashboard for monitoring capacity and incoming intake requests.")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Incoming Intake Requests")
    st.info("Real-time intake queue will appear here once SOAP/triage pipeline is live.")

with col2:
    st.subheader("Current Capacity (Mock Data)")
    resp = httpx.get(f"{API_BASE}/routing/find-clinic", timeout=10)  # noqa: F841
    # Placeholder: render mock_data capacity table
    st.json(
        {
            "note": "Capacity loaded from mock_data/clinic_capacity.json",
            "instruction": "POST to /routing/find-clinic to query live routing.",
        }
    )
