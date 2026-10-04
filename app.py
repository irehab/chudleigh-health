import datetime
import streamlit as st
import google.generativeai as genai

# Page Configuration
st.set_page_config(
    page_title="Chudleigh Health Hub - Longevity Report Generator",
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
    </style>
    """,
    unsafe_allow_html=True,
)

# Header Banner
st.markdown(
    """
    <div class="main-header">
        <h1>Chudleigh Health Hub</h1>
        <p>Diagnostic Longevity Pilot &bull; Clinical Report Generator</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# --- SIDEBAR CONFIGURATION ---
st.sidebar.header("Configuration & Settings")

# Secure API Key Input for Gemini
api_key = st.sidebar.text_input(
    "Google Gemini API Key", type="password", help="Enter your Google Gemini API key here."
)

st.sidebar.divider()

# Assessment Type Dropdown
assessment_type = st.sidebar.selectbox(
    "Select Assessment Type",
    [
        "Tanita Body Composition",
        "Push-Up Assessment",
        "Spirometry",
        "AGE Reader",
        "ECG",
        "Autonomic/HRV",
    ],
)

# --- MAIN FORM: PATIENT METADATA ---
st.subheader("📋 Participant Metadata")
col1, col2 = st.columns(2)

with col1:
    participant_name = st.text_input(
        "Participant Name", placeholder="e.g. John Doe"
    )
    age_gender = st.text_input(
        "Age / Gender", placeholder="e.g. 48 / Male"
    )

with col2:
    assessment_date = st.date_input(
        "Assessment Date", value=datetime.date.today()
    )
    body_mass_height = st.text_input(
        "Body Mass / Height", placeholder="e.g. 78 kg / 175 cm"
    )

st.divider()

# --- DYNAMIC INPUT AREA ---
st.subheader(f"📊 Input Data: {assessment_type}")

input_data_payload = {}

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

    input_data_payload = {
        "RMSSD": rmssd,
        "SDNN": sdnn,
        "Respiration Rate": resp_rate,
        "Blood Pressure": blood_pressure,
    }
else:
    raw_notes = st.text_area(
        "Paste Raw Metrics, Values, or Notes from Test Device",
        placeholder="Paste extracted data metrics or notes here...",
        height=150,
    )
    input_data_payload = {"Raw Data / Notes": raw_notes}

st.divider()

# --- GENERATE BUTTON LOGIC ---
if st.button("Generate HTML Report", type="primary", use_container_width=True):
    if not api_key:
        st.error(
            "Please enter your Google Gemini API key in the sidebar before generating reports."
        )
    elif not participant_name:
        st.warning("Please enter the participant's name.")
    else:
        with st.spinner(
            "Synthesizing data and generating clinical HTML report with Gemini..."
        ):
            try:
                # Configure Gemini API
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel("gemini-1.5-flash")

                # Constructing the prompt payload for the LLM
                prompt_content = f"""
                Act as an expert clinical web developer and longevity data analyst at Chudleigh Health Hub.
                Generate a fully customized, patient-specific HTML web page report for a longevity assessment pilot participant.
                
                Assessment Type: {assessment_type}
                Participant Name: {participant_name}
                Age / Gender: {age_gender}
                Assessment Date: {str(assessment_date)}
                Body Mass / Height: {body_mass_height}
                
                Input Data Metrics:
                {input_data_payload}
                
                Requirements:
                - Use a professional design system with primary color #0f382b.
                - Create clean metric boxes and an evidence-based clinical interpretation section tailored to these specific figures.
                - Output ONLY valid, complete, production-ready HTML code without markdown code blocks wrapper or citation markers.
                """

                response = model.generate_content(prompt_content)
                html_output = response.text

                # Clean potential markdown markdown ticks if returned
                if html_output.startswith("```html"):
                    html_output = html_output[7:]
                if html_output.endswith("```"):
                    html_output = html_output[:-3]

                st.success("Report successfully generated!")

                # Display download button
                st.download_button(
                    label="📥 Download HTML Report File",
                    data=html_output,
                    file_name=f"{participant_name.replace(' ', '_')}_{assessment_type.replace(' ', '_')}_Report.html",
                    mime="text/html",
                )

                # Live preview container
                st.subheader("🔎 Live Report Preview")
                st.components.v1.html(html_output, height=650, scrolling=True)

            except Exception as e:
                st.error(f"An error occurred during generation: {e}")
