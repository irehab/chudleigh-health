"""Reader for the AGE Scanner (Diagnoptics) 'Measurement report'.

The sentences on this report are text, but the large gauge numbers are drawn graphics, so those are read by OCR from the gauge
area and cross-checked against the text. The person's name and birth date are never read.
"""
from __future__ import annotations

import re

from . import ocr
from .base import Check, Page, ReadResult, Value, close, make_value, status_from

DEVICE = "age_scanner"
LABEL = "AGE Scanner (Diagnoptics) measurement report"
APP_ASSESSMENT = "AGE Reader (Advanced Glycation End-Products)"
GAUGE_BOX = (0.09, 0.26, 0.50, 0.385)
SPLIT_X = 175  # points: the two sentences under the gauges sit in two columns


def matches(text_without_spaces: str) -> bool:
    t = text_without_spaces.upper()
    return "MEASUREMENTREPORT" in t and "AGELEVEL" in t and "BIRTHDATE" in t


def _col(words, x0, x1, t0, t1):
    rows: dict = {}
    for w in words:
        if x0 <= w["x0"] < x1 and t0 <= w["top"] <= t1:
            rows.setdefault(round(w["top"] / 4), []).append(w)
    return " ".join(" ".join(x["text"] for x in sorted(r, key=lambda x: x["x0"])) for _, r in sorted(rows.items()))


def read(pages: list, data: bytes | None = None) -> ReadResult:
    res = ReadResult(device=DEVICE, device_label=LABEL, has_text_layer=True)
    words = pages[0]
    p = Page(words)
    v: dict = {}
    interp = next((w for w in p.words if w["text"].lower().startswith("interpretation")), None)
    sent_top = 0
    # the two sentences under the gauges (left and right column), above 'Interpretation'
    limit = interp["top"] - 1 if interp else 10_000
    gauge_sentences_top = next((w["top"] for w in p.words if w["text"].lower().startswith("you're")), None)
    left = _col(words, 0, SPLIT_X, (gauge_sentences_top or 0) - 2, limit)
    right = _col(words, SPLIT_X, 10_000, (gauge_sentences_top or 0) - 2, limit)

    m = re.search(r"(\d{1,3})\s*%\s*of\s*your\s*age\s*group", left)
    v["Position within age group (%)"] = make_value(m.group(1) + "%") if m else None
    m = re.search(r"(\d{1,3})\s*%\s*(below|above)\s*the\s*average\s*age\s*level\s*score\s*for\s*(\d{1,3})\s*year", right, re.I)
    percent_dir = None
    if m:
        v["AGE level compared with average (%)"] = make_value(m.group(1) + "%")
        percent_dir = m.group(2).lower()
        v["Comparison direction"] = Value(text=percent_dir, number=None, unit="")
        v["Age used for comparison (years)"] = make_value(m.group(3) + "years")
    flat = " ".join(w["text"] for w in sorted(words, key=lambda w: (round(w["top"] / 4), w["x0"])))
    m = re.search(r"(?<![A-Za-z])Date:\s*(\d{1,2}/\d{1,2}/\d{4})", flat)
    if m:
        v["Report date"] = Value(text=m.group(1), number=None, unit="")
    for key, val in list(v.items()):
        if val is None:
            res.notes.append(f"Could not read: {key}")
            del v[key]

    if interp:
        para = _col(words, 0, 10_000, interp["top"] + 6, 10_000)
        para = re.sub(r"\s*(?:Diagnoptics)\s*$", "", para).strip()
        if para:
            res.statements.append({"text": para, "kind": "device_interpretation",
                                   "caution": "The device's own wording, not a clinical finding. Not added to reports automatically."})

    # the gauge numbers: drawn graphics, read by OCR
    gauge = None
    if data is not None and ocr.available():
        res.used_ocr = True
        text = ocr.read_text(ocr.crop(ocr.render(data, 3.0), GAUGE_BOX), psm=6)
        gauge = _parse_gauge(text)
        for key, raw in (("BodyAge (years)", gauge.get("bodyage")), ("AGE level", gauge.get("level")), ("AGE level, average for age", gauge.get("average")),
                         ("BodyAge difference from age (years)", gauge.get("diff"))):
            val = make_value(str(raw)) if raw is not None else None
            if val:
                val.source = "ocr"
                if key.endswith("(years)"):
                    val.unit = "years"; val.text = f"{raw} years"
                v[key] = val
            else:
                res.notes.append(f"Could not read: {key}")
        if gauge.get("risk"):
            v["Risk label (as printed)"] = Value(text=gauge["risk"], number=None, unit="", source="ocr")
        res.notes.append("The gauge numbers are drawn graphics, so they were read by text recognition and checked against the sentences.")
    else:
        for key in ("BodyAge (years)", "AGE level", "AGE level, average for age"):
            res.notes.append(f"Could not read: {key} (drawn as a graphic; text recognition is not available)")
    res.values = v
    res.checks = run_checks(res)
    res.status = status_from(res)
    return res


def _parse_gauge(text: str) -> dict:
    out: dict = {}
    m = re.search(r"^\D*(\d{1,3})\s+(\d{2,4})\s*$", text, re.M)
    if m:
        out["bodyage"], out["level"] = int(m.group(1)), int(m.group(2))
    m = re.search(r"(\d{1,2})\s*years", text, re.I)
    out["diff"] = int(m.group(1)) if m else None
    m = re.search(r"Average\s*(\d{2,4})", text, re.I)
    out["average"] = int(m.group(1)) if m else None
    m = re.search(r"\b(No|Low|Moderate|High|Very high|Medium)\s*risk", text, re.I)
    out["risk"] = " ".join(m.group(0).split()) if m else None
    return out


def run_checks(res: ReadResult) -> list:
    n, out = res.number, []
    age, body, diff = n("Age used for comparison (years)"), n("BodyAge (years)"), n("BodyAge difference from age (years)")
    out.append(Check("BodyAge differs from the age by the printed number of years", None not in (age, body, diff) and abs(age - body) == diff,
                     f"|{age} - {body}| vs {diff}"))
    lvl, avg, pct = n("AGE level"), n("AGE level, average for age"), n("AGE level compared with average (%)")
    if None not in (lvl, avg, pct) and avg:
        direction = res.values.get("Comparison direction")
        actual = (1 - lvl / avg) * 100 if (direction and direction.text == "below") else (lvl / avg - 1) * 100
        out.append(Check("AGE level and average match the '% below/above average' sentence", close(actual, pct, 1.01), f"{actual:.1f}% from {lvl} and {avg} vs {pct}% printed"))
    else:
        out.append(Check("AGE level and average match the '% below/above average' sentence", False, "could not check: missing a number"))
    return out


def app_fields(res: ReadResult) -> dict:
    d = lambda k: res.values[k].display if k in res.values else ""
    variance = ""
    if d("AGE level compared with average (%)") and d("Age used for comparison (years)"):
        variance = f"{d('AGE level compared with average (%)')} {res.values['Comparison direction'].text} the average for age {int(res.number('Age used for comparison (years)'))}"
    return {"BodyAge": d("BodyAge (years)"), "AGE Level Score": d("AGE level"), "Variance": variance}
