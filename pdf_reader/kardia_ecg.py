"""Reader for the Kardia 12-lead ECG report (one page with a text layer, in three columns).

It reads each column on its own, never reads the patient line, and checks the corrected QT values against the heart rate.
The report's own machine interpretation is kept as a *statement* marked unconfirmed, and is not treated as a finding.
"""
from __future__ import annotations

import math
import re

from .base import Check, Page, ReadResult, Value, close, make_value, status_from

DEVICE = "kardia_ecg"
LABEL = "Kardia 12-lead ECG report"
APP_ASSESSMENT = "12-Lead ECG (Electrocardiogram)"


def matches(text_without_spaces: str) -> bool:
    t = text_without_spaces.upper()
    return "KARDIA" in t and "QRSDURATION" in t and "PRINTERVAL" in t


def _column_text(words, x0, x1, top_limit):
    rows: dict = {}
    for w in words:
        if x0 <= w["x0"] < x1 and w["top"] < top_limit:
            rows.setdefault(round(w["top"] / 4), []).append(w)
    return "\n".join(" ".join(x["text"] for x in sorted(r, key=lambda x: x["x0"])) for _, r in sorted(rows.items()))


def _lines_after(words, x0, x1, start_top, top_limit, max_gap=14):
    """Lines of a column from a heading downwards, stopping at the first big gap (so nothing from the trace area below is picked up)."""
    rows: dict = {}
    for w in words:
        if x0 <= w["x0"] < x1 and start_top - 1 <= w["top"] < top_limit:
            rows.setdefault(round(w["top"] / 4), []).append(w)
    out, last = [], None
    for _, r in sorted(rows.items()):
        top = min(x["top"] for x in r)
        if last is not None and top - last > max_gap:
            break
        out.append(" ".join(x["text"] for x in sorted(r, key=lambda x: x["x0"])))
        last = top
    return "\n".join(out)


def _split_x(words, right_x, top_limit):
    """Where the left column ends and the middle one begins: the widest gap in the text to the left of the right column.
    (The middle column is centred, so its lines do not all start at the same place.)"""
    spans = sorted((w["x0"], w["x1"]) for w in words if w["top"] < top_limit and w["x0"] < right_x)
    merged: list = []
    for a, b in spans:
        if merged and a <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    if len(merged) < 2:
        return None
    return max((merged[i + 1][0] - merged[i][1], (merged[i][1] + merged[i + 1][0]) / 2) for i in range(len(merged) - 1))[1]


def read(pages: list, data: bytes | None = None) -> ReadResult:
    res = ReadResult(device=DEVICE, device_label=LABEL, has_text_layer=True)
    words = pages[0]
    p = Page(words)
    anchors = {name: next((w for w in p.words if w["text"] == name), None) for name in ("Interpretation:", "Analysis")}
    if not anchors["Interpretation:"]:
        res.status = "check"
        res.notes.append("Could not read: the report looked like this device but its columns were not where expected, so nothing was read.")
        return res
    top_limit = anchors["Analysis"]["top"] - 2 if anchors["Analysis"] else 10_000
    right_x = anchors["Interpretation:"]["x0"] - 2
    mid_x = _split_x(words, right_x, top_limit)
    if mid_x is None:
        res.status = "check"
        res.notes.append("Could not read: the report's columns could not be told apart, so nothing was read.")
        return res
    left = _column_text(words, 0, mid_x, top_limit)
    middle = _column_text(words, mid_x, right_x, top_limit)
    right = _lines_after(words, right_x, 10_000, anchors["Interpretation:"]["top"], top_limit)
    v: dict = {}

    def put(key, raw, unit=None):
        val = make_value(raw, unit) if raw else None
        if val:
            v[key] = val
        else:
            res.notes.append(f"Could not read: {key}")

    def grab(pattern, text, flags=re.S | re.I):
        m = re.search(pattern, text, flags)
        return m.groups() if m else None

    g = grab(r"Heart\s*Rate:\s*(\d+)\s*bpm", middle); put("Heart rate (bpm)", f"{g[0]}bpm" if g else None)
    g = grab(r"PR\s*Interval:\s*(\d+)\s*ms", middle); put("PR interval (ms)", f"{g[0]}ms" if g else None)
    g = grab(r"QRS\s*Duration:\s*(\d+)\s*ms", middle); put("QRS duration (ms)", f"{g[0]}ms" if g else None)
    g = grab(r"QT\s*/\s*QTcB\s*/\s*QTcF:\s*(\d+)\s*ms\s*/\s*(\d+)\s*ms\s*/\s*(\d+)\s*ms", middle)
    for key, i in (("QT (ms)", 0), ("QTcB, Bazett (ms)", 1), ("QTcF, Fridericia (ms)", 2)):
        put(key, f"{g[i]}ms" if g else None)
    g = grab(r"P\s*/\s*QRS\s*/\s*T\s*Axis:\s*(-?\d+)\s*°\s*/\s*(-?\d+)\s*°\s*/\s*(-?\d+)\s*°", middle)
    for key, i in (("P axis (°)", 0), ("QRS axis (°)", 1), ("T axis (°)", 2)):
        put(key, f"{g[i]}°" if g else None)
    g = grab(r"Gender,\s*Age:\s*([A-Za-z]+)\s*,\s*(\d+)\s*yrs", left)
    if g:
        v["Sex (as printed)"] = Value(text=g[0], number=None, unit="")
        put("Age (years)", f"{g[1]}years")
    else:
        res.notes.append("Could not read: Sex and age")
    g = grab(r"Recorded:\s*([^\n]+)", left)
    if g:
        v["Recorded"] = Value(text=" ".join(g[0].split()), number=None, unit="")

    # the line about how the recording was analysed (full width, at the bottom)
    if anchors["Analysis"]:
        line = " ".join(w["text"] for w in sorted((w for w in p.words if abs(w["top"] - anchors["Analysis"]["top"]) <= 3), key=lambda w: w["x0"]))
        m = re.match(r"Analysis\s*Mode:\s*(.*)", line)
        if m:
            v["Analysis mode (as printed)"] = Value(text=m.group(1).strip(), number=None, unit="")
            if re.search(r"\bsymptomatic\b|\basymptomatic\b", m.group(1), re.I):
                res.notes.append("The word 'Asymptomatic' (or 'Symptomatic') on the analysis-mode line is a recording setting chosen on the device, not a finding about the person.")

    # the device's own machine interpretation: kept as a statement, clearly marked unconfirmed
    m = re.search(r"Interpretation:\s*(?:\((.*?)\))?\s*(.*)", right, re.S | re.I)
    if m and m.group(2).strip():
        res.statements.append({
            "text": " ".join(m.group(2).split()),
            "kind": "device_interpretation",
            "caution": " ".join((m.group(1) or "Unconfirmed machine interpretation").split()),
        })
    res.values = v

    res.checks = run_checks(res)
    res.status = status_from(res)
    return res


def run_checks(res: ReadResult) -> list:
    n = res.number
    out: list = []
    hr, qt = n("Heart rate (bpm)"), n("QT (ms)")
    if hr and qt:
        rr = 60.0 / hr
        for name, key, expected in (("QTcB (Bazett) matches the QT and heart rate", "QTcB, Bazett (ms)", qt / math.sqrt(rr)),
                                    ("QTcF (Fridericia) matches the QT and heart rate", "QTcF, Fridericia (ms)", qt / rr ** (1 / 3))):
            got = n(key)
            out.append(Check(name, close(got, expected, 3.0), f"printed {got} vs {expected:.1f} worked out from QT {qt} and heart rate {hr}"))
    else:
        out.append(Check("QT corrections can be checked", False, "could not check: missing heart rate or QT"))
    axes = [n("P axis (°)"), n("QRS axis (°)"), n("T axis (°)")]
    out.append(Check("axes are between -180° and 180°", all(a is not None and -180 <= a <= 180 for a in axes), f"{axes}"))
    return out


def app_fields(res: ReadResult) -> dict:
    d = lambda k: res.values[k].display if k in res.values else ""
    qt = " / ".join(x for x in (f"{d('QTcB, Bazett (ms)')} (Bazett)" if d("QTcB, Bazett (ms)") else "", f"{d('QTcF, Fridericia (ms)')} (Fridericia)" if d("QTcF, Fridericia (ms)") else "") if x)
    axis = f"P/QRS/T axis: {d('P axis (°)')} / {d('QRS axis (°)')} / {d('T axis (°)')}" if all(d(k) for k in ("P axis (°)", "QRS axis (°)", "T axis (°)")) else ""
    return {"Heart Rate": d("Heart rate (bpm)"), "PR Interval": d("PR interval (ms)"), "QRS Duration": d("QRS duration (ms)"), "QTc Interval": qt, "Rhythm & Axis": axis}
