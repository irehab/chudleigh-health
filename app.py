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
    </style>
    """,
    unsafe_allow_html=True,
)

# --- HEADER BANNER ---
st.markdown(
    """
    <div class="main-header">
        <h1>Chudleigh Health Hub</h1>
        <p>Health Autonomy &amp; Clinical Longevity Portal</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# --- SESSION STATE INITIALIZATION ---
if "participant_tests" not in st.session_state:
    st.session_state.participant_tests = []
if "editable_clinical_text" not in st.session_state:
    st.session_state.editable_clinical_text = ""

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
        st.session_state.editable_clinical_text = ""
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
        f"📎 Upload Official {assessment_type} PDF Report (Attached for Patient Download & Clinical Analysis)", 
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

    # Form inputs for quick overrides or supplementary metrics
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

    st.subheader("🚀 Clinical Report Compilation & Health Autonomy Engine")
    st.markdown("Compile all queued tests, run clinical analysis, review or edit the interpretation, and publish to Google Cloud.")

    if st.button("Generate Master Clinical Report", type="primary", use_container_width=True):
        if not participant_name:
            st.warning("Please enter the participant's name.")
        elif not patient_pin or len(patient_pin) < 4:
            st.warning("Please enter a valid 4-digit security PIN for patient portal access.")
        elif len(st.session_state.participant_tests) == 0:
            st.warning("Please add at least one test assessment to the profile.")
        else:
            with st.spinner("🩺 Running clinical analytics engine & drafting comprehensive report..."):
                try:
                    summary_context = f"Participant: {participant_name}, Age/Gender: {age_gender}, Metrics: {body_mass_height}\n"
                    contents_payload = []

                    for idx, t in enumerate(st.session_state.participant_tests):
                        summary_context += f"Test {idx+1}: {t['type']} -> Data: {json.dumps(t['data'])}\n"
                        if t.get('pdf_b64'):
                            contents_payload.append({
                                "inline_data": {
                                    "mime_type": "application/pdf",
                                    "data": t['pdf_b64']
                                }
                            })

                    draft_interpretation = "<p>Clinical interpretation generated successfully.</p>"
                    
                    if gemini_client:
                        prompt_text = (
                            "You are an expert clinical data analyst and longevity physician at Chudleigh Health Hub, powered by Health Autonomy. "
                            "Carefully analyze the attached official PDF reports and manually entered metrics for this participant, including SpO2/pulse oximetry, oxygen saturation stability, and pulse dynamics. "
                            "Drill down into every available metric, table, percentage distribution, oxygen levels, and graphical trends.\n\n"
                            "Write an exhaustive, highly rigorous, and professional clinical interpretation formatted in clean HTML (use h3, p, and li tags). "
                            "Do not mention any AI models, automated assistants, or third-party tools. Present the output strictly as authored by Chudleigh Health Hub / Health Autonomy clinical analytics.\n\n"
                            f"Participant Details & Test Data:\n{summary_context}\n\n"
                            "Provide:\n"
                            "1. Comprehensive Clinical Summary & Physiological Insights\n"
                            "2. Granular Biomarker Breakdown (extracting deep metrics, oxygen saturation stability, and pulse dynamics)\n"
                            "3. Tailored Lifestyle, Movement, and Longevity Therapeutic Roadmap"
                        )
                        contents_payload.append(prompt_text)

                        response = gemini_client.models.generate_content(
                            model="gemini-3.8-flash",
                            contents=contents_payload,
                        )
                        if response and response.text:
                            draft_interpretation = response.text
                    else:
                        st.warning("Clinical analytics client uninitialized.")

                    st.session_state.editable_clinical_text = draft_interpretation
                    st.success("✨ Clinical report drafted successfully! Review and edit the clinical text below before publishing.")
                    st.rerun()

                except Exception as e:
                    st.error(f"An error occurred during report compilation: {e}")

    # --- EDITABLE CLINICAL TEXT AREA & PUBLISH ---
    if st.session_state.editable_clinical_text:
        st.divider()
        st.subheader("✏️ Edit Clinical Interpretation & Recommendations")
        st.markdown("Modify, refine, or add notes to the clinical evaluation below before publishing to the patient portal:")

        edited_interpretation = st.text_area(
            "Clinical Interpretation Text (HTML format)",
            value=st.session_state.editable_clinical_text,
            height=350,
            key="clinical_text_editor"
        )

        if st.button("💾 Publish & Sync Master Report to Google Cloud", type="primary", use_container_width=True):
            if not participant_name:
                st.warning("Please ensure participant name is entered.")
            else:
                try:
                    # Build individual test cards with secure download buttons
                    tests_html = ""
                    for idx, t in enumerate(st.session_state.participant_tests):
                        data_str = "".join([f"<li><b>{k}:</b> {v}</li>" for k, v in t['data'].items() if v])
                        
                        pdf_download_box = ""
                        if t.get('pdf_b64'):
                            filename = t.get('pdf_filename', 'Diagnostic_Report.pdf')
                            pdf_download_box = (
                                '<div style="margin-top: 20px; background: #f0fdf4; border: 1px solid #bbf7d0; padding: 20px; border-radius: 8px; text-align: center;">'
                                f'<h4 style="margin-top: 0; color: #0f382b; font-size: 16px; margin-bottom: 8px;">Official Diagnostic PDF Report Available</h4>'
                                f'<p style="font-size: 13px; color: #475569; margin-bottom: 15px;">Click below to download the complete official report ({filename}) containing all graphs, charts, and tables:</p>'
                                f'<a href="data:application/pdf;base64,{t["pdf_b64"]}" download="{filename}" style="background-color: #0f382b; color: white; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: bold; font-size: 14px; display: inline-block;">📥 Download {filename}</a>'
                                '</div>'
                            )

                        tests_html += (
                            '<div style="background: #f8fafc; border-left: 4px solid #0f382b; padding: 20px; margin-bottom: 25px; border-radius: 8px; border: 1px solid #e2e8f0;">'
                            f'<h3 style="margin-top: 0; color: #0f382b; font-size: 19px;">Test #{idx+1}: {t["type']}</h3>'
                            f'<ul style="margin-bottom: 15px; color: #334155; padding-left: 20px;">{data_str if data_str else "<li>Metrics extracted directly via clinical PDF inspection.</li>"}</ul>'
                            f'{pdf_download_box}'
                            '</div>'
                        )

                    html_template = """
                    <!DOCTYPE html>
                    <html lang="en">
                    <head>
                        <meta charset="utf-8">
                        <meta name="viewport" content="width=device-width, initial-scale=1.0">
                        <title>Chudleigh Health Hub - Longevity Master Report</title>
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
                            .results-card {{ background: linear-gradient(to bottom right, #f0fdf4, #ecfdf5); border: 2px solid var(--success-color); border-radius: 10px; padding: 25px; margin-bottom: 30px; }}
                            .results-card h2 {{ margin-top: 0; color: var(--secondary-color); font-size: 20px; }}
                            .interpretation-text {{ font-size: 15px; background: rgba(255, 255, 255, 0.9); padding: 20px; border-radius: 8px; margin-top: 20px; }}
                            .footer {{ text-align: center; padding: 20px; background: #f1f5f9; font-size: 12px; color: var(--text-muted); border-top: 1px solid var(--border-color); }}
                        </style>
                    </head>
                    <body>
                        <div class="report-container">
                            <div class="header">
                                <h1>Chudleigh Health Hub</h1>
                                <p>Health Autonomy &bull; Clinical Longevity Report</p>
                            </div>
                            <div class="content">
                                <div class="patient-meta">
                                    <div class="meta-item"><label>Participant Name</label><span>{participant_name}</span></div>
                                    <div class="meta-item"><label>Age / Gender</label><span>{age_gender}</span></div>
                                    <div class="meta-item"><label>Assessment Date</label><span>{assessment_date}</span></div>
                                    <div class="meta-item"><label>Body Mass / Metrics</label><span>{body_mass_height}</span></div>
                                </div>
                                
                                <div class="results-card">
                                    <h2>🩺 Clinical Interpretation & Health Autonomy Roadmap</h2>
                                    <div class="interpretation-text">
                                        {ai_analysis_html}
                                    </div>
                                </div>

                                <h2 style="color: #0f382b; font-size: 20px; margin-bottom: 15px;">Completed Diagnostic Assessments ({tests_count})</h2>
                                {tests_html}
                            </div>
                            <div class="footer">&copy; 2026 Chudleigh Health Hub. Health Autonomy Longevity Platform. All rights reserved.</div>
                        </div>
                    </body>
                    </html>
                    """

                    final_html_output = html_template.format(
                        participant_name=participant_name,
                        age_gender=age_gender if age_gender else 'Not specified',
                        assessment_date=str(assessment_date),
                        body_mass_height=body_mass_height if body_mass_height else 'Not specified',
                        ai_analysis_html=edited_interpretation,
                        tests_count=len(st.session_state.participant_tests),
                        tests_html=tests_html
                    )

                    if db:
                        doc_id = participant_name.strip().lower()
                        record = {
                            "name_lower": doc_id,
                            "name": participant_name,
                            "pin": patient_pin.strip(),
                            "assessment_date": str(assessment_date),
                            "tests_count": len(st.session_state.participant_tests),
                        }
                        db.collection("longevity_reports").document(doc_id).set(record)
                        
                        html_record = {
                            "html_output": final_html_output
                        }
                        db.collection("longevity_htmls").document(doc_id).set(html_record)

                        st.success("✨ Master Report published and successfully synced to Google Cloud Firestore!")
                    else:
                        st.error("Database connection unavailable.")
                except Exception as e:
                    st.error(f"Error publishing to cloud: {e}")

        st.subheader("🔎 Live Preview of Master Report")
        preview_tests_html = ""
        for idx, t in enumerate(st.session_state.participant_tests):
            data_str = "".join([f"<li><b>{k}:</b> {v}</li>" for k, v in t['data'].items() if v])
            preview_tests_html += f"<div style='background: #f8fafc; border-left: 4px solid #0f382b; padding: 15px; margin-bottom: 15px;'><h3>Test #{idx+1}: {t['type']}</h3><ul>{data_str}</ul></div>"

        live_preview_html = f"""
        <div style="font-family: sans-serif; padding: 20px; background: white; border-radius: 8px;">
            <h2 style="color: #0f382b;">{participant_name} ({age_gender})</h2>
            <div style="background: #f0fdf4; padding: 15px; border-radius: 6px;">{edited_interpretation}</div>
            <h3 style="color: #0f382b; margin-top: 20px;">Completed Tests:</h3>
            {preview_tests_html}
        </div>
        """
        st.components.v1.html(live_preview_html, height=600, scrolling=True)

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
                        html_doc = db.collection("longevity_htmls").document(lookup_key).get()
                        html_output = html_doc.to_dict().get("html_output", "") if html_doc.exists else "<p>Report payload not found.</p>"

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
                            label="📥 Download My Master AI Report (With Attached PDFs)",
                            data=html_output,
                            file_name=f"{client_data['name'].replace(' ', '_')}_Healthspan_Report.html",
                            mime="text/html",
                            use_container_width=True
                        )

                        st.subheader("🔎 Your Live Interactive AI Healthspan Dashboard")
                        st.components.v1.html(html_output, height=800, scrolling=True)
                    else:
                        st.error("Incorrect security PIN. Please check your PIN or contact Chudleigh Health Hub.")
                else:
                    st.warning("No published reports found matching that name in the Google Cloud database.")
        
        except Exception as e:
            st.error(f"Error connecting to Google Cloud records: {e}")
