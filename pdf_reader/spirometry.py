"""Reader for the 'Spirometry Results' report (one A4 page, made by the spirometer's software, with a text layer).

The report prints, for each measure, the best value, the lower limit of normal (LLN), the predicted value, % predicted and a z-score,
worked out by the spirometer's software from the person's age, sex, height and ethnic origin. The reader takes those as printed and
checks them against each other. It deliberately never reads the person's name or date of birth.
"""
from __future__ import annotations

import re

from .base import Check, ReadResult, Value, close, make_value, status_from

DEVICE = "spirometry_results"
LABEL = "Spirometry report"
APP_ASSESSMENT = "Spirometry (Pulmonary Function)"

# the rows of the results table: (name as printed, unit as printed, key used here)
ROWS = [("FVC", "L", "FVC"), ("FEV1", "L", "FEV1"), ("FEV1/FVC%", "", "FEV1/FVC"), ("PEF", "L/m", "PEF"), ("FEF2575", "L/s", "FEF25-75"),
        ("FEF25", "L/s", "FEF25"), ("FEF50", "L/s", "FEF50"), ("FEF75", "L/s", "FEF75"), ("PEFTime", "ms", "PEF time"), ("EVol", "mL", "Extrapolated volume"),
        ("FEV6", "L", "FEV6")]
COLUMNS = ("best", "lln", "pred", "pct", "z")
GOOD_GRADES = ("A", "B", "C")        # ATS/ERS 2019 grades that are acceptable for interpretation
_NUM = r"-?\d+(?:\.\d+)?"


def matches(text_without_spaces: str) -> bool:
    t = text_without_spaces.upper()
    return "SPIROMETRYRESULTS" in t and "ACCEPTABILITYCRITERIA" in t and "ZSCORE" in t


def _lines(pages) -> list:
    """The page's text as lines (words with the same height on the page, left to right)."""
    rows: dict = {}
    for w in pages[0]:
        rows.setdefault(round(w["top"] / 3), []).append(w)
    return [" ".join(x.get("raw", x["text"]) for x in sorted(ws, key=lambda x: x["x0"])) for _k, ws in sorted(rows.items())]


def read(pages: list, data: bytes | None = None) -> ReadResult:
    res = ReadResult(device=DEVICE, device_label=LABEL, has_text_layer=True)
    lines = _lines(pages)
    text = "\n".join(lines)
    v: dict = {}
    res.table = {}

    for printed, unit, key in ROWS:
        # the row name, its unit, then a number (so 'FEV1 Grade: E' and 'FEV1/FVC%' are not taken for the FEV1 row)
        pat = (rf"^{re.escape(printed)}\s*{re.escape(unit)}\s+({_NUM}(?:\s.*)?)$" if unit else rf"^{re.escape(printed)}\s+({_NUM}(?:\s.*)?)$")
        line = next((l for l in lines if re.match(pat, l)), None)
        if not line:
            if key in ("FVC", "FEV1", "FEV1/FVC"):
                res.notes.append(f"Could not read: the {key} row")
            continue
        cells = re.match(pat, line).group(1).split()
        row = {}
        for name, cell in zip(COLUMNS, cells):
            row[name] = float(cell) if re.fullmatch(_NUM, cell) else None
        res.table[key] = row
        shown_unit = {"L/m": "L/min"}.get(unit, unit)
        if row.get("best") is not None:
            v[f"{key} ({shown_unit or '%'})"] = Value(text=f"{row['best']:g} {shown_unit}".strip() if shown_unit else f"{row['best']:g}%", number=row["best"], unit=shown_unit or "%")
        for col, label in (("lln", "LLN"), ("pred", "predicted"), ("pct", "% predicted"), ("z", "z-score")):
            if row.get(col) is not None:
                v[f"{key} {label}"] = Value(text=f"{row[col]:g}", number=row[col], unit="")

    # who the predicted values are for (the name and date of birth are never read)
    for label, pat, unit in (("Age (years)", r"\bAge\s+(\d{1,3})\b", "years"), ("Height (cm)", r"\bHeight\s+(\d{2,3})\s*cm", "cm"),
                             ("Weight (kg)", rf"\bWeight\s+({_NUM})\s*kg", "kg"), ("BMI", rf"\bBMI\s+({_NUM})", "")):
        m = re.search(pat, text)
        if m:
            v[label] = make_value(m.group(1) + unit) if unit else Value(text=m.group(1), number=float(m.group(1)), unit="")
    m = re.search(r"\bGender\s+([MF])\b", text)
    if m:
        v["Sex (as printed)"] = Value(text={"M": "male", "F": "female"}[m.group(1)], number=None, unit="")
    m = re.search(r"\bOrigin\s+([A-Za-z]+)", text)
    if m:
        v["Ethnic origin used for the predicted values"] = Value(text=m.group(1), number=None, unit="")

    # test quality, as graded by the spirometer (ATS/ERS 2019: A to C acceptable for interpretation; D to F, and U, not)
    grades = {}
    for key in ("FEV1", "FVC"):
        m = re.search(rf"\b{key}\s+Grade:\s*([A-FU])\b", text)
        if m:
            grades[key] = m.group(1)
            v[f"{key} quality grade"] = Value(text=m.group(1), number=None, unit="")
    res.grades = grades
    for label, pat in (("Acceptable FVC blows", r"Acceptable FVC:\s*(\d+)"), ("Acceptable FEV1 blows", r"Acceptable FEV1:\s*(\d+)")):
        m = re.search(pat, text)
        if m:
            v[label] = Value(text=m.group(1), number=float(m.group(1)), unit="")
    if not grades:
        res.notes.append("Could not read: the test quality grades")
    res.values = v
    res.not_printed.append("The reference equations used for the predicted values (they are set in the spirometer's software)")
    res.checks = run_checks(res)
    res.status = status_from(res)
    return res


def run_checks(res: ReadResult) -> list:
    checks: list = []
    t = getattr(res, "table", {})
    for key in ("FVC", "FEV1", "FEV1/FVC", "FEF25-75", "FEF75", "PEF"):
        row = t.get(key) or {}
        if row.get("best") is not None and row.get("pred") and row.get("pct") is not None:
            pct = row["best"] / row["pred"] * 100
            checks.append(Check(f"{key}: % predicted = value / predicted", close(pct, row["pct"], 0.6), f"{row['pct']:g} vs {pct:.1f}"))
        if row.get("best") is not None and row.get("lln") is not None and row.get("z") is not None and row["best"] != row["lln"]:
            consistent = (row["best"] < row["lln"]) == (row["z"] < -1.645)
            checks.append(Check(f"{key}: z-score agrees with the lower limit of normal", consistent,
                                f"value {row['best']:g}, LLN {row['lln']:g}, z {row['z']:g}"))
    fvc, fev1, ratio = (t.get("FVC") or {}).get("best"), (t.get("FEV1") or {}).get("best"), (t.get("FEV1/FVC") or {}).get("best")
    if fvc and fev1 and ratio is not None:
        checks.append(Check("FEV1/FVC = FEV1 / FVC", close(fev1 / fvc * 100, ratio, 0.3), f"{ratio:g} vs {fev1 / fvc * 100:.2f}"))
    n = res.number
    if n("Weight (kg)") and n("Height (cm)") and n("BMI"):
        bmi = n("Weight (kg)") / (n("Height (cm)") / 100) ** 2
        checks.append(Check("BMI = weight / height squared", close(bmi, n("BMI"), 0.15), f"{n('BMI'):g} vs {bmi:.2f}"))
    grades = getattr(res, "grades", {})
    if grades:
        good = all(g in GOOD_GRADES for g in grades.values())
        checks.append(Check("test quality (grades A to C are good enough to interpret)", good,
                            ", ".join(f"{k} grade {g}" for k, g in grades.items())
                            + ("" if good else ". The values may read lower than the person's true values: consider repeating the test."), severity="note"))
    return checks


def app_fields(res: ReadResult) -> dict:
    t = getattr(res, "table", {})

    def best(key, unit):
        b = (t.get(key) or {}).get("best")
        return "" if b is None else (f"{b:g}%" if unit == "%" else f"{b:g} {unit}")

    def col(key, name):
        x = (t.get(key) or {}).get(name)
        return "" if x is None else f"{x:g}"
    grades = getattr(res, "grades", {})
    return {"FVC": best("FVC", "L"), "FVC % Predicted": col("FVC", "pct"), "FVC z-score": col("FVC", "z"),
            "FEV1": best("FEV1", "L"), "FEV1 % Predicted": col("FEV1", "pct"), "FEV1 z-score": col("FEV1", "z"),
            "FEV1/FVC Ratio": best("FEV1/FVC", "%"), "FEV1/FVC z-score": col("FEV1/FVC", "z"),
            "PEF": best("PEF", "L/min"), "FEF 25-75": best("FEF25-75", "L/s"), "FEF 75": best("FEF75", "L/s"),
            "FEV1 Grade": grades.get("FEV1", ""), "FVC Grade": grades.get("FVC", "")}
