"""Pure helper functions for Chudleigh Health Hub.

Nothing in here imports Streamlit, Firestore, Stripe or Gemini, so it can be unit-tested
on its own (see tests/test_helpers.py).
"""
import hashlib
import hmac
import html
import datetime
import re
import secrets
from decimal import Decimal, InvalidOperation

PIN_HASH_ITERATIONS = 310_000


# --- HTML / text helpers ---
def esc(value) -> str:
    """Escape any user/DB-supplied value before placing it in HTML."""
    return html.escape("" if value is None else str(value), quote=True)


_FENCE_RE = re.compile(r"^\s*```[a-zA-Z]*\s*|\s*```\s*$")


def strip_code_fences(text: str) -> str:
    return _FENCE_RE.sub("", text or "").strip()


# --- Patient record key ---
def patient_key(name: str):
    """Firestore document ID for a participant. Returns None for names that can't be used safely."""
    key = (name or "").strip().lower()
    if not key or len(key) > 200 or "/" in key or key in (".", ".."):
        return None
    if key.startswith("__") and key.endswith("__"):
        return None
    return key


def new_patient_id() -> str:
    """Record ID for a new participant: random, so two people with the same name get separate records, and nothing about
    the person is in it. Lower-case letters, digits and '-' only, so patient_key(id) == id and older checks still accept it."""
    return "p-" + secrets.token_hex(10)


def short_ref(key: str) -> str:
    """Stable, non-reversible reference for audit logs, so logs never contain patient names."""
    return hashlib.sha256((key or "").encode("utf-8")).hexdigest()[:16]


# --- Prices ---
def parse_price(value):
    try:
        d = Decimal(str(value).strip().lstrip("£").strip())
    except (InvalidOperation, ValueError):
        return None
    if not d.is_finite() or d < Decimal("0.50") or d > Decimal("10000"):
        return None
    return d.quantize(Decimal("0.01"))


def fmt_price(d) -> str:
    if d is None:
        return "—"
    return str(int(d)) if d == d.to_integral_value() else f"{d:.2f}"


# --- PIN hashing (PBKDF2-SHA256, per-user salt) ---
def hash_pin(pin: str, salt: bytes = None, iterations: int = PIN_HASH_ITERATIONS):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, iterations)
    return salt.hex(), digest.hex()


def verify_pin(pin: str, record) -> bool:
    if not record:
        hash_pin(pin)  # equalise timing so unknown names can't be detected
        return False
    if record.get("pin_hash") and record.get("pin_salt"):
        _, digest = hash_pin(pin, bytes.fromhex(record["pin_salt"]), int(record.get("pin_iterations", PIN_HASH_ITERATIONS)))
        return hmac.compare_digest(digest, record["pin_hash"])
    legacy = record.get("pin")
    if legacy is not None:
        hash_pin(pin)
        return hmac.compare_digest(str(legacy).strip().encode(), pin.encode())
    return False


# --- Data minimisation for the AI ---
_MONTHS = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_DATE_PATTERNS = [
    re.compile(r"\b\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}\b"),                                  # 15/03/1978, 15-03-78
    re.compile(r"\b\d{4}[/.\-]\d{1,2}[/.\-]\d{1,2}\b"),                                    # 1978-03-15
    re.compile(rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+{_MONTHS},?\s+\d{{2,4}}\b", re.IGNORECASE),   # 15 March 1978
    re.compile(rf"\b{_MONTHS}\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{2,4}}\b", re.IGNORECASE),  # March 15, 1978
]
_SEPARATORS = " /,;|-"


def redact_for_ai(text: str) -> str:
    """Remove date-of-birth style dates from free text before it is sent to the AI.

    '48 yrs / Male / 15/03/1978' -> '48 yrs / Male'
    """
    s = text or ""
    for pattern in _DATE_PATTERNS:
        s = pattern.sub("", s)
    s = re.sub(r"(?:\s*[/,;|]\s*){2,}", " / ", s)  # collapse separators left behind
    s = s.strip(_SEPARATORS)
    return s or "not specified"


# --- Request metadata ---
def client_ip_from_xff(header_value: str) -> str:
    """Pick the client IP from an X-Forwarded-For header.

    On Cloud Run the last entry is the one added by Google's front end; earlier entries can be
    supplied by the client, so they are not trusted. If you later put another proxy or load
    balancer in front of the service, revisit this.
    """
    parts = [p.strip() for p in (header_value or "").split(",") if p.strip()]
    return parts[-1][:64] if parts else "unknown"


# --- Bespoke plans ---
PLAN_STATUSES = ("requested", "in_progress", "delivered")

# What a participant is asked after paying for a plan: (key, question, longest answer allowed, required)
QUESTIONNAIRE_FIELDS = [
    ("goals", "What would you most like to achieve over this period?", 600, True),
    ("injuries", "Any injuries, pain or symptoms we should know about?", 600, False),
    ("health", "Any medical conditions or medication that could affect exercise or lifestyle advice?", 600, False),
    ("exercise", "What exercise do you do now, and how often?", 400, False),
    ("time_equipment", "How much time can you spend, and what do you have access to (gym, home, none)?", 300, False),
    ("sleep_stress", "How are your sleep and stress at the moment?", 300, False),
    ("other", "Anything else you would like us to know?", 500, False),
]
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def add_working_days(start: datetime.date, days: int) -> datetime.date:
    """The date that many working days (Monday to Friday) after start. Bank holidays are not counted."""
    d, left = start, max(0, int(days))
    while left > 0:
        d += datetime.timedelta(days=1)
        if d.weekday() < 5:
            left -= 1
    return d


def friendly_date(iso: str) -> str:
    """'2026-10-19' -> 'Mon 19 Oct 2026'. Anything that is not a date comes back unchanged."""
    try:
        return datetime.date.fromisoformat(str(iso)[:10]).strftime("%a %d %b %Y")
    except ValueError:
        return str(iso or "")


def clean_questionnaire(raw: dict) -> dict:
    """Keep only the known questions, strip control characters, trim, and cut each answer to its limit. Blank answers are dropped."""
    out = {}
    for key, _question, limit, _required in QUESTIONNAIRE_FIELDS:
        value = _CONTROL_CHARS.sub("", str((raw or {}).get(key) or "")).strip()[:limit]
        if value:
            out[key] = value
    return out


def questionnaire_missing(answers: dict) -> list:
    """The questions that must be answered but were not."""
    return [q for key, q, _limit, required in QUESTIONNAIRE_FIELDS if required and not (answers or {}).get(key)]


def plan_text_to_html(text: str) -> str:
    """Turn the plain text a clinician types into simple, safe HTML.

    A blank line starts a new paragraph. A line starting '## ' is a heading. Lines starting '- ' or '* ' are list items.
    **bold** works. HTML comments are removed, and everything else is escaped first, so no HTML can be injected.
    """
    text = re.sub(r"<!--.*?(?:-->|\Z)", "", text or "", flags=re.S)
    out, para, items = [], [], []

    def inline(line: str) -> str:
        return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc(line))

    def flush():
        if para:
            out.append("<p>" + "<br>".join(inline(x) for x in para) + "</p>")
            para.clear()
        if items:
            out.append("<ul>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ul>")
            items.clear()

    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw.strip()
        if not line:
            flush()
            continue
        heading = re.match(r"^#{1,3}\s+(.*)$", line)
        bullet = re.match(r"^[-*\u2022]\s+(.*)$", line)
        if heading:
            flush()
            out.append(f"<h3>{inline(heading.group(1))}</h3>")
        elif bullet:
            if para:
                flush()
            items.append(bullet.group(1))
        else:
            if items:
                flush()
            para.append(line)
    flush()
    return "".join(out)


# --- A clinician's personal note on the report ---
NOTE_MAX = 1500


def clean_note(text, limit: int = NOTE_MAX, single_line: bool = False) -> str:
    """Tidy a note typed by a clinician: no control characters, tidy line endings, trimmed, and cut to the limit.
    With single_line, new lines become spaces (for a name to sign it with)."""
    t = _CONTROL_CHARS.sub("", str(text if text is not None else "")).replace("\r\n", "\n").replace("\r", "\n")
    if single_line:
        t = " ".join(t.split())
    else:
        t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()[:limit].strip()


# --- Device reports (PDFs) kept in a private Google Cloud Storage bucket ---
# These talk to Cloud Storage over its plain web API, with the credentials the app already has, so nothing new needs installing.
# `session` is anything that behaves like a requests session (google.auth.transport.requests.AuthorizedSession in the app).
GCS_UPLOAD_URL = "https://storage.googleapis.com/upload/storage/v1/b/{bucket}/o"
GCS_OBJECT_URL = "https://storage.googleapis.com/storage/v1/b/{bucket}/o/{name}"
MAX_SHARED_PDF_BYTES = 20 * 1024 * 1024         # one report
MAX_SHARED_TOTAL_BYTES = 40 * 1024 * 1024       # all the reports on one scan
_OBJECT_NAME_RE = re.compile(r"^[0-9a-f]{32}\.pdf$")


class StorageError(Exception):
    """A report file could not be stored, fetched or removed."""


def is_pdf(data) -> bool:
    return isinstance(data, (bytes, bytearray)) and bytes(data[:5]) == b"%PDF-"


def new_object_name() -> str:
    """A random name with nothing about the participant in it."""
    return secrets.token_hex(16) + ".pdf"


def valid_object_name(name) -> bool:
    return isinstance(name, str) and bool(_OBJECT_NAME_RE.fullmatch(name))


def safe_download_name(label: str, date_text: str) -> str:
    """The file name a participant is offered: the device and the date, never the original file name (which may carry a name)."""
    base = re.sub(r"[^A-Za-z0-9]+", "_", str(label or "Report")).strip("_")[:60] or "Report"
    day = re.sub(r"[^0-9-]", "", str(date_text or ""))[:10]
    return f"{base}_{day}.pdf" if day else f"{base}.pdf"


def friendly_size(num_bytes) -> str:
    n = int(num_bytes or 0)
    return f"{n / 1024 / 1024:.1f} MB" if n >= 1024 * 1024 else f"{max(1, round(n / 1024))} KB"


def _quote(name: str) -> str:
    from urllib.parse import quote
    return quote(name, safe="")


def gcs_upload(session, bucket: str, name: str, data: bytes) -> None:
    """Store one PDF. Never overwrites an existing object (ifGenerationMatch=0), and checks the stored size matches what was sent."""
    if not valid_object_name(name):
        raise StorageError("invalid object name")
    if not is_pdf(data):
        raise StorageError("not a PDF")
    resp = session.post(GCS_UPLOAD_URL.format(bucket=bucket), params={"uploadType": "media", "name": name, "ifGenerationMatch": "0"},
                        data=bytes(data), headers={"Content-Type": "application/pdf"}, timeout=60)
    if resp.status_code != 200:
        raise StorageError(f"upload failed ({resp.status_code})")
    try:
        stored = int(resp.json().get("size", -1))
    except Exception:
        stored = -1
    if stored != len(data):
        raise StorageError("the stored size does not match")


def gcs_download(session, bucket: str, name: str) -> bytes:
    if not valid_object_name(name):
        raise StorageError("invalid object name")
    resp = session.get(GCS_OBJECT_URL.format(bucket=bucket, name=_quote(name)), params={"alt": "media"}, timeout=60)
    if resp.status_code == 404:
        raise FileNotFoundError(name)
    if resp.status_code != 200:
        raise StorageError(f"download failed ({resp.status_code})")
    return bytes(resp.content)


def gcs_delete(session, bucket: str, name: str) -> bool:
    """Remove one object. True if it was deleted, False if it was already gone. Anything else is an error, so a deletion is never assumed."""
    if not valid_object_name(name):
        raise StorageError("invalid object name")
    resp = session.delete(GCS_OBJECT_URL.format(bucket=bucket, name=_quote(name)), timeout=60)
    if resp.status_code in (200, 204):
        return True
    if resp.status_code == 404:
        return False
    raise StorageError(f"delete failed ({resp.status_code})")
