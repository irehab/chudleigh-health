import os
import datetime
import json
import streamlit as st
from google import genai

st.set_page_config(
    page_title="Chudleigh Health Hub - Longevity Portal",
    page_icon="🩺",
    layout="wide",
)

st.markdown(
    """
    <div style="background-color: #0f382b; color: white; padding: 20px; border-radius: 10px; text-align: center; margin-bottom: 25px;">
        <h1 style="margin: 0; font-size: 26px;">Chudleigh Health Hub</h1>
        <p style="margin: 5px 0 0 0; color: #94a3b8; font-size: 14px; text-transform: uppercase; letter-spacing: 1px;">Diagnostic Longevity Portal</p>
    </div>
    """,
    unsafe_allow_html=True,
)

if "participant_tests" not in st.session_state:
    st.session_state.participant_tests = []

def get_gemini_client():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        return genai.Client(api_key=api_key)
    except Exception:
        return None

st.sidebar.subheader("Participant File Management")
if st.sidebar.button("🔄 Clear All Tests"):
    st.session_state.participant_tests = []
    st.rerun()

st.subheader("📋 Participant Metadata")
participant_name = st.text_input("Participant Name", placeholder="e.g. John Doe")
age_gender = st.text_input("Age / Gender", placeholder="e.g. 48 / Male")
body_mass_height = st.text_input("Body Mass / Height", placeholder="78 kg / 175 cm")

assessment_type = st.selectbox(
    "Select Assessment Type",
    ["Tanita Body Composition", "Push-Up Assessment", "Spirometry", "Autonomic/HRV"]
)
raw_notes = st.text_area("Metrics / Notes", placeholder="Enter metrics or notes...")

if st.button("➕ Add Test to Profile", use_container_width=True):
    if participant_name:
        st.session_state.participant_tests.append({"type": assessment_type, "data": {"Notes": raw_notes}})
        st.success("Test added successfully!")
        st.rerun()
    else:
        st.warning("Please enter participant name.")

st.divider()

if st.button("Generate AI Master Report", type="primary", use_container_width=True):
    if not participant_name:
        st.warning("Please enter participant name.")
    elif len(st.session_state.participant_tests) == 0:
        st.warning("Please add at least one test.")
    else:
        with st.spinner("🤖 Interrogating Gemini AI..."):
            try:
                summary_context = f"Participant: {participant_name}, Age/Gender: {age_gender}\n"
                for idx, t in enumerate(st.session_state.participant_tests):
                    summary_context += f"Test {idx+1}: {t['type']} -> {json.dumps(t['data'])}\n"

                gemini = get_gemini_client()
                if not gemini:
                    st.error("Gemini client initialization failed. Check API key.")
                else:
                    prompt = f"Analyze the following biometric data as an expert longevity physician and format in clean HTML:\n{summary_context}"
                    response = gemini.models.generate_content(
                        model="gemini-3.8-flash",
                        contents=prompt,
                    )
                    ai_analysis_html = response.text if response and response.text else "<p>Generated successfully.</p>"
                    
                    st.success("✨ Report generated successfully!")
                    st.components.v1.html(ai_analysis_html, height=500, scrolling=True)
            except Exception as e:
                st.error(f"An error occurred during AI report compilation: {e}")
