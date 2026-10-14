"""VetRelay AI — MVP 1 Client Streamlit app (pet owner intake form)."""

import httpx
import streamlit as st

API_BASE = "http://localhost:8000"

st.set_page_config(page_title="VetRelay AI — Pet Intake", layout="centered")
st.title("🐾 VetRelay AI — Pet Intake")

with st.form("intake_form"):
    species = st.selectbox("Species", ["canine", "feline", "avian", "other"])
    age = st.number_input("Approximate age (years)", min_value=0.0, step=0.5)
    statement = st.text_area("Describe your pet's symptoms", height=150)
    zip_code = st.text_input("Your ZIP code (5 digits)", max_chars=5)
    submitted = st.form_submit_button("Submit")

if submitted:
    if not statement or not zip_code:
        st.error("Please fill in all required fields.")
    else:
        # Step 1: SOAP summarisation
        with st.spinner("Generating clinical summary…"):
            soap_resp = httpx.post(
                f"{API_BASE}/soap/summarise",
                json={"owner_statement": statement, "species": species, "age_years": age},
                timeout=30,
            )
        if soap_resp.status_code != 200:
            st.error(f"SOAP API error: {soap_resp.text}")
        else:
            soap_data = soap_resp.json()
            st.subheader("Clinical SOAP Summary")
            for section, text in soap_data["soap"].items():
                st.markdown(f"**{section.capitalize()}:** {text}")

        # Step 2: Triage evaluation
        with st.spinner("Evaluating triage…"):
            triage_resp = httpx.post(
                f"{API_BASE}/triage/evaluate",
                json={"symptoms": statement.split("."), "species": species, "weight_kg": None},
                timeout=30,
            )
        if triage_resp.status_code == 200:
            triage_data = triage_resp.json()
            if triage_data["escalation_required"]:
                st.error(f"🚨 EMERGENCY — {triage_data['recommended_action']}")
                st.stop()  # Block all non-emergency flows per Archetype 3 contract
            else:
                sev = triage_data["severity"]
                action = triage_data["recommended_action"]
                st.info(f"Severity: {sev} — {action}")

        # Step 3: Clinic routing
        with st.spinner("Finding available clinics…"):
            routing_resp = httpx.post(
                f"{API_BASE}/routing/find-clinic",
                json={"zip_code": zip_code, "urgent": False},
                timeout=30,
            )
        if routing_resp.status_code == 200:
            routing_data = routing_resp.json()
            if routing_data["routed_to"]:
                clinic = routing_data["routed_to"]
                st.success(
                    f"Routed to **{clinic['name']}** ({clinic['clinic_type']}) — "
                    f"{clinic['distance_miles']} mi · 📞 {clinic['phone']}"
                )
                if routing_data["fallback_used"]:
                    st.warning("Preferred clinic type unavailable — nearest alternative selected.")
            else:
                st.error(
                    "No available clinics found. Please call 911 or an emergency animal hospital."
                )
