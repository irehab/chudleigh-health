"""Shared report drafts: one Longevity report filled in two halves, from two devices.

The health checks half (Tanita, ECG, spirometry, AGE Reader and so on) can be added on one device, and the force plate half
(VALD) on another. Both save into the same draft, which is kept in the database until the report is published or discarded.
Nothing in a draft is shown to the participant. This module holds the parts with no screen or database in them, so they can be tested.
"""
from __future__ import annotations

import secrets

FORCE_PLATES = "Force plates"
HEALTH_CHECKS = "Health checks"
HALVES = (HEALTH_CHECKS, FORCE_PLATES)
DRAFT_KEEP_DAYS = 30          # a draft not touched for this long is deleted, with its files

# What a test in a draft keeps (the PDF itself is stored separately, under pdf_ref).
TEST_FIELDS = ("uid", "type", "data", "pdf_filename", "pdf_ref", "from_reader", "extra", "printed_ranges", "source", "added_by")

# The VALD Test Metrics export (pdf_reader/vald_csv.py) -> the Longevity report's force plate boxes. Only boxes whose meaning
# matches the export's column are filled; the rest are left for the clinician. "bw" is the body weight on the plate.
CSV_TO_BOXES = {
    "CMJ": ("VALD ForceDecks - Countermovement Jump (CMJ)",
            {"Jump Height": "jump_height", "Peak Power/Mass": "peak_power_bm", "Modified RSI": "rsi_mod",
             "Braking Impulse Asymmetry": "ecc_decel_impulse_asym", "Push-off Impulse Asymmetry": "con_impulse_asym",
             "Landing Force Asymmetry": "landing_force_asym", "Body Weight": "bw"}),
    "QSB": ("VALD ForceDecks - Quiet Stand (Balance)",
            {"Mean Velocity": "mean_velocity", "Side-to-Side Sway": "cop_ml", "AP Sway Range": "cop_ap", "Weight Asymmetry": "mean_force_asym"}),
    "SQT": ("VALD ForceDecks - Multi-Rep Squat",
            {"Standing-up Impulse Asymmetry": "con_impulse_asym", "Body Weight": "bw"}),
    "PUSHUPT": ("Push-Up Assessment (VALD ForceDecks)",
                {"Push-up Impulse Asymmetry": "con_impulse_asym"}),
    "SLSB": ("VALD ForceDecks - Single Leg Stance / Balance",
             {"Left Sway Velocity": "mean_velocity_l", "Right Sway Velocity": "mean_velocity_r",
              "Left Side-to-Side Sway": "cop_ml_l", "Right Side-to-Side Sway": "cop_ml_r",
              "Left Front-to-Back Sway": "cop_ap_l", "Right Front-to-Back Sway": "cop_ap_r"}),
    "STSTS": ("VALD ForceDecks - Sit-to-Stand",
              {"Time to Stand": "time_to_stand", "Limb Asymmetry": "standing_force_asym", "Body Weight": "bw"}),
}


def half_of(assessment_type: str) -> str:
    return FORCE_PLATES if "VALD ForceDecks" in (assessment_type or "") else HEALTH_CHECKS


def new_uid() -> str:
    return secrets.token_hex(8)


def boxes_from_csv_row(row, display) -> tuple[str, dict] | None:
    """(assessment type, {box: text}) for one VALD export test, or None if none of its results fill a report box.
    `display` turns a stored metric into text, e.g. '9.7% R' (vald_csv.display)."""
    spec = CSV_TO_BOXES.get(row.code)
    if not spec:
        return None
    assessment, boxes = spec
    data = {}
    for box, metric in boxes.items():
        if metric == "bw":
            if row.body_weight:
                data[box] = f"{row.body_weight:g}"
        elif metric in row.metrics:
            data[box] = display(row.metrics[metric])
    if not any(k != "Body Weight" for k in data):
        return None
    return assessment, data


def for_storage(test: dict) -> dict:
    """A queued test as kept in the draft: no PDF bytes."""
    return {k: test.get(k) for k in TEST_FIELDS if test.get(k) not in (None, "", [], {})}


def merge_tests(saved: list, local: list, removed: set) -> list:
    """The draft's tests after this device saves: the saved ones (less any this device removed), then this device's new ones.
    Order is kept: saved first, in their order, then new ones as added here."""
    seen = set()
    out = []
    for t in saved or []:
        uid = t.get("uid")
        if uid and uid not in removed and uid not in seen:
            seen.add(uid)
            out.append(t)
    for t in local or []:
        uid = t.get("uid")
        if uid and uid not in removed and uid not in seen:
            seen.add(uid)
            out.append(t)
    return out


def counts(tests: list) -> dict:
    """{half: number of tests}."""
    out = {h: 0 for h in HALVES}
    for t in tests or []:
        out[half_of(t.get("type", ""))] += 1
    return out


def draft_label(d: dict) -> str:
    """'John Evans, 26 Oct 2026: 4 health checks, 3 force plates'."""
    c = counts(d.get("tests") or [])
    name = (d.get("name") or "No name yet").strip()
    when = d.get("date_text") or d.get("date") or ""
    return f"{name}{', ' + when if when else ''}: {c[HEALTH_CHECKS]} health check{'s' if c[HEALTH_CHECKS] != 1 else ''}, " \
           f"{c[FORCE_PLATES]} force plate test{'s' if c[FORCE_PLATES] != 1 else ''}"
