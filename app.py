import datetime
import json
import base64
import requests
import streamlit as st

# Page Configuration
st.set_page_config(
    page_title="Chudleigh Health Hub - Master Longevity Report Generator",
    page_icon="🩺",
    layout="wide",
)

# Custom Styling to match Chudleigh Health Hub brand guidelines
st.markdown(
    """
    <style>
    :root {
        --primary-color: #0f382b;
        --secondary-color: #2b6a52;
    }
    .main-header {
        background-color: #0f382b;
        color: white;
        padding: 20px;
        border-radius: 10px;
        text-align: center;
        margin-bottom: 25px;
    }
    .main-header h1 {
        margin: 0;
        font-size: 26px;
    }
    .main-header p {
        margin: 5px 0 0 0;
        color: #94a3b8;
        font-size: 14px;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    .test-card {
        background-color: #f8fafc;
        border-left: 4px solid #0f382b;
        padding: 10px 15px;
        margin-bottom: 10px;
        border-radius: 4px;
        color: #1e293b;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Header Banner
st.markdown(
    """
    <div class="main-header">
        <h1>Chudleigh Health Hub</h1>
        <p>Comprehensive Diagnostic Longevity &bull; Master Report Generator</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# --- INITIALIZE SESSION STATE FOR MULTI-TEST BATCHING ---
if "participant_tests" not in st.session_state:
    st.session_state.participant_tests = []

# --- SIDEBAR CONFIGURATION ---
st.sidebar.header("Configuration & Settings")

api_key = st.sidebar.text_input(
    "Google Gemini API Key", type="password", help="Enter your Google Gemini API key here."
)

st.sidebar.divider()
st.sidebar.subheader("Participant File Management")

# Reset / New Participant Button
if st.sidebar.button("🔄 Clear All Tests / New Patient"):
    st.session_state.participant_tests = []
    st.rerun()

# Display current queued tests count in sidebar
st.sidebar.markdown(f"**Tests Logged in Profile:** {len(st.session_state.participant_tests)}")
for idx, t in enumerate(st.session_state.participant_tests):
    st.sidebar.markdown(f"<div class='test-card'><b>{idx+1}. {t['type']}</b></div>", unsafe_allow_html=True)

# --- MAIN FORM: PARTICIPANT METADATA ---
st.subheader("📋 Participant Metadata")
col1, col2 = st.columns(2)

with col1:
    participant_name = st.text_input(
        "Participant Name", placeholder="e.g. John Doe", key="p_name"
    )
    age_gender = st.text_input(
        "Age / Gender", placeholder="e.g. 48 / Male", key="p_ag"
    )

with col2:
    assessment_date = st.date_input(
        "Assessment Date", value=datetime.date.today(), key="p_date"
    )
    body_mass_height = st.text_input(
        "Body Mass / Height", placeholder="e.g. 78 kg / 175 cm", key="p_bm"
    )

st.divider()

# --- DYNAMIC INPUT AREA FOR INDIVIDUAL TESTS ---
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
        "VALD ForceDecks - Squat",
        "VALD ForceDecks - Quiet Stand (Balance)",
    ],
)

st.subheader(f"📊 Input Data: {assessment_type}")

uploaded_pdf = None
test_payload_data = {}

if assessment_type == "Autonomic/HRV":
    col_h1, col_h2 = st.columns(2)
    with col_h1:
        rmssd = st.text_input("RMSSD (ms)", placeholder="e.g. 45ms")
        sdnn = st.text_input("SDNN (ms)", placeholder="e.g. 52ms")
    with col_h2:
        resp_rate = st.text_input(
            "Respiration Rate (breaths/min)", placeholder="e.g. 14"
        )
        blood_pressure = st.text_input(
            "Blood Pressure (mmHg)", placeholder="e.g. 120/80"
        )

    test_payload_data = {
        "RMSSD": rmssd,
        "SDNN": sdnn,
        "Respiration Rate": resp_rate,
        "Blood Pressure": blood_pressure,
    }
else:
    uploaded_pdf = st.file_uploader(
        f"Upload official {assessment_type} PDF report (optional)", type=["pdf"], key=f"pdf_{assessment_type}"
    )
    raw_notes = st.text_area(
        "Or Paste Raw Metrics / Notes",
        placeholder="Paste extracted data metrics or notes here...",
        height=100,
        key=f"notes_{assessment_type}"
    )
    test_payload_data = {"Raw Data / Notes": raw_notes}

# Button to add current test to session batch
if st.button("➕ Add This Test to Participant Profile", use_container_width=True):
    if not participant_name:
        st.warning("Please enter the participant's name before adding tests.")
    else:
        pdf_b64 = None
        if uploaded_pdf is not None:
            pdf_bytes = uploaded_pdf.getvalue()
            pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

        # Save test object to session state
        st.session_state.participant_tests.append({
            "type": assessment_type,
            "data": test_payload_data,
            "pdf_b64": pdf_b64
        })
        st.success(f"Successfully added {assessment_type} to {participant_name}'s profile!")
        st.rerun()

st.divider()

# --- MASTER REPORT GENERATION BUTTON ---
st.subheader("🚀 Master Report Compilation")
st.markdown("Once you have added all individual test results for this participant, click below to generate the master longitudinal report featuring tailored Chudleigh Health Hub clinical and therapeutic care pathways.")

if st.button("Generate Master Longitudinal Summary Report", type="primary", use_container_width=True):
    if not api_key:
        st.error("Please enter your Google Gemini API key in the sidebar.")
    elif not participant_name:
        st.warning("Please enter the participant's name.")
    elif len(st.session_state.participant_tests) == 0:
        st.warning("Please add at least one test assessment to the participant's profile before generating the master report.")
    else:
        with st.spinner(f"Synthesizing {len(st.session_state.participant_tests)} clinical assessments and formulating therapeutic care plan..."):
            try:
                # Compile prompt text
                prompt_text = f"""
                Act as an expert clinical lead and longevity data analyst at Chudleigh Health Hub.
                Generate a fully customized, multi-test, comprehensive master longitudinal HTML web page report for the following participant:
                
                Participant Name: {participant_name}
                Age / Gender: {age_gender}
                Assessment Date: {str(assessment_date)}
                Body Mass / Height: {body_mass_height}
                
                The participant has completed the following {len(st.session_state.participant_tests)} individual assessments:
                """

                parts = [{"text": prompt_text}]

                # Attach each test's data and optional PDF
                for idx, t in enumerate(st.session_state.participant_tests):
                    test_desc = f"\n--- Test #{idx+1}: {t['type']} ---\nData/Notes: {t['data']}"
                    parts.append({"text": test_desc})
                    
                    if t["pdf_b64"]:
                        parts.append({
                            "inline_data": {
                                "mime_type": "application/pdf",
                                "data": t["pdf_b64"]
                            }
                        })

                final_instructions = """
                Requirements for the Master Report:
                - Create a professional, executive-level multi-test dashboard layout using primary color #0f382b.
                - Provide an Executive Summary section synthesizing cross-system correlations (analyzing neuromuscular performance from force plates alongside body composition and metabolic health).
                - Include individual breakdown modules for each test completed.
                - **Chudleigh Health Hub Therapeutic & Clinical Action Plan:** Include a prominent, dedicated intervention section that outlines tailored practitioner recommendations based on the participant's findings:
                    1. **Osteopathic Manual Therapy Pathway:** Prescribe specific care frequency (e.g., weekly or monthly sessions) specifically justified by any tissue stiffness, asymmetries, neuromuscular restrictions, or postural imbalances found across the assessments.
                    2. **Targeted Exercise & Personal Training Prescription:** Outline concrete programming (e.g., prescriptive blocks like 3x personal training sessions per week for 6 weeks) addressing specific force plate deficits (rate of force development, eccentric impulse) or body composition goals (lean mass optimization).
                    3. **Longevity Lifestyle & Autonomous Recovery:** Actionable daily habits for autonomic nervous system regulation and recovery.
                - Output ONLY valid, complete, production-ready HTML code without markdown code blocks wrapper or citation markers.
                """
                parts.append({"text": final_instructions})

                payload = {
                    "contents": [{
                        "parts": parts
                    }]
                }
                headers = {"Content-Type": "application/json"}

                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent?key={api_key}"
                response = requests.post(url, headers=headers, data=json.dumps(payload))
                res_json = response.json()

                if response.status_code != 200:
                    error_msg = res_json.get("error", {}).get("message", "Unknown API error")
                    st.error(f"API Error ({response.status_code}): {error_msg}")
                else:
                    html_output = res_json["candidates"][0]["content"]["parts"][0]["text"]

                    # Clean potential markdown code ticks if returned
                    if html_output.startswith("```html"):
                        html_output = html_output[7:]
                    if html_output.endswith("```"):
                        html_output = html_output[:-3]

                    st.success("Master Longitudinal Report successfully generated!")

                    # Display download button
                    st.download_button(
                        label="📥 Download Master HTML Report File",
                        data=html_output,
                        file_name=f"{participant_name.replace(' ', '_')}_Master_Longevity_Report.html",
                        mime="text/html",
                    )

                    # Live preview container
                    st.subheader("🔎 Live Master Report Preview")
                    st.components.v1.html(html_output, height=800, scrolling=True)

            except Exception as e:
                st.error(f"An error occurred during generation: {e}")
