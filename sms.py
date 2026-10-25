"""Sending text messages to patients (reminders), through Brevo's transactional SMS service.

Settings:  BREVO_API_KEY (keep it in Secret Manager), SMS_SENDER (the name the text comes from: up to 11 letters and digits, e.g. "ChudHealth").
For a test copy on a computer, SMS_OUTBOX_DIR instead saves each text as a file in that folder, and nothing is sent.

Texts never carry health details, and never a "STOP" opt-out code: Brevo treats a text with one as marketing. Patients switch
texts off in their portal (Message settings) instead, and each text says so.
"""
from __future__ import annotations

import json
import os
import re
import time

BREVO_SMS_URL = "https://api.brevo.com/v3/transactionalSMS/send"
BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "").strip()
SMS_SENDER = re.sub(r"[^A-Za-z0-9]", "", os.environ.get("SMS_SENDER", "ChudHealth"))[:11] or "ChudHealth"
SMS_OUTBOX_DIR = os.environ.get("SMS_OUTBOX_DIR", "").strip()
MAX_SMS_CHARS = 160          # one text; longer ones cost two


def sms_on() -> bool:
    """True when texts can be sent (or, on a test copy, saved to the outbox folder)."""
    return bool(BREVO_API_KEY or SMS_OUTBOX_DIR)


def brevo_number(mobile: str) -> str:
    """'+447700900123' -> '447700900123' (Brevo wants the country code and digits only)."""
    digits = re.sub(r"\D", "", mobile or "")
    if not 6 <= len(digits) <= 15:
        raise ValueError("not a mobile number")
    return digits


def send(mobile: str, text: str, tag: str = ""):
    """Send one text (raises on failure), or on a test copy save it to the outbox folder."""
    if len(text) > MAX_SMS_CHARS:
        raise ValueError(f"text is {len(text)} characters; the limit is {MAX_SMS_CHARS}")
    body = {"sender": SMS_SENDER, "recipient": brevo_number(mobile), "content": text, "type": "transactional"}
    if tag:
        body["tag"] = tag
    if BREVO_API_KEY:
        import requests
        r = requests.post(BREVO_SMS_URL, json=body, headers={"api-key": BREVO_API_KEY, "accept": "application/json"}, timeout=20)
        if r.status_code >= 300:
            raise RuntimeError(f"Brevo SMS failed with status {r.status_code}")
    elif SMS_OUTBOX_DIR:
        os.makedirs(SMS_OUTBOX_DIR, exist_ok=True)
        with open(os.path.join(SMS_OUTBOX_DIR, f"{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns() % 1000000}.json"), "w", encoding="utf-8") as f:
            json.dump(body, f, indent=1)
    else:
        raise RuntimeError("No text message service is set up (BREVO_API_KEY)")
