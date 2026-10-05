import os
import datetime
import json
import base64
import streamlit as st
from supabase import create_client, Client
from google import genai

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

# --- INITIALIZE SESSION STATE ---
if "participant_tests" not in st.session_state:
    st.session_state.participant_tests = []

# --- SECURE URL ROUTING ---
query_params = st.query_params
is_patient_link = query_params.get("portal") == "true"

if is_patient_link:
    app_mode = "Secure Patient Mobile Portal"
    st.sidebar.subheader("🔒 Client Portal")
    st.sidebar.markdown("Chudleigh Health Hub Secure Patient Access")
    st.sidebar.divider()
else:
    st.sidebar.header("Portal Navigation")
    app_mode = st.sidebar.selectbox(
        "Select Portal View",
        ["Clinician Dashboard", "Secure Patient Mobile Portal"]
    )
    st.sidebar.divider()

# Initialize Supabase client safely
def get_supabase_client():
    url = "https://eyuvugzgxfawagpndmqo.supabase.co"
    key = "sb_publishable_hC0EacZHCbJ3wo-qKP2Q0A_sqn-_FC9"
    try:
        return create_client(url, key)
    except Exception:
        return None

# Initialize Gemini AI Client using environment variable
def get_gemini_client():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        return genai.Client(api_key=api_key)
    except Exception:
        return None

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

    st.subheader("🚀 AI Master Report Compilation & Cloud Publishing")
    st.markdown("Compile all queued tests, prompt Gemini for clinical interpretation, and securely sync to Supabase.")

    if st.button("Generate AI Master Report", type="primary", use_container_width=True):
        if not participant_name:
            st.warning("Please enter the participant's name.")
        elif not patient_pin or len(patient_pin) < 4:
            st.warning("Please enter a valid 4-digit security PIN for patient portal protection.")
        elif len(st.session_state.participant_tests) == 0:
            st.warning("Please add at least one test assessment to the profile.")
        else:
            with st.spinner("🤖 Interrogating Gemini AI and compiling master clinical report..."):
                try:
                    # Construct context payload for Gemini
                    summary_context = f"Participant: {participant_name}, Age/Gender: {age_gender}, Metrics: {body_mass_height}\n"
                    for idx, t in enumerate(st.session_state.participant_tests):
                        summary_context += f"Test {idx+1}: {t['type']} -> Data: {json.dumps(t['data'])}\n"

                    ai_analysis_html = "<p>Clinical interpretation generated successfully.</p>"
                    
                    gemini = get_gemini_client()
                    if gemini:
                        prompt = f"""
                        You are an expert longevity physician and clinical director at Chudleigh Health Hub. 
                        Analyze the following biometric and functional assessments for a patient and write a professional, encouraging, yet thorough clinical interpretation formatted in clean HTML (use h3, p, and li tags).
                        
                        Patient Details & Test Data:
                        {summary_context}
                        
                        Provide:
                        1. Clinical Summary & Insights
                        2. Key Biomarker Highlights
                        3. Tailored Lifestyle & Therapeutic Recommendations
                        """
                        response = gemini.models.generate_content(
                            model="gemini-3.8-flash",
                            contents=prompt,
                        )
                        if response and response.text:
                            ai_analysis_html = response.text

                    # Build individual test cards for HTML
                    tests_html = ""
                    for idx, t in enumerate(st.session_state.participant_tests):
                        data_str = "".join([f"<li><b>{k}:</b> {v}</li>" for k, v in t['data'].items() if v])
                        tests_html += f"""
                        <div style="background: #f8fafc; border-left: 4px solid #0f382b; padding: 15px; margin-bottom: 15px; border-radius: 4px;">
                            <h3 style="margin-top: 0; color: #0f382b;">Test #{idx+1}: {t['type']}</h3>
                            <ul style="margin-bottom: 0; color: #334155;">{data_str if data_str else "<li>Standard clinical metrics recorded.</li>"}</ul>
                        </div>
                        """

                    html_output = f"""
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <meta charset="utf-8">
                        <title>Chudleigh Health Hub - AI Longevity Report</title>
                        <style>
                            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b; line-height: 1.6; padding: 30px; max-width: 900px; margin: 0 auto; background: #ffffff; }}
                            .header {{ background: #0f382b; color: white; padding: 25px; border-radius: 8px; text-align: center; margin-bottom: 30px; }}
                            .section {{ background: #f0fdf4; border: 1px solid #bbf7d0; padding: 20px; border-radius: 8px; margin-bottom: 25px; }}
                            h1, h2, h3 {{ color: #0f382b; }}
                        </style>
                    </head>
                    <body>
                        <div class="header">
                            <h1 style="color: white; margin: 0;">Chudleigh Health Hub</h1>
                            <p style="margin: 5px 0 0 0; text-transform: uppercase; letter-spacing: 1px; color: #94a3b8;">AI-Powered Longevity &amp; Clinical Report</p>
                        </div>
                        
                        <div class="section">
                            <h2>Participant Executive Summary</h2>
                            <p><b>Participant Name:</b> {participant_name}</p>
                            <p><b>Age / Gender:</b> {age_gender if age_gender else 'Not specified'}</p>
                            <p><b>Assessment Date:</b> {str(assessment_date)}</p>
                            <p><b>Body Mass / Height:</b> {body_mass_height if body_mass_height else 'Not specified'}</p>
                        </div>

                        <div class="section">
                            <h2>🤖 Gemini AI Clinical Interpretation</h2>
                            {ai_analysis_html}
                        </div>

                        <h2>Completed Diagnostic Assessments</h2>
                        {tests_html}
                    </body>
                    </html>
                    """

                    # Sync to Supabase Cloud Database
                    db = get_supabase_client()
                    if db:
                        record = {
                            "name_lower": participant_name.strip().lower(),
                            "name": participant_name,
                            "pin": patient_pin.strip(),
                            "assessment_date": str(assessment_date),
                            "tests_count": len(st.session_state.participant_tests),
                            "html_output": html_output
                        }
                        db.table("longevity_reports").upsert(record, on_conflict="name_lower").execute()
                        st.success("✨ AI Master Report generated and successfully synced to Supabase Cloud!")
                    else:
                        st.success("✨ AI Master Report generated successfully!")

                    st.download_button(
                        label="📥 Download Master HTML Report File",
                        data=html_output,
                        file_name=f"{participant_name.replace(' ', '_')}_AI_Longevity_Report.html",
                        mime="text/html",
                    )

                    st.subheader("🔎 Live AI Master Report Preview")
                    st.components.v1.html(html_output, height=800, scrolling=True)

                except Exception as e:
                    st.error(f"An error occurred during AI report compilation: {e}")

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
        
        try:
            db = get_supabase_client()
            if not db:
                st.error("Cloud database connection unavailable.")
            else:
                response = db.table("longevity_reports").select("*").eq("name_lower", lookup_key).execute()
                data = response.data

                if data and len(data) > 0:
                    client_data = data[0]
                    
                    if client_data["pin"] == client_pin.strip():
                        st.success(f"Authentication successful. Welcome back, {client_data['name']}!")

                        st.markdown(
                            f"""
                            <div class='portal-box'>
                                <h3>📋 Your Longevity Profile Summary</h3>
                                <p><b>Participant:</b> {client_data['name']}</p>
                                <p><b>Last Clinical Assessment:</b> {client_data['assessment_date']}</p>
                                <p><b>Total Assessments On File:</b> {client_data['tests_count']}</p>
                            </div>
                            """,
                            unsafe_allow_html=True
                        )

                        st.download_button(
                            label="📥 Download My Master AI Report (Mobile / PC)",
                            data=client_data['html_output'],
                            file_name=f"{client_data['name'].replace(' ', '_')}_Healthspan_Report.html",
                            mime="text/html",
                            use_container_width=True
                        )

                        st.subheader("🔎 Your Live Interactive AI Healthspan Dashboard")
                        st.components.v1.html(client_data['html_output'], height=750, scrolling=True)
                    else:
                        st.error("Incorrect security PIN. Please check your PIN or contact Chudleigh Health Hub.")
                else:
                    st.warning("No published reports found matching that name in the cloud database.")
        
        except Exception as e:
            st.error(f"Error connecting to cloud records: {e}")
