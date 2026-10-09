import os
import io
import re
import json
import hmac
import math
import time
import secrets
import hashlib
import logging
import datetime
from decimal import Decimal

import nh3
import stripe
import streamlit as st
import streamlit.components.v1 as components
from google import genai
from google.genai import errors as genai_errors
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from helpers import (
    PIN_HASH_ITERATIONS,
    client_ip_from_xff,
    esc,
    fmt_price,
    hash_pin,
    parse_price,
    patient_key,
    redact_for_ai,
    short_ref,
    strip_code_fences,
    verify_pin,
)

# --- LOGGING (stdout -> Cloud Logging). Never log patient names, PINs or clinical content. ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("chudleigh")

# --- SERVER CONFIGURATION (set via environment / Secret Manager) ---
APP_URL = os.environ.get("APP_URL", "https://chudleigh-health-66895860161.europe-west2.run.app").rstrip("/")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
FIRESTORE_DATABASE = os.environ.get("FIRESTORE_DATABASE", "default")
CLINICIAN_PASSWORD = os.environ.get("CLINICIAN_PASSWORD", "")
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")

# --- SECURITY SETTINGS ---
MIN_NEW_PIN_LENGTH = 6          # new / reset PINs
LEGACY_MIN_PIN_LENGTH = 4       # existing 4-digit PINs can still sign in
MAX_PIN_LENGTH = 8
MAX_LOGIN_ATTEMPTS = 5
MAX_CLINICIAN_ATTEMPTS_PER_IP = 5
MAX_CLINICIAN_ATTEMPTS_GLOBAL = 25      # ceiling across all addresses (guards against rotating IPs)
MAX_PATIENT_ATTEMPTS_PER_IP = 25        # stops one address spraying many names
LOCKOUT_SECONDS = 15 * 60
PATIENT_SESSION_SECONDS = 30 * 60
CLINICIAN_SESSION_SECONDS = 60 * 60
MAX_PDF_BYTES = 20 * 1024 * 1024
MAX_FIRESTORE_DOC_BYTES = 950_000
PDF_READY_TIMEOUT_SECONDS = 120

REPORTS = "longevity_reports"
TIERS = ("30", "60", "90")
TIER_INFO = {
    "30": {
        "title": "30-Day Foundation Sprint",
        "editor_heading": "#### 30-Day Foundation Sprint (High-Priority Fixes)",
        "unlock_text": "Unlock this foundational sprint for",
        "product": "Chudleigh Health Hub - 30-Day Action Plan",
        "default_price": "49",
        "default_unlocked": True,
    },
    "60": {
        "title": "60-Day Progression Plan",
        "editor_heading": "#### 60-Day Progression Plan (Secondary Integration)",
        "unlock_text": "Unlock this progression tier for",
        "product": "Chudleigh Health Hub - 60-Day Progression Plan",
        "default_price": "89",
        "default_unlocked": False,
    },
    "90": {
        "title": "90-Day Mastery Plan",
        "editor_heading": "#### 90-Day Mastery Plan (Long-Term Optimization)",
        "unlock_text": "Unlock the complete 90-day roadmap for",
        "product": "Chudleigh Health Hub - 90-Day Mastery Plan",
        "default_price": "129",
        "default_unlocked": False,
    },
}
PLAN_START = "<!-- PLAN_SECTION_START -->"
PLAN_END = "<!-- PLAN_SECTION_END -->"

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
TEXT_KEYS = ["ta_mod1", "ta_mod2", "ta_mod3", "ta_master", "ta_pe", "ta_plan_30", "ta_plan_60", "ta_plan_90"]
if "participant_tests" not in st.session_state:
    st.session_state.participant_tests = []
for _k in TEXT_KEYS:
    if _k not in st.session_state:
        st.session_state[_k] = ""


# --- GOOGLE CLOUD & GEMINI INITIALIZATIONS ---
@st.cache_resource
def init_firestore():
    try:
        return firestore.Client(database=FIRESTORE_DATABASE)
    except Exception:
        log.exception("Firestore initialisation failed")
        return None


@st.cache_resource
def init_gemini():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        log.warning("GEMINI_API_KEY not set; AI drafting disabled")
        return None
    try:
        return genai.Client(api_key=api_key)
    except Exception:
        log.exception("Gemini initialisation failed")
        return None


db = init_firestore()
gemini_client = init_gemini()


# ==========================================
# HELPERS
# ==========================================
def clean_html(fragment: str) -> str:
    """Sanitise AI-generated or clinician-edited HTML (removes scripts, event handlers, etc.)."""
    return nh3.clean(strip_code_fences(fragment))


def fail(user_msg: str, context: str):
    """Call from inside an except block: logs the traceback, shows a generic message with a reference."""
    ref = secrets.token_hex(4)
    log.exception("%s [ref=%s]", context, ref)
    st.error(f"{user_msg} (reference: {ref})")


def strip_pdf_payloads(tests):
    """Remove raw PDF data so records stay under Firestore's 1 MiB limit and out of prompts."""
    return [{k: v for k, v in t.items() if k not in ("pdf_b64", "pdf_bytes")} for t in (tests or [])]


# --- PIN storage (hashing itself lives in helpers.py) ---
def pin_fields(pin: str) -> dict:
    salt, digest = hash_pin(pin)
    return {
        "pin_hash": digest,
        "pin_salt": salt,
        "pin_iterations": PIN_HASH_ITERATIONS,
        "pin_weak": len(pin) < MIN_NEW_PIN_LENGTH,  # flags short legacy PINs so a clinician can reset them
        "pin": firestore.DELETE_FIELD,  # remove any legacy plaintext PIN
    }


# --- Brute-force protection (shared across all app instances via Firestore) ---
def _attempt_ref(scope: str, identifier: str):
    doc_id = hashlib.sha256(f"{scope}:{identifier}".encode("utf-8")).hexdigest()
    return db.collection("auth_attempts").document(doc_id)


def lockout_remaining(scope: str, identifier: str) -> int:
    if not db:
        return 0
    try:
        snap = _attempt_ref(scope, identifier).get()
        if snap.exists:
            return max(0, int(snap.to_dict().get("locked_until", 0) - time.time()))
    except Exception:
        log.exception("Lockout check failed")
    return 0


@firestore.transactional
def _bump_attempts(transaction, ref, now, max_attempts):
    """Read-modify-write inside a transaction so simultaneous guesses are all counted."""
    snap = ref.get(transaction=transaction)
    data = snap.to_dict() if snap.exists else {}
    if now - data.get("window_start", 0) > LOCKOUT_SECONDS:
        data = {"window_start": now, "count": 0}
    data["count"] = data.get("count", 0) + 1
    if data["count"] >= max_attempts:
        data = {"window_start": now, "count": 0, "locked_until": now + LOCKOUT_SECONDS}
    transaction.set(ref, data)


def record_failed_attempt(scope: str, identifier: str, max_attempts: int = MAX_LOGIN_ATTEMPTS, delay: bool = True):
    if delay:
        time.sleep(1)  # slow down automated guessing
    if not db:
        return
    try:
        _bump_attempts(db.transaction(), _attempt_ref(scope, identifier), time.time(), max_attempts)
    except Exception:
        log.exception("Failed to record login attempt")


def client_ip() -> str:
    """Best-effort client address (Cloud Run puts it in X-Forwarded-For)."""
    try:
        return client_ip_from_xff(st.context.headers.get("x-forwarded-for", ""))
    except Exception:
        return "unknown"


def audit(event: str, key: str = "", **details):
    """Write an audit-trail entry. Stores a short hash of the patient key, never the name.

    Failures are logged but never block the action being audited.
    """
    if not db:
        return
    try:
        db.collection("audit_log").add({
            "event": event,
            "patient_ref": short_ref(key) if key else None,
            "at": firestore.SERVER_TIMESTAMP,
            "ip": client_ip(),
            **details,
        })
    except Exception:
        log.exception("Audit write failed")


def clear_attempts(scope: str, identifier: str):
    if not db:
        return
    try:
        _attempt_ref(scope, identifier).delete()
    except Exception:
        log.exception("Failed to clear login attempts")


# --- Gemini ---
def generate(contents, json_mode: bool = False) -> str:
    if not gemini_client:
        raise RuntimeError("Gemini client not configured")
    config = {"response_mime_type": "application/json"} if json_mode else None
    for attempt in range(3):
        try:
            res = gemini_client.models.generate_content(model=GEMINI_MODEL, contents=contents, config=config)
            text = (res.text or "") if res else ""
            if not text.strip():
                raise RuntimeError("Empty response from model")
            return text
        except genai_errors.APIError as e:
            if getattr(e, "code", None) in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(2 * (2 ** attempt))
                continue
            raise
    raise RuntimeError("Model unavailable")


class PdfAttachError(Exception):
    """A PDF could not be prepared for Gemini (message is safe to show to the clinician)."""


def wait_until_active(f, timeout: int = PDF_READY_TIMEOUT_SECONDS):
    """Block until Gemini has finished processing an uploaded file.

    Using a file before it is ACTIVE is a common cause of intermittent 400 errors on large PDFs.
    """
    deadline = time.time() + timeout
    while True:
        state = getattr(f, "state", None)
        name = str(getattr(state, "name", state) or "ACTIVE").upper()  # no state reported -> treat as ready
        if "FAILED" in name:
            raise RuntimeError("Gemini could not process the PDF")
        if "ACTIVE" in name:
            return f
        if time.time() >= deadline:
            raise TimeoutError("PDF still processing after timeout")
        time.sleep(2)
        f = gemini_client.files.get(name=f.name)


def upload_pdfs(tests):
    """Upload each test's PDF to Gemini and wait until it is ready.

    If any PDF fails, everything uploaded so far is deleted and PdfAttachError is raised, so a review is
    never drafted while silently ignoring an attached report.
    """
    refs = []
    for t in tests:
        data = t.get("pdf_bytes")
        if not data:
            continue
        uploaded = None
        try:
            uploaded = gemini_client.files.upload(file=io.BytesIO(data), config={"mime_type": "application/pdf"})
            refs.append(wait_until_active(uploaded))
        except Exception as e:
            log.exception("PDF upload to Gemini failed")
            if uploaded is not None:
                delete_uploaded([uploaded])
            delete_uploaded(refs)
            raise PdfAttachError(
                f"Could not prepare the PDF for {t['type']}. Please try again, "
                "or remove that PDF and draft from the entered metrics only."
            ) from e
    return refs


def delete_uploaded(refs):
    for f in refs:
        try:
            gemini_client.files.delete(name=f.name)
        except Exception:
            log.warning("Could not delete uploaded Gemini file")


def gemini_ready() -> bool:
    if not gemini_client:
        st.error("AI drafting is unavailable: GEMINI_API_KEY is not configured on the server.")
        return False
    return True


# --- Participant lookups ---
@st.cache_data(ttl=60, show_spinner=False)
def lookup_history(key: str):
    """Return (profile_info or None, previous_scan_summary or None). Cached for a minute.

    Only non-sensitive fields are returned (never PIN data), and each publish clears the cache.
    """
    profile_ref = db.collection(REPORTS).document(key)
    snap = profile_ref.get()
    profile = None
    if snap.exists:
        d = snap.to_dict() or {}
        legacy_pin = d.get("pin")
        profile = {
            "pin_weak": bool(d.get("pin_weak")) or (legacy_pin is not None and len(str(legacy_pin)) < MIN_NEW_PIN_LENGTH),
            **{f"price_{t}": d.get(f"price_{t}") for t in TIERS},
        }
    previous = None
    docs = list(
        profile_ref.collection("scans")
        .order_by("assessment_date", direction=firestore.Query.DESCENDING)
        .limit(1)
        .stream()
    )
    if docs:
        p = docs[0].to_dict() or {}
        previous = {k: p.get(k) for k in ("assessment_date", "tests_count", "tests", "master_html", "age_gender", "body_mass_height")}
    return profile, previous


# --- Data-rights tools (export / delete) ---
_SECRET_FIELDS = ("pin", "pin_hash", "pin_salt", "pin_iterations")


def export_participant(key: str) -> str:
    """Everything held about one participant, as JSON (PIN data excluded)."""
    profile_ref = db.collection(REPORTS).document(key)
    snap = profile_ref.get()
    if not snap.exists:
        raise LookupError("No record found")
    profile = {k: v for k, v in (snap.to_dict() or {}).items() if k not in _SECRET_FIELDS}
    scans = {d.id: d.to_dict() for d in profile_ref.collection("scans").stream()}
    payments = [
        {"checkout_session": d.id, **(d.to_dict() or {})}
        for d in db.collection("payments").where(filter=FieldFilter("patient_key", "==", key)).stream()
    ]
    return json.dumps({"profile": profile, "scans": scans, "payments": payments}, default=str, indent=2)


def delete_participant(key: str) -> int:
    """Permanently delete a participant's profile and scans. Payment records are kept for accounting."""
    profile_ref = db.collection(REPORTS).document(key)
    deleted = 0
    for d in profile_ref.collection("scans").stream():
        d.reference.delete()
        deleted += 1
    profile_ref.delete()
    clear_attempts("patient", key)
    return deleted


# --- Report building ---
def build_plan_section(raw_plans: dict, unlocked: dict, price_labels: dict) -> str:
    parts = []
    for i, tier in enumerate(TIERS):
        info = TIER_INFO[tier]
        if unlocked.get(tier):
            margin = "" if i == 0 else " margin-top: 30px;"
            parts.append(
                f'<h3 style="color: #b45309; border-bottom: 2px solid #fde68a; padding-bottom: 5px;{margin}">{info["title"]}</h3>'
                f'{clean_html(raw_plans.get(tier, ""))}'
            )
        else:
            margin = "" if i == 0 else " margin-top: 20px;"
            parts.append(
                f'<div style="background: #fff; border: 2px dashed #f59e0b; padding: 20px; border-radius: 8px; text-align: center;{margin}">'
                f'<h3 style="color: #b45309; margin-top: 0;">🔒 {info["title"]} (Locked)</h3>'
                f'<p style="color: #475569; font-size: 14px;">{info["unlock_text"]} <b>£{esc(price_labels.get(tier, ""))}</b> '
                'in your Chudleigh Health Hub patient portal.</p></div>'
            )
    return f'{PLAN_START}<div class="interpretation-text">{"".join(parts)}</div>{PLAN_END}'


# --- Stripe ---
_CHECKOUT_ID_RE = re.compile(r"cs_[A-Za-z0-9_]{10,255}")


def stripe_field(obj, key):
    """Read a field from a Stripe object; newer stripe-python versions don't support .get()."""
    if obj is None:
        return None
    try:
        return obj[key]
    except (KeyError, TypeError, AttributeError):
        return None


def create_checkout_url(key: str, tier: str, price: Decimal) -> str:
    session = stripe.checkout.Session.create(
        line_items=[{
            "price_data": {
                "currency": "gbp",
                "product_data": {"name": TIER_INFO[tier]["product"]},
                "unit_amount": int(price * 100),
            },
            "quantity": 1,
        }],
        mode="payment",
        client_reference_id=key,
        # Patient and tier are bound server-side; the return URL carries only the session ID.
        metadata={"patient_key": key, "tier": tier},
        success_url=f"{APP_URL}/?portal=true&session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{APP_URL}/?portal=true",
    )
    return session.url


def handle_stripe_return(session_id: str):
    if not _CHECKOUT_ID_RE.fullmatch(session_id or ""):
        st.error("Invalid payment reference.")
        return
    if not stripe.api_key or not db:
        st.error("Payment verification is temporarily unavailable. Please contact Chudleigh Health Hub.")
        return
    try:
        cs = stripe.checkout.Session.retrieve(session_id)
    except Exception:
        fail("We couldn't verify your payment right now. Please contact Chudleigh Health Hub.", "Stripe session retrieve failed")
        return

    if stripe_field(cs, "payment_status") != "paid":
        st.warning("Your payment hasn't completed yet. If you were charged, please contact Chudleigh Health Hub.")
        return

    metadata = stripe_field(cs, "metadata")
    key = stripe_field(metadata, "patient_key")
    tier = stripe_field(metadata, "tier")
    if tier not in TIERS or not key or patient_key(key) != key:
        log.warning("Paid Stripe session without valid metadata: %s", session_id)
        st.error(f"We couldn't match this payment to a plan. Please contact Chudleigh Health Hub quoting: {session_id[-12:]}")
        return

    try:
        profile_ref = db.collection(REPORTS).document(key)
        if not profile_ref.get().exists:
            log.warning("Paid Stripe session for missing profile: %s", session_id)
            st.error(f"We couldn't find your record. Please contact Chudleigh Health Hub quoting: {session_id[-12:]}")
            return
        profile_ref.update({f"unlock_{tier}": True})
        db.collection("payments").document(session_id).set({
            "patient_key": key,
            "tier": tier,
            "amount_total": stripe_field(cs, "amount_total"),
            "currency": stripe_field(cs, "currency"),
            "processed_at": firestore.SERVER_TIMESTAMP,
        }, merge=True)
    except Exception:
        fail("Your payment was received but we couldn't unlock your plan automatically. Please contact Chudleigh Health Hub.",
             "Unlock after payment failed")
        return

    audit("payment_unlock", key, tier=tier)
    st.success(f"🎉 Payment verified! Your {tier}-Day Action Plan has been unlocked. Sign in below to view it.")


# ==========================================
# ASSESSMENT INPUT DEFINITIONS
# Each assessment is a list of columns; each field is (label, example shown as a placeholder, payload key).
# Fields start EMPTY so example numbers can never end up in a real report by accident.
# ==========================================
ASSESSMENTS = {
    "SpO2 / Pulse Oximetry (ViHealth)": {
        "columns": [
            [("Highest SpO2 (%)", "98", "Highest SpO2"), ("Average SpO2 (%)", "96", "Average SpO2")],
            [("Lowest SpO2 (%)", "94", "Lowest SpO2"), ("Highest Pulse Rate (BPM)", "59", "Highest Pulse Rate")],
            [("Average Pulse Rate (BPM)", "54", "Average Pulse Rate"), ("Lowest Pulse Rate (BPM)", "49", "Lowest Pulse Rate")],
        ],
        "full_width": [("Duration / Time Window", "00:04:48", "Duration")],
    },
    "Tanita Body Composition (MC-780MA)": {
        "columns": [
            [("Weight (kg)", "78.0", "Weight"), ("Fat Percentage (%)", "18.5", "Fat %"), ("Fat-Free Mass (kg)", "63.5", "FFM")],
            [("Muscle Mass (kg)", "60.2", "Muscle Mass"), ("Total Body Water (kg / %)", "48.2 kg (61.8%)", "TBW"), ("ECW / TBW Ratio", "0.378", "ECW/TBW")],
            [("Visceral Fat Rating", "6", "Visceral Fat"), ("Metabolic Age", "42", "Metabolic Age"), ("Phase Angle", "6.8°", "Phase Angle")],
        ],
    },
    "Push-Up Assessment (VALD ForceDecks)": {
        "columns": [
            [("Peak Push Force (N)", "520 N", "Peak Push Force"), ("Concentric Impulse (Ns)", "310 Ns", "Concentric Impulse")],
            [("Left/Right Symmetry (%)", "96.5%", "L/R Symmetry"), ("Peak Power Output (W)", "680 W", "Peak Power")],
        ],
    },
    "Spirometry (Pulmonary Function)": {
        "columns": [
            [("FVC (L / % Pred)", "4.85 L (104%)", "FVC"), ("FEV1 (L / % Pred)", "3.92 L (102%)", "FEV1")],
            [("FEV1 / FVC Ratio (%)", "80.8%", "FEV1/FVC Ratio"), ("PEF (L/m / % Pred)", "9.4 L/s (98%)", "PEF")],
            [("FEF 25-75% (L/s)", "4.21 L/s", "FEF 25-75"), ("FEF 75% (L/s)", "1.85 L/s", "FEF 75")],
        ],
    },
    "AGE Reader (Advanced Glycation End-Products)": {
        "columns": [
            [("BodyAge", "44 yrs", "BodyAge")],
            [("AGE Level Score", "1.9 AU", "AGE Level Score")],
            [("Variance vs. Average", "-8%", "Variance")],
        ],
    },
    "12-Lead ECG (Electrocardiogram)": {
        "columns": [
            [("Heart Rate (BPM)", "58 BPM", "Heart Rate"), ("PR Interval (ms)", "162 ms", "PR Interval")],
            [("QRS Duration (ms)", "92 ms", "QRS Duration"), ("QTc Interval (ms)", "410 ms", "QTc Interval")],
            [("Rhythm & Axis", "Normal Sinus Rhythm, Normal Axis", "Rhythm & Axis")],
        ],
    },
    "Autonomic / HRV (3-Min Rest, BP, Respiration)": {
        "columns": [
            [("RMSSD (ms)", "52 ms", "RMSSD"), ("SDNN (ms)", "64 ms", "SDNN")],
            [("Respiration Rate (breaths/min)", "12 breaths/min", "Respiration Rate"), ("Blood Pressure (mmHg)", "118/76 mmHg", "Blood Pressure")],
        ],
    },
    "VALD ForceDecks - Sit-to-Stand": {
        "columns": [
            [("Peak Concentric Force (N)", "780 N", "Peak Concentric Force"), ("Transition Time (s)", "0.62 s", "Transition Time")],
            [("Concentric RFD (N/s)", "1450 N/s", "Concentric RFD"), ("Limb Asymmetry (%)", "4.2%", "Limb Asymmetry")],
        ],
    },
    "VALD ForceDecks - Multi-Rep Squat": {
        "columns": [
            [("Peak Force (N)", "849 N", "Peak Force"), ("Concentric Impulse (Ns)", "412 Ns", "Concentric Impulse")],
            [("Eccentric Impulse (Ns)", "405 Ns", "Eccentric Impulse"), ("Left/Right Asymmetry (%)", "13.0%", "L/R Asymmetry")],
        ],
    },
    "VALD ForceDecks - Single Leg Stance / Balance": {
        "columns": [
            [("Left Sway Velocity (mm/s)", "14.2 mm/s", "Left Sway Velocity"), ("Right Sway Velocity (mm/s)", "12.8 mm/s", "Right Sway Velocity")],
            [("Left Ellipse Area (mm²)", "185 mm²", "Left Ellipse Area"), ("Right Ellipse Area (mm²)", "160 mm²", "Right Ellipse Area")],
        ],
    },
    "VALD ForceDecks - Countermovement Jump (CMJ)": {
        "columns": [
            [("Jump Height (cm)", "34.5 cm", "Jump Height"), ("Peak Power / Mass (W/kg)", "48.2 W/kg", "Peak Power/Mass")],
            [("Modified RSI", "0.58", "Modified RSI"), ("Peak Force Asymmetry (%)", "3.8%", "Peak Force Asymmetry")],
            [("Eccentric Peak Force (N)", "1420 N", "Eccentric Peak Force"), ("Eccentric RFD (N/s)", "4200 N/s", "Eccentric RFD")],
        ],
    },
    "VALD ForceDecks - Quiet Stand (Balance)": {
        "columns": [
            [("Total Path Length (mm)", "310 mm", "Total Path Length"), ("Mean Velocity (mm/s)", "5.2 mm/s", "Mean Velocity")],
            [("AP Sway Range (mm)", "24.5 mm", "AP Sway Range"), ("Weight Distribution Asymmetry (%)", "2.1%", "Weight Distribution Asymmetry")],
        ],
    },
}

MODULES = [
    {
        "state_key": "ta_mod1",
        "heading": "### 🫀 Module 1: Cardiorespiratory & Autonomic",
        "match": lambda t: any(x in t for x in ["SpO2", "Spirometry", "ECG", "Autonomic / HRV"]),
        "button": "Draft Cardiorespiratory Review",
        "button_key": "btn_mod1",
        "empty_msg": "No cardiorespiratory tests queued yet.",
        "spinner": "Synthesizing cardiorespiratory clinical review...",
        "role": "an expert clinical cardiologist and longevity physician",
        "domain": "Cardiorespiratory and Autonomic function",
        "edit_label": "Edit Cardiorespiratory Clinical Review (HTML)",
    },
    {
        "state_key": "ta_mod2",
        "heading": "### ⚖️ Module 2: Body Composition & Metabolic Age",
        "match": lambda t: any(x in t for x in ["Tanita", "AGE Reader"]),
        "button": "Draft Body Comp & Metabolic Review",
        "button_key": "btn_mod2",
        "empty_msg": "No body composition or metabolic tests queued yet.",
        "spinner": "Synthesizing metabolic and body composition clinical review...",
        "role": "an expert clinical metabolic specialist and longevity physician",
        "domain": "Body Composition and AGE Reader metrics",
        "edit_label": "Edit Body Comp & Metabolic Clinical Review (HTML)",
    },
    {
        "state_key": "ta_mod3",
        "heading": "### 🏋️ Module 3: Biomechanical & Neuromuscular Function",
        "match": lambda t: "VALD" in t or "Push-Up" in t,
        "button": "Draft Biomechanical Review",
        "button_key": "btn_mod3",
        "empty_msg": "No biomechanical or force plate tests queued yet.",
        "spinner": "Synthesizing biomechanical and neuromuscular review...",
        "role": "an expert clinical biomechanist and sports physiologist",
        "domain": "Biomechanical and Neuromuscular Function",
        "edit_label": "Edit Biomechanical Clinical Review (HTML)",
    },
]

REPORT_TEMPLATE = """
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
            const views = ['clinical', 'plain', 'plan'];
            views.forEach(function (v) {{
                document.getElementById('card-' + v).style.display = (v === viewName) ? 'block' : 'none';
                document.getElementById('btn-' + v).classList.toggle('active', v === viewName);
            }});
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
                {plan_section}
            </div>

            <h2 style="color: #0f382b; font-size: 20px; margin-bottom: 15px;">Completed Diagnostic Assessments ({tests_count})</h2>
            {tests_html}
        </div>
        <div class="footer">&copy; {year} Chudleigh Health Hub. Expert Clinical Longevity Platform. All rights reserved.</div>
    </div>
</body>
</html>
"""


def build_report(participant_name, age_gender, assessment_date, body_mass_height, tests, state, prices, unlock_flags):
    """Build the patient report HTML.

    Returns (report_html, sanitised_text_by_key, raw_plans_by_tier). `state` is st.session_state.
    """
    tests_html = ""
    for idx, t in enumerate(tests):
        items = [f"<li><b>{esc(k)}:</b> {esc(v)}</li>" for k, v in t["data"].items() if v]
        list_content = "".join(items) or "<li>Metrics extracted directly via clinical inspection.</li>"
        pdf_note_box = ""
        if t.get("pdf_filename"):
            pdf_note_box = (
                '<div style="margin-top: 15px; background: #f0fdf4; border: 1px solid #bbf7d0; padding: 15px; border-radius: 8px;">'
                f'<p style="font-size: 13px; color: #166534; margin: 0;"><b>Official Diagnostic Report Attached:</b> {esc(t["pdf_filename"])} (Reviewed and synthesized by Chudleigh Health Hub clinicians)</p>'
                '</div>'
            )
        tests_html += (
            '<div style="background: #f8fafc; border-left: 4px solid #0f382b; padding: 20px; margin-bottom: 25px; border-radius: 8px; border: 1px solid #e2e8f0;">'
            f'<h3 style="margin-top: 0; color: #0f382b; font-size: 19px;">Test #{idx + 1}: {esc(t["type"])}</h3>'
            f'<ul style="margin-bottom: 15px; color: #334155; padding-left: 20px;">{list_content}</ul>'
            f'{pdf_note_box}'
            '</div>'
        )

    safe = {k: clean_html(state[k]) for k in TEXT_KEYS}
    raw_plans = {tier: safe[f"ta_plan_{tier}"] for tier in TIERS}

    report_html = REPORT_TEMPLATE.format(
        participant_name=esc(participant_name),
        age_gender=esc(age_gender or "Not specified"),
        assessment_date=esc(assessment_date),
        body_mass_height=esc(body_mass_height or "Not specified"),
        master_html=safe["ta_master"] or "<p>Master summary pending.</p>",
        mod1_html=safe["ta_mod1"] or "<p>Cardiorespiratory module pending.</p>",
        mod2_html=safe["ta_mod2"] or "<p>Metabolic module pending.</p>",
        mod3_html=safe["ta_mod3"] or "<p>Biomechanical module pending.</p>",
        plain_english_html=safe["ta_pe"] or "<p>Plain English summary pending.</p>",
        plan_section=build_plan_section(raw_plans, unlock_flags, {t: fmt_price(p) for t, p in prices.items()}),
        tests_count=len(tests),
        tests_html=tests_html,
        year=datetime.date.today().year,
    )
    return report_html, safe, raw_plans


# ==========================================
# CLINICIAN AUTHENTICATION
# ==========================================
def clinician_gate() -> bool:
    if not CLINICIAN_PASSWORD:
        st.error("The clinician dashboard is disabled because CLINICIAN_PASSWORD is not configured on the server.")
        return False

    authed_at = st.session_state.get("clinician_auth_at")
    if authed_at and time.time() - authed_at < CLINICIAN_SESSION_SECONDS:
        st.session_state.clinician_auth_at = time.time()  # sliding idle timeout
        return True
    if authed_at:
        st.session_state.pop("clinician_auth_at", None)
        st.info("Your clinician session timed out. Please sign in again.")

    st.subheader("🔐 Clinician Sign-In")
    with st.form("clinician_login"):
        password = st.text_input("Clinician password", type="password")
        submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)

    if submitted:
        ip = client_ip()
        remaining = max(lockout_remaining("clinician-ip", ip), lockout_remaining("clinician-global", "dashboard"))
        if remaining:
            st.error(f"Too many failed attempts. Try again in {math.ceil(remaining / 60)} minute(s).")
            return False
        ok = hmac.compare_digest(
            hashlib.sha256(password.encode("utf-8")).digest(),
            hashlib.sha256(CLINICIAN_PASSWORD.encode("utf-8")).digest(),
        )
        if ok:
            clear_attempts("clinician-ip", ip)
            st.session_state.clinician_auth_at = time.time()
            log.info("Clinician signed in")
            audit("clinician_login")
            st.rerun()
        record_failed_attempt("clinician-ip", ip, MAX_CLINICIAN_ATTEMPTS_PER_IP)
        record_failed_attempt("clinician-global", "dashboard", MAX_CLINICIAN_ATTEMPTS_GLOBAL, delay=False)
        log.warning("Failed clinician sign-in")
        st.error("Incorrect password.")
    return False


# --- URL ROUTING & NAVIGATION ---
is_patient_link = st.query_params.get("portal") == "true"

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
if app_mode == "Clinician Dashboard" and clinician_gate():
    if st.sidebar.button("🚪 Sign out", use_container_width=True):
        for k in ["clinician_auth_at", "participant_tests", "dr_export", *TEXT_KEYS]:
            st.session_state.pop(k, None)
        st.rerun()

    st.sidebar.subheader("Active Participant Queue")

    if st.sidebar.button("🔄 Clear All Tests / New Patient", use_container_width=True):
        st.session_state.participant_tests = []
        for k in TEXT_KEYS:
            st.session_state[k] = ""
        st.rerun()

    st.sidebar.markdown(f"**Tests Queued:** {len(st.session_state.participant_tests)}")
    for idx, t in enumerate(st.session_state.participant_tests):
        st.sidebar.markdown(f"<div class='test-card'><b>{idx+1}. {esc(t['type'])}</b></div>", unsafe_allow_html=True)

    st.subheader("📋 Participant Metadata & Security PIN")
    col1, col2 = st.columns(2)

    with col1:
        participant_name = st.text_input("Participant Full Name", placeholder="e.g. John Evans", key="p_name", max_chars=120)
        age_gender = st.text_input("Age / Gender / DOB", placeholder="e.g. 48 yrs / Male / 15/03/1978", key="p_ag", max_chars=120)

    with col2:
        assessment_date = st.date_input("Assessment Date", value=datetime.date.today(), key="p_date")
        patient_pin = st.text_input(
            f"Patient Secure PIN ({MIN_NEW_PIN_LENGTH}-{MAX_PIN_LENGTH} digits)",
            type="password", placeholder="••••••", key="p_pin", max_chars=MAX_PIN_LENGTH,
            help="Required for new participants. For existing participants, leave blank to keep their current PIN.",
        )

    body_mass_height = st.text_input("Body Mass / Height / BMI", placeholder="e.g. 78 kg / 175 cm / 25.4", key="p_bm", max_chars=120)

    # --- EXISTING PROFILE & LONGITUDINAL HISTORY CHECK (cached for 60s) ---
    c_key = patient_key(participant_name)
    if participant_name and not c_key:
        st.warning("This name can't be used as a record key (it must not contain '/' and must be under 200 characters).")

    existing_profile = False
    existing_info = None
    previous_scan = None
    confirm_same_person = False
    if c_key and db:
        try:
            existing_info, previous_scan = lookup_history(c_key)
            existing_profile = existing_info is not None
            if previous_scan:
                st.markdown(
                    f"""
                    <div class='history-box'>
                        <b>📈 Longitudinal History Detected:</b> Found previous assessment on <b>{esc(previous_scan.get('assessment_date'))}</b> with {esc(previous_scan.get('tests_count'))} test(s) on file. Comparative progress analysis will be integrated into the synthesis.
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            if existing_profile:
                prev_details = ""
                if previous_scan:
                    prev_details = (
                        f" The previous scan recorded: age/gender \"{previous_scan.get('age_gender') or 'not specified'}\", "
                        f"body metrics \"{previous_scan.get('body_mass_height') or 'not specified'}\"."
                    )
                st.warning(
                    "An existing record matches this name. Publishing will add a scan to that record, and whoever signs in with "
                    "that name and PIN will see it. Records are matched by name only." + prev_details
                )
                confirm_same_person = st.checkbox(
                    "I have checked that this is the same person as the existing record",
                    key=f"confirm_same::{c_key}",
                )
                if existing_info.get("pin_weak"):
                    st.warning("This participant still has a short legacy PIN. Enter a new 6-8 digit PIN above to replace it.")
        except Exception:
            log.exception("History lookup failed")
            st.warning("Could not check for previous scans.")

    st.divider()

    assessment_type = st.selectbox("Select Diagnostic Assessment Type", list(ASSESSMENTS.keys()))

    st.subheader(f"📊 Input Data: {assessment_type}")

    uploaded_pdf = st.file_uploader(
        f"📎 Upload Official {assessment_type} PDF Report (Attached for Clinical Review)",
        type=["pdf"],
        key=f"pdf_{assessment_type}"
    )

    st.caption(
        "Uploaded PDFs are sent to Google's Gemini service to help draft the review, then deleted from it. "
        "Where possible, avoid uploading reports that show the participant's name or date of birth."
    )
    pdf_bytes_content = None
    pdf_filename_str = None

    if uploaded_pdf is not None:
        data = uploaded_pdf.getvalue()
        if len(data) > MAX_PDF_BYTES:
            st.error(f"PDF is too large ({len(data) / 1024 / 1024:.1f} MB). Maximum is {MAX_PDF_BYTES // 1024 // 1024} MB.")
        elif not data.startswith(b"%PDF-"):
            st.error("That file doesn't look like a valid PDF.")
        else:
            pdf_bytes_content = data
            pdf_filename_str = os.path.basename(uploaded_pdf.name)[:150]
            st.success(f"PDF Loaded Successfully: {pdf_filename_str} ({len(data) / 1024:.1f} KB)")

    spec = ASSESSMENTS[assessment_type]
    test_payload_data = {}
    for col, fields in zip(st.columns(len(spec["columns"])), spec["columns"]):
        with col:
            for label, example, payload_key in fields:
                test_payload_data[payload_key] = st.text_input(label, value="", placeholder=f"e.g. {example}", key=f"in::{assessment_type}::{label}", max_chars=200)
    for label, example, payload_key in spec.get("full_width", []):
        test_payload_data[payload_key] = st.text_input(label, value="", placeholder=f"e.g. {example}", key=f"in::{assessment_type}::{label}", max_chars=200)

    if st.button("➕ Add Assessment to Participant Profile", use_container_width=True):
        if not participant_name:
            st.warning("Please enter the participant's name before adding assessments.")
        elif not any((v or "").strip() for v in test_payload_data.values()):
            st.warning("Please enter at least one measurement before adding this assessment. Blank fields are left out of the report.")
        else:
            st.session_state.participant_tests.append({
                "type": assessment_type,
                "data": {k: (v or "").strip() for k, v in test_payload_data.items()},
                "pdf_filename": pdf_filename_str,
                "pdf_bytes": pdf_bytes_content,
            })
            st.success(f"Successfully added {assessment_type} to {participant_name}'s profile!")
            st.rerun()

    st.divider()

    # ==========================================
    # MODULAR CLINICAL GENERATION ENGINES
    # ==========================================
    st.subheader("🧩 Expert Clinical Review & Synthesis Engine")
    st.markdown("Compile, review, and refine clinical evaluations by physiological domain.")

    for mod in MODULES:
        with st.container():
            st.markdown(mod["heading"])
            mod_tests = [t for t in st.session_state.participant_tests if mod["match"](t["type"])]

            if st.button(mod["button"], use_container_width=True, key=mod["button_key"]):
                if not participant_name:
                    st.warning("Please enter participant name.")
                elif not mod_tests:
                    st.info(mod["empty_msg"])
                elif gemini_ready():
                    drafted = False
                    with st.spinner(mod["spinner"]):
                        file_refs = []
                        try:
                            context_str = f"Participant details (age/sex only; identity withheld): {redact_for_ai(age_gender)}\n"
                            for t in mod_tests:
                                context_str += f"Test: {t['type']} -> Metrics: {json.dumps(t['data'])}\n"
                            file_refs = upload_pdfs(mod_tests)
                            prompt = (
                                f"You are {mod['role']} at Chudleigh Health Hub. "
                                f"Carefully inspect the attached official PDF reports and structured metrics for {mod['domain']}. "
                                "Write a rigorous, exhaustive, and professional clinical breakdown authored strictly by Chudleigh Health Hub clinical analytics, formatted in clean HTML (h3, p, li tags). "
                                "Do not mention any AI models, automated assistants, or third-party tools. "
                                "Return only the HTML fragment, without markdown code fences.\n\n"
                                f"Patient Data:\n{context_str}"
                            )
                            st.session_state[mod["state_key"]] = strip_code_fences(generate([*file_refs, prompt]))
                            drafted = True
                        except PdfAttachError as e:
                            st.error(str(e))
                        except Exception:
                            fail("Drafting failed. Please try again.", f"Generation error in {mod['button_key']}")
                        finally:
                            delete_uploaded(file_refs)
                    if drafted:
                        st.rerun()

            st.text_area(mod["edit_label"], height=180, key=mod["state_key"])

        st.divider()

    # Module 4: Master Synthesis & Plain English Breakdown
    with st.container():
        st.subheader("🎯 Module 4: Master Synthesis & Longitudinal Progress Analysis")
        st.markdown("Synthesize all modules, evaluate historical progress deltas against previous scans, and generate patient-friendly coaching guides.")

        col_gen1, col_gen2 = st.columns(2)
        with col_gen1:
            if st.button("✨ Draft Master Executive Synthesis & Delta Analysis", use_container_width=True, key="btn_master"):
                if not any(st.session_state[k].strip() for k in ("ta_mod1", "ta_mod2", "ta_mod3")):
                    st.warning("Please draft at least one module review first.")
                elif gemini_ready():
                    drafted = False
                    with st.spinner("Synthesizing master executive review and tracking longitudinal progress..."):
                        try:
                            history_context = ""
                            if previous_scan:
                                history_context = (
                                    f"\n\nPREVIOUS SCAN HISTORY (Date: {previous_scan.get('assessment_date')}):\n"
                                    f"Previous Metrics / Summary: {json.dumps(strip_pdf_payloads(previous_scan.get('tests', [])), default=str)}\n"
                                    f"Previous Master Summary: {previous_scan.get('master_html', 'None')}\n"
                                )

                            master_prompt = (
                                "You are the lead longevity physician at Chudleigh Health Hub. "
                                "Synthesize the following modular clinical evaluations into a cohesive, overarching executive clinical review authored strictly by Chudleigh Health Hub clinical analytics, formatted in clean HTML (h3, p, li tags). "
                                "Return only the HTML fragment, without markdown code fences."
                                f"{history_context}\n"
                                "If historical scan data is provided above, you MUST include a dedicated subsection titled '📈 Longitudinal Progress & Delta Analysis' detailing how metrics have shifted since the last scan, evaluating the efficacy of the previous period's focus areas.\n\n"
                                f"Current Cardiorespiratory Module:\n{st.session_state.ta_mod1}\n\n"
                                f"Current Body Composition & Metabolic Module:\n{st.session_state.ta_mod2}\n\n"
                                f"Current Biomechanical Module:\n{st.session_state.ta_mod3}"
                            )
                            st.session_state.ta_master = strip_code_fences(generate(master_prompt))
                            drafted = True
                        except Exception:
                            fail("Drafting failed. Please try again.", "Generation error in master synthesis")
                    if drafted:
                        st.rerun()

        with col_gen2:
            if st.button("🗣️ Draft Plain English Patient Breakdown", use_container_width=True, key="btn_pe"):
                if not st.session_state.ta_master.strip():
                    st.warning("Please generate the Master Executive Synthesis first.")
                elif gemini_ready():
                    drafted = False
                    with st.spinner("Drafting plain English coaching guide..."):
                        try:
                            pe_prompt = (
                                "You are an empathetic longevity physician and health coach at Chudleigh Health Hub. "
                                "Based on the clinical findings and progress deltas below, write an encouraging, crystal-clear, jargon-free summary directly addressed to the participant as authored by Chudleigh Health Hub clinicians. "
                                "Format the output in clean HTML (h3, p, li tags), without markdown code fences, covering exactly these three sections:\n"
                                "1. What this all means for you & your progress over time (The big picture summary)\n"
                                "2. What is good and why this will help (Positive reinforcement of strong metrics or improvements)\n"
                                "3. What you need to work on next (Clear, actionable, prioritized focus areas)\n\n"
                                f"Master Clinical Summary:\n{st.session_state.ta_master}"
                            )
                            st.session_state.ta_pe = strip_code_fences(generate(pe_prompt))
                            drafted = True
                        except Exception:
                            fail("Drafting failed. Please try again.", "Generation error in plain English breakdown")
                    if drafted:
                        st.rerun()

        st.text_area("Edit Master Executive Synthesis (HTML)", height=220, key="ta_master")
        st.text_area("Edit Plain English Breakdown (HTML)", height=220, key="ta_pe")

    st.divider()

    # ==========================================
    # STEP 1 & 2: ACTION PLAN BUILDER & UNLOCK CONTROLS
    # ==========================================
    st.subheader("🚀 Step 1 & 2: Tiered Action Plans & Portal Access Control")
    st.markdown("Configure tier pricing, generate progressive roadmaps, and select which tiers are unlocked for the participant.")

    price_inputs = {}
    for col, tier in zip(st.columns(3), TIERS):
        with col:
            price_inputs[tier] = st.text_input(f"{tier}-Day Tier Price (£)", value=TIER_INFO[tier]["default_price"], key=f"p_{tier}", max_chars=10)
    prices = {tier: parse_price(v) for tier, v in price_inputs.items()}
    bad_prices = [tier for tier, p in prices.items() if p is None]
    if bad_prices:
        st.warning(f"Invalid price for the {', '.join(bad_prices)}-day tier(s). Enter an amount between £0.50 and £10,000.")
    if existing_info:
        stored_prices = {t: parse_price(existing_info.get(f"price_{t}")) for t in TIERS}
        if any(stored_prices[t] is not None and stored_prices[t] != prices[t] for t in TIERS):
            st.warning(
                "Stored prices for this participant: "
                + ", ".join(f"{t}-day £{fmt_price(stored_prices[t])}" for t in TIERS)
                + ". Publishing will replace them with the prices entered above."
            )

    if st.button("✨ Draft Prioritized 30/60/90-Day Tiered Plans", use_container_width=True, key="btn_tier_plans"):
        if not participant_name:
            st.warning("Please enter participant name.")
        elif not st.session_state.ta_master.strip():
            st.warning("Please generate the Master Executive Synthesis first.")
        elif gemini_ready():
            drafted = False
            with st.spinner("Building prioritized tiered action plans based on longitudinal shifts..."):
                try:
                    plan_prompt = (
                        "You are an expert longevity physician and health strategist at Chudleigh Health Hub. "
                        "Based on the master clinical review and longitudinal progress below, build a progressive 30-Day, 60-Day, and 90-Day Action Plan. "
                        "Prioritize the biggest clinical vulnerabilities or delta shifts that need attention first in the 30-day plan, "
                        "followed by secondary integrations in the 60-day plan, and long-term fine-tuning in the 90-day plan. "
                        "Return your response strictly as a JSON object with three keys: 'plan_30', 'plan_60', and 'plan_90'. "
                        "Each value must be a string of clean HTML (using h3, p, and li tags).\n\n"
                        f"Master Clinical Review:\n{st.session_state.ta_master}"
                    )
                    plan_data = json.loads(strip_code_fences(generate(plan_prompt, json_mode=True)))
                    if not isinstance(plan_data, dict):
                        raise ValueError("Plan response was not a JSON object")
                    for tier in TIERS:
                        value = plan_data.get(f"plan_{tier}", "")
                        st.session_state[f"ta_plan_{tier}"] = value if isinstance(value, str) else json.dumps(value)
                    drafted = True
                except Exception:
                    fail("Generating tiered plans failed. Please try again.", "Generation error in tiered plans")
            if drafted:
                st.rerun()

    for tier in TIERS:
        st.markdown(TIER_INFO[tier]["editor_heading"])
        st.text_area(f"Edit {tier}-Day Plan (HTML)", height=180, key=f"ta_plan_{tier}")

    st.markdown("---")
    st.markdown("#### 🔓 Patient Portal Unlock Tiers")
    st.caption("Ticking a plan unlocks it. Plans a participant has already paid for stay unlocked when you publish again.")
    unlock_flags = {
        tier: st.checkbox(f"Unlock {tier}-Day Plan in Patient Portal", value=TIER_INFO[tier]["default_unlocked"], key=f"chk_unl_{tier}")
        for tier in TIERS
    }

    st.divider()

    # --- REVIEW, APPROVE & PUBLISH ---
    st.markdown("#### ✅ Review & Approve")
    if st.checkbox("👁️ Preview the report as the participant will see it", key="chk_preview"):
        if participant_name:
            preview_html, _, _ = build_report(
                participant_name, age_gender, assessment_date, body_mass_height,
                st.session_state.participant_tests, st.session_state, prices, unlock_flags,
            )
            components.html(preview_html, height=700, scrolling=True)
        else:
            st.info("Enter the participant's name to preview the report.")

    approver = st.text_input("Approving clinician (full name)", key="approver_name", max_chars=80)
    approved = st.checkbox(
        "I confirm a clinician has reviewed and approved this report, including all AI-assisted drafting, before it is released to the participant.",
        key="chk_approved",
    )

    # --- PUBLISH & SYNC TO GOOGLE CLOUD (LONGITUDINAL SUBCOLLECTION) ---
    if st.button("💾 Publish & Sync New Scan & Tiered Plans to Cloud", type="primary", use_container_width=True):
        pin = (patient_pin or "").strip()
        if not participant_name or not c_key:
            st.warning("Please ensure a valid participant name is entered.")
        elif pin and not re.fullmatch(rf"[0-9]{{{MIN_NEW_PIN_LENGTH},{MAX_PIN_LENGTH}}}", pin):
            st.warning(f"The PIN must be {MIN_NEW_PIN_LENGTH}-{MAX_PIN_LENGTH} digits.")
        elif not pin and not existing_profile:
            st.warning(f"New participants need a {MIN_NEW_PIN_LENGTH}-{MAX_PIN_LENGTH} digit security PIN.")
        elif existing_profile and not confirm_same_person:
            st.warning("An existing record matches this name. Please tick the box confirming it is the same person before publishing.")
        elif bad_prices:
            st.warning("Please fix the tier prices before publishing.")
        elif not (approver or "").strip() or not approved:
            st.warning("Please enter the approving clinician's name and tick the approval box before publishing.")
        elif not db:
            st.error("Database connection unavailable.")
        else:
            try:
                final_html_output, safe, raw_plans = build_report(
                    participant_name, age_gender, assessment_date, body_mass_height,
                    st.session_state.participant_tests, st.session_state, prices, unlock_flags,
                )

                scan_id = str(assessment_date)
                scan_record = {
                    "assessment_date": scan_id,
                    "tests_count": len(st.session_state.participant_tests),
                    "tests": strip_pdf_payloads(st.session_state.participant_tests),
                    "body_mass_height": body_mass_height,
                    "age_gender": age_gender,
                    "master_html": safe["ta_master"],
                    "plain_english_html": safe["ta_pe"],
                    "plan_30_raw": raw_plans["30"],
                    "plan_60_raw": raw_plans["60"],
                    "plan_90_raw": raw_plans["90"],
                    "html_output": final_html_output,
                    "approved_by": approver.strip(),
                    "approved_at": firestore.SERVER_TIMESTAMP,
                }
                record_size = len(json.dumps(scan_record, default=str).encode("utf-8"))
                if record_size > MAX_FIRESTORE_DOC_BYTES:
                    st.error(f"This report is too large to store ({record_size / 1024:.0f} KB). Please shorten the clinical text.")
                else:
                    profile_record = {
                        "name_lower": c_key,
                        "name": participant_name.strip(),
                        **{f"price_{tier}": fmt_price(prices[tier]) for tier in TIERS},
                        # Only ever write True. A missing flag means "locked", and this way publishing can never
                        # re-lock a plan the participant has already paid for (even if a payment lands mid-publish).
                        **{f"unlock_{tier}": True for tier in TIERS if unlock_flags[tier]},
                        "updated_at": firestore.SERVER_TIMESTAMP,
                    }
                    if pin:
                        profile_record.update(pin_fields(pin))

                    profile_ref = db.collection(REPORTS).document(c_key)
                    profile_ref.set(profile_record, merge=True)
                    profile_ref.collection("scans").document(scan_id).set(scan_record)
                    lookup_history.clear()
                    audit("scan_published", c_key, scan_date=scan_id, approved_by=approver.strip())
                    log.info("Published scan %s", scan_id)
                    st.success(f"✨ Scan for {assessment_date} published & synced to cloud historical records!")
            except Exception:
                fail("Publishing failed. Nothing was lost locally; please try again.", "Publish to Firestore failed")

    # --- DATA RIGHTS: EXPORT / DELETE ---
    st.divider()
    with st.expander("🛡️ Data rights: export or delete a participant's records"):
        st.caption("Use this to answer a participant's data access or erasure request. Every export and deletion is written to the audit log.")
        dr_name = st.text_input("Participant full name (exactly as recorded)", key="dr_name", max_chars=120)
        dr_key = patient_key(dr_name)
        if dr_key and db:
            if st.button("📦 Prepare export", key="dr_export_btn"):
                try:
                    st.session_state["dr_export"] = {"key": dr_key, "json": export_participant(dr_key)}
                    audit("data_export", dr_key)
                except LookupError:
                    st.warning("No record found for that name.")
                except Exception:
                    fail("The export failed. Please try again.", "Data export failed")
            export = st.session_state.get("dr_export")
            if export and export["key"] == dr_key:
                st.download_button(
                    "📥 Download export (JSON)",
                    data=export["json"],
                    file_name="participant_export.json",
                    mime="application/json",
                    key="dr_download",
                )

            st.markdown("**Delete this participant's profile and scans** (cannot be undone; payment records are kept for accounting)")
            confirm_text = st.text_input("Type the participant's full name again to confirm", key="dr_confirm", max_chars=120)
            if st.button("🗑️ Permanently delete these records", key="dr_delete_btn"):
                if patient_key(confirm_text) != dr_key:
                    st.warning("The name you typed doesn't match.")
                else:
                    try:
                        deleted_scans = delete_participant(dr_key)
                        audit("participant_deleted", dr_key, scans_deleted=deleted_scans)
                        lookup_history.clear()
                        st.session_state.pop("dr_export", None)
                        st.success(f"Deleted the profile and {deleted_scans} scan(s).")
                    except Exception:
                        fail("The deletion failed. Please try again.", "Participant deletion failed")

# ==========================================
# VIEW 2: SECURE PATIENT MOBILE PORTAL
# ==========================================
elif app_mode == "Secure Patient Mobile Portal":
    st.subheader("📱 Participant Companion Portal")

    # Returning from Stripe checkout: verify payment, then strip the ID from the URL.
    stripe_session_id = st.query_params.get("session_id")
    if stripe_session_id:
        try:
            handle_stripe_return(stripe_session_id)
        except Exception:
            fail("We couldn't verify your payment right now. Please contact Chudleigh Health Hub.", "Stripe return handling failed")
        st.query_params.clear()
        st.query_params["portal"] = "true"

    portal_auth = st.session_state.get("portal_auth")
    if portal_auth and time.time() - portal_auth["at"] > PATIENT_SESSION_SECONDS:
        st.session_state.pop("portal_auth", None)
        portal_auth = None
        st.info("Your session expired. Please sign in again.")

    if not db:
        st.error("The client portal is temporarily unavailable. Please try again later.")

    elif not portal_auth:
        st.markdown("Welcome to the Chudleigh Health Hub client portal. Enter your full name and secure PIN.")
        with st.form("patient_login"):
            col_l1, col_l2 = st.columns(2)
            with col_l1:
                client_lookup = st.text_input("Your Full Name", placeholder="e.g. John Evans", max_chars=120)
            with col_l2:
                client_pin = st.text_input("Your Secure PIN", type="password", placeholder="••••••", max_chars=MAX_PIN_LENGTH)
            submitted = st.form_submit_button("Unlock My Healthspan Portal", type="primary", use_container_width=True)

        if submitted:
            lookup_key = patient_key(client_lookup)
            pin = (client_pin or "").strip()
            limiter_id = lookup_key or "invalid-name"
            ip = client_ip()
            remaining = max(lockout_remaining("patient", limiter_id), lockout_remaining("patient-ip", ip))
            generic_error = "We couldn't verify those details. Please check your name and PIN, or contact Chudleigh Health Hub."

            if remaining:
                st.error(f"Too many failed attempts. Please try again in {math.ceil(remaining / 60)} minute(s).")
            elif not re.fullmatch(rf"[0-9]{{{LEGACY_MIN_PIN_LENGTH},{MAX_PIN_LENGTH}}}", pin) or not lookup_key:
                st.error(generic_error)
            else:
                try:
                    doc_ref = db.collection(REPORTS).document(lookup_key)
                    snap = doc_ref.get()
                    record = snap.to_dict() if snap.exists else None
                    if verify_pin(pin, record):
                        clear_attempts("patient", limiter_id)
                        audit("patient_login", lookup_key)
                        if not record.get("pin_hash"):
                            doc_ref.update(pin_fields(pin))  # migrate legacy plaintext PIN
                        st.session_state.portal_auth = {"key": lookup_key, "at": time.time()}
                        signed_in = True
                    else:
                        record_failed_attempt("patient", limiter_id)
                        record_failed_attempt("patient-ip", ip, MAX_PATIENT_ATTEMPTS_PER_IP, delay=False)
                        signed_in = False
                except Exception:
                    signed_in = None
                    fail("We couldn't reach your records right now. Please try again shortly.", "Patient sign-in failed")
                if signed_in:
                    st.rerun()
                elif signed_in is False:
                    st.error(generic_error)

    else:
        lookup_key = portal_auth["key"]
        st.session_state.portal_auth["at"] = time.time()  # sliding idle timeout

        if st.sidebar.button("🚪 Sign out", use_container_width=True):
            for k in [k for k in st.session_state.keys() if k.startswith(("portal_", "checkout_url_"))]:
                st.session_state.pop(k, None)
            st.rerun()

        load_failed = False
        try:
            profile_ref = db.collection(REPORTS).document(lookup_key)
            snap = profile_ref.get()
            client_data = snap.to_dict() if snap.exists else None
            # Only the dates are listed here; the full report is fetched below for the one scan being viewed.
            scan_ids = [
                d.id for d in profile_ref.collection("scans")
                .order_by("assessment_date", direction=firestore.Query.DESCENDING)
                .select(["assessment_date"])
                .stream()
            ] if client_data else []
        except Exception:
            client_data, scan_ids = None, []
            load_failed = True
            fail("We couldn't load your records right now. Please try again shortly.", "Portal load failed")

        if load_failed:
            pass  # error already shown; keep the participant signed in so they can retry
        elif client_data is None:
            st.session_state.pop("portal_auth", None)
        elif not scan_ids:
            st.warning("No assessment scans found on file.")
        else:
            display_name = client_data.get("name", "")
            selected_scan_date = st.selectbox("Select Assessment Date", scan_ids, key="portal_scan_date")
            try:
                scan_snap = profile_ref.collection("scans").document(selected_scan_date).get()
                scan_data = (scan_snap.to_dict() or {}) if scan_snap.exists else {}
            except Exception:
                scan_data = {}
                fail("We couldn't load that report right now. Please try again shortly.", "Scan load failed")
            html_output = scan_data.get("html_output") or "<p>Report payload not found.</p>"

            st.success(f"Authentication successful. Welcome back, {display_name}!")
            st.markdown(
                f"""
                <div class='portal-box'>
                    <h3>📋 Longevity Profile &amp; Scan History</h3>
                    <p><b>Participant:</b> {esc(display_name)}</p>
                    <p><b>Viewing Assessment Date:</b> {esc(selected_scan_date)}</p>
                    <p><b>Total Scans On File:</b> {len(scan_ids)}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # --- DYNAMICALLY PATCH TIER UNLOCK STATUS BASED ON LIVE FLAGS ---
            unlocked = {tier: bool(client_data.get(f"unlock_{tier}", False)) for tier in TIERS}
            prices = {tier: parse_price(client_data.get(f"price_{tier}", TIER_INFO[tier]["default_price"])) for tier in TIERS}
            raw_plans = {tier: scan_data.get(f"plan_{tier}_raw", "") for tier in TIERS}
            plan_section = build_plan_section(raw_plans, unlocked, {t: fmt_price(p) for t, p in prices.items()})

            start_idx = html_output.find(PLAN_START)
            end_idx = html_output.find(PLAN_END)
            if start_idx != -1 and end_idx > start_idx:
                html_output = html_output[:start_idx] + plan_section + html_output[end_idx + len(PLAN_END):]

            safe_file_name = re.sub(r"[^A-Za-z0-9_-]+", "_", display_name).strip("_") or "Participant"
            st.download_button(
                label=f"📥 Download Report ({selected_scan_date})",
                data=html_output,
                file_name=f"{safe_file_name}_{selected_scan_date}_Healthspan_Report.html",
                mime="text/html",
                use_container_width=True,
            )

            # --- STRIPE CHECKOUT (created only when the patient asks to pay) ---
            locked = [tier for tier in TIERS if not unlocked[tier]]
            if locked and stripe.api_key:
                st.subheader("🔓 Unlock Your Action Plans")
                for col, tier in zip(st.columns(len(locked)), locked):
                    with col:
                        price = prices[tier]
                        title = TIER_INFO[tier]["title"]
                        url_key = f"checkout_url_{tier}"
                        if price is None:
                            st.caption(f"{title}: please contact Chudleigh Health Hub to unlock.")
                        elif st.session_state.get(url_key):
                            st.link_button(f"💳 Continue to secure payment (£{fmt_price(price)})", st.session_state[url_key],
                                           type="primary", use_container_width=True)
                        elif st.button(f"💳 Unlock {title} (£{fmt_price(price)})", key=f"buy_{tier}", use_container_width=True):
                            try:
                                st.session_state[url_key] = create_checkout_url(lookup_key, tier, price)
                                created = True
                            except Exception:
                                created = False
                                fail("We couldn't start the payment. Please try again shortly.", "Stripe checkout creation failed")
                            if created:
                                st.rerun()

            st.subheader(f"🔎 Clinical Healthspan Dashboard ({selected_scan_date})")
            components.html(html_output, height=800, scrolling=True)
