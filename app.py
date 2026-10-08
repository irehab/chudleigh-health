import os
import datetime
import json
import base64
import tempfile
import streamlit as st
from google.cloud import firestore
from google import genai
import stripe

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Chudleigh Health Hub - Longevity Portal",
    page_icon="🩺",
    layout="wide",
)

# --- STRIPE CONFIGURATION ---
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")

# --- BRAND STYLING ---
st.markdown(
    """
    <style>
    :root {
        --primary: #0f382b;
        --secondary: #2b6a52;
        --success: #10b981;
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
    .module-box {
        background-color: #f8fafc;
        border: 1px solid #cbd5e1;
        padding: 20px;
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
        <p>Health Autonomy &amp; Expert Clinical Longevity Portal</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# --- SESSION STATE INITIALIZATION ---
if "participant_tests" not in st.session_state:
    st.session_state.participant_tests = []
if "ta_mod1" not in st.session_state:
    st.session_state.ta_mod1 = ""
if "ta_mod2" not in st.session_state:
    st.session_state.ta_mod2 = ""
if "ta_mod3" not in st.session_state:
    st.session_state.ta_mod3 = ""
if "ta_master" not in st.session_state:
    st.session_state.ta_master = ""
if "ta_pe" not in st.session_state:
    st.session_state.ta_pe = ""
if "ta_plan_30" not in st.session_state:
    st.session_state.ta_plan_30 = ""
if "ta_plan_60" not in st.session_state:
    st.session_state.ta_plan_60 = ""
if "ta_plan_90" not in st.session_state:
    st.session_state.ta_plan_90 = ""

# --- GOOGLE CLOUD & GEMINI INITIALIZATIONS ---
@st.cache_resource
def init_firestore():
    try:
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
        st.session_state.ta_mod1 = ""
        st.session_state.ta_mod2 = ""
        st.session_state.ta_mod3 = ""
        st.session_state.ta_master = ""
        st.session_state.ta_pe = ""
        st.session_state.ta_plan_30 = ""
        st.session_state.ta_plan_60 = ""
        st.session_state.ta_plan_90 = ""
        st.rerun()

    st.sidebar.markdown(f"**Tests Queued:** {len(st.session_state.participant_tests)}")
    for idx, t in enumerate(st.session_state.participant_tests):
        st.sidebar.markdown(f"<div class='test-card'><b>{idx+1}. {t['type']}</b></div>", unsafe_allow_html=True)

    st.subheader("📋 Participant Metadata & Security PIN")
    col1, col2 = st.columns(2)

    with col1:
        participant_name = st.text_input("Participant Full Name", placeholder="e.g. John Evans", key="p_name")
        age_gender = st.text_input("Age / Gender / DOB", placeholder="e.g. 48 yrs / Male / 15/03/1978", key="p_ag")

    with col2:
        assessment_date = st.date_input("Assessment Date", value=datetime.date.today(), key="p_date")
        patient_pin = st.text_input("Patient Secure PIN (4 digits)", type="password", placeholder="1234", key="p_pin")

    body_mass_height = st.text_input("Body Mass / Height / BMI", placeholder="e.g. 78 kg / 175 cm / 25.4", key="p_bm")

    st.divider()

    assessment_type = st.selectbox(
        "Select Diagnostic Assessment Type",
        [
            "SpO2 / Pulse Oximetry (ViHealth)",
            "Tanita Body Composition (MC-780MA)",
            "Push-Up Assessment (VALD ForceDecks)",
            "Spirometry (Pulmonary Function)",
            "AGE Reader (Advanced Glycation End-Products)",
            "12-Lead ECG (Electrocardiogram)",
            "Autonomic / HRV (3-Min Rest, BP, Respiration)",
            "VALD ForceDecks - Sit-to-Stand",
            "VALD ForceDecks - Multi-Rep Squat",
            "VALD ForceDecks - Single Leg Stance / Balance",
            "VALD ForceDecks - Countermovement Jump (CMJ)",
            "VALD ForceDecks - Quiet Stand (Balance)",
        ],
    )

    st.subheader(f"📊 Input Data: {assessment_type}")

    uploaded_pdf = st.file_uploader(
        f"📎 Upload Official {assessment_type} PDF Report (Attached for Clinical Review)", 
        type=["pdf"], 
        key=f"pdf_{assessment_type}"
    )

    test_payload_data = {}
    pdf_bytes_content = None
    pdf_filename_str = None

    if uploaded_pdf is not None:
        pdf_bytes_content = uploaded_pdf.getvalue()
        pdf_filename_str = uploaded_pdf.name
        st.success(f"PDF Loaded Successfully: {pdf_filename_str} ({len(pdf_bytes_content) / 1024:.1f} KB)")

    if assessment_type == "SpO2 / Pulse Oximetry (ViHealth)":
        c1, c2, c3 = st.columns(3)
        with c1:
            spo2_high = st.text_input("Highest SpO2 (%)", "98")
            spo2_avg = st.text_input("Average SpO2 (%)", "96")
        with c2:
            spo2_low = st.text_input("Lowest SpO2 (%)", "94")
            pr_high = st.text_input("Highest Pulse Rate (BPM)", "59")
        with c3:
            pr_avg = st.text_input("Average Pulse Rate (BPM)", "54")
            pr_low = st.text_input("Lowest Pulse Rate (BPM)", "49")
        spo2_dur = st.text_input("Duration / Time Window", "00:04:48")
        test_payload_data = {
            "Highest SpO2": spo2_high, "Average SpO2": spo2_avg, "Lowest SpO2": spo2_low,
            "Highest Pulse Rate": pr_high, "Average Pulse Rate": pr_avg, "Lowest Pulse Rate": pr_low,
            "Duration": spo2_dur
        }

    elif assessment_type == "Tanita Body Composition (MC-780MA)":
        c1, c2, c3 = st.columns(3)
        with c1:
            t_weight = st.text_input("Weight (kg)", "78.0")
            t_fat_pct = st.text_input("Fat Percentage (%)", "18.5")
            t_ffm = st.text_input("Fat-Free Mass (kg)", "63.5")
        with c2:
            t_muscle = st.text_input("Muscle Mass (kg)", "60.2")
            t_tbw = st.text_input("Total Body Water (kg / %)", "48.2 kg (61.8%)")
            t_ecw_tbw = st.text_input("ECW / TBW Ratio", "0.378")
        with c3:
            t_visceral = st.text_input("Visceral Fat Rating", "6")
            t_met_age = st.text_input("Metabolic Age", "42")
            t_phase_angle = st.text_input("Phase Angle", "6.8°")
        test_payload_data = {"Weight": t_weight, "Fat %": t_fat_pct, "FFM": t_ffm, "Muscle Mass": t_muscle, "TBW": t_tbw, "ECW/TBW": t_ecw_tbw, "Visceral Fat": t_visceral, "Metabolic Age": t_met_age, "Phase Angle": t_phase_angle}

    elif assessment_type == "Push-Up Assessment (VALD ForceDecks)":
        c1, c2 = st.columns(2)
        with c1:
            pu_force = st.text_input("Peak Push Force (N)", "520 N")
            pu_impulse = st.text_input("Concentric Impulse (Ns)", "310 Ns")
        with c2:
            pu_sym = st.text_input("Left/Right Symmetry (%)", "96.5%")
            pu_power = st.text_input("Peak Power Output (W)", "680 W")
        test_payload_data = {"Peak Push Force": pu_force, "Concentric Impulse": pu_impulse, "L/R Symmetry": pu_sym, "Peak Power": pu_power}

    elif assessment_type == "Spirometry (Pulmonary Function)":
        c1, c2, c3 = st.columns(3)
        with c1:
            sp_fvc = st.text_input("FVC (L / % Pred)", "4.85 L (104%)")
            sp_fev1 = st.text_input("FEV1 (L / % Pred)", "3.92 L (102%)")
        with c2:
            sp_ratio = st.text_input("FEV1 / FVC Ratio (%)", "80.8%")
            sp_pef = st.text_input("PEF (L/m / % Pred)", "9.4 L/s (98%)")
        with c3:
            sp_fef2575 = st.text_input("FEF 25-75% (L/s)", "4.21 L/s")
            sp_fef75 = st.text_input("FEF 75% (L/s)", "1.85 L/s")
        test_payload_data = {"FVC": sp_fvc, "FEV1": sp_fev1, "FEV1/FVC Ratio": sp_ratio, "PEF": sp_pef, "FEF 25-75": sp_fef2575, "FEF 75": sp_fef75}

    elif assessment_type == "AGE Reader (Advanced Glycation End-Products)":
        c1, c2, c3 = st.columns(3)
        with c1:
            ag_bodyage = st.text_input("BodyAge", "44 yrs")
        with c2:
            ag_level = st.text_input("AGE Level Score", "1.9 AU")
        with c3:
            ag_var = st.text_input("Variance vs. Average", "-8%")
        test_payload_data = {"BodyAge": ag_bodyage, "AGE Level Score": ag_level, "Variance": ag_var}

    elif assessment_type == "12-Lead ECG (Electrocardiogram)":
        c1, c2, c3 = st.columns(3)
        with c1:
            ecg_hr = st.text_input("Heart Rate (BPM)", "58 BPM")
            ecg_pr = st.text_input("PR Interval (ms)", "162 ms")
        with c2:
            ecg_qrs = st.text_input("QRS Duration (ms)", "92 ms")
            ecg_qtc = st.text_input("QTc Interval (ms)", "410 ms")
        with c3:
            ecg_rhythm = st.text_input("Rhythm & Axis", "Normal Sinus Rhythm, Normal Axis")
        test_payload_data = {"Heart Rate": ecg_hr, "PR Interval": ecg_pr, "QRS Duration": ecg_qrs, "QTc Interval": ecg_qtc, "Rhythm & Axis": ecg_rhythm}

    elif assessment_type == "Autonomic / HRV (3-Min Rest, BP, Respiration)":
        c1, c2 = st.columns(2)
        with c1:
            hrv_rmssd = st.text_input("RMSSD (ms)", "52 ms")
            hrv_sdnn = st.text_input("SDNN (ms)", "64 ms")
        with c2:
            hrv_resp = st.text_input("Respiration Rate (breaths/min)", "12 breaths/min")
            hrv_bp = st.text_input("Blood Pressure (mmHg)", "118/76 mmHg")
        test_payload_data = {"RMSSD": hrv_rmssd, "SDNN": hrv_sdnn, "Respiration Rate": hrv_resp, "Blood Pressure": hrv_bp}

    elif assessment_type == "VALD ForceDecks - Sit-to-Stand":
        c1, c2 = st.columns(2)
        with c1:
            sts_force = st.text_input("Peak Concentric Force (N)", "780 N")
            sts_time = st.text_input("Transition Time (s)", "0.62
