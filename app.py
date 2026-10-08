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
    .history-box {
        background-color: #eff6ff;
        border: 1px solid #bfdbfe;
        padding: 16px;
        border-radius: 8px;
        margin-bottom: 20px;
        color: #1e3a8a;
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
        <p>Health Autonomy &amp; Expert Clinical Longevity Portal (Longitudinal Edition)</p>
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

    # --- LONGITUDINAL HISTORY CHECK ---
    previous_scan = None
    if participant_name and db:
        try:
            c_key = participant_name.strip().lower()
            scans_ref = db.collection("longevity_reports").document(c_key).collection("scans")
            past_docs = list(scans_ref.order_by("assessment_date", direction=firestore.Query.DESCENDING).limit(1).stream())
            if past_docs:
                previous_scan = past_docs[0].to_dict()
                st.markdown(
                    f"""
                    <div class='history-box'>
                        <b>📈 Longitudinal History Detected:</b> Found previous assessment on <b>{previous_scan.get('assessment_date')}</b> with {previous_scan.get('tests_count')} test(s) on file. Comparative progress analysis will be integrated into the synthesis.
                    </div>
                    """,
                    unsafe_allow_html=True
                )
        except Exception:
            pass

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
            sts_time = st.text_input("Transition Time (s)", "0.62 s")
        with c2:
            sts_rfd = st.text_input("Concentric RFD (N/s)", "1450 N/s")
            sts_asym = st.text_input("Limb Asymmetry (%)", "4.2%")
        test_payload_data = {"Peak Concentric Force": sts_force, "Transition Time": sts_time, "Concentric RFD": sts_rfd, "Limb Asymmetry": sts_asym}

    elif assessment_type == "VALD ForceDecks - Multi-Rep Squat":
        c1, c2 = st.columns(2)
        with c1:
            sq_force = st.text_input("Peak Force (N)", "849 N")
            sq_c_imp = st.text_input("Concentric Impulse (Ns)", "412 Ns")
        with c2:
            sq_e_imp = st.text_input("Eccentric Impulse (Ns)", "405 Ns")
            sq_asym = st.text_input("Left/Right Asymmetry (%)", "13.0%")
        test_payload_data = {"Peak Force": sq_force, "Concentric Impulse": sq_c_imp, "Eccentric Impulse": sq_e_imp, "L/R Asymmetry": sq_asym}

    elif assessment_type == "VALD ForceDecks - Single Leg Stance / Balance":
        c1, c2 = st.columns(2)
        with c1:
            sls_l_sway = st.text_input("Left Sway Velocity (mm/s)", "14.2 mm/s")
            sls_r_sway = st.text_input("Right Sway Velocity (mm/s)", "12.8 mm/s")
        with c2:
            sls_l_ell = st.text_input("Left Ellipse Area (mm²)", "185 mm²")
            sls_r_ell = st.text_input("Right Ellipse Area (mm²)", "160 mm²")
        test_payload_data = {"Left Sway Velocity": sls_l_sway, "Right Sway Velocity": sls_r_sway, "Left Ellipse Area": sls_l_ell, "Right Ellipse Area": sls_r_ell}

    elif assessment_type == "VALD ForceDecks - Countermovement Jump (CMJ)":
        c1, c2, c3 = st.columns(3)
        with c1:
            cmj_height = st.text_input("Jump Height (cm)", "34.5 cm")
            cmj_power = st.text_input("Peak Power / Mass (W/kg)", "48.2 W/kg")
        with c2:
            cmj_rsi = st.text_input("Modified RSI", "0.58")
            cmj_asym = st.text_input("Peak Force Asymmetry (%)", "3.8%")
        with c3:
            cmj_eforce = st.text_input("Eccentric Peak Force (N)", "1420 N")
            cmj_erfd = st.text_input("Eccentric RFD (N/s)", "4200 N/s")
        test_payload_data = {"Jump Height": cmj_height, "Peak Power/Mass": cmj_power, "Modified RSI": cmj_rsi, "Peak Force Asymmetry": cmj_asym, "Eccentric Peak Force": cmj_eforce, "Eccentric RFD": cmj_erfd}

    elif assessment_type == "VALD ForceDecks - Quiet Stand (Balance)":
        c1, c2 = st.columns(2)
        with c1:
            qs_path = st.text_input("Total Path Length (mm)", "310 mm")
            qs_vel = st.text_input("Mean Velocity (mm/s)", "5.2 mm/s")
        with c2:
            qs_ap = st.text_input("AP Sway Range (mm)", "24.5 mm")
            qs_asym = st.text_input("Weight Distribution Asymmetry (%)", "2.1%")
        test_payload_data = {"Total Path Length": qs_path, "Mean Velocity": qs_vel, "AP Sway Range": qs_ap, "Weight Distribution Asymmetry": qs_asym}

    else:
        raw_notes = st.text_area("Clinical Observations / Metrics", placeholder="Enter notes or raw data...")
        test_payload_data = {"Raw Data / Notes": raw_notes}

    if st.button("➕ Add Assessment to Participant Profile", use_container_width=True):
        if not participant_name:
            st.warning("Please enter the participant's name before adding assessments.")
        else:
            pdf_b64 = None
            if pdf_bytes_content is not None:
                pdf_b64 = base64.b64encode(pdf_bytes_content).decode("utf-8")

            st.session_state.participant_tests.append({
                "type": assessment_type,
                "data": test_payload_data,
                "pdf_filename": pdf_filename_str,
                "pdf_b64": pdf_b64
            })
            st.success(f"Successfully added {assessment_type} to {participant_name}'s profile!")
            st.rerun()

    st.divider()

    # ==========================================
    # MODULAR CLINICAL GENERATION ENGINES
    # ==========================================
    st.subheader("🧩 Expert Clinical Review & Synthesis Engine")
    st.markdown("Compile, review, and refine clinical evaluations by physiological domain.")

    def upload_pdf_to_gemini(pdf_b64_str):
        if not pdf_b64_str or not gemini_client:
            return None
        try:
            pdf_bytes = base64.b64decode(pdf_b64_str)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(pdf_bytes)
                tmp_path = tmp.name
            
            uploaded_file = gemini_client.files.upload(
                file=tmp_path,
                config={'mime_type': 'application/pdf'}
            )
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            return uploaded_file
        except Exception:
            return None

    # Module 1: Cardiorespiratory
    with st.container():
        st.markdown("### 🫀 Module 1: Cardiorespiratory & Autonomic")
        cardio_tests = [t for t in st.session_state.participant_tests if any(x in t['type'] for x in ["SpO2", "Spirometry", "ECG", "Autonomic / HRV"])]
        
        if st.button("Draft Cardiorespiratory Review", use_container_width=True, key="btn_mod1"):
            if not participant_name:
                st.warning("Please enter participant name.")
            elif len(cardio_tests) == 0:
                st.info("No cardiorespiratory tests queued yet.")
            else:
                with st.spinner("Synthesizing cardiorespiratory clinical review..."):
                    try:
                        payload = []
                        context_str = f"Participant: {participant_name}, Age/Gender: {age_gender}\n"
                        for t in cardio_tests:
                            context_str += f"Test: {t['type']} -> Metrics: {json.dumps(t['data'])}\n"
                            f_ref = upload_pdf_to_gemini(t.get('pdf_b64'))
                            if f_ref:
                                payload.append(f_ref)
                        
                        prompt = (
                            "You are an expert clinical cardiologist and longevity physician at Chudleigh Health Hub. "
                            "Carefully inspect the attached official PDF reports and structured metrics for Cardiorespiratory and Autonomic function. "
                            "Write a rigorous, exhaustive, and professional clinical breakdown authored strictly by Chudleigh Health Hub clinical analytics, formatted in clean HTML (h3, p, li tags). "
                            "Do not mention any AI models, automated assistants, or third-party tools.\n\n"
                            f"Patient Data:\n{context_str}"
                        )
                        payload.append(prompt)
                        res = gemini_client.models.generate_content(model="gemini-3.8-flash", contents=payload)
                        if res and res.text:
                            st.session_state.ta_mod1 = res.text
                            st.success("Cardiorespiratory review drafted successfully!")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Generation error: {e}")

        st.text_area("Edit Cardiorespiratory Clinical Review (HTML)", height=180, key="ta_mod1")

    st.divider()

    # Module 2: Body Composition & Metabolic Age
    with st.container():
        st.markdown("### ⚖️ Module 2: Body Composition & Metabolic Age")
        metabolic_tests = [t for t in st.session_state.participant_tests if any(x in t['type'] for x in ["Tanita", "AGE Reader"])]
        
        if st.button("Draft Body Comp & Metabolic Review", use_container_width=True, key="btn_mod2"):
            if not participant_name:
                st.warning("Please enter participant name.")
            elif len(metabolic_tests) == 0:
                st.info("No body composition or metabolic tests queued yet.")
            else:
                with st.spinner("Synthesizing metabolic and body composition clinical review..."):
                    try:
                        payload = []
                        context_str = f"Participant: {participant_name}, Age/Gender: {age_gender}\n"
                        for t in metabolic_tests:
                            context_str += f"Test: {t['type']} -> Metrics: {json.dumps(t['data'])}\n"
                            f_ref = upload_pdf_to_gemini(t.get('pdf_b64'))
                            if f_ref:
                                payload.append(f_ref)
                        
                        prompt = (
                            "You are an expert clinical metabolic specialist and longevity physician at Chudleigh Health Hub. "
                            "Carefully inspect the attached official PDF reports and structured metrics for Body Composition and AGE Reader metrics. "
                            "Write a rigorous, exhaustive, and professional clinical breakdown authored strictly by Chudleigh Health Hub clinical analytics, formatted in clean HTML (h3, p, li tags). "
                            "Do not mention any AI models, automated assistants, or third-party tools.\n\n"
                            f"Patient Data:\n{context_str}"
                        )
                        payload.append(prompt)
                        res = gemini_client.models.generate_content(model="gemini-3.8-flash", contents=payload)
                        if res and res.text:
                            st.session_state.ta_mod2 = res.text
                            st.success("Metabolic review drafted successfully!")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Generation error: {e}")

        st.text_area("Edit Body Comp & Metabolic Clinical Review (HTML)", height=180, key="ta_mod2")

    st.divider()

    # Module 3: Biomechanical & Neuromuscular Function
    with st.container():
        st.markdown("### 🏋️ Module 3: Biomechanical & Neuromuscular Function")
        biomech_tests = [t for t in st.session_state.participant_tests if "VALD" in t['type'] or "Push-Up" in t['type']]
        
        if st.button("Draft Biomechanical Review", use_container_width=True, key="btn_mod3"):
            if not participant_name:
                st.warning("Please enter participant name.")
            elif len(biomech_tests) == 0:
                st.info("No biomechanical or force plate tests queued yet.")
            else:
                with st.spinner("Synthesizing biomechanical and neuromuscular review..."):
                    try:
                        payload = []
                        context_str = f"Participant: {participant_name}, Age/Gender: {age_gender}\n"
                        for t in biomech_tests:
                            context_str += f"Test: {t['type']} -> Metrics: {json.dumps(t['data'])}\n"
                            f_ref = upload_pdf_to_gemini(t.get('pdf_b64'))
                            if f_ref:
                                payload.append(f_ref)
                        
                        prompt = (
                            "You are an expert clinical biomechanist and sports physiologist at Chudleigh Health Hub. "
                            "Carefully inspect the attached official PDF reports and structured metrics for Biomechanical and Neuromuscular Function. "
                            "Write a rigorous, exhaustive, and professional clinical breakdown authored strictly by Chudleigh Health Hub clinical analytics, formatted in clean HTML (h3, p, li tags). "
                            "Do not mention any AI models, automated assistants, or third-party tools.\n\n"
                            f"Patient Data:\n{context_str}"
                        )
                        payload.append(prompt)
                        res = gemini_client.models.generate_content(model="gemini-3.8-flash", contents=payload)
                        if res and res.text:
                            st.session_state.ta_mod3 = res.text
                            st.success("Biomechanical review drafted successfully!")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Generation error: {e}")

        st.text_area("Edit Biomechanical Clinical Review (HTML)", height=180, key="ta_mod3")

    st.divider()

    # Module 4: Master Synthesis & Plain English Breakdown
    with st.container():
        st.subheader("🎯 Module 4: Master Synthesis & Longitudinal Progress Analysis")
        st.markdown("Synthesize all modules, evaluate historical progress deltas against previous scans, and generate patient-friendly coaching guides.")

        col_gen1, col_gen2 = st.columns(2)
        with col_gen1:
            if st.button("✨ Draft Master Executive Synthesis & Delta Analysis", use_container_width=True, key="btn_master"):
                with st.spinner("Synthesizing master executive review and tracking longitudinal progress..."):
                    try:
                        history_context = ""
                        if previous_scan:
                            history_context = (
                                f"\n\nPREVIOUS SCAN HISTORY (Date: {previous_scan.get('assessment_date')}):\n"
                                f"Previous Metrics / Summary: {json.dumps(previous_scan.get('tests', []))}\n"
                                f"Previous Master Summary: {previous_scan.get('master_html', 'None')}\n"
                            )

                        master_prompt = (
                            "You are the lead longevity physician at Chudleigh Health Hub. "
                            "Synthesize the following modular clinical evaluations into a cohesive, overarching executive clinical review authored strictly by Chudleigh Health Hub clinical analytics, formatted in clean HTML (h3, p, li tags). "
                            f"{history_context}\n"
                            "If historical scan data is provided above, you MUST include a dedicated subsection titled '📈 Longitudinal Progress & Delta Analysis' detailing how metrics have shifted since the last scan, evaluating the efficacy of the previous period's focus areas.\n\n"
                            f"Current Cardiorespiratory Module:\n{st.session_state.ta_mod1}\n\n"
                            f"Current Body Composition & Metabolic Module:\n{st.session_state.ta_mod2}\n\n"
                            f"Current Biomechanical Module:\n{st.session_state.ta_mod3}"
                        )
                        res = gemini_client.models.generate_content(model="gemini-3.8-flash", contents=master_prompt)
                        if res and res.text:
                            st.session_state.ta_master = res.text
                            st.success("Master executive synthesis & longitudinal delta drafted!")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Generation error: {e}")

        with col_gen2:
            if st.button("🗣️ Draft Plain English Patient Breakdown", use_container_width=True, key="btn_pe"):
                with st.spinner("Drafting plain English coaching guide..."):
                    try:
                        pe_prompt = (
                            "You are an empathetic longevity physician and health coach at Chudleigh Health Hub. "
                            "Based on the clinical findings and progress deltas below, write an encouraging, crystal-clear, jargon-free summary directly addressed to the participant as authored by Chudleigh Health Hub clinicians. "
                            "Format the output in clean HTML (h3, p, li tags) covering exactly these three sections:\n"
                            "1. What this all means for you & your progress over time (The big picture summary)\n"
                            "2. What is good and why this will help (Positive reinforcement of strong metrics or improvements)\n"
                            "3. What you need to work on next (Clear, actionable, prioritized focus areas)\n\n"
                            f"Master Clinical Summary:\n{st.session_state.ta_master}"
                        )
                        res = gemini_client.models.generate_content(model="gemini-3.8-flash", contents=pe_prompt)
                        if res and res.text:
                            st.session_state.ta_pe = res.text
                            st.success("Plain English breakdown drafted!")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Generation error: {e}")

        st.text_area("Edit Master Executive Synthesis (HTML)", height=220, key="ta_master")
        st.text_area("Edit Plain English Breakdown (HTML)", height=220, key="ta_pe")

    st.divider()

    # ==========================================
    # STEP 1 & 2: ACTION PLAN BUILDER & UNLOCK CONTROLS
    # ==========================================
    st.subheader("🚀 Step 1 & 2: Tiered Action Plans & Portal Access Control")
    st.markdown("Configure tier pricing, generate progressive roadmaps, and select which tiers are unlocked for the participant.")

    col_p1, col_p2, col_p3 = st.columns(3)
    with col_p1:
        price_30 = st.text_input("30-Day Tier Price (£)", value="49", key="p_30")
    with col_p2:
        price_60 = st.text_input("60-Day Tier Price (£)", value="89", key="p_60")
    with col_p3:
        price_90 = st.text_input("90-Day Tier Price (£)", value="129", key="p_90")

    if st.button("✨ Draft Prioritized 30/60/90-Day Tiered Plans", use_container_width=True, key="btn_tier_plans"):
        if not participant_name:
            st.warning("Please enter participant name.")
        elif not st.session_state.ta_master:
            st.warning("Please generate the Master Executive Synthesis first.")
        else:
            with st.spinner("Building prioritized tiered action plans based on longitudinal shifts..."):
                try:
                    plan_prompt = (
                        "You are an expert longevity physician and health strategist at Chudleigh Health Hub. "
                        "Based on the master clinical review and longitudinal progress below, build a progressive 30-Day, 60-Day, and 90-Day Action Plan. "
                        "Prioritize the biggest clinical vulnerabilities or delta shifts that need attention first in the 30-day plan, "
                        "followed by secondary integrations in the 60-day plan, and long-term fine-tuning in the 90-day plan. "
                        "Return your response strictly as a JSON object with three keys: 'plan_30', 'plan_60', and 'plan_90'. "
                        "Each value must be formatted in clean HTML (using h3, p, and li tags).\n\n"
                        f"Master Clinical Review:\n{st.session_state.ta_master}"
                    )
                    res = gemini_client.models.generate_content(
                        model="gemini-3.8-flash", 
                        contents=plan_prompt,
                        config={"response_mime_type": "application/json"}
                    )
                    if res and res.text:
                        plan_data = json.loads(res.text)
                        st.session_state.ta_plan_30 = plan_data.get("plan_30", "")
                        st.session_state.ta_plan_60 = plan_data.get("plan_60", "")
                        st.session_state.ta_plan_90 = plan_data.get("plan_90", "")
                        st.success("Tiered 30/60/90-day action plans drafted successfully!")
                        st.rerun()
                except Exception as e:
                    st.error(f"Error generating tiered plans: {e}")

    st.markdown("#### 30-Day Foundation Sprint (High-Priority Fixes)")
    st.text_area("Edit 30-Day Plan (HTML)", height=180, key="ta_plan_30")

    st.markdown("#### 60-Day Progression Plan (Secondary Integration)")
    st.text_area("Edit 60-Day Plan (HTML)", height=180, key="ta_plan_60")

    st.markdown("#### 90-Day Mastery Plan (Long-Term Optimization)")
    st.text_area("Edit 90-Day Plan (HTML)", height=180, key="ta_plan_90")

    st.markdown("---")
    st.markdown("#### 🔓 Patient Portal Unlock Tiers")
    unlock_30_flag = st.checkbox("Unlock 30-Day Plan in Patient Portal", value=True, key="chk_unl_30")
    unlock_60_flag = st.checkbox("Unlock 60-Day Plan in Patient Portal", value=False, key="chk_unl_60")
    unlock_90_flag = st.checkbox("Unlock 90-Day Plan in Patient Portal", value=False, key="chk_unl_90")

    st.divider()

    # --- PUBLISH & SYNC TO GOOGLE CLOUD (LONGITUDINAL SUBCOLLECTION) ---
    if st.button("💾 Publish & Sync New Scan & Tiered Plans to Cloud", type="primary", use_container_width=True):
        if not participant_name:
            st.warning("Please ensure participant name is entered.")
        elif not patient_pin or len(patient_pin) < 4:
            st.warning("Please enter a valid 4-digit security PIN.")
        else:
            try:
                tests_html = ""
                for idx, t in enumerate(st.session_state.participant_tests):
                    data_str = "".join([f"<li><b>{k}:</b> {v}</li>" for k, v in t['data'].items() if v])
                    filename = t.get('pdf_filename', 'Diagnostic_Report.pdf')
                    pdf_note_box = ""
                    if filename:
                        pdf_note_box = (
                            '<div style="margin-top: 15px; background: #f0fdf4; border: 1px solid #bbf7d0; padding: 15px; border-radius: 8px;">'
                            f'<p style="font-size: 13px; color: #166534; margin: 0;"><b>Official Diagnostic Report Attached:</b> {filename} (Reviewed and synthesized by Chudleigh Health Hub clinicians)</p>'
                            '</div>'
                        )

                    test_type = t['type']
                    test_num = idx + 1
                    fallback_li = "<li>Metrics extracted directly via clinical inspection.</li>"
                    list_content = data_str if data_str else fallback_li

                    tests_html += (
                        '<div style="background: #f8fafc; border-left: 4px solid #0f382b; padding: 20px; margin-bottom: 25px; border-radius: 8px; border: 1px solid #e2e8f0;">'
                        f'<h3 style="margin-top: 0; color: #0f382b; font-size: 19px;">Test #{test_num}: {test_type}</h3>'
                        f'<ul style="margin-bottom: 15px; color: #334155; padding-left: 20px;">{list_content}</ul>'
                        f'{pdf_note_box}'
                        '</div>'
                    )

                html_template = """
                <!DOCTYPE html>
                <html lang="en">
                <head>
                    <meta charset="utf-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <title>Chudleigh Health Hub - Expert Clinical Longevity Report</title>
                    <style>
                        :root {{
                            --primary-color: #0f382b;
                            --secondary-color: #2b6a52;
                            --success-color: #10b981;
                            --bg-color: #f8fafc;
                            --card-bg: #ffffff;
                            --text-main: #1e293b;
                            --text-muted: #64748b;
                            --border-color: #e2e8f0;
                        }}
                        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: var(--bg-color); color: var(--text-main); line-height: 1.6; margin: 0; padding: 20px; }}
                        .report-container {{ max-width: 950px; margin: 0 auto; background: var(--card-bg); border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.05); overflow: hidden; border: 1px solid var(--border-color); }}
                        .header {{ background-color: var(--primary-color); color: white; padding: 30px; text-align: center; }}
                        .header h1 {{ margin: 0 0 5px 0; font-size: 24px; color: white; }}
                        .header p {{ margin: 0; color: #94a3b8; font-size: 14px; text-transform: uppercase; letter-spacing: 1px; }}
                        .content {{ padding: 30px; }}
                        .patient-meta {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; background: #f1f5f9; padding: 20px; border-radius: 8px; margin-bottom: 30px; }}
                        .meta-item label {{ display: block; font-size: 12px; color: var(--text-muted); text-transform: uppercase; font-weight: 600; }}
                        .meta-item span {{ font-size: 16px; font-weight: 700; color: var(--primary-color); }}
                        
                        .view-switcher {{ display: flex; justify-content: center; gap: 10px; margin-bottom: 25px; background: #e2e8f0; padding: 6px; border-radius: 10px; flex-wrap: wrap; }}
                        .view-btn {{ background: transparent; border: none; padding: 12px 20px; font-size: 15px; font-weight: 700; color: var(--text-muted); border-radius: 8px; cursor: pointer; transition: all 0.2s ease; }}
                        .view-btn.active {{ background: var(--primary-color); color: white; box-shadow: 0 2px 8px rgba(0,0,0,0.15); }}

                        .results-card {{ background: linear-gradient(to bottom right, #f0fdf4, #ecfdf5); border: 2px solid var(--success-color); border-radius: 10px; padding: 25px; margin-bottom: 30px; }}
                        .results-card h2 {{ margin-top: 0; color: var(--secondary-color); font-size: 20px; }}
                        .plain-english-card {{ background: linear-gradient(to bottom right, #f8fafc, #f1f5f9); border: 2px solid var(--secondary-color); border-radius: 10px; padding: 25px; margin-bottom: 30px; }}
                        .plain-english-card h2 {{ margin-top: 0; color: var(--primary-color); font-size: 20px; }}
                        .plan-card {{ background: linear-gradient(to bottom right, #fffbeb, #fef3c7); border: 2px solid #f59e0b; border-radius: 10px; padding: 25px; margin-bottom: 30px; }}
                        .plan-card h2 {{ margin-top: 0; color: #b45309; font-size: 20px; }}
                        .interpretation-text {{ font-size: 15px; background: rgba(255, 255, 255, 0.9); padding: 20px; border-radius: 8px; margin-top: 20px; }}
                        .footer {{ text-align: center; padding: 20px; background: #f1f5f9; font-size: 12px; color: var(--text-muted); border-top: 1px solid var(--border-color); }}
                    </style>
                    <script>
                        function switchView(viewName) {{
                            const clinicalCard = document.getElementById('card-clinical');
                            const plainCard = document.getElementById('card-plain');
                            const planCard = document.getElementById('card-plan');
                            const btnClinical = document.getElementById('btn-clinical');
                            const btnPlain = document.getElementById('btn-plain');
                            const btnPlan = document.getElementById('btn-plan');

                            clinicalCard.style.display = 'none';
                            plainCard.style.display = 'none';
                            planCard.style.display = 'none';
                            btnClinical.classList.remove('active');
                            btnPlain.classList.remove('active');
                            btnPlan.classList.remove('active');

                            if (viewName === 'clinical') {{
                                clinicalCard.style.display = 'block';
                                btnClinical.classList.add('active');
                            }} else if (viewName === 'plain') {{
                                plainCard.style.display = 'block';
                                btnPlain.classList.add('active');
                            }} else if (viewName === 'plan') {{
                                planCard.style.display = 'block';
                                btnPlan.classList.add('active');
                            }}
                        }}
                    </script>
                </head>
                <body>
                    <div class="report-container">
                        <div class="header">
                            <h1>Chudleigh Health Hub</h1>
                            <p>Expert Clinical Review &bull; Longevity Master Report</p>
                        </div>
                        <div class="content">
                            <div class="patient-meta">
                                <div class="meta-item"><label>Participant Name</label><span>{participant_name}</span></div>
                                <div class="meta-item"><label>Age / Gender</label><span>{age_gender}</span></div>
                                <div class="meta-item"><label>Assessment Date</label><span>{assessment_date}</span></div>
                                <div class="meta-item"><label>Body Mass / Metrics</label><span>{body_mass_height}</span></div>
                            </div>
                            
                            <div class="view-switcher">
                                <button onclick="switchView('clinical')" id="btn-clinical" class="view-btn active">🩺 Professional Clinical View</button>
                                <button onclick="switchView('plain')" id="btn-plain" class="view-btn">🗣️ Plain English Breakdown</button>
                                <button onclick="switchView('plan')" id="btn-plan" class="view-btn">🚀 30/60/90-Day Action Plans</button>
                            </div>

                            <div id="card-clinical" class="results-card">
                                <h2>🎯 Master Executive Clinical Review &amp; Longitudinal Progress</h2>
                                <div class="interpretation-text">
                                    <h3 style="color: #0f382b; border-bottom: 2px solid #bbf7d0; padding-bottom: 5px;">Executive Summary &amp; Progress Delta</h3>
                                    {master_html}
                                    <h3 style="color: #0f382b; border-bottom: 2px solid #bbf7d0; padding-bottom: 5px; margin-top: 30px;">🫀 Cardiorespiratory &amp; Autonomic Analysis</h3>
                                    {mod1_html}
                                    <h3 style="color: #0f382b; border-bottom: 2px solid #bbf7d0; padding-bottom: 5px; margin-top: 30px;">⚖️ Body Composition &amp; Metabolic Age Analysis</h3>
                                    {mod2_html}
                                    <h3 style="color: #0f382b; border-bottom: 2px solid #bbf7d0; padding-bottom: 5px; margin-top: 30px;">🏋️ Biomechanical &amp; Neuromuscular Analysis</h3>
                                    {mod3_html}
                                </div>
                            </div>

                            <div id="card-plain" class="plain-english-card" style="display: none;">
                                <h2>🗣️ What This Means For You &amp; Your Action Plan</h2>
                                <div class="interpretation-text">{plain_english_html}</div>
                            </div>

                            <div id="card-plan" class="plan-card" style="display: none;">
                                <h2>🚀 Your Tailored 30 / 60 / 90-Day Longevity Roadmaps</h2>
                                <!-- PLAN_SECTION_START -->
                                <div class="interpretation-text">
                                    {p30_html}
                                    {p60_html}
                                    {p90_html}
                                </div>
                                <!-- PLAN_SECTION_END -->
                            </div>

                            <h2 style="color: #0f382b; font-size: 20px; margin-bottom: 15px;">Completed Diagnostic Assessments ({tests_count})</h2>
                            {tests_html}
                        </div>
                        <div class="footer">&copy; 2026 Chudleigh Health Hub. Expert Clinical Longevity Platform. All rights reserved.</div>
                    </div>
                </body>
                </html>
                """

                p30_content = f'<h3 style="color: #b45309; border-bottom: 2px solid #fde68a; padding-bottom: 5px;">30-Day Foundation Sprint</h3>{st.session_state.ta_plan_30}' if unlock_30_flag else f'<div style="background: #fff; border: 2px dashed #f59e0b; padding: 20px; border-radius: 8px; text-align: center;"><h3 style="color: #b45309; margin-top: 0;">🔒 30-Day Foundation Sprint (Locked)</h3><p style="color: #475569; font-size: 14px;">Unlock this foundational sprint for <b>£{price_30}</b>.</p></div>'
                p60_content = f'<h3 style="color: #b45309; border-bottom: 2px solid #fde68a; padding-bottom: 5px; margin-top: 30px;">60-Day Progression Plan</h3>{st.session_state.ta_plan_60}' if unlock_60_flag else f'<div style="background: #fff; border: 2px dashed #f59e0b; padding: 20px; border-radius: 8px; text-align: center; margin-top: 20px;"><h3 style="color: #b45309; margin-top: 0;">🔒 60-Day Progression Plan (Locked)</h3><p style="color: #475569; font-size: 14px;">Unlock this progression tier for <b>£{price_60}</b>.</p></div>'
                p90_content = f'<h3 style="color: #b45309; border-bottom: 2px solid #fde68a; padding-bottom: 5px; margin-top: 30px;">90-Day Mastery Plan</h3>{st.session_state.ta_plan_90}' if unlock_90_flag else f'<div style="background: #fff; border: 2px dashed #f59e0b; padding: 20px; border-radius: 8px; text-align: center; margin-top: 20px;"><h3 style="color: #b45309; margin-top: 0;">🔒 90-Day Mastery Plan (Locked)</h3><p style="color: #475569; font-size: 14px;">Unlock the complete 90-day roadmap for <b>£{price_90}</b>.</p></div>'

                final_html_output = html_template.format(
                    participant_name=participant_name,
                    age_gender=age_gender if age_gender else 'Not specified',
                    assessment_date=str(assessment_date),
                    body_mass_height=body_mass_height if body_mass_height else 'Not specified',
                    master_html=st.session_state.ta_master if st.session_state.ta_master else '<p>Master summary pending.</p>',
                    mod1_html=st.session_state.ta_mod1 if st.session_state.ta_mod1 else '<p>Cardiorespiratory module pending.</p>',
                    mod2_html=st.session_state.ta_mod2 if st.session_state.ta_mod2 else '<p>Metabolic module pending.</p>',
                    mod3_html=st.session_state.ta_mod3 if st.session_state.ta_mod3 else '<p>Biomechanical module pending.</p>',
                    plain_english_html=st.session_state.ta_pe if st.session_state.ta_pe else '<p>Plain English summary pending.</p>',
                    p30_html=p30_content,
                    p60_html=p60_content,
                    p90_html=p90_content,
                    tests_count=len(st.session_state.participant_tests),
                    tests_html=tests_html
                )

                if db:
                    client_lower = participant_name.strip().lower()
                    scan_id = str(assessment_date)

                    # 1. Save/Update Root Client Profile
                    profile_record = {
                        "name_lower": client_lower,
                        "name": participant_name,
                        "pin": patient_pin.strip(),
                        "price_30": price_30,
                        "price_60": price_60,
                        "price_90": price_90,
                        "unlock_30": unlock_30_flag,
                        "unlock_60": unlock_60_flag,
                        "unlock_90": unlock_90_flag,
                    }
                    db.collection("longevity_reports").document(client_lower).set(profile_record, merge=True)

                    # 2. Save Assessment Scan to Subcollection (Preserves History!)
                    scan_record = {
                        "assessment_date": str(assessment_date),
                        "tests_count": len(st.session_state.participant_tests),
                        "tests": st.session_state.participant_tests,
                        "body_mass_height": body_mass_height,
                        "age_gender": age_gender,
                        "master_html": st.session_state.ta_master,
                        "plain_english_html": st.session_state.ta_pe,
                        "plan_30_raw": st.session_state.ta_plan_30,
                        "plan_60_raw": st.session_state.ta_plan_60,
                        "plan_90_raw": st.session_state.ta_plan_90,
                        "html_output": final_html_output
                    }
                    db.collection("longevity_reports").document(client_lower).collection("scans").document(scan_id).set(scan_record)

                    st.success(f"✨ Scan for {assessment_date} published & synced to cloud historical records!")
                else:
                    st.error("Database connection unavailable.")
            except Exception as e:
                st.error(f"Error publishing to cloud: {e}")

# ==========================================
# VIEW 2: SECURE PATIENT MOBILE PORTAL
# ==========================================
elif app_mode == "Secure Patient Mobile Portal":
    st.subheader("📱 Participant Companion Portal")
    st.markdown("Welcome to the Chudleigh Health Hub client portal. Enter your full name and secure 4-digit PIN.")

    # Check if returning from a Stripe payment checkout
    query_params = st.query_params
    stripe_session_id = query_params.get("session_id")
    verified_patient = query_params.get("patient")
    verified_tier = query_params.get("tier")

    if stripe_session_id and verified_patient and verified_tier:
        try:
            if not stripe.api_key:
                stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
            
            session = stripe.checkout.Session.retrieve(stripe_session_id)
            if session.payment_status == "paid":
                lookup_key = verified_patient.strip().lower()
                update_field = f"unlock_{verified_tier}"
                
                db.collection("longevity_reports").document(lookup_key).update({update_field: True})
                st.success(f"🎉 Payment verified! Your {verified_tier}-Day Action Plan has been successfully unlocked.")
        except Exception as e:
            st.error(f"Payment verification error: {e}")

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
                        # Fetch all historical scans for this patient, ordered newest first
                        scans_ref = db.collection("longevity_reports").document(lookup_key).collection("scans")
                        scans_docs = list(scans_ref.order_by("assessment_date", direction=firestore.Query.DESCENDING).stream())

                        if not scans_docs:
                            st.warning("No assessment scans found on file.")
                        else:
                            # Let patient select which scan date to view if multiple exist
                            scan_dates = [d.id for d in scans_docs]
                            selected_scan_date = st.selectbox("Select Assessment Date", scan_dates)

                            selected_scan_doc = next((d for d in scans_docs if d.id == selected_scan_date), scans_docs[0])
                            scan_data = selected_scan_doc.to_dict()
                            html_output = scan_data.get("html_output", "<p>Report payload not found.</p>")

                            st.success(f"Authentication successful. Welcome back, {client_data['name']}!")

                            st.markdown(
                                f"""
                                <div class='portal-box'>
                                    <h3>📋 Longevity Profile &amp; Scan History</h3>
                                    <p><b>Participant:</b> {client_data['name']}</p>
                                    <p><b>Viewing Assessment Date:</b> {selected_scan_date}</p>
                                    <p><b>Total Scans On File:</b> {len(scans_docs)}</p>
                                </div>
                                """,
                                unsafe_allow_html=True,
                            )

                            # --- DYNAMICALLY PATCH TIER UNLOCK STATUS BASED ON LIVE FLAGS ---
                            u30 = client_data.get("unlock_30", False)
                            u60 = client_data.get("unlock_60", False)
                            u90 = client_data.get("unlock_90", False)
                            
                            p30_raw = scan_data.get("plan_30_raw", "")
                            p60_raw = scan_data.get("plan_60_raw", "")
                            p90_raw = scan_data.get("plan_90_raw", "")
                            
                            p_30 = client_data.get("price_30", "49")
                            p_60 = client_data.get("price_60", "89")
                            p_90 = client_data.get("price_90", "129")

                            new_p30 = f'<h3 style="color: #b45309; border-bottom: 2px solid #fde68a; padding-bottom: 5px;">30-Day Foundation Sprint</h3>{p30_raw}' if u30 else f'<div style="background: #fff; border: 2px dashed #f59e0b; padding: 20px; border-radius: 8px; text-align: center;"><h3 style="color: #b45309; margin-top: 0;">🔒 30-Day Foundation Sprint (Locked)</h3><p style="color: #475569; font-size: 14px;">Unlock this foundational sprint for <b>£{p_30}</b>.</p></div>'
                            new_p60 = f'<h3 style="color: #b45309; border-bottom: 2px solid #fde68a; padding-bottom: 5px; margin-top: 30px;">60-Day Progression Plan</h3>{p60_raw}' if u60 else f'<div style="background: #fff; border: 2px dashed #f59e0b; padding: 20px; border-radius: 8px; text-align: center; margin-top: 20px;"><h3 style="color: #b45309; margin-top: 0;">🔒 60-Day Progression Plan (Locked)</h3><p style="color: #475569; font-size: 14px;">Unlock this progression tier for <b>£{p_60}</b>.</p></div>'
                            new_p90 = f'<h3 style="color: #b45309; border-bottom: 2px solid #fde68a; padding-bottom: 5px; margin-top: 30px;">90-Day Mastery Plan</h3>{p90_raw}' if u90 else f'<div style="background: #fff; border: 2px dashed #f59e0b; padding: 20px; border-radius: 8px; text-align: center; margin-top: 20px;"><h3 style="color: #b45309; margin-top: 0;">🔒 90-Day Mastery Plan (Locked)</h3><p style="color: #475569; font-size: 14px;">Unlock the complete 90-day roadmap for <b>£{p_90}</b>.</p></div>'

                            updated_plans_html = f"""<!-- PLAN_SECTION_START -->
                            <div class="interpretation-text">
                                {new_p30}
                                {new_p60}
                                {new_p90}
                            </div>
                            <!-- PLAN_SECTION_END -->"""

                            if "<!-- PLAN_SECTION_START -->" in html_output and "<!-- PLAN_SECTION_END -->" in html_output:
                                start_idx = html_output.find("<!-- PLAN_SECTION_START -->")
                                end_idx = html_output.find("<!-- PLAN_SECTION_END -->") + len("<!-- PLAN_SECTION_END -->")
                                html_output = html_output[:start_idx] + updated_plans_html + html_output[end_idx:]

                            # --- DYNAMIC STRIPE CHECKOUT SESSION GENERATION ---
                            if not stripe.api_key:
                                stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")

                            app_url = "https://chudleigh-health-66895860161.europe-west2.run.app"

                            stripe_url_30 = ""
                            if not u30:
                                cs_30 = stripe.checkout.Session.create(
                                    line_items=[{
                                        'price_data': {
                                            'currency': 'gbp',
                                            'product_data': {'name': 'Chudleigh Health Hub - 30-Day Action Plan'},
                                            'unit_amount': int(float(p_30) * 100),
                                        },
                                        'quantity': 1,
                                    }],
                                    mode='payment',
                                    success_url=f"{app_url}/?portal=true&session_id={{CHECKOUT_SESSION_ID}}&patient={client_data['name']}&tier=30",
                                    cancel_url=f"{app_url}/?portal=true",
                                )
                                stripe_url_30 = cs_30.url

                            stripe_url_60 = ""
                            if not u60:
                                cs_60 = stripe.checkout.Session.create(
                                    line_items=[{
                                        'price_data': {
                                            'currency': 'gbp',
                                            'product_data': {'name': 'Chudleigh Health Hub - 60-Day Progression Plan'},
                                            'unit_amount': int(float(p_60) * 100),
                                        },
                                        'quantity': 1,
                                    }],
                                    mode='payment',
                                    success_url=f"{app_url}/?portal=true&session_id={{CHECKOUT_SESSION_ID}}&patient={client_data['name']}&tier=60",
                                    cancel_url=f"{app_url}/?portal=true",
                                )
                                stripe_url_60 = cs_60.url

                            stripe_url_90 = ""
                            if not u90:
                                cs_90 = stripe.checkout.Session.create(
                                    line_items=[{
                                        'price_data': {
                                            'currency': 'gbp',
                                            'product_data': {'name': 'Chudleigh Health Hub - 90-Day Mastery Plan'},
                                            'unit_amount': int(float(p_90) * 100),
                                        },
                                        'quantity': 1,
                                    }],
                                    mode='payment',
                                    success_url=f"{app_url}/?portal=true&session_id={{CHECKOUT_SESSION_ID}}&patient={client_data['name']}&tier=90",
                                    cancel_url=f"{app_url}/?portal=true",
                                )
                                stripe_url_90 = cs_90.url

                            if stripe_url_30:
                                html_output = html_output.replace(
                                    '🔒 30-Day Foundation Sprint (Locked)', 
                                    f'🔒 30-Day Foundation Sprint (Locked)</p><a href="javascript:void(0);" onclick="window.open(\'{stripe_url_30}\', \'_blank\');" style="display: inline-block; background-color: #0f382b; color: white; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: bold; margin-top: 10px; cursor: pointer;">💳 Unlock 30-Day Plan (£{p_30})</a><p style="display:none;'
                                )
                            if stripe_url_60:
                                html_output = html_output.replace(
                                    '🔒 60-Day Progression Plan (Locked)', 
                                    f'🔒 60-Day Progression Plan (Locked)</p><a href="javascript:void(0);" onclick="window.open(\'{stripe_url_60}\', \'_blank\');" style="display: inline-block; background-color: #0f382b; color: white; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: bold; margin-top: 10px; cursor: pointer;">💳 Unlock 60-Day Plan (£{p_60})</a><p style="display:none;'
                                )
                            if stripe_url_90:
                                html_output = html_output.replace(
                                    '🔒 90-Day Mastery Plan (Locked)', 
                                    f'🔒 90-Day Mastery Plan (Locked)</p><a href="javascript:void(0);" onclick="window.open(\'{stripe_url_90}\', \'_blank\');" style="display: inline-block; background-color: #0f382b; color: white; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: bold; margin-top: 10px; cursor: pointer;">💳 Unlock 90-Day Plan (£{p_90})</a><p style="display:none;'
                                )

                            st.download_button(
                                label=f"📥 Download Report ({selected_scan_date})",
                                data=html_output,
                                file_name=f"{client_data['name'].replace(' ', '_')}_{selected_scan_date}_Healthspan_Report.html",
                                mime="text/html",
                                use_container_width=True,
                            )

                            st.subheader(f"🔎 Clinical Healthspan Dashboard ({selected_scan_date})")
                            st.components.v1.html(html_output, height=800, scrolling=True)
                    else:
                        st.error("Incorrect security PIN. Please check your PIN or contact Chudleigh Health Hub.")
                else:
                    st.warning("No published profiles found matching that name in the Google Cloud database.")
        
        except Exception as e:
            st.error(f"Error connecting to Cloud records: {e}")
