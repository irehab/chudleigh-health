"""Reader for VALD Hub ForceDecks report PDFs (landscape, one measure per page, made by software with a text layer).

Page 1 lists the test sessions (date, time, reps, body weight). Every other page shows one measure: its name and unit, a
'Range / Average / CoV / SD' line, and a chart whose bars are labelled with each rep's value (or, for some balance tests, each
session's value, labelled by date). The reader matches each label to its rep or date by its position on the page, then checks the
values against the printed range and average, so a misread or mismatched label makes a check fail.

It deliberately never reads the person's name. Some text is drawn twice in these PDFs ('0044//0099' for '04/09'); that is undone.
"""
from __future__ import annotations

import datetime
import io
import re

from .base import Check, ReadResult, Value, status_from

DEVICE = "vald_hub"
LABEL = "VALD Hub ForceDecks report"
APP_ASSESSMENT = ""     # depends on the test in the report: see ReadResult.app_assessment
TESTS = {
    "CMJ": "VALD ForceDecks - Countermovement Jump (CMJ)",
    "SQT": "VALD ForceDecks - Multi-Rep Squat",
    "STSTS": "VALD ForceDecks - Sit-to-Stand",
    "SLSB": "VALD ForceDecks - Single Leg Stance / Balance",
    "QSB": "VALD ForceDecks - Quiet Stand (Balance)",
}
_DATE = re.compile(r"\d{2}/\d{2}/\d{4}")
_NUM = re.compile(r"-?\d+(?:\.\d+)?")
_SUMMARY = re.compile(r"^(-?[\d.]+)\s*([LR])?\s*-\s*(-?[\d.]+)\s*([LR])?\s+(-?[\d.]+)\s*([LR])?\s+([\d.]+)%\s+([\d.]+)$")
_UNIT_WORDS = {"s", "n", "n/s", "mm", "mm/s", "w/kg", "w", "kg", "ms", "cm", "m/s", "l", "r", "%"}


def matches(text_without_spaces: str) -> bool:
    t = text_without_spaces.upper()
    return "FORCEDECKS" in t and "CALCULATIONTYPE" in t and "RANGEAVERAGECOVSD" in t


def undouble(text: str) -> str:
    """'0044//0099//22002266' -> '04/09/2026', '11' -> '1'. Text that is not doubled is returned unchanged."""
    return text[0::2] if len(text) >= 2 and len(text) % 2 == 0 and text[0::2] == text[1::2] else text


def _words(page) -> list:
    return [{"text": w["text"], "x0": w["x0"], "x1": w["x1"], "top": w["top"], "size": w.get("size", 0)} for w in page.extract_words(extra_attrs=["size"])]


def _line(words, top, tol=2.5, max_size=None):
    return sorted((w for w in words if abs(w["top"] - top) <= tol and (max_size is None or w["size"] <= max_size)), key=lambda w: w["x0"])


def _sessions(words) -> list:
    """[{'date': date, 'time': '2:44 PM', 'reps': 3, 'bw': 76.6}] from the table on page 1 (the profile name is never read)."""
    head = {w["text"]: w for w in words if w["text"] in ("DATE", "REPS", "BW") and w["top"] < 130}
    if "DATE" not in head or "REPS" not in head:
        return []
    bw_right = max((w["x1"] for w in words if w["text"] == "[KG]" and abs(w["top"] - head["DATE"]["top"]) < 3), default=None)
    out = []
    for d in sorted((w for w in words if _DATE.fullmatch(w["text"]) and w["top"] > head["DATE"]["top"]), key=lambda w: w["top"]):
        near = [w for w in words if 0 <= w["top"] - d["top"] <= 22]
        reps = [w for w in near if re.fullmatch(r"\d+", w["text"]) and abs(w["x1"] - head["REPS"]["x1"]) <= 10]
        bw = [w for w in near if _NUM.fullmatch(w["text"]) and bw_right is not None and abs(w["x1"] - bw_right) <= 10]
        time = [w for w in words if 10 <= w["top"] - d["top"] <= 30 and abs(w["x0"] - d["x0"]) <= 3 and re.fullmatch(r"\d{1,2}:\d{2}", w["text"])]
        ampm = [w for w in words if time and abs(w["top"] - time[0]["top"]) <= 2 and w["text"] in ("AM", "PM") and 0 <= w["x0"] - time[0]["x1"] <= 8]
        out.append({
            "date": datetime.datetime.strptime(d["text"], "%d/%m/%Y").date(),
            "time": f"{time[0]['text']} {ampm[0]['text']}" if time and ampm else "",
            "reps": int(reps[0]["text"]) if reps else None,
            "bw": float(bw[0]["text"]) if bw else None,
        })
    return out


def _signed(value: float, side: str | None) -> float:
    return -value if side == "L" else value


def _measure_page(words, previous_title: str):
    """One measure page -> dict, or None if the page is not a measure (force trace, centre of pressure picture...)."""
    header = next((w for w in words if w["text"] == "Range" and w["size"] < 10), None)
    if not header or not any(w["text"] == "Average" and abs(w["top"] - header["top"]) < 2 for w in words):
        return None
    title_words = [w for w in words if 80 <= w["top"] <= 95 and w["size"] > 14]
    title = " ".join(w["text"] for w in sorted(title_words, key=lambda w: w["x0"]))
    side_words = " ".join(w["text"] for w in sorted((w for w in words if 80 <= w["top"] <= 115 and 12 < w["size"] < 14.5), key=lambda w: (w["top"], w["x0"])))
    side = "L" if "LEFT SIDE" in side_words else ("R" if "RIGHT SIDE" in side_words else None)
    if not title and previous_title and side:              # the second page of a left/right pair repeats no title
        title = previous_title.replace("(Left)", "(Right)") if side == "R" else previous_title
    unit_m = re.search(r"\[([^\]]+)\]\s*$", title)
    unit = unit_m.group(1) if unit_m else ""
    name = title[:unit_m.start()].strip() if unit_m else title
    summary_words = [w for w in words if 12 <= w["top"] - header["top"] <= 26 and w["size"] < 10]
    summary_text = " ".join(w["text"] for w in sorted(summary_words, key=lambda w: w["x0"]))
    m = _SUMMARY.match(summary_text)
    summary = None
    if m:
        summary = {"min": _signed(float(m.group(1)), m.group(2)), "max": _signed(float(m.group(3)), m.group(4)),
                   "average": _signed(float(m.group(5)), m.group(6)), "cov": float(m.group(7)), "sd": float(m.group(8)), "text": summary_text}

    # the chart: categories (reps or dates) along the bottom, or rep numbers down the left side for left/right asymmetry charts
    labels = [w for w in words if w["size"] > 14 and w["top"] > header["top"] + 30 and _NUM.fullmatch(w["text"])]
    small = [dict(w, text=undouble(w["text"])) for w in words if 10.5 < w["size"] < 12 and w["top"] > header["top"] + 30]
    dates = [w for w in small if _DATE.fullmatch(w["text"])]
    bottom = [w for w in small if re.fullmatch(r"\d{1,2}", w["text"]) and w["top"] > 400]
    left = [w for w in small if re.fullmatch(r"\d{1,2}", w["text"]) and w["x1"] < 110]
    points, by = [], ""
    if dates:
        cats, by = [(w["text"], (w["x0"] + w["x1"]) / 2) for w in dates], "date"
    elif "Asymmetry" in name and left:
        seen = {}
        for w in left:
            seen.setdefault(w["text"], w["top"])
        cats, by = [(k, v) for k, v in seen.items()], "rep_row"
    else:
        cats, by = [(w["text"], (w["x0"] + w["x1"]) / 2) for w in bottom], "rep"
    decimals = 0
    for w in labels:
        decimals = max(decimals, len(w["text"].split(".")[1]) if "." in w["text"] else 0)
        if by == "rep_row":
            pos, tol = w["top"] + 5, 18
        else:
            pos, tol = (w["x0"] + w["x1"]) / 2, 45
            unit_after = [u for u in words if abs(u["top"] - w["top"]) < 2 and 0 <= u["x0"] - w["x1"] <= 8 and u["size"] > 14]
            if unit_after:
                pos = (w["x0"] + unit_after[0]["x1"]) / 2
        best = min(cats, key=lambda c: abs(c[1] - pos), default=None)
        if best and abs(best[1] - pos) <= tol:
            points.append({"at": best[0], "value": float(w["text"])})
    # duplicates of one label (the PDF sometimes draws a label twice) count once
    uniq = {}
    for p in points:
        uniq.setdefault(p["at"], p["value"])
    points = [{"at": k, "value": v} for k, v in uniq.items()]
    # a rep whose value is exactly 0 gets no label on the chart (seen on asymmetry charts): only when the printed range starts at 0
    if by.startswith("rep") and summary and summary["min"] == 0:
        for rep, _pos in cats:
            if rep not in uniq:
                points.append({"at": rep, "value": 0.0, "inferred": True})
    if by.startswith("rep"):
        points.sort(key=lambda p: int(p["at"]))
    else:
        points.sort(key=lambda p: datetime.datetime.strptime(p["at"], "%d/%m/%Y"))
    return {"name": name, "unit": unit, "side": side, "summary": summary, "points": points, "by": "date" if by == "date" else "rep",
            "label_decimals": decimals, "asymmetry": "Asymmetry" in name}


def read(pages: list, data: bytes | None = None) -> ReadResult:
    import pdfplumber
    res = ReadResult(device=DEVICE, device_label=LABEL, has_text_layer=True)
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        all_words = [_words(p) for p in pdf.pages]
    first = all_words[0]
    code = next((w["text"] for w in first if w["top"] < 40 and w["x0"] > 600 and w["size"] > 15), "")
    res.device_label = f"{LABEL}: {code or 'unknown test'}"
    res.test_code = code
    res.app_assessment = TESTS.get(code, "")
    if not res.app_assessment:
        res.notes.append(f"Could not read: which ForceDecks test this is ('{code}' is not one the app knows yet)")
    calc = " ".join(w["text"] for w in _line(first, next((w["top"] for w in first if w["text"] == "Calculation"), -99)))
    res.calculation = (re.search(r"Calculation type:\s*(\w+)", calc) or [None, ""])[1]
    res.sessions = _sessions(first)
    if not res.sessions:
        res.notes.append("Could not read: the test table on page 1 (dates, reps and body weight)")
    res.measures = []
    previous = ""
    for words in all_words[1:]:
        m = _measure_page(words, previous)
        if m:
            res.measures.append(m)
            previous = m["name"] + (f" [{m['unit']}]" if m["unit"] else "")
    if not res.measures:
        res.notes.append("Could not read: no measures were found in this report")

    v = {}
    latest = max(res.sessions, key=lambda s: s["date"]) if res.sessions else None
    if latest:
        v["Test date"] = Value(text=latest["date"].isoformat(), number=None, unit="")
        if latest["bw"] is not None:
            v["Body weight on the plate (kg)"] = Value(text=f"{latest['bw']:g} kg", number=latest["bw"], unit="kg")
        if latest["reps"] is not None:
            v["Reps (latest session)"] = Value(text=str(latest["reps"]), number=latest["reps"], unit="")
    for m in res.measures:
        label = m["name"] + (f" [{m['unit']}]" if m["unit"] else "")
        if m["by"] == "date" and latest:
            mine = [p for p in m["points"] if p["at"] == latest["date"].strftime("%d/%m/%Y")]
            if mine:
                v[f"{label}, {latest['date']:%d/%m/%Y}"] = Value(text=f"{mine[0]['value']:g}", number=mine[0]["value"], unit=m["unit"])
            for p in m["points"]:
                if not mine or p["at"] != mine[0]["at"]:
                    v[f"{label}, earlier session {p['at']}"] = Value(text=f"{p['value']:g}", number=p["value"], unit=m["unit"])
        elif m["summary"]:
            for p in m["points"]:
                v[f"{label}, rep {p['at']}"] = Value(text=f"{p['value']:g}", number=p["value"], unit=m["unit"])
            v[f"{label}, average"] = Value(text=f"{m['summary']['average']:g}", number=m["summary"]["average"], unit=m["unit"])
    res.values = v
    res.notes.append("Left/right asymmetry is stored as a signed number: negative = left, positive = right (as on the report's chart).")
    res.checks = run_checks(res)
    res.status = status_from(res)
    return res


def _decimals(x: float) -> int:
    s = f"{x:g}"
    return len(s.split(".")[1]) if "." in s else 0


def _close(a: float, b: float, printed: float, label_decimals: int = 3) -> bool:
    """Equal to the precision the report printed: allows for the chart labels' rounding and the printed number's own rounding."""
    tol = 0.5 * 10 ** -label_decimals + 0.5 * 10 ** -_decimals(printed) + 1e-9
    return abs(a - b) <= max(tol, abs(printed) * 0.005)


BW_PLAUSIBLE = (35.0, 200.0)     # kg: outside this, the body weight on the plate was probably entered or measured wrongly


def run_checks(res: ReadResult) -> list:
    checks: list = []
    reps_by_date = {s["date"].strftime("%d/%m/%Y"): s["reps"] for s in getattr(res, "sessions", [])}
    # the squat's table counts reps differently from its charts (confirmed by the clinic: the charts show every squat), so it is not compared
    one_session = len(reps_by_date) == 1 and getattr(res, "test_code", "") != "SQT"
    for s in getattr(res, "sessions", []):
        if s["bw"] is not None:
            lo, hi = BW_PLAUSIBLE
            checks.append(Check(f"body weight on the plate looks right ({s['date']:%d/%m/%Y})", lo <= s["bw"] <= hi,
                                f"{s['bw']:g} kg. Results per kg (such as W/kg) are worked out from this weight, so check it in VALD Hub if it is wrong"))
    for m in getattr(res, "measures", []):
        label = m["name"] + (f" ({'left' if m['side'] == 'L' else 'right'})" if m["side"] and "(Left)" not in m["name"] and "(Right)" not in m["name"] else "")
        s, pts = m["summary"], m["points"]
        if not s:
            checks.append(Check(f"{label}: summary line read", False, "the Range / Average line could not be read"))
            continue
        if not pts:
            checks.append(Check(f"{label}: values read from the chart", False, "no value labels could be matched to a rep or date"))
            continue
        vals = [p["value"] for p in pts]
        dec = m.get("label_decimals", 3)
        if m["by"] == "date":
            # the chart shows each session's average; the printed range is of the single reps, so each session must lie inside it
            inside = min(vals) >= s["min"] - 0.5 * 10 ** -dec and max(vals) <= s["max"] + 0.5 * 10 ** -dec
            checks.append(Check(f"{label}: each session's value lies inside the printed range of reps", inside,
                                f"sessions {min(vals):g} to {max(vals):g}, reps {s['min']:g} to {s['max']:g}"))
            weights = [reps_by_date.get(p["at"]) or 0 for p in pts]
            if all(weights):
                mean = sum(p["value"] * w for p, w in zip(pts, weights)) / sum(weights)
                checks.append(Check(f"{label}: printed average matches each session's value weighted by its reps", _close(mean, s["average"], s["average"], dec),
                                    f"{mean:.1f} vs printed {s['average']:g}"))
        else:
            if m.get("asymmetry"):       # the printed range is the smallest and the largest difference, whichever side
                lo, hi = min(vals, key=abs), max(vals, key=abs)
                ok = _close(abs(lo), abs(s["min"]), s["min"], dec) and _close(abs(hi), abs(s["max"]), s["max"], dec) and (hi == 0 or (hi < 0) == (s["max"] < 0))
            else:
                lo, hi = min(vals), max(vals)
                ok = _close(lo, s["min"], s["min"], dec) and _close(hi, s["max"], s["max"], dec)
            checks.append(Check(f"{label}: smallest and largest match the printed range", ok, f"read {lo:g} to {hi:g}, printed {s['min']:g} to {s['max']:g}"))
            mean = sum(vals) / len(vals)
            checks.append(Check(f"{label}: printed average matches the reps read", _close(mean, s["average"], s["average"], dec), f"{mean:.2f} vs printed {s['average']:g}"))
            if any(p.get("inferred") for p in pts):
                checks.append(Check(f"{label}: a rep with no label on the chart was taken as 0", True,
                                    "the chart draws no label for a value of 0, and the printed range starts at 0", severity="note"))
            if one_session:
                expected = next(iter(reps_by_date.values()))
                if expected is not None and len(pts) != expected:
                    checks.append(Check(f"{label}: number of reps matches the test table", False,
                                        f"{len(pts)} values on the chart, {expected} reps in the table", severity="note"))
    return checks


# Which value goes in each of the app's boxes. Agreed with the clinic on 2026-10-19: the best rep for strength and power,
# the average for time to stand, left/right asymmetry and balance. Each entry: (box, measure name as printed, how).
#   best_max / best_min: the highest / lowest rep   average: the printed average   latest: the latest session's value (balance by date)
FIELD_MAP = {
    "CMJ": [("Jump Height", r"Jump Height.*", "best_max"), ("Peak Power/Mass", r"Peak Power / BM", "best_max"),
            ("Modified RSI", r"RSI-?modified|RSI ?mod", "best_max"), ("Flight Time:Contraction Time", r"Flight Time:Contraction Time", "best_max"),
            ("Peak Force Asymmetry", r"Concentric Peak Force Asymmetry", "average"), ("Braking Impulse Asymmetry", r"Eccentric Braking Impulse Asymmetry", "average"),
            ("Body Weight", None, "bw")],
    "SQT": [("Peak Force", r"Peak Force", "best_max"), ("L/R Asymmetry", r"Concentric Peak Force Asymmetry", "average"), ("Body Weight", None, "bw")],
    "STSTS": [("Time to Stand", r"Time to Stand", "average"), ("Peak Standing Force", r"Peak Standing Force", "best_max"),
              ("Limb Asymmetry", r"Peak Standing Force Asymmetry", "average"), ("Peak Standing RFD", r"Peak Standing RFD.*", "best_max"),
              ("Body Weight", None, "bw")],
    "SLSB": [(f"{side} {box}", rf"{name} \({side}\)", "latest") for side in ("Left", "Right")
             for box, name in (("Total Excursion", "Total Excursion"), ("Sway Velocity", "Mean Velocity"),
                               ("Side-to-Side Sway", "CoP Range - Medial-Lateral"), ("Front-to-Back Sway", "CoP Range - Anterior-Posterior"))],
    "QSB": [("Total Path Length", r"Total Excursion", "average"), ("Mean Velocity", r"Mean Velocity", "average"),
            ("Side-to-Side Sway", r"CoP Range - Medial-Lateral", "average"), ("AP Sway Range", r"CoP Range - Anterior-Posterior", "average")],
}
PER_KG = re.compile(r"/\s*(BM|kg)\b|W/kg", re.I)


def _show(value: float, unit: str, asymmetry: bool) -> str:
    if asymmetry:
        return "0%" if value == 0 else f"{abs(value):g}% {'L' if value < 0 else 'R'}"
    unit = {"% L,R": "%"}.get(unit, unit)
    return f"{value:g} {unit}".strip() if unit and unit != "%" else (f"{value:g}%" if unit == "%" else f"{value:g}")


def field_numbers(res: ReadResult) -> dict:
    """The app's boxes for this test as numbers: {box: {"value", "unit", "asymmetry"}}, or None for a box whose measure is not in the report.
    Per-kg results are None when the body weight on the plate failed its check (they would be wrong). Asymmetry is signed: negative = left."""
    code = getattr(res, "test_code", "")
    bad_bw = any(not c.ok and c.name.startswith("body weight") for c in res.checks)
    sessions = getattr(res, "sessions", [])
    latest = max(sessions, key=lambda s: s["date"])["date"].strftime("%d/%m/%Y") if sessions else None
    out = {}
    for box, pattern, how in FIELD_MAP.get(code, []):
        if how == "bw":           # the latest session's body weight, only if it passed its check
            bw = max(sessions, key=lambda s: s["date"])["bw"] if sessions else None
            out[box] = None if bw is None or bad_bw else {"value": bw, "unit": "kg", "asymmetry": False}
            continue
        m = next((m for m in getattr(res, "measures", []) if re.fullmatch(pattern, m["name"], re.I)), None)
        if not m or (bad_bw and PER_KG.search(f"{m['name']} [{m['unit']}]")):
            out[box] = None
            continue
        vals = [p["value"] for p in m["points"]]
        if how == "latest":
            value = next((p["value"] for p in m["points"] if p["at"] == latest), None)
        elif how == "average":
            value = m["summary"]["average"] if m["summary"] else None
        elif vals:
            value = max(vals) if how == "best_max" else min(vals)
        else:
            value = None
        out[box] = None if value is None else {"value": value, "unit": m["unit"], "asymmetry": m["asymmetry"]}
    return out


def app_fields(res: ReadResult) -> dict:
    """The app's boxes for this test, filled from the report. A box whose measure is not in the report stays empty."""
    return {box: "" if n is None else (f"{n['value']:g} kg" if box == "Body Weight" else _show(n["value"], n["unit"], n["asymmetry"]))
            for box, n in field_numbers(res).items()}
