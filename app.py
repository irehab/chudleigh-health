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

# --- SECURE URL ROUTING ---
query_params = st.query_params
is_patient_link = query_params.get("portal") == "true"

if is_patient_link:
    app_mode = "Secure Patient Mobile Portal"
    st.sidebar.subheader("🔒 Client Portal")
else:
    st.sidebar.header("Portal Navigation")
    app_mode = st.sidebar.selectbox(
        "Select Portal View",
        ["Clinician Dashboard", "Secure Patient Mobile Portal"]
    )
    st.sidebar.divider()

def get_supabase_client():
    url = "https://eyuvugzgxfawagpndmqo.supabase.co"
    key = "sb_publishable_hC0EacZHCbJ3wo-qKP2Q0A_sqn-_FC9"
    try:
        return create_client(url, key)
    except Exception:
        return None

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

    st.sidebar.markdown(f"**Tests Logged:** {len(st.session_state.participant_tests)}")

    st.subheader("📋 Participant Metadata & Security PIN")
    col1, col2 = st.columns(2)

    with col1:
        participant_name = st.text_input("Participant Name", placeholder="e.g. John Doe", key="p_name")
        age_gender = st.text_input("Age / Gender", placeholder="e.g. 48 / Male", key="p_ag")

    with col2:
        assessment_date = st.date_input("Assessment Date", value=datetime.date.today(), key="p_date")
        patient_pin = st.text_input("Patient Secure PIN (4 digits)", type="password", placeholder="1234", key="p_pin")

    body_mass_height = st.text_input("Body Mass / Height", placeholder="78 kg / 175 cm", key="p_bm")

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

    uploaded_pdf = st.file_uploader(f"📎 Upload Official {assessment_type} PDF Report (Optional)", type=["pdf"], key=f"pdf_{assessment_type}")
    raw_notes = st.text_area("Metrics / Notes", placeholder="Paste metrics or notes here...", height=100, key=f"notes_{assessment_type}")

    if st.button("➕ Add Test to Profile", use_container_width=True):
        if participant_name:
            pdf_b64 = base64.b64encode(uploaded_pdf.getvalue()).decode("utf-8") if uploaded_pdf else None
            st.session_state.participant_tests.append({
                "type": assessment_type,
                "data": {"Notes": raw_notes},
                "pdf_b64": pdf_b64
            })
            st.success(f"Added {assessment_type} successfully!")
            st.rerun()
        else:
            st.warning("Please enter participant name.")

    st.divider()

    st.subheader("🚀 AI Master Report Compilation")

    if st.button("Generate AI Master Report", type="primary", use_container_width=True):
        if not participant_name:
            st.warning("Please enter participant name.")
        elif not patient_pin or len(patient_pin) < 4:
            st.warning("Please enter a valid 4-digit PIN.")
        elif len(st.session_state.participant_tests) == 0:
            st.warning("Please add at least one test.")
        else:
            summary_context = f"Participant: {participant_name}, Age/Gender: {age_gender}, Metrics: {body_mass_height}\n"
            for idx, t in enumerate(st.session_state.participant_tests):
                summary_context += f"Test {idx+1}: {t['type']} -> {json.dumps(t['data'])}\n"

            # 1. Test Gemini AI Step Independently
            ai_analysis_html = "<p>Clinical interpretation fallback generated.</p>"
            with st.spinner("🤖 Step 1/2: Querying Gemini AI..."):
                try:
                    gemini = get_gemini_client()
                    if not gemini:
                        st.error("Gemini client initialization failed. Check API key.")
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
                except Exception as e:
                    st.error(f"❌ GEMINI API ERROR: {e}")

            html_output = f"""
            <div>
                <h2>AI Clinical Interpretation</h2>
                {ai_analysis_html}
            </div>
            """

            # 2. Test Supabase Sync Step Independently
            with st.spinner("☁️ Step 2/2: Syncing to Supabase Cloud..."):
                try:
                    db = get_supabase_client()
                    if not db:
                        st.warning("Supabase client could not be created.")
                    else:
                        record = {
                            "name_lower": participant_name.strip().lower(),
                            "name": participant_name,
                            "pin": patient_pin.strip(),
                            "assessment_date": str(assessment_date),
                            "tests_count": len(st.session_state.participant_tests),
                            "html_output": html_output
                        }
                        db.table("longevity_reports").upsert(record, on_conflict="name_lower").execute()
                        st.success("✨ Successfully synced to Supabase Cloud Database!")
                except Exception as e:
                    st.error(f"❌ SUPABASE DATABASE ERROR: {e}")

            st.download_button(
                label="📥 Download Master Report",
                data=html_output,
                file_name="report.html",
                mime="text/html",
            )
            st.components.v1.html(html_output, height=600, scrolling=True)

# ==========================================
# VIEW 2: SECURE PATIENT MOBILE PORTAL
# ==========================================
elif app_mode == "Secure Patient Mobile Portal":
    st.subheader("📱 Participant Companion Portal")
    client_lookup = st.text_input("Your Full Name", placeholder="e.g. John Doe")
    client_pin = st.text_input("Your Secure 4-Digit PIN", type="password", placeholder="****")

    if st.button("Unlock Portal", type="primary", use_container_width=True):
        try:
            db = get_supabase_client()
            if db:
                response = db.table("longevity_reports").select("*").eq("name_lower", client_lookup.strip().lower()).execute()
                data = response.data
                if data and data[0]["pin"] == client_pin.strip():
                    st.success("Access Granted!")
                    st.components.v1.html(data[0]['html_output'], height=600, scrolling=True)
                else:
                    st.error("Invalid name or PIN.")
        except Exception as e:
            st.error(f"❌ PATIENT PORTAL ERROR: {e}")
