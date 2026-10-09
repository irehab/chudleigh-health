"""Pure helper functions for Chudleigh Health Hub.

Nothing in here imports Streamlit, Firestore, Stripe or Gemini, so it can be unit-tested
on its own (see tests/test_helpers.py).
"""
import hashlib
import hmac
import html
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
