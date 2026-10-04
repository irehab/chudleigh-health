import datetime
import json
import base64
import requests
import streamlit as st

# Page Configuration
st.set_page_config(
    page_title="Chudleigh Health Hub - Longevity Portal",
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
    .portal-box {
        background-color: #f0fdf4;
        border: 1px solid #bbf7d0;
        padding: 20px;
        border-radius: 8px;
        margin-bottom: 20px;
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
        <p>Diagnostic Longevity &amp; Patient Companion Portal</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# --- INITIALIZE SESSION STATE FOR STORAGE ---
if "participant_tests" not in st.session_state:
    st.session_state.participant_tests = []
if "saved_reports" not in st.session_state:
    st.session_state.saved_reports = {} 

# --- DETECT URL PARAMETERS TO DEFAULT TO PATIENT PORTAL ---
query_params = st.query_params
default_mode_index = 1 if query_params.get("portal") == "true" else 0

# --- SIDEBAR NAVIGATION ---
st.sidebar.header("Portal Navigation")
app_mode = st.sidebar.selectbox(
    "Select Portal View",
    ["Clinician Dashboard", "Secure Patient Mobile Portal"],
    index=default_mode_index
)

# Only show the Gemini API key input in the Clinician Dashboard view
api_key = ""
if app_mode == "Clinician Dashboard":
    api_key = st.sidebar.text_input(
        "Google Gemini API Key", type="password", help="Enter your Google Gemini API key here."
    )

st.sidebar.divider()

# ==========================================
# VIEW 1: CLINICIAN DASHBOARD
# ==========================================
if app_mode == "Clinician Dashboard":
    st.sidebar.subheader("Participant File Management")

    if st.sidebar.button("🔄 Clear All Tests / New Patient"):
        st.session_state.participant_tests = []
        st.rerun()

    st.sidebar.markdown(f"**Tests Logged in Profile:** {len(st.session_state.participant_tests)}")
    for idx, t in enumerate(st.session_state.participant_tests):
        st.sidebar.markdown(f"<div class='test-card'><b>{idx+1}. {t['type']}</b></div>", unsafe_allow_html=True)

    st.subheader("📋 Participant Metadata & Security PIN")
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
        patient_pin = st.text_input(
            "Patient Secure PIN (4 digits)", type="password", placeholder="e.g. 1234", key="p_pin"
        )

    body_mass_height = st.text_input(
        "Body Mass / Height", placeholder="e.g. 78 kg / 175 cm", key="p_bm"
    )

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

    if st.button("➕ Add This Test to Participant Profile", use_container_width=True):
        if not participant_name:
            st.warning("Please enter the participant's name before adding tests.")
        else:
            pdf_b64 = None
            if uploaded_pdf is not None:
                pdf_bytes = uploaded_pdf.getvalue()
                pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

            st.session_state.participant_tests.append({
                "type": assessment_type,
                "data": test_payload_data,
                "pdf_b64": pdf_b64
            })
            st.success(f"Successfully added {assessment_type} to {participant_name}'s profile!")
            st.rerun()

    st.divider()

    st.subheader("🚀 Master Report Compilation & Portal Publishing")
    st.markdown("Compile all queued tests into a master report and securely publish it to the participant's mobile companion portal.")

    if st.button("Generate & Publish Master Report", type="primary", use_container_width=True):
        if not api_key:
            st.error("Please enter your Google Gemini API key in the sidebar.")
        elif not participant_name:
            st.warning("Please enter the participant's name.")
        elif not patient_pin or len(patient_pin) < 4:
            st.warning("Please enter a valid 4-digit security PIN for patient portal protection.")
        elif len(st.session_state.participant_tests) == 0:
            st.warning("Please add at least one test assessment to the profile.")
        else:
            with st.spinner(f"Synthesizing {len(st.session_state.participant_tests)} assessments and formulating clinical care plan..."):
                try:
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
                    - Provide an Executive Summary section synthesizing cross-system correlations.
                    - Include individual breakdown modules for each test completed.
                    - **Chudleigh Health Hub Therapeutic & Clinical Action Plan:** Include a prominent intervention section outlining:
                        1. **Osteopathic Manual Therapy Pathway:** Specific care frequency (weekly or monthly sessions) justified by tissue stiffness or asymmetries.
                        2. **Targeted Exercise & Personal Training Prescription:** Concrete programming (e.g., 3x personal training sessions per week for 6 weeks) addressing force plate or body composition goals.
                        3. **Longevity Lifestyle & Autonomous Recovery:** Daily habits for nervous system regulation.
                    - Output ONLY valid, complete, production-ready HTML code without markdown code blocks wrapper or citation markers.
                    """
                    parts.append({"text": final_instructions})

                    payload = {"contents": [{"parts": parts}]}
                    headers = {"Content-Type": "application/json"}

                    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent?key={api_key}"
                    response = requests.post(url, headers=headers, data=json.dumps(payload))
                    res_json = response.json()

                    if response.status_code != 200:
                        error_msg = res_json.get("error", {}).get("message", "Unknown API error")
                        st.error(f"API Error ({response.status_code}): {error_msg}")
                    else:
                        html_output = res_json["candidates"][0]["content"]["parts"][0]["text"]

                        if html_output.startswith("```html"):
                            html_output = html_output[7:]
                        if html_output.endswith("```"):
                            html_output = html_output[:-3]

                        st.session_state.saved_reports[participant_name.strip().lower()] = {
                            "name": participant_name,
                            "pin": patient_pin.strip(),
                            "date": str(assessment_date),
                            "html": html_output,
                            "tests_count": len(st.session_state.participant_tests)
                        }

                        st.success("Master Report successfully generated and published with PIN protection!")

                        st.download_button(
                            label="📥 Download Master HTML Report File",
                            data=html_output,
                            file_name=f"{participant_name.replace(' ', '_')}_Master_Longevity_Report.html",
                            mime="text/html",
                        )

                        st.subheader("🔎 Live Master Report Preview")
                        st.components.v1.html(html_output, height=800, scrolling=True)

                except Exception as e:
                    st.error(f"An error occurred during generation: {e}")

# ==========================================
# VIEW 2: SECURE PATIENT MOBILE PORTAL
# ==========================================
elif app_mode == "Secure Patient Mobile Portal":
    st.subheader("📱 Participant Companion Portal")
    st.markdown("Welcome to the Chudleigh Health Hub client portal. Enter your name and your secure 4-digit PIN provided by your clinician to access your records.")

    col_l1, col_l2 = st.columns(2)
    with col_l1:
        client_lookup = st.text_input("Your Full Name", placeholder="e.g. John Doe")
    with col_l2:
        client_pin = st.text_input("Your Secure 4-Digit PIN", type="password", placeholder="****")

    if st.button("Unlock My Healthspan Portal", type="primary", use_container_width=True):
        lookup_key = client_lookup.strip().lower()
        
        if lookup_key in st.session_state.saved_reports:
            client_data = st.session_state.saved_reports[lookup_key]
            
            if client_data["pin"] == client_pin.strip():
                st.success(f"Authentication successful. Welcome back, {client_data['name']}!")

                st.markdown(
                    f"""
                    <div class='portal-box'>
                        <h3>📋 Your Longevity Profile Summary</h3>
                        <p><b>Participant:</b> {client_data['name']}</p>
                        <p><b>Last Clinical Assessment:</b> {client_data['date']}</p>
                        <p><b>Total Assessments On File:</b> {client_data['tests_count']}</p>
                        <p><b>Assigned Care Schedule:</b> Active 6-Week Therapeutic Care Plan &amp; Osteopathic Protocol</p>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                st.download_button(
                    label="📥 Download My Master HTML Report (Mobile / PC)",
                    data=client_data['html'],
                    file_name=f"{client_data['name'].replace(' ', '_')}_Healthspan_Report.html",
                    mime="text/html",
                    use_container_width=True
                )

                st.subheader("🔎 Your Live Interactive Healthspan Dashboard")
                st.components.v1.html(client_data['html'], height=750, scrolling=True)
            else:
                st.error("Incorrect security PIN. Please check your PIN or contact Chudleigh Health Hub.")
        else:
            st.warning("No published reports found matching that name. Please check your spelling or contact your clinician.")
