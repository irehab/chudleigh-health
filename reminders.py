"""Care emails to patients: "have you done your exercises?", "your re-test is due" and "new results are ready".

Run once a day as a Cloud Run job, started by Cloud Scheduler:   python reminders.py
The app itself sends "new results are ready" when a clinician publishes (build_email("results", ...)).

Only care messages, only to patients whose record says they agreed to them (care_messages_ok), and never any health details:
just that something is waiting, or that it is time for something agreed with their clinician. Nothing here markets anything.
Each email is plain text with no links, so the email service has nothing to track; it names the website instead.
"""
from __future__ import annotations

import datetime
import logging
import os
import sys

import mailer
from helpers import short_ref

REPORTS = "longevity_reports"
REMINDER_EVERY_DAYS = {"weekly": 7, "fortnightly": 14}       # exercise reminders; "off" (or nothing) means none
REMINDER_CHOICES = {"off": "No reminders", "weekly": "Weekly", "fortnightly": "Every 2 weeks"}
WEBSITE = "chudleighhealth.com"
PHONE = "07902 065739"
STOP_LINE = ("To stop these emails, switch them off under \"Message settings\" in your portal, or reply to this email "
             "and we'll do it for you.")
log = logging.getLogger("chudleigh.reminders")


def _date(value):
    try:
        return datetime.date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def due(profile: dict, today: datetime.date) -> list:
    """Which reminders this patient should get today: a list of "exercise" and/or "retest". Pure, so it can be tested on its own.

    Exercise: only with care consent, an email, an exercise link and reminders switched on; not after the programme's end date;
    not if a reminder went out (or the programme was set, or the patient ticked their exercises off) within the reminder gap.
    Re-test: only with care consent and an email, once, on or after the re-test date the clinician agreed with the patient."""
    if not profile.get("care_messages_ok") or not profile.get("email"):
        return []
    sent = profile.get("last_reminders") or {}
    kinds = []
    every = REMINDER_EVERY_DAYS.get(profile.get("exercise_reminders") or "off")
    until = _date(profile.get("exercise_until"))
    if every and profile.get("exercise_link") and (not until or today <= until):
        recent = [d for d in (_date(sent.get("exercise")), _date(profile.get("exercise_set_on")),
                              *(_date(x) for x in (profile.get("exercise_done") or []))) if d]
        if not any((today - d).days < every for d in recent):
            kinds.append("exercise")
    retest = _date(profile.get("retest_due"))
    last_retest = _date(sent.get("retest"))
    if retest and retest <= today and not (last_retest and last_retest >= retest):
        kinds.append("retest")
    return kinds


def build_email(kind: str, profile: dict):
    """The email for one reminder ("exercise", "retest" or "results"). Plain text only."""
    first = (str(profile.get("name") or "").split() or [""])[0].title()
    hello = f"Hello {first}," if first else "Hello,"
    sign_in = f"Sign in to your patient portal at {WEBSITE} (\"Patient login\", at the bottom of any page) with your email address."
    if kind == "exercise":
        subject = "Your exercise reminder from Chudleigh Health Hub"
        lines = [hello, "This is your reminder to keep going with the exercises your clinician gave you.",
                 sign_in + " Your programme opens from there, and you can tick off this week's exercises so we don't remind you again this week.",
                 f"If anything has changed or you have any questions, call us on {PHONE}."]
    elif kind == "retest":
        subject = "Your re-test is due at Chudleigh Health Hub"
        lines = [hello, "The re-test you agreed with your clinician is now due.",
                 f"Please call us on {PHONE}, or book online at {WEBSITE}, to arrange a time that suits you.", sign_in]
    elif kind == "results":
        subject = "New results in your Chudleigh Health Hub portal"
        lines = [hello, "New results from your recent visit are ready in your patient portal.", sign_in,
                 "Your clinician will be happy to talk them through with you."]
    else:
        raise ValueError(f"unknown reminder {kind!r}")
    return mailer.build(profile["email"], subject, lines, footer=STOP_LINE, html=False)


def run(db, today: datetime.date, send=mailer.send) -> int:
    """Send today's reminders. Returns how many were sent. Each one is recorded on the patient's record (so it is never sent twice)
    and in the audit log (without the patient's name)."""
    from google.cloud import firestore
    from google.cloud.firestore_v1.base_query import FieldFilter
    sent = 0
    for snap in db.collection(REPORTS).where(filter=FieldFilter("care_messages_ok", "==", True)).stream():
        profile = snap.to_dict() or {}
        for kind in due(profile, today):
            try:
                send(build_email(kind, profile))
            except Exception:
                log.exception("Sending a %s reminder failed", kind)
                continue
            last = dict(profile.get("last_reminders") or {})
            last[kind] = today.isoformat()
            snap.reference.update({"last_reminders": last})
            profile["last_reminders"] = last
            db.collection("audit_log").add({"event": "reminder_sent", "kind": kind, "patient_ref": short_ref(snap.id), "at": firestore.SERVER_TIMESTAMP})
            sent += 1
    return sent


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not mailer.email_on():
        log.error("No email service is set up (SMTP_HOST), so no reminders were sent")
        return 1
    from google.cloud import firestore
    db = firestore.Client(database=os.environ.get("FIRESTORE_DATABASE", "default"))
    today = datetime.datetime.now(datetime.timezone.utc).date()   # it runs at 9am UK time, when the UK and UTC dates are the same
    log.info("Reminders sent: %d", run(db, today))
    return 0


if __name__ == "__main__":
    sys.exit(main())
