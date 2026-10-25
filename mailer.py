"""Sending emails to patients (sign-in links now, reminders later).

Any email service that offers SMTP works (Amazon SES in London, Brevo, Mailjet, Google Workspace...), set with these settings:
    SMTP_HOST, SMTP_PORT (default 587), SMTP_USER, SMTP_PASSWORD (keep it in Secret Manager), MAIL_FROM (e.g. "Chudleigh Health Hub <portal@chudleighhealth.com>")
For a test copy on a computer, EMAIL_OUTBOX_DIR instead saves each email as a file in that folder, and nothing is sent.

Emails never carry health details: only that something is waiting in the portal, and a link.
"""
from __future__ import annotations

import os
import smtplib
import ssl
import time
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from helpers import esc

SMTP_HOST = os.environ.get("SMTP_HOST", "").strip()
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587") or 587)
SMTP_USER = os.environ.get("SMTP_USER", "").strip()
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
MAIL_FROM = os.environ.get("MAIL_FROM", "").strip() or formataddr(("Chudleigh Health Hub", "portal@chudleighhealth.com"))
EMAIL_OUTBOX_DIR = os.environ.get("EMAIL_OUTBOX_DIR", "").strip()
SIGNATURE = "Chudleigh Health Hub · 90 Fore Street, Chudleigh, Devon TQ13 0HT · 07902 065739"


def email_on() -> bool:
    """True when emails can be sent (or, on a test copy, saved to the outbox folder)."""
    return bool(SMTP_HOST or EMAIL_OUTBOX_DIR)


def build(to: str, subject: str, lines: list, button_text: str = "", button_url: str = "", footer: str = "", html: bool = True) -> EmailMessage:
    """A short email with a plain-text part and, unless html is False, a simple HTML part. lines: the paragraphs.
    Plain text only (html=False) gives the email service no tracking image and no links to rewrite: used for sign-in codes."""
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = MAIL_FROM, to, subject
    msg["Message-ID"] = make_msgid(domain="chudleighhealth.com")
    text = "\n\n".join(lines + ([f"{button_text}:\n{button_url}"] if button_url else []) + ([footer] if footer else []) + [SIGNATURE])
    msg.set_content(text)
    if not html:
        return msg
    button = (f'<p style="margin:24px 0"><a href="{esc(button_url)}" style="background:#3D7F88;color:#ffffff;text-decoration:none;font-weight:bold;'
              f'padding:12px 22px;border-radius:999px;display:inline-block">{esc(button_text)}</a></p>'
              f'<p style="font-size:13px;color:#5E615F">If the button doesn\'t work, copy this link into your browser:<br>{esc(button_url)}</p>') if button_url else ""
    paras = "".join(f'<p>{esc(p)}</p>' for p in lines)
    foot = f'<p style="font-size:13px;color:#5E615F">{esc(footer)}</p>' if footer else ""
    msg.add_alternative(
        f'<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;color:#3F4140;line-height:1.5;max-width:560px;margin:0 auto;padding:16px">'
        f'<p style="font-size:20px;color:#2F3130;margin:0 0 16px">Chudleigh Health Hub</p>{paras}{button}{foot}'
        f'<hr style="border:none;border-top:1px solid #E2E4E3"><p style="font-size:12px;color:#5E615F">{esc(SIGNATURE)}</p></body></html>',
        subtype="html")
    return msg


def send(msg: EmailMessage):
    """Send the email (raises on failure), or on a test copy save it to the outbox folder."""
    if SMTP_HOST:
        context = ssl.create_default_context()
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context, timeout=20) as s:
                if SMTP_USER:
                    s.login(SMTP_USER, SMTP_PASSWORD)
                s.send_message(msg)
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as s:
                s.starttls(context=context)
                if SMTP_USER:
                    s.login(SMTP_USER, SMTP_PASSWORD)
                s.send_message(msg)
    elif EMAIL_OUTBOX_DIR:
        os.makedirs(EMAIL_OUTBOX_DIR, exist_ok=True)
        with open(os.path.join(EMAIL_OUTBOX_DIR, f"{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns() % 1000000}.eml"), "wb") as f:
            f.write(bytes(msg))
    else:
        raise RuntimeError("No email service is set up (SMTP_HOST)")
