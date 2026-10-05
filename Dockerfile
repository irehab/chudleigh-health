import os
import datetime
import json
import base64
import streamlit as st
from google import genai

# Page Configuration
st.set_page_config(
    page_title="Chudleigh Health Hub - Longevity Portal",
    page_icon="🩺",
    layout="wide",
)

st.markdown(
    """
    <div style="background-color: #0f382b; color: white; padding: 20px; border-radius: 10px; text-align: center; margin-bottom: 25px;">
        <h1 style="margin: 0; font-size: 26px;">Chudleigh Health Hub</h1>
        <p style="margin: 5px 0 0 0; color: #94a3b8; font-size: 14px; text-transform: uppercase; letter-spacing: 1px;">Diagnostic Longevity &amp; Patient Companion Portal</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# --- INITIALIZE SESSION STATE ---
if "participant_tests" not in st.session_state:
    st.session_state.participant_tests = []

# Initialize Gemini AI Client using environment variable
def get_gemini_client():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        return genai.Client(api_key=api_key)
    except Exception:
        return None

st.sidebar.subheader("Participant File Management")
if st.sidebar.button("🔄 Clear All Tests / New Patient"):
    st.session_state.participant_tests = []
    st.rerun()

st.sidebar.markdown(f"**Tests Logged:** {len(st.session_state.participant_tests)}")

st.subheader("📋 Participant Metadata")
col1, col2 = st.columns(2)

with col1:
    participant_name = st.text_input("Participant Name", placeholder="e.g. John Doe")
    age_gender = st.text_input("Age / Gender", placeholder="e.g. 48 / Male")

with col2:
    assessment_date = st.date_input("Assessment Date", value=datetime.date.today())
    patient_pin = st.text_input("Patient Secure PIN (4 digits)", type="password", placeholder="1234")

body_mass_height = st.text_input("Body Mass / Height", placeholder="78 kg / 175 cm")

st.divider()

assessment_type = st.selectbox(
    "Select Assessment Type to Add",
    [
        "Tanita Body Composition",
        "Push-Up Assessment",
        "Spirometry",
        "AGE Reader",
        "ECG",
        "Autonomic/HRV",
        "VALD ForceDecks - Sit-to-Stand",
    ],
)

raw_notes = st.text_area("Raw Metrics / Notes", placeholder="Enter test metrics or notes here...", height=100)

if st.button("➕ Add Test to Profile", use_container_width=True):
    if not participant_name:
        st.warning("Please enter participant name.")
    else:
        st.session_state.participant_tests.append({
            "type": assessment_type,
            "data": {"Notes": raw_notes}
        })
        st.success(f"Added {assessment_type} successfully!")
        st.rerun()

st.divider()

st.subheader("🚀 AI Report Compilation Test")

if st.button("Generate AI Master Report", type="primary", use_container_width=True):
    if not participant_name:
        st.warning("Please enter participant name.")
    elif len(st.session_state.participant_tests) == 0:
        st.warning("Please add at least one test.")
    else:
        with st.spinner("🤖 Interrogating Gemini AI..."):
            try:
                summary_context = f"Participant: {participant_name}, Age/Gender: {age_gender}, Metrics: {body_mass_height}\n"
                for idx, t in enumerate(st.session_state.participant_tests):
                    summary_context += f"Test {idx+1}: {t['type']} -> Data: {json.dumps(t['data'])}\n"

                ai_analysis_html = "<p>Clinical interpretation generated successfully.</p>"
                
                gemini = get_gemini_client()
                if not gemini:
                    st.error("Gemini client could not be initialized. Check GEMINI_API_KEY environment variable.")
                else:
                    prompt = f"""
                    You are an expert longevity physician at Chudleigh Health Hub. 
                    Analyze the following biometric data and write a professional clinical interpretation in clean HTML (h3, p, li tags):
                    {summary_context}
                    """
                    response = gemini.models.generate_content(
                        model="gemini-3.8-flash",
                        contents=prompt,
                    )
                    if response and response.text:
                        ai_analysis_html = response.text

                html_output = f"""
                <div>
                    <h2>AI Clinical Interpretation</h2>
                    {ai_analysis_html}
                </div>
                """

                st.success("✨ AI Master Report generated successfully!")
                st.download_button(
                    label="📥 Download Report",
                    data=html_output,
                    file_name="report.html",
                    mime="text/html",
                )
                st.components.v1.html(html_output, height=500, scrolling=True)

            except Exception as e:
                st.error(f"An error occurred during AI report compilation: {e}")
