"""Reader for the ViHealth 'Oxygen Level Report'. The whole report is a picture, so it is read by OCR, table by table, by position.

What is read: the highest, average and lowest oxygen level and pulse rate, and the share of the recording spent in each band (as a
percentage). What is NOT read, on purpose: the date, the start and end times, the duration of the test, and the time spent in each
band. How long the test ran, and when, are not used anywhere. The only date in the app is the assessment date the clinician enters.

Because OCR can misread a digit, every number is checked against the others: the three figures against each other, the percentages in
each table against 100, and the two oxygen band tables against each other. A misread makes a check fail and the status 'check'.
"""
from __future__ import annotations

import re

from . import ocr
from .base import Check, ReadResult, Value, make_value, status_from

DEVICE = "vihealth_oxygen"
LABEL = "ViHealth oxygen level report"
APP_ASSESSMENT = "SpO2 / Pulse Oximetry (ViHealth)"

REGIONS = {
    "top_right": (0.66, 0.085, 0.985, 0.165),
    "left_tables": (0.03, 0.195, 0.34, 0.405),
    "right_table": (0.66, 0.195, 0.985, 0.405),
}
# a table row is a time and a percentage. The time is only used to find the row: it is thrown away, and only the percentage is kept.
_ROW = re.compile(r"(\d{1,2}:\d{2}:\d{2})\s+(\d{1,3})\s*%")
_OX_LEFT = ["95 and above", "90-94", "below 90"]
_PULSE = ["above 120", "50-120", "below 50"]
_OX_RIGHT = ["95-100", "90-94", "80-89", "70-79", "below 70"]
PCT = "%Total as printed"          # the name of a band's percentage in the values


def matches_banner(banner_upper: str) -> bool:
    return "OXYGEN" in banner_upper and "REPORT" in banner_upper


def read_image(data: bytes) -> ReadResult:
    res = ReadResult(device=DEVICE, device_label=LABEL, has_text_layer=False, used_ocr=True)
    if not ocr.available():
        res.status = "no_text"
        res.notes.append("This report is a picture and the text recognition software is not installed, so it was not read.")
        return res
    img = ocr.render(data, 2.0)
    txt = {name: ocr.read_text(ocr.crop(img, box), psm=6) for name, box in REGIONS.items()}
    v: dict = {}

    def put(key, value):
        if value is not None:
            value.source = "ocr"
            v[key] = value
        else:
            res.notes.append(f"Could not read: {key}")

    # highest / average / lowest: two rows of three numbers, oxygen first and pulse second (read by order, because the OCR'd labels are unreliable)
    triplets = [m for m in (re.search(r"(\d{1,3})\s+(\d{1,3})\s+(\d{1,3})\s*$", line.strip()) for line in txt["top_right"].splitlines()) if m]
    for (name, unit_txt, unit), m in zip((("Oxygen level", "(%)", "%"), ("Pulse rate", "(/min)", "")), triplets + [None, None]):
        for i, which in enumerate(("highest", "average", "lowest")):
            put(f"{name}, {which} {unit_txt}", make_value(m.group(i + 1) + unit) if m else None)

    # band tables: rows are read by their position, because OCR garbles symbols such as >= and <
    def rows(text):
        return _ROW.findall(text)

    left_lines = txt["left_tables"].splitlines()
    split = next((i for i, l in enumerate(left_lines) if re.search(r"Pulse", l, re.I)), len(left_lines))
    ox_rows, pulse_rows = rows("\n".join(left_lines[:split])), rows("\n".join(left_lines[split:]))
    right_rows = rows(txt["right_table"])
    m = re.search(r"Oxygen\s*Level:?\s*(\d{2,3})", txt["left_tables"])
    if m:
        v["Oxygen level shown in the band table heading (%)"] = make_value(m.group(1) + "%")
        v["Oxygen level shown in the band table heading (%)"].source = "ocr"

    def band(prefix, names, found):
        if len(found) != len(names):
            res.notes.append(f"Could not read: {prefix} bands (found {len(found)} of {len(names)} rows)")
            return
        for name, (_time, pct) in zip(names, found):
            v[f"{prefix} {name}: {PCT}"] = Value(text=f"{pct}%", number=float(pct), unit="%", source="ocr")

    band("Oxygen", _OX_LEFT, ox_rows)
    band("Pulse", _PULSE, pulse_rows)
    band("Oxygen, second table,", _OX_RIGHT, right_rows)
    res.values = v

    res.checks = run_checks(res)
    res.notes.append("Read by text recognition from a picture. The chart lines are graphics and are not read. "
                     "The date, the times and how long the test ran are not read or used.")
    res.status = status_from(res)
    return res


def _pcts(res, prefix, names):
    vals = [res.number(f"{prefix} {n}: {PCT}") for n in names]
    return None if any(x is None for x in vals) else vals


def run_checks(res: ReadResult) -> list:
    n, out = res.number, []
    for nm, hi, av, lo in (("oxygen", "Oxygen level, highest (%)", "Oxygen level, average (%)", "Oxygen level, lowest (%)"),
                           ("pulse", "Pulse rate, highest (/min)", "Pulse rate, average (/min)", "Pulse rate, lowest (/min)")):
        a, b, c = n(hi), n(av), n(lo)
        out.append(Check(f"{nm}: lowest <= average <= highest", None not in (a, b, c) and c <= b <= a, f"{c} <= {b} <= {a}"))
    # the two oxygen tables describe the same recording, so the shares in the bands they have in common agree (to a point of rounding)
    pairs = [("Oxygen 95 and above", "Oxygen, second table, 95-100"), ("Oxygen 90-94", "Oxygen, second table, 90-94")]
    miss = [k for pair in pairs for k in pair if n(f"{k}: {PCT}") is None]
    out.append(Check("the two oxygen band tables agree (95+ and 90-94)", not miss and all(abs(n(f"{a}: {PCT}") - n(f"{b}: {PCT}")) <= 1 for a, b in pairs),
                     ("could not check: missing " + ", ".join(miss)) if miss else " and ".join(f"{n(f'{a}: {PCT}'):g}% = {n(f'{b}: {PCT}'):g}%" for a, b in pairs)))
    low = _pcts(res, "Oxygen, second table,", ["80-89", "70-79", "below 70"])
    below90 = n(f"Oxygen below 90: {PCT}")
    out.append(Check("oxygen below 90 = 80-89 + 70-79 + below 70", low is not None and below90 is not None and abs(below90 - sum(low)) <= 1.5,
                     f"{below90} vs {sum(low) if low else None}"))
    # each table's shares add up to a whole (to a point or two of rounding)
    for label, prefix, names in (("oxygen", "Oxygen", _OX_LEFT), ("pulse", "Pulse", _PULSE), ("second oxygen", "Oxygen, second table,", _OX_RIGHT)):
        shares = _pcts(res, prefix, names)
        if shares is None:
            out.append(Check(f"{label} band shares add up to 100%", False, "could not check: a row is missing"))
        else:
            out.append(Check(f"{label} band shares add up to 100%", abs(sum(shares) - 100) <= 2, f"{' + '.join(f'{s:g}' for s in shares)} = {sum(shares):g}"))
    return out


def app_fields(res: ReadResult) -> dict:
    d = lambda k: res.values[k].display if k in res.values else ""
    return {"Highest SpO2": d("Oxygen level, highest (%)"), "Average SpO2": d("Oxygen level, average (%)"), "Lowest SpO2": d("Oxygen level, lowest (%)"),
            "Highest Pulse Rate": d("Pulse rate, highest (/min)"), "Average Pulse Rate": d("Pulse rate, average (/min)"),
            "Lowest Pulse Rate": d("Pulse rate, lowest (/min)")}
