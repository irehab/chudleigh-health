"""Reader for the ViHealth 'Oxygen Level Report'. The whole report is a picture, so it is read by OCR, table by table, by position.

Because OCR can misread a digit, every number is checked against the others (times against the duration, percentages against
the band times, the two band tables against each other). A misread makes a check fail and the status 'check'.
"""
from __future__ import annotations

import re

from . import ocr
from .base import Check, ReadResult, Value, close, hms_to_seconds, make_value, seconds_to_hms, status_from

DEVICE = "vihealth_oxygen"
LABEL = "ViHealth oxygen level report"
APP_ASSESSMENT = "SpO2 / Pulse Oximetry (ViHealth)"

REGIONS = {
    "top_right": (0.66, 0.085, 0.985, 0.165),
    "times": (0.03, 0.093, 0.66, 0.145),
    "left_tables": (0.03, 0.195, 0.34, 0.405),
    "right_table": (0.66, 0.195, 0.985, 0.405),
}
_ROW = re.compile(r"(\d{1,2}:\d{2}:\d{2})\s+(\d{1,3})\s*%")
_OX_LEFT = ["95 and above", "90-94", "below 90"]
_PULSE = ["above 120", "50-120", "below 50"]
_OX_RIGHT = ["95-100", "90-94", "80-89", "70-79", "below 70"]


def matches_banner(banner_upper: str) -> bool:
    return "OXYGEN" in banner_upper and "REPORT" in banner_upper


def _secs(res_values, key):
    v = res_values.get(key)
    return None if v is None else v.number


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

    # start, end, duration
    m = re.search(r"Start\s*time:?\s*(\d{1,2}:\d{2}:\d{2})\s+([A-Za-z]{3}\s+\d{1,2},\s*\d{4})", txt["times"])
    if m:
        v["Start time"] = Value(text=f"{m.group(1)} {m.group(2)}", number=hms_to_seconds(m.group(1)), unit="", source="ocr")
    else:
        res.notes.append("Could not read: Start time")
    m2 = re.search(r"End\s*time:?\s*(\d{1,2}:\d{2}:\d{2})\s+([A-Za-z]{3}\s+\d{1,2},\s*\d{4})", txt["times"])
    if m2:
        v["End time"] = Value(text=f"{m2.group(1)} {m2.group(2)}", number=hms_to_seconds(m2.group(1)), unit="", source="ocr")
    else:
        res.notes.append("Could not read: End time")
    m3 = re.search(r"Duration:?\s*(\d{1,2}:\d{2}:\d{2})", txt["times"])
    put("Duration", Value(text=m3.group(1), number=hms_to_seconds(m3.group(1)), unit="s") if m3 else None)

    # band tables: rows are read by their position, because OCR garbles symbols such as ≥ and <
    def rows(text):
        return _ROW.findall(text)

    left_lines = txt["left_tables"].splitlines()
    split = next((i for i, l in enumerate(left_lines) if re.search(r"Pulse", l, re.I)), len(left_lines))
    ox_rows, pulse_rows = rows("\n".join(left_lines[:split])), rows("\n".join(left_lines[split:]))
    right_rows = rows(txt["right_table"])
    m = re.search(r"Oxygen\s*Level:?\s*(\d{2,3})", txt["left_tables"])
    if m:
        v["Oxygen level shown in the band table heading (%)"] = make_value(m.group(1) + "%"); v["Oxygen level shown in the band table heading (%)"].source = "ocr"

    def band(prefix, names, found):
        if len(found) != len(names):
            res.notes.append(f"Could not read: {prefix} bands (found {len(found)} of {len(names)} rows)")
            return
        for name, (t, pct) in zip(names, found):
            v[f"{prefix} {name}: time"] = Value(text=t, number=hms_to_seconds(t), unit="s", source="ocr")
            v[f"{prefix} {name}: %Total as printed"] = Value(text=f"{pct}%", number=float(pct), unit="%", source="ocr")

    band("Oxygen", _OX_LEFT, ox_rows)
    band("Pulse", _PULSE, pulse_rows)
    band("Oxygen, second table,", _OX_RIGHT, right_rows)
    res.values = v

    res.checks = run_checks(res)
    shares = _share_notes(res)
    if shares:
        res.notes.append(shares)
    res.notes.append("Read by text recognition from a picture. The chart lines are graphics and are not read.")
    res.status = status_from(res)
    return res


def _tot(res, prefix, names):
    vals = [res.values.get(f"{prefix} {n}: time") for n in names]
    return None if any(x is None for x in vals) else sum(x.number for x in vals)


def run_checks(res: ReadResult) -> list:
    n, out = res.number, []
    for nm, hi, av, lo in (("oxygen", "Oxygen level, highest (%)", "Oxygen level, average (%)", "Oxygen level, lowest (%)"),
                           ("pulse", "Pulse rate, highest (/min)", "Pulse rate, average (/min)", "Pulse rate, lowest (/min)")):
        a, b, c = n(hi), n(av), n(lo)
        out.append(Check(f"{nm}: lowest <= average <= highest", None not in (a, b, c) and c <= b <= a, f"{c} <= {b} <= {a}"))
    st, en, du = res.values.get("Start time"), res.values.get("End time"), n("Duration")
    if st and en and du is not None:
        diff = (en.number - st.number) % 86400
        out.append(Check("end time minus start time = duration", abs(diff - du) <= 1, f"{seconds_to_hms(int(diff))} vs {seconds_to_hms(int(du))}"))
    else:
        out.append(Check("end time minus start time = duration", False, "could not check: missing a time"))
    # the two oxygen tables show the same recording
    keys = [("Oxygen 95 and above: time", "Oxygen, second table, 95-100: time"), ("Oxygen 90-94: time", "Oxygen, second table, 90-94: time")]
    miss = [k for pair in keys for k in pair if n(k) is None]
    out.append(Check("the two oxygen band tables agree (95+ and 90-94)", not miss and all(n(a) == n(b) for a, b in keys),
                     ("could not check: missing " + ", ".join(miss)) if miss else " and ".join(f"{seconds_to_hms(int(n(a)))} = {seconds_to_hms(int(n(b)))}" for a, b in keys)))
    low = _tot(res, "Oxygen, second table,", ["80-89", "70-79", "below 70"])
    out.append(Check("oxygen below 90 = 80-89 + 70-79 + below 70", low is not None and n("Oxygen below 90: time") is not None and n("Oxygen below 90: time") == low,
                     f"{n('Oxygen below 90: time')} s vs {low} s"))
    ox_tot, pulse_tot = _tot(res, "Oxygen", _OX_LEFT), _tot(res, "Pulse", _PULSE)
    out.append(Check("oxygen and pulse band times cover the same total", ox_tot is not None and pulse_tot is not None and abs(ox_tot - pulse_tot) <= 1,
                     f"{ox_tot} s vs {pulse_tot} s"))
    for label, prefix, names, tot in (("oxygen", "Oxygen", _OX_LEFT, ox_tot), ("pulse", "Pulse", _PULSE, pulse_tot)):
        if not tot:
            out.append(Check(f"each {label} %Total is that band's share of the band total", False, "could not check: band times missing")); continue
        bad = [nm for nm in names if not close(n(f"{prefix} {nm}: %Total as printed"), 100.0 * n(f"{prefix} {nm}: time") / tot, 1.0)]
        out.append(Check(f"each {label} %Total is that band's share of the band total", not bad, f"band total {seconds_to_hms(int(tot))}" + (f"; off: {', '.join(bad)}" if bad else "")))
    if ox_tot is not None and du is not None:
        gap = du - ox_tot
        out.append(Check("band times cover the full duration", abs(gap) <= 2,
                         f"bands add up to {seconds_to_hms(int(ox_tot))} of {seconds_to_hms(int(du))}" + (f" ({int(gap)} s not counted by the device)" if gap else ""),
                         severity="note" if 0 < gap <= 30 else "error"))
    return out


def _share_notes(res: ReadResult) -> str:
    n = res.number
    tot, du = _tot(res, "Oxygen", _OX_LEFT), n("Duration")
    if not tot or not du or tot == du:
        return ""
    of_dur = all(close(n(f"Oxygen {nm}: %Total as printed"), 100.0 * n(f"Oxygen {nm}: time") / du, 0.6) for nm in _OX_LEFT if n(f"Oxygen {nm}: time") is not None)
    return "" if of_dur else (f"The %Total figures are each band's share of the band total ({seconds_to_hms(int(tot))}), not of the full duration "
                              f"({seconds_to_hms(int(du))}).")


def app_fields(res: ReadResult) -> dict:
    d = lambda k: res.values[k].display if k in res.values else ""
    return {"Highest SpO2": d("Oxygen level, highest (%)"), "Average SpO2": d("Oxygen level, average (%)"), "Lowest SpO2": d("Oxygen level, lowest (%)"),
            "Highest Pulse Rate": d("Pulse rate, highest (/min)"), "Average Pulse Rate": d("Pulse rate, average (/min)"),
            "Lowest Pulse Rate": d("Pulse rate, lowest (/min)"), "Duration": d("Duration")}
