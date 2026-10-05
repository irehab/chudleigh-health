import os
import datetime
import json
import base64
import streamlit as st
from google.cloud import firestore
from google import genai

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Chudleigh Health Hub - Longevity Portal",
    page_icon="🩺",
    layout="wide",
)

# --- BRAND STYLING ---
st.markdown(
    """
    <style>
    :root {
        --primary: #0f382b;
        --secondary: #2b6a52;
    }
    .main-header {
        background-color: var(--primary);
        color: white;
        padding: 24px;
        border-radius: 12px;
        text-align: center;
        margin-bottom: 25px;
    }
    .main-header h1 {
        margin: 0;
        font-size: 28px;
        color: white;
    }
    .main-header p {
        margin: 6px 0 0 0;
        color: #94a3b8;
        font-size: 13px;
        text-transform: uppercase;
        letter-spacing: 1.5px;
    }
    .test-card {
        background-color: #f8fafc;
        border-left: 4px solid var(--primary);
        padding: 12px 16px;
        margin-bottom: 12px;
        border-radius: 6px;
        color: #1e293b;
    }
    .portal-box {
        background-color: #f0fdf4;
        border: 1px solid #bbf7d0;
        padding: 24px;
        border-radius: 10px;
        margin-bottom: 20px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- HEADER BANNER ---
st.markdown(
    """
    <div class="main-header">
        <h1>Chudleigh Health Hub</h1>
        <p>Google Cloud &amp; Gemini AI Longevity Portal</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# --- SESSION STATE INITIALIZATION ---
if "participant_tests" not in st.session_state:
    st.session_state.participant_tests = []

# --- GOOGLE CLOUD & GEMINI INITIALIZATIONS ---
@st.cache_resource
def init_firestore():
    try:
        # Connected explicitly to your 'default' Firestore database instance
        return firestore.Client(database="default")
    except Exception:
        return None

@st.cache_resource
def init_gemini():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        return genai.Client(api_key=api_key)
    except Exception:
        return None

db = init_firestore()
gemini_client = init_gemini()

# --- URL ROUTING & NAVIGATION ---
query_params = st.query_params
is_patient_link = query_params.get("portal") == "true"

if is_patient_link:
    app_mode = "Secure Patient Mobile Portal"
    st.sidebar.subheader("🔒 Client Portal Access")
    st.sidebar.markdown("Chudleigh Health Hub Secure Patient Companion")
    st.sidebar.divider()
else:
    st.sidebar.header("Portal Navigation")
    app_mode = st.sidebar.selectbox(
        "Select Portal View",
        ["Clinician Dashboard", "Secure Patient Mobile Portal"]
    )
    st.sidebar.divider()

# ==========================================
# VIEW 1: CLINICIAN DASHBOARD
# ==========================================
if app_mode == "Clinician Dashboard":
    st.sidebar.subheader("Active Participant Queue")

    if st.sidebar.button("🔄 Clear All Tests / New Patient", use_container_width=True):
        st.session_state.participant_tests = []
        st.rerun()

    st.sidebar.markdown(f"**Tests Queued:** {len(st.session_state.participant_tests)}")
    for idx, t in enumerate(st.session_state.participant_tests):
        st.sidebar.markdown(f"<div class='test-card'><b>{idx+1}. {t['type']}</b></div>", unsafe_allow_html=True)

    st.subheader("📋 Participant Metadata & Security PIN")
    col1, col2 = st.columns(2)

    with col1:
        participant_name = st.text_input("Participant Full Name", placeholder="e.g. John Evans", key="p_name")
        age_gender = st.text_input("Age / Gender", placeholder="e.g. 48 / Male", key="p_ag")

    with col2:
        assessment_date = st.date_input("Assessment Date", value=datetime.date.today(), key="p_date")
        patient_pin = st.text_input("Patient Secure PIN (4 digits)", type="password", placeholder="1234", key="p_pin")

    body_mass_height = st.text_input("Body Mass / Height", placeholder="e.g. 78 kg / 175 cm", key="p_bm")

    st.divider()

    assessment_type = st.selectbox(
        "Select Diagnostic Assessment Type",
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

    # Universal PDF Report Uploader for every test type
    uploaded_pdf = st.file_uploader(
        f"📎 Upload Official {assessment_type} PDF Report (Optional)", 
        type=["pdf"], 
        key=f"pdf_{assessment_type}"
    )

    test_payload_data = {}

    if assessment_type == "Autonomic/HRV":
        col_h1, col_h2 = st.columns(2)
        with col_h1:
            rmssd = st.text_input("RMSSD (ms)", placeholder="e.g. 45ms")
            sdnn = st.text_input("SDNN (ms)", placeholder="e.g. 52ms")
        with col_h2:
            resp_rate = st.text_input("Respiration Rate (breaths/min)", placeholder="e.g. 14")
            blood_pressure = st.text_input("Blood Pressure (mmHg)", placeholder="e.g. 120/80")

        test_payload_data = {
            "RMSSD": rmssd,
            "SDNN": sdnn,
            "Respiration Rate": resp_rate,
            "Blood Pressure": blood_pressure,
        }
    else:
        raw_notes = st.text_area(
            "Or Paste Raw Metrics / Clinical Observations",
            placeholder="Paste extracted data metrics, device outputs, or qualitative observations here...",
            height=100,
            key=f"notes_{assessment_type}"
        )
        test_payload_data = {"Raw Data / Notes": raw_notes}

    if st.button("➕ Add Assessment to Participant Profile", use_container_width=True):
        if not participant_name:
            st.warning("Please enter the participant's name before adding assessments.")
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

    st.subheader("🚀 AI Master Report Compilation & Google Cloud Publishing")
    st.markdown("Compile all queued tests, interrogate Gemini 3.8-flash for clinical interpretation, and securely sync to Google Cloud Firestore.")

    if st.button("Generate AI Master Report", type="primary", use_container_width=True):
        if not participant_name:
            st.warning("Please enter the participant's name.")
        elif not patient_pin or len(patient_pin) < 4:
            st.warning("Please enter a valid 4-digit security PIN for patient portal access.")
        elif len(st.session_state.participant_tests) == 0:
            st.warning("Please add at least one test assessment to the profile.")
        else:
            with st.spinner("🤖 Interrogating Gemini 3.8-flash and compiling master clinical report..."):
                try:
                    summary_context = f"Participant: {participant_name}, Age/Gender: {age_gender}, Metrics: {body_mass_height}\n"
                    for idx, t in enumerate(st.session_state.participant_tests):
                        summary_context += f"Test {idx+1}: {t['type']} -> Data: {json.dumps(t['data'])}\n"

                    ai_analysis_html = "<p>Clinical interpretation generated successfully.</p>"
                    
                    if gemini_client:
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
                        response = gemini_client.models.generate_content(
                            model="gemini-3.8-flash",
                            contents=prompt,
                        )
                        if response and response.text:
                            ai_analysis_html = response.text
                    else:
                        st.warning("Gemini client is uninitialized. Defaulting to standard clinical report structure.")

                    # Build individual test cards for HTML output
                    tests_html = ""
                    for idx, t in enumerate(st.session_state.participant_tests):
                        data_str = "".join([f"<li><b>{k}:</b> {v}</li>" for k, v in t['data'].items() if v])
                        has_pdf = "📎 Official PDF Report Attached" if t.get('pdf_b64') else ""
                        tests_html += f"""
                        <div style="background: #f8fafc; border-left: 4px solid #0f382b; padding: 15px; margin-bottom: 15px; border-radius: 4px;">
                            <h3 style="margin-top: 0; color: #0f382b;">Test #{idx+1}: {t['type']}</h3>
                            <p style="color: #2b6a52; font-size: 14px; font-weight: bold;">{has_pdf}</p>
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
                            <h2>🤖 Gemini 3.8-Flash Clinical Interpretation</h2>
                            {ai_analysis_html}
                        </div>

                        <h2>Completed Diagnostic Assessments</h2>
                        {tests_html}
                    </body>
                    </html>
                    """

                    # Sync to Google Cloud Firestore Database
                    if db:
                        doc_id = participant_name.strip().lower()
                        record = {
                            "name_lower": doc_id,
                            "name": participant_name,
                            "pin": patient_pin.strip(),
                            "assessment_date": str(assessment_date),
                            "tests_count": len(st.session_state.participant_tests),
                            "html_output": html_output
                        }
                        db.collection("longevity_reports").document(doc_id).set(record)
                        st.success("✨ AI Master Report generated and successfully synced to Google Cloud Firestore!")
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
    st.markdown("Welcome to the Chudleigh Health Hub client portal. Enter your full name and your secure 4-digit PIN provided by your clinician to access your records.")

    col_l1, col_l2 = st.columns(2)
    with col_l1:
        client_lookup = st.text_input("Your Full Name", placeholder="e.g. John Evans")
    with col_l2:
        client_pin = st.text_input("Your Secure 4-Digit PIN", type="password", placeholder="****")

    if st.button("Unlock My Healthspan Portal", type="primary", use_container_width=True):
        lookup_key = client_lookup.strip().lower()
        
        try:
            if not db:
                st.error("Google Cloud database connection unavailable.")
            else:
                doc_ref = db.collection("longevity_reports").document(lookup_key)
                doc = doc_ref.get()

                if doc.exists:
                    client_data = doc.to_dict()
                    
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
                    st.warning("No published reports found matching that name in the Google Cloud database.")
        
        except Exception as e:
            st.error(f"Error connecting to Google Cloud records: {e}")
