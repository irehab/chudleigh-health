"""Care messages to patients: "have you done your exercises?", "your re-test is due" and "new results are ready", by email, text or both.

Run as a Cloud Run job, started by Cloud Scheduler:
    python reminders.py                  emails (9am)
    python reminders.py --channel sms    texts (6pm, when people are home and more likely to do their exercises)
    add --dry-run to log how many would be sent, without sending anything or recording it
The app itself sends "new results are ready" when a clinician publishes (build_email / build_sms with "results").

Only care messages, only to patients whose record says they agreed to them (care_messages_ok), and never any health details:
just that something is waiting, or that it is time for something agreed with their clinician. Nothing here markets anything.
Emails are plain text with no links, and texts carry no links either, so the services sending them have nothing to track.
"""
from __future__ import annotations

import datetime
import logging
import os
import sys

import mailer
import sms
from helpers import short_ref

REPORTS = "longevity_reports"
REMINDER_EVERY_DAYS = {"weekly": 7, "fortnightly": 14}       # exercise reminders; "off" (or nothing) means none
REMINDER_CHOICES = {"off": "No reminders", "weekly": "Weekly", "fortnightly": "Every 2 weeks"}
CHANNELS = ("email", "sms")
CHANNEL_CHOICES = {("email",): "Email", ("sms",): "Text message", ("email", "sms"): "Email and text"}
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


def channels(profile: dict) -> tuple:
    """How this patient wants care messages: ("email",), ("sms",) or both. Email unless they chose otherwise."""
    chosen = tuple(c for c in CHANNELS if c in (profile.get("reminder_channels") or ["email"]))
    return chosen or ("email",)


def _sent_key(kind: str, channel: str) -> str:
    return kind if channel == "email" else f"{kind}:{channel}"   # emails keep the plain names used before texts existed


def can_reach(profile: dict, channel: str) -> bool:
    return bool(profile.get("care_messages_ok")) and channel in channels(profile) and bool(profile.get("email" if channel == "email" else "mobile"))


def due(profile: dict, today: datetime.date, channel: str = "email") -> list:
    """Which reminders this patient should get today on this channel: a list of "exercise" and/or "retest". Pure, so it can be tested.

    Exercise: only with care consent, this channel chosen (with an email or mobile for it), an exercise link and reminders switched on;
    not after the programme's end date; not if a reminder went out on this channel (or the programme was set, or the patient ticked
    their exercises off) within the reminder gap. Re-test: once per channel, on or after the re-test date agreed with the clinician."""
    if not can_reach(profile, channel):
        return []
    sent = profile.get("last_reminders") or {}
    kinds = []
    every = REMINDER_EVERY_DAYS.get(profile.get("exercise_reminders") or "off")
    until = _date(profile.get("exercise_until"))
    if every and profile.get("exercise_link") and (not until or today <= until):
        recent = [d for d in (_date(sent.get(_sent_key("exercise", channel))), _date(profile.get("exercise_set_on")),
                              *(_date(x) for x in (profile.get("exercise_done") or []))) if d]
        if not any((today - d).days < every for d in recent):
            kinds.append("exercise")
    retest = _date(profile.get("retest_due"))
    last_retest = _date(sent.get(_sent_key("retest", channel)))
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


SMS_TEXTS = {   # each must fit in one text (160 characters) and has no link and no "STOP" code
    "exercise": "Chudleigh Health Hub: time for your exercises. Your programme is in your patient portal at chudleighhealth.com. Turn off texts in Message settings.",
    "retest": f"Chudleigh Health Hub: your re-test is now due. Please call {PHONE.replace(' ', '')} or book at chudleighhealth.com. Turn off texts in your portal.",
    "results": "Chudleigh Health Hub: new results are ready in your patient portal at chudleighhealth.com. Turn off texts in your portal's Message settings.",
}


def build_sms(kind: str) -> str:
    """The text for one reminder ("exercise", "retest" or "results")."""
    return SMS_TEXTS[kind]


def send_one(kind: str, profile: dict, channel: str, send_email=mailer.send, send_sms=sms.send):
    if channel == "email":
        send_email(build_email(kind, profile))
    else:
        send_sms(profile["mobile"], build_sms(kind), tag=kind)


def run(db, today: datetime.date, channel: str = "email", send_email=mailer.send, send_sms=sms.send) -> int:
    """Send today's reminders on one channel. Returns how many were sent. Each one is recorded on the patient's record (so it is
    never sent twice) and in the audit log (without the patient's name)."""
    from google.cloud import firestore
    from google.cloud.firestore_v1.base_query import FieldFilter
    sent = 0
    for snap in db.collection(REPORTS).where(filter=FieldFilter("care_messages_ok", "==", True)).stream():
        profile = snap.to_dict() or {}
        for kind in due(profile, today, channel):
            try:
                send_one(kind, profile, channel, send_email, send_sms)
            except Exception:
                log.exception("Sending a %s reminder by %s failed", kind, channel)
                continue
            last = dict(profile.get("last_reminders") or {})
            last[_sent_key(kind, channel)] = today.isoformat()
            snap.reference.update({"last_reminders": last})
            profile["last_reminders"] = last
            db.collection("audit_log").add({"event": "reminder_sent", "kind": kind, "channel": channel, "patient_ref": short_ref(snap.id),
                                            "at": firestore.SERVER_TIMESTAMP})
            sent += 1
    return sent


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = list(sys.argv[1:] if argv is None else argv)
    channel = args[args.index("--channel") + 1] if "--channel" in args else "email"
    dry_run = "--dry-run" in args
    if channel not in CHANNELS:
        log.error("Unknown channel %r", channel)
        return 2
    if not (mailer.email_on() if channel == "email" else sms.sms_on()):
        log.error("No %s service is set up, so no reminders were sent", channel)
        return 1
    from google.cloud import firestore
    db = firestore.Client(database=os.environ.get("FIRESTORE_DATABASE", "default"))
    today = datetime.datetime.now(datetime.timezone.utc).date()   # it runs during the UK day, when the UK and UTC dates are the same
    if dry_run:
        from google.cloud.firestore_v1.base_query import FieldFilter
        n = sum(len(due(s.to_dict() or {}, today, channel))
                for s in db.collection(REPORTS).where(filter=FieldFilter("care_messages_ok", "==", True)).stream())
        log.info("Dry run: %d reminder(s) would be sent by %s today; nothing was sent", n, channel)
        return 0
    log.info("Reminders sent by %s: %d", channel, run(db, today, channel))
    return 0


if __name__ == "__main__":
    sys.exit(main())
