"""Reader for VALD Hub ForceDecks "Test Metrics" CSV exports (Profiles -> a person -> Result Table -> Export -> Test Metrics).

One file holds one test type, one row per test (often several dates). It contains only the columns shown in that Result Table,
so a metric the clinic has not chosen to show is simply absent. Headers are matched by name, ignoring case, spacing and the
unit; unknown columns are listed and ignored. The file has the person's name but no ID, so the clinician picks the patient.

Asymmetry cells read like "9.7 R", "1.1 L" or "0": stored as a signed number (negative = left, positive = right, as elsewhere in
the app). A body weight of -1 means not weighed, and one outside 35-250 kg is treated as a mis-weigh: both are kept as missing.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field

TEST_NAMES = {"CMJ": "Countermovement jump", "QSB": "Quiet stand", "SLSB": "Single leg stand", "SQT": "Squat",
              "STSTS": "Sit to stand to sit", "PUSHUPT": "Push-up"}
BW_PLAUSIBLE = (35.0, 250.0)
# The metrics the app uses, per test: (key, header as VALD prints it without the unit, label for people, better: "lower" | "higher" | None).
# A header with " (L)" / " (R)" / " (Asym)" after the name is the same metric for one side, or the left/right difference.
METRICS = {
    "CMJ": [("jump_height", "Jump Height (Imp-Mom)", "Jump height", "higher"),
            ("rsi_mod", "RSI-modified", "Springiness (RSI modified)", "higher"),
            ("peak_power_bm", "Peak Power / BM", "Power for your body weight", "higher"),
            ("ecc_peak_velocity", "Eccentric Peak Velocity", "Speed dipping down", None),
            ("cm_depth", "Countermovement Depth", "Depth of the dip", None),
            ("ecc_decel_impulse_asym", "Eccentric Deceleration Impulse % (Asym)", "Left–right difference slowing the dip", "lower"),
            ("con_impulse_asym", "Concentric Impulse % (Asym)", "Left–right difference pushing off", "lower"),
            ("landing_force_asym", "Peak Landing Force % (Asym)", "Left–right difference landing", "lower")],
    "QSB": [("cop_ml", "CoP Range - Medial-Lateral", "Side-to-side sway", "lower"),
            ("cop_ap", "CoP Range - Anterior-Posterior", "Front-to-back sway", "lower"),
            ("cop_area", "Area of CoP Ellipse", "Sway area", "lower"),
            ("mean_velocity", "Mean Velocity", "Sway speed", "lower"),
            ("mean_force_asym", "Mean Force % (Asym)", "Left–right weight difference", "lower")],
    "SLSB": [("cop_ml", "CoP Range - Medial-Lateral", "Side-to-side sway", "lower"),
             ("cop_ap", "CoP Range - Anterior-Posterior", "Front-to-back sway", "lower"),
             ("cop_area", "Area of CoP Ellipse", "Sway area", "lower"),
             ("mean_velocity", "Mean Velocity", "Sway speed", "lower")],
    "SQT": [("depth", "Squat Depth", "Squat depth", None),
            ("ecc_impulse_asym", "Eccentric Impulse % (Asym)", "Left–right difference lowering", "lower"),
            ("con_impulse_asym", "Concentric Impulse % (Asym)", "Left–right difference standing up", "lower"),
            ("ecc_mean_velocity", "Eccentric Mean Velocity", "Speed lowering", None),
            ("con_mean_velocity", "Concentric Mean Velocity", "Speed standing up", None)],
    "STSTS": [("time_to_stand", "Time to Stand", "Time to stand", "lower"),
              ("time_to_sit", "Time to Sit", "Time to sit", None),
              ("standing_force_asym", "Mean Standing Force % (Asym)", "Left–right difference standing up", "lower"),
              ("sitting_force_asym", "Mean Sitting Force % (Asym)", "Left–right difference sitting down", "lower")],
    "PUSHUPT": [("depth", "Push Up Depth", "Push-up depth", None),
                ("ecc_impulse_asym", "Eccentric Impulse % (Asym)", "Left–right difference lowering", "lower"),
                ("con_impulse_asym", "Concentric Impulse % (Asym)", "Left–right difference pushing up", "lower"),
                ("ecc_mean_velocity", "Eccentric Mean Velocity", "Speed lowering", None),
                ("con_mean_velocity", "Concentric Mean Velocity", "Speed pushing up", None)],
}
# Single leg stand: each metric also per leg and as a left/right difference, e.g. "Mean Velocity [mm/s] (L)".
SIDE_SUFFIXES = {"L": "_l", "R": "_r", "Asym": "_asym"}
# The results a person sees first, per test (the rest stay in the record and the clinician's view).
HEADLINES = {
    "QSB": ["mean_velocity", "cop_area", "mean_force_asym"],
    "SLSB": ["mean_velocity_l", "mean_velocity_r", "mean_velocity_asym"],
    "SQT": ["con_impulse_asym", "ecc_impulse_asym", "depth"],
    "STSTS": ["time_to_stand", "standing_force_asym"],
    "PUSHUPT": ["con_impulse_asym", "depth"],
    "CMJ": ["jump_height", "rsi_mod", "peak_power_bm", "con_impulse_asym"],
}
COMMON = {"name", "externalid", "test type", "date", "time", "bw", "reps", "reps (l)", "reps (r)", "tags", "additional load",
          "exercise length", "eyes closed", "unstable surface", "secondary task"}

_UNIT = re.compile(r"\s*\[([^\]]*)\]\s*")
_ASYM_CELL = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*([LR])?\s*$", re.I)
_NUM = re.compile(r"^\s*-?\d+(?:\.\d+)?\s*$")


def _norm(text: str) -> str:
    """'Mean Force % (Asym) (%)' -> 'mean force % (asym)'; spacing and case do not matter."""
    t = re.sub(r"\(\s*%\s*\)", "", text or "")
    return re.sub(r"\s+", " ", t).strip().lower()


def split_header(header: str):
    """'Mean Velocity [mm/s] (L)' -> ('mean velocity', 'mm/s', 'L'); 'Concentric Impulse % (Asym) (%)' -> ('concentric impulse % (asym)', '%', None)."""
    h = (header or "").replace("﻿", "").strip()
    m = _UNIT.search(h)
    unit = m.group(1).strip() if m else ""
    rest = (h[:m.start()] + " " + h[m.end():]) if m else h
    side = None
    s = re.search(r"\((L|R|Asym)\)\s*(\(\s*%\s*\))?\s*$", rest.strip())
    if s and m:                                       # a per-side column always has its unit before the side
        side = s.group(1)
        rest = rest.strip()[:s.start()]
    if "(asym)" in rest.lower() or side == "Asym":
        unit = "%"
    return _norm(rest), unit, side


@dataclass
class TestRow:
    code: str
    date: str            # ISO yyyy-mm-dd
    time: str            # 24-hour hh:mm, "" if not given
    name: str
    body_weight: float | None
    reps: str
    metrics: dict = field(default_factory=dict)   # key -> {"value", "unit", "asymmetry", "label", "better"}
    notes: list = field(default_factory=list)

    @property
    def doc_id(self) -> str:
        return f"{self.date}_{self.time.replace(':', '')}_{self.code}" if self.time else f"{self.date}_{self.code}"


@dataclass
class CsvResult:
    tests: list = field(default_factory=list)
    unknown_columns: list = field(default_factory=list)
    missing: dict = field(default_factory=dict)      # test code -> labels of the app's metrics not in this file
    problems: list = field(default_factory=list)     # reasons the file could not be read at all

    @property
    def codes(self) -> list:
        return sorted({t.code for t in self.tests})


def _date(text: str) -> str | None:
    m = re.fullmatch(r"\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*", text or "")
    return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}" if m else None


def _time(text: str) -> str:
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*([AP]M)?\s*", text or "", re.I)
    if not m:
        return ""
    h, mins, ampm = int(m.group(1)), m.group(2), (m.group(3) or "").upper()
    if ampm == "PM" and h != 12:
        h += 12
    if ampm == "AM" and h == 12:
        h = 0
    return f"{h:02d}:{mins}"


def _value(cell: str, asymmetry: bool):
    """A cell as a number: asymmetry signed (negative = left). None for an empty or unreadable cell."""
    if asymmetry:
        m = _ASYM_CELL.match(cell or "")
        if not m:
            return None
        v = abs(float(m.group(1)))
        return -v if (m.group(2) or "").upper() == "L" else v
    return float(cell) if _NUM.match(cell or "") else None


def read_csv(data: bytes) -> CsvResult:
    res = CsvResult()
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = data.decode("cp1252")
        except UnicodeDecodeError:
            res.problems.append("The file could not be read as text.")
            return res
    rows = list(csv.reader(io.StringIO(text)))
    if len(rows) < 2:
        res.problems.append("The file has no test rows.")
        return res
    header = rows[0]
    cols = {_norm(_UNIT.sub(" ", h)): i for i, h in enumerate(header)}
    need = ("name", "test type", "date")
    if any(n not in cols for n in need):
        res.problems.append("This doesn't look like a VALD Hub Test Metrics export (no Name, Test Type or Date column).")
        return res
    code_of = lambda r: (r[cols["test type"]] if len(r) > cols["test type"] else "").strip().upper()
    codes = {code_of(r) for r in rows[1:] if any(c.strip() for c in r)}
    # which column holds which metric, for each test code in the file
    by_col = {}
    known_names = {(_norm(name), key) for c in METRICS.values() for key, name, _, _ in c}
    for i, h in enumerate(header):
        base, unit, side = split_header(h)
        if not base or base in COMMON or base.startswith("bw") or base.startswith("reps"):
            continue
        match = None
        for code in codes:
            for key, name, label, better in METRICS.get(code, []):
                if _norm(name) == base:
                    k = key + (SIDE_SUFFIXES[side] if side else "")
                    asym = "(asym)" in base or side == "Asym"
                    lab = label + {None: "", "L": " (left)", "R": " (right)", "Asym": ", left–right difference"}[side]
                    match = (k, unit, asym, lab, "lower" if side == "Asym" else better)
        if match:
            by_col[i] = match
        elif not any(_norm(n) == base for n, _ in known_names):
            res.unknown_columns.append(h.strip())
    seen = set()
    for r in rows[1:]:
        if not any(c.strip() for c in r):
            continue
        cell = lambda name: r[cols[name]].strip() if name in cols and cols[name] < len(r) else ""
        code = code_of(r)
        date = _date(cell("date"))
        if code not in TEST_NAMES or not date:
            res.problems.append(f"A row was skipped: test type '{code}' or date '{cell('date')}' was not recognised.")
            continue
        bw_text = cell("bw")
        try:
            bw = float(bw_text)
        except ValueError:
            bw = None
        t = TestRow(code=code, date=date, time=_time(cell("time")), name=cell("name"), body_weight=None, reps=cell("reps"))
        lo, hi = BW_PLAUSIBLE
        if bw is not None and lo <= bw <= hi:
            t.body_weight = bw
        elif bw is not None and bw != -1:
            t.notes.append(f"Body weight {bw:g} kg looks wrong, so it was not used. Check the weigh-in in VALD Hub.")
        for i, (key, unit, asym, label, better) in by_col.items():
            v = _value(r[i] if i < len(r) else "", asym)
            if v is not None:
                t.metrics[key] = {"value": v, "unit": unit, "asymmetry": asym, "label": label, "better": better}
        if t.code == "CMJ" and t.metrics.get("cm_depth", {}).get("value") == 0:
            t.notes.append("The dip depth reads 0, which usually means a failed or incomplete jump.")
        if t.doc_id in seen:
            continue                                    # the same test twice in one file
        seen.add(t.doc_id)
        res.tests.append(t)
    for code in {t.code for t in res.tests}:
        have = {k for t in res.tests if t.code == code for k in t.metrics}
        res.missing[code] = [label for key, _, label, _ in METRICS[code]
                             if key not in have and not any(k.startswith(key + "_") for k in have)]
    return res


def display(m: dict) -> str:
    """A stored metric as people read it: '18.2 cm', '9.7% R', '0%'."""
    v, unit = m["value"], m.get("unit") or ""
    if m.get("asymmetry"):
        return "0%" if v == 0 else f"{abs(v):g}% {'L' if v < 0 else 'R'}"
    return f"{v:g} {unit}".strip()
