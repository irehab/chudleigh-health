"""Compares a participant's measured values with published reference data for their age and sex.

Everything here is a table look-up or a sum. No model is involved, and a comparison is only made when the reference data
covers the participant's age and (where it matters) sex. Otherwise the measure is listed as "not compared", with the reason.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from . import data

NORMS_VERSION = "2026-10-11"

# statuses
WITHIN, BELOW, ABOVE, WELL_ABOVE, REPORTED, NO_REFERENCE = "within", "below", "above", "well_above", "reported", "no_reference"

# assessment names used by the app (kept here as plain strings so this package stands alone)
A_SPO2 = "SpO2 / Pulse Oximetry (ViHealth)"
A_TANITA = "Tanita Body Composition (MC-780MA)"
A_ECG = "12-Lead ECG (Electrocardiogram)"
A_AGE = "AGE Reader (Advanced Glycation End-Products)"


@dataclass
class Comparison:
    key: str
    label: str
    assessment: str
    status: str
    source: str = ""
    value: float | None = None
    value_text: str = ""
    range_text: str = ""
    group: str = ""
    sentence: str = ""
    detail: str = ""
    reason: str = ""  # why a measure could not be compared
    calculated: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


# ------------------------------------------------------------------------------------------------ reading numbers out of the tests
_NUM = re.compile(r"-?\d+(?:\.\d+)?")


def _num(text):
    """The first number in a string like '54 bpm' or '18.3%', or None."""
    m = _NUM.search(str(text if text is not None else ""))
    return float(m.group(0)) if m else None


def _extra_num(test, *names):
    for name in names:
        v = (test.get("extra") or {}).get(name)
        if v is not None and _num(v) is not None:
            return _num(v)
    return None


def _qtc_numbers(text) -> dict:
    """'406 ms (Bazett) / 413 ms (Fridericia)' -> {'bazett': 406, 'fridericia': 413}. A single QTc with no formula named gives nothing."""
    out = {}
    for number, formula in re.findall(r"(\d{3})\s*(?:ms)?\s*\(\s*(bazett|fridericia)\s*\)", str(text or ""), re.I):
        out[formula.lower()] = float(number)
    return out


def measures_from_tests(tests: list, height_cm: float | None = None) -> dict:
    """Pull the numbers we can compare out of the participant's assessments. If a type was added more than once, the last one is used.

    Returns {measure key: {"value": float, "assessment": str, "calculated": bool, ...}}.
    """
    out: dict = {}
    for t in tests or []:
        a, d = t.get("type", ""), t.get("data") or {}
        if a == A_SPO2:
            if _num(d.get("Average SpO2")) is not None:
                out["spo2_avg"] = {"value": _num(d["Average SpO2"]), "assessment": a}
            if _num(d.get("Average Pulse Rate")) is not None:
                out["pulse_avg"] = {"value": _num(d["Average Pulse Rate"]), "assessment": a}
        elif a == A_TANITA:
            if _num(d.get("Fat %")) is not None:
                out["fat_pct"] = {"value": _num(d["Fat %"]), "assessment": a}
            bmi = _extra_num(t, "BMI")
            calculated = False
            weight = _num(d.get("Weight"))
            if bmi is None and weight and height_cm:
                bmi, calculated = round(weight / (height_cm / 100.0) ** 2, 1), True
            if bmi is not None:
                out["bmi"] = {"value": bmi, "assessment": a, "calculated": calculated}
        elif a == A_ECG:
            for key, field_name in (("ecg_hr", "Heart Rate"), ("ecg_pr", "PR Interval"), ("ecg_qrs", "QRS Duration")):
                if _num(d.get(field_name)) is not None:
                    out[key] = {"value": _num(d[field_name]), "assessment": a}
            qtc = _qtc_numbers(d.get("QTc Interval"))
            b = _extra_num(t, "QTcB, Bazett (ms)") or qtc.get("bazett")
            f = _extra_num(t, "QTcF, Fridericia (ms)") or qtc.get("fridericia")
            if b:
                out["ecg_qtcb"] = {"value": b, "assessment": a}
            if f:
                out["ecg_qtcf"] = {"value": f, "assessment": a}
        elif a == A_AGE:
            pos = _extra_num(t, "Position within age group (%)")
            vs = _extra_num(t, "AGE level compared with average (%)")
            if pos is not None:
                out["age_pos"] = {"value": pos, "assessment": a}
            if vs is not None:
                out["age_vs_avg"] = {"value": vs, "assessment": a, "direction": ((t.get("extra") or {}).get("Comparison direction") or "").lower(),
                                     "age_used": _extra_num(t, "Age used for comparison (years)")}
    return out


# ------------------------------------------------------------------------------------------------ helpers
def normalise_sex(sex) -> str | None:
    s = str(sex or "").strip().lower()
    if s in ("male", "m", "man"):
        return "male"
    if s in ("female", "f", "woman"):
        return "female"
    return None


def _group(groups, age):
    for lo, hi, label in groups:
        if lo <= age <= hi:
            return label
    return None


def _who(sex, label):
    return f"{'men' if sex == 'male' else 'women'} aged {label}"


def _fmt(v) -> str:
    return f"{v:g}"


def _unit_text(value, unit):
    return f"{_fmt(value)} {unit}".strip() if unit not in ("%",) else f"{_fmt(value)}%"


def _no_ref(key, label, assessment, value, unit, reason, calculated=False) -> Comparison:
    return Comparison(key=key, label=label, assessment=assessment, status=NO_REFERENCE, value=value, value_text=_unit_text(value, unit), reason=reason, calculated=calculated)


def _missing(age, sex, need_sex=True, min_age=None, min_age_text="") -> str:
    """What the participant's details lack for this comparison, as a sentence, or '' if nothing is missing."""
    if age is None and need_sex and sex is None:
        return "Needs the participant's age and sex to choose reference data."
    if age is None:
        return "Needs the participant's age to choose reference data."
    if need_sex and sex is None:
        return "Needs the participant's sex (male or female) to choose reference data."
    return ""


def _range_status(v, lo, hi) -> str:
    return BELOW if v < lo else ABOVE if v > hi else WITHIN


_WHERE = {WITHIN: "within that range", BELOW: "lower than that range", ABOVE: "higher than that range"}

_PULSE_NOTE = {
    BELOW: "A lower resting pulse is common in people who exercise regularly. If you also have dizziness, fainting or breathlessness, speak to your clinician or GP.",
    ABOVE: "Resting pulse can be higher after caffeine, poor sleep, stress, illness or being less fit. If it stays high, it is worth discussing with your clinician.",
}
_ECG_NOTE = {
    BELOW: "Your clinician will read this together with the rest of your ECG. A value outside the usual range is not a diagnosis.",
    ABOVE: "Your clinician will read this together with the rest of your ECG. A value outside the usual range is not a diagnosis.",
}

# ------------------------------------------------------------------------------------------------ the comparisons
_ECG_LABELS = {
    "ecg_hr": ("Heart rate at the ECG", "beats per minute", "bpm"),
    "ecg_pr": ("ECG PR interval", "milliseconds", "ms"),
    "ecg_qrs": ("ECG QRS duration", "milliseconds", "ms"),
    "ecg_qtcb": ("ECG QTc (Bazett correction)", "milliseconds", "ms"),
    "ecg_qtcf": ("ECG QTc (Fridericia correction)", "milliseconds", "ms"),
}


def _compare_one(key, m, age, sex, height_cm) -> Comparison:
    v, a = m["value"], m["assessment"]
    calc = bool(m.get("calculated"))

    if key == "pulse_avg":
        label, unit = "Resting pulse (average over the recording)", "bpm"
        why = _missing(age, sex)
        if why:
            return _no_ref(key, label, a, v, unit, why)
        if age < 20:
            return _no_ref(key, label, a, v, unit, "The reference survey covers ages 20 and over.")
        g = _group(data.PULSE_GROUPS, age)
        lo, med, hi = data.PULSE[sex][g]
        status = _range_status(v, lo, hi)
        who = _who(sex, g)
        return Comparison(
            key=key, label=label, assessment=a, status=status, source="nhanes_pulse", value=v, value_text=f"{_fmt(v)} bpm",
            range_text=f"{lo} to {hi} bpm", group=who,
            sentence=(f"Your resting pulse averaged {_fmt(v)} beats per minute. In a large US health survey, 9 in 10 healthy {who} had a resting pulse "
                      f"between {lo} and {hi}. Yours is {_WHERE[status]}."),
            detail=_PULSE_NOTE.get(status, ""),
        )

    if key in _ECG_LABELS:
        label, unit_long, unit = _ECG_LABELS[key]
        why = _missing(age, sex)
        if why:
            return _no_ref(key, label, a, v, unit, why)
        g = _group(data.ECG_GROUPS, age)
        if g is None:
            why = "The reference study has too few people aged 80 and over for reliable limits." if age >= 80 else "The reference study covers ages 16 to 79."
            return _no_ref(key, label, a, v, unit, why)
        lo, med, hi = data.ECG[key][sex][g]
        status = _range_status(v, lo, hi)
        who = _who(sex, g)
        return Comparison(
            key=key, label=label, assessment=a, status=status, source="rijnbeek_ecg", value=v, value_text=f"{_fmt(v)} {unit}",
            range_text=f"{lo} to {hi} {unit}", group=who,
            sentence=(f"Your {label[0].lower() + label[1:] if not label.startswith('ECG') else label} was {_fmt(v)} {unit_long}. In a study of healthy adults, "
                      f"about 96 in 100 {who} were between {lo} and {hi}. Yours is {_WHERE[status]}."),
            detail=_ECG_NOTE.get(status, ""),
        )

    if key == "fat_pct":
        label, unit = "Body fat", "%"
        why = _missing(age, sex)
        if why:
            return _no_ref(key, label, a, v, unit, why)
        g = _group(data.FAT_GROUPS, age)
        if g is None:
            return _no_ref(key, label, a, v, unit, "The reference table covers ages 20 to 79.")
        low, over, obese = data.FAT[sex][g]
        who = _who(sex, g)
        status = BELOW if v < low else WITHIN if v < over else ABOVE if v < obese else WELL_ABOVE
        where = {BELOW: "lower than that range, in the range that matches a BMI under 18.5",
                 WITHIN: "within that range",
                 ABOVE: "above that range, in the range that matches a BMI of 25 to 30",
                 WELL_ABOVE: "well above that range, in the range that matches a BMI of 30 or more"}[status]
        return Comparison(
            key=key, label=label, assessment=a, status=status, source="gallagher_fat", value=v, value_text=f"{_fmt(v)}%",
            range_text=f"{low}% to under {over}%", group=who,
            sentence=(f"Your body fat was {_fmt(v)}%. For {who}, the study's healthy range is {low}% to under {over}%. Yours is {where}."),
            detail=("These ranges are provisional and were worked out from BMI limits. Body fat from a bioimpedance scale can differ from the laboratory methods used to make them."
                    + (" A lower body fat is common in people who train hard." if status == BELOW else "")),
        )

    if key == "bmi":
        label, unit = "Body mass index (BMI)", ""
        if age is not None and age < 18:
            return _no_ref(key, label, a, v, unit, "The WHO adult groups are for people aged 18 and over.", calc)
        lo, over, obese = data.BMI_LIMITS
        status = BELOW if v < lo else WITHIN if v < over else ABOVE if v < obese else WELL_ABOVE
        where = {BELOW: "lower than the healthy range", WITHIN: "within the healthy range", ABOVE: "above the healthy range, in the overweight group",
                 WELL_ABOVE: "well above the healthy range, in the group the WHO calls obese"}[status]
        return Comparison(
            key=key, label=label, assessment=a, status=status, source="who_bmi", value=v, value_text=_fmt(v), calculated=calc,
            range_text="18.5 to under 25", group="adults",
            sentence=(f"Your BMI was {_fmt(v)}{' (worked out from your weight and height)' if calc else ''}. The World Health Organization's healthy range for adults "
                      f"is 18.5 to under 25. Yours is {where}."),
            detail="BMI is only a rough guide. It cannot tell muscle from fat, so it can mislead for very muscular people.",
        )

    if key == "spo2_avg":
        label, unit = "Blood oxygen level (average over the recording)", "%"
        why = _missing(age, sex, need_sex=False)
        if why:
            return _no_ref(key, label, a, v, unit, why)
        if age < 18:
            return _no_ref(key, label, a, v, unit, "The reference data is for adults aged 18 and over.")
        older = age >= data.SPO2_OLDER_AGE
        lower = data.SPO2_OLDER_LOWER if older else data.SPO2_ADULT_LOWER
        status = WITHIN if v >= lower else BELOW
        if older:
            sentence = (f"Your blood oxygen level averaged {_fmt(v)}%. In a study of healthy adults over 65, 95 in 100 had a reading of {lower}% or higher. "
                        f"Yours is {'within' if status == WITHIN else 'lower than'} that range.")
        else:
            sentence = (f"Your blood oxygen level averaged {_fmt(v)}%. In healthy adults it is usually {lower}% or higher. "
                        f"Yours is {'within' if status == WITHIN else 'lower than'} that range.")
        return Comparison(
            key=key, label=label, assessment=a, status=status, source="spo2_older" if older else "spo2_adults", value=v, value_text=f"{_fmt(v)}%",
            range_text=f"{lower}% or higher", group="healthy adults aged 65 and over" if older else "healthy adults under 65", sentence=sentence,
            detail=("A short reading can be affected by cold hands, movement or nail polish. If readings stay low, or you feel breathless, speak to your GP."
                    if status == BELOW else ""),
        )

    if key == "age_pos":
        return Comparison(
            key=key, label="Skin AGE level compared with others of your age", assessment=a, status=REPORTED, source="age_scanner_printed", value=v,
            value_text=f"{_fmt(v)}%", range_text="the device's own comparison",
            sentence=f"Your AGE Scanner report places you at {_fmt(v)}% within your age group, using the device maker's own reference group.",
        )
    if key == "age_vs_avg":
        way = m.get("direction") or ""
        age_used = m.get("age_used")
        if way not in ("below", "above"):
            return _no_ref(key, "Skin AGE level compared with the average", a, v, "%", "The report's wording about above or below the average could not be read.")
        return Comparison(
            key=key, label="Skin AGE level compared with the average", assessment=a, status=REPORTED, source="age_scanner_printed", value=v,
            value_text=f"{_fmt(v)}% {way}", range_text="the device's own comparison",
            sentence=(f"Your AGE Scanner report says your AGE level is {_fmt(v)}% {way} the average for "
                      f"{str(int(age_used)) + '-year-olds' if age_used else 'your age group'}, using the device maker's own reference group."),
        )
    return _no_ref(key, key, a, v, "", "No reference data is available for this measure.")


_ORDER = ["pulse_avg", "spo2_avg", "ecg_hr", "ecg_pr", "ecg_qrs", "ecg_qtcf", "ecg_qtcb", "fat_pct", "bmi", "age_pos", "age_vs_avg"]


def compare(tests: list, age, sex, height_cm=None) -> list:
    """All the comparisons that can be made for this participant's tests, as a list of Comparison objects."""
    def positive(x, cast):
        try:
            return cast(x) if x not in (None, "") and float(x) > 0 else None
        except (TypeError, ValueError):
            return None

    age, height_cm, sex = positive(age, int), positive(height_cm, float), normalise_sex(sex)
    measures = measures_from_tests(tests, height_cm)
    return [_compare_one(k, measures[k], age, sex, height_cm) for k in _ORDER if k in measures]


# ------------------------------------------------------------------------------------------------ summary and text for the AI
def tally(comparisons: list) -> dict:
    counts = {WITHIN: 0, BELOW: 0, ABOVE: 0, WELL_ABOVE: 0, REPORTED: 0, NO_REFERENCE: 0}
    for c in comparisons:
        counts[c["status"] if isinstance(c, dict) else c.status] += 1
    return counts


def summary_sentence(comparisons: list) -> str:
    c = tally(comparisons)
    compared = c[WITHIN] + c[BELOW] + c[ABOVE] + c[WELL_ABOVE]
    if not compared:
        return "None of your results could be compared with reference data yet." if not c[REPORTED] else "Your AGE Scanner report includes its own comparison, shown below."
    parts = [f"{c[WITHIN]} within the usual range"]
    if c[BELOW]:
        parts.append(f"{c[BELOW]} lower")
    if c[ABOVE] + c[WELL_ABOVE]:
        parts.append(f"{c[ABOVE] + c[WELL_ABOVE]} higher")
    return f"We compared {compared} of your results with reference data: " + ", ".join(parts) + "."


def comparison_context(comparisons: list, assessments=None) -> str:
    """Plain lines for the AI, so it can mention the comparisons exactly as the app worked them out. Empty if there are none."""
    lines = []
    for c in comparisons:
        c = c if isinstance(c, dict) else c.to_dict()
        if assessments is not None and c["assessment"] not in assessments:
            continue
        if c["status"] == NO_REFERENCE:
            continue
        if c["status"] == REPORTED:
            lines.append(f"- {c['label']}: {c['value_text']} (the device's own comparison, as printed on the report)")
        else:
            lines.append(f"- {c['label']}: {c['value_text']}; for {c['group']} the reference range is {c['range_text']}; this is {c['status'].replace('_', ' ')} "
                         f"(source: {data.SOURCES[c['source']]['short']})")
    if not lines:
        return ""
    return ("Reference comparisons computed by the app from published tables. Use them exactly as given and do not add any other ranges:\n" + "\n".join(lines) + "\n")
