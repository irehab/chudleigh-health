"""Compares a participant's measured values with published reference data for their age and sex, and says what that means.

Everything here is a table look-up, a sum, or wording chosen from fixed templates. No model is involved. A comparison is only made
when the reference data covers the participant's age and (where it matters) sex. Otherwise the measure is listed as "not compared",
with the reason.

The wording follows three rules. It states the fact first, then says plainly whether it is good news or something to work on, and
then explains why. It only links a result to a health outcome where a source says so (WHO, the NCHS pulse report, the systematic
review in data.SOURCES), and it never promises an outcome. Every sentence a participant reads is kept to 20 words or fewer.

The AGE Reader (Diagnoptics) is the one device whose own norms are used: its printed average AGE level for the person's age, how far
above or below it they are, its BodyAge against their age, and its own label. Those are judged here exactly as the report prints them.
Dates, times and how long a test ran are never used.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from . import data

NORMS_VERSION = "2026-10-19.4"

# statuses
WITHIN, BELOW, ABOVE, WELL_ABOVE, REPORTED, NO_REFERENCE = "within", "below", "above", "well_above", "reported", "no_reference"
# themes: how a result is described in the overall summary
DOING_WELL, WATCH, WORK_ON, DISCUSS, INFO = "doing_well", "watch", "work_on", "discuss", "info"

# assessment names used by the app (kept here as plain strings so this package stands alone)
A_SPO2 = "SpO2 / Pulse Oximetry (ViHealth)"
A_TANITA = "Tanita Body Composition (MC-780MA)"
A_ECG = "12-Lead ECG (Electrocardiogram)"
A_AGE = "AGE Reader (Advanced Glycation End-Products)"

# What a participant reads as the name of each result, and one plain line on what it measures.
PATIENT_TEXT = {
    "pulse_avg": ("Resting pulse", "How many times your heart beats each minute while you are at rest."),
    "spo2_avg": ("Blood oxygen level", "How much oxygen your blood is carrying, as a percentage."),
    "ecg_hr": ("Heart rate at your ECG", "How many times your heart beat each minute during your ECG."),
    "ecg_pr": ("Heart signal timing (PR interval)", "How long the heart's electrical signal takes to pass from the top of your heart to the bottom."),
    "ecg_qrs": ("Heart squeeze timing (QRS duration)", "How long the electrical signal takes to spread through the lower chambers of your heart."),
    "ecg_qtcf": ("Heart reset time (QTc)", "How long your heart takes to reset between beats, adjusted for your heart rate."),
    "ecg_qtcb": ("Heart reset time (QTc, Bazett)", "How long your heart takes to reset between beats, adjusted for your heart rate."),
    "fat_pct": ("Body fat", "The share of your body weight that is fat, as estimated by the body composition scale."),
    "bmi": ("BMI", "A rough measure of whether your weight suits your height."),
    "age_level": ("Skin AGE level", "A skin scan that estimates the build-up of substances called AGEs, which build up naturally as we age."),
    "age_bodyage": ("Skin age estimate (BodyAge)", "The age at which an average person has your skin AGE level, according to the AGE Reader."),
    "asm_index": ("Arm and leg muscle (sarcopenia check)", "The muscle in your arms and legs, compared with your height."),
}


@dataclass
class Comparison:
    key: str
    label: str           # the technical name, for the clinician
    assessment: str
    status: str
    source: str = ""
    value: float | None = None
    value_text: str = ""
    range_text: str = ""
    group: str = ""
    headline: str = ""   # a short verdict: "A good result", "Worth working on"
    sentence: str = ""   # the facts: your value, the range, and where you sit
    meaning: str = ""    # what it means, in plain words
    detail: str = ""     # a caution, where one is needed
    position: str = ""   # for a result within its range: lower, middle or upper
    theme: str = ""      # doing_well, watch, work_on, discuss or info
    reason: str = ""     # why a measure could not be compared
    calculated: bool = False
    also_sources: list = field(default_factory=list)
    status_text: str = ""     # the words for the chip, when "within the expected range" is not the right wording
    patient_label: str = ""   # the name a participant reads
    measures: str = ""        # one plain line on what it measures
    low: float | None = None  # the usual range, as numbers, for the bar
    high: float | None = None

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
            limbs = [_num(d.get(f"{side} {limb} Muscle")) for side in ("Right", "Left") for limb in ("Arm", "Leg")]
            if all(x is not None and x > 0 for x in limbs):
                asm = round(sum(limbs), 1)
                h = height_cm or _extra_num(t, "Height (cm)")           # the height entered by the clinician, or the one printed on the Tanita
                out["asm_index"] = {"value": round(asm / (h / 100.0) ** 2, 1) if h else asm, "asm": asm, "height_cm": h, "assessment": a, "calculated": True}
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
            ex = t.get("extra") or {}
            level, avg = _extra_num(t, "AGE level"), _extra_num(t, "AGE level, average for age")
            pct, age_used = _extra_num(t, "AGE level compared with average (%)"), _extra_num(t, "Age used for comparison (years)")
            direction = (ex.get("Comparison direction") or "").strip().lower()
            calculated = False
            if pct is None and level is not None and avg:           # the gauge numbers are printed even if the sentence could not be read
                pct, calculated = round(abs(1 - level / avg) * 100, 1), True
                direction = direction or ("below" if level < avg else "above" if level > avg else "")
            if pct is not None or level is not None:
                out["age_level"] = {"value": level if level is not None else pct, "assessment": a, "level": level, "average": avg, "pct": pct, "direction": direction,
                                    "age_used": age_used, "label": (ex.get("Risk label (as printed)") or "").strip(), "calculated": calculated,
                                    "position": _extra_num(t, "Position within age group (%)")}
            body = _extra_num(t, "BodyAge (years)")
            if body is not None:
                out["age_bodyage"] = {"value": body, "assessment": a, "age_used": age_used, "diff": _extra_num(t, "BodyAge difference from age (years)")}
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


def _missing(age, sex, need_sex=True) -> str:
    """What the participant's details lack for this comparison, as a sentence, or '' if nothing is missing."""
    if age is None and need_sex and sex is None:
        return "Age and sex are needed to choose reference data."
    if age is None:
        return "An age is needed to choose reference data."
    if need_sex and sex is None:
        return "A sex (male or female) is needed to choose reference data."
    return ""


def _range_status(v, lo, hi) -> str:
    return BELOW if v < lo else ABOVE if v > hi else WITHIN


def _position(v, lo, hi) -> str:
    """Where a value inside a range sits: the lower, middle or upper third."""
    if hi <= lo:
        return "middle"
    f = (v - lo) / (hi - lo)
    return "lower" if f < 1 / 3 else "middle" if f < 2 / 3 else "upper"


_POS_TEXT = {"lower": "toward the lower end", "middle": "around the middle", "upper": "toward the upper end"}


def _where(status, pos) -> str:
    return {WITHIN: f"within that range, {_POS_TEXT.get(pos, 'inside it')}", BELOW: "lower than that range", ABOVE: "higher than that range"}[status]


# ------------------------------------------------------------------------------------------------ the wording (every sentence is 20 words or fewer)
_CAUTION = ("Your clinician will look at this closely with the rest of your ECG. A value outside the expected range is not a diagnosis. "
            "There are often harmless explanations.")
_PULSE_LINK = "Studies have linked a higher resting pulse with a higher chance of heart disease."
_GRADED = "The chance of type 2 diabetes and heart disease generally rises step by step as body fat goes up."

_ECG_LABELS = {
    "ecg_hr": ("Heart rate at the ECG", "beats per minute", "bpm"),
    "ecg_pr": ("ECG PR interval", "milliseconds", "ms"),
    "ecg_qrs": ("ECG QRS duration", "milliseconds", "ms"),
    "ecg_qtcb": ("ECG QTc (Bazett correction)", "milliseconds", "ms"),
    "ecg_qtcf": ("ECG QTc (Fridericia correction)", "milliseconds", "ms"),
}


# how a sentence refers to each ECG result (plain words; the card title also carries the technical name in brackets)
_ECG_SUBJECT = {"ecg_hr": "heart rate at the ECG", "ecg_pr": "PR interval", "ecg_qrs": "QRS duration", "ecg_qtcf": "QTc", "ecg_qtcb": "QTc (Bazett correction)"}


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
        pos = _position(v, lo, hi) if status == WITHIN else ""
        sentence = (f"Your resting pulse averaged {_fmt(v)} beats per minute. In a large US health survey, 9 in 10 healthy {who} were between {lo} and {hi}. "
                    f"Yours is {_where(status, pos)}.")
        if status == WITHIN and v <= med:
            headline, theme = "A good result", DOING_WELL
            meaning = f"That is in the lower half of the expected range, which is a good place to be. {_PULSE_LINK} So a lower one is the better direction."
        elif status == WITHIN:
            headline, theme = "Within the expected range", DOING_WELL
            meaning = (f"That is in the upper half of the expected range, which is fine. {_PULSE_LINK} "
                       "If you would like to bring it down, regular exercise, good sleep and managing stress can all help.")
        elif status == ABOVE:
            headline, theme = "Worth working on", WORK_ON
            meaning = (f"A higher resting pulse can follow caffeine, poor sleep, stress, illness or being less fit. {_PULSE_LINK} "
                       "It is worth working on, and worth mentioning to your clinician if it stays high.")
        else:
            headline, theme = "Worth a mention to your clinician", DISCUSS
            meaning = "A low resting pulse is common in people who exercise regularly. If you also feel dizzy, faint or breathless, speak to your clinician or GP."
        return Comparison(key=key, label=label, assessment=a, status=status, source="nhanes_pulse", value=v, value_text=f"{_fmt(v)} bpm",
                          range_text=f"{lo} to {hi} bpm", group=who, headline=headline, sentence=sentence, meaning=meaning, position=pos, theme=theme, low=lo, high=hi)

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
        pos = _position(v, lo, hi) if status == WITHIN else ""
        name = _ECG_SUBJECT[key]
        sentence = (f"Your {name} was {_fmt(v)} {unit_long}. In a study of healthy adults, about 96 in 100 {who} were between {lo} and {hi}. "
                    f"Yours is {_where(status, pos)}.")
        if status == WITHIN:
            headline, theme = "Within the range seen in healthy adults", DOING_WELL
            meaning = "Good news. Your clinician reads this together with the rest of your ECG."
        else:
            headline, theme = "Worth discussing with your clinician", DISCUSS
            meaning = _CAUTION
        return Comparison(key=key, label=label, assessment=a, status=status, source="rijnbeek_ecg", value=v, value_text=f"{_fmt(v)} {unit}",
                          range_text=f"{lo} to {hi} {unit}", group=who, headline=headline, sentence=sentence, meaning=meaning, position=pos, theme=theme, low=lo, high=hi)

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
        pos = _position(v, low, over) if status == WITHIN else ""
        where = {BELOW: "lower than it, in the range that matches a BMI under 18.5",
                 WITHIN: f"within it, {_POS_TEXT.get(pos, '')}",
                 ABOVE: "above it, in the range that matches a BMI of 25 to 30",
                 WELL_ABOVE: "well above it, in the range that matches a BMI of 30 or more"}[status]
        sentence = f"Your body fat was {_fmt(v)}%. For {who}, the healthy range in the study is {low}% to under {over}%. Yours is {where}."
        if status == WITHIN and pos in ("lower", "middle"):
            headline, theme = "A good result", DOING_WELL
            meaning = f"Well done. {_GRADED} Being {'toward the lower end of' if pos == 'lower' else 'around the middle of'} the healthy range is a good place to be."
        elif status == WITHIN:
            headline, theme = "Within the healthy range, toward the top", WATCH
            meaning = f"You are still within the healthy range, which is good, but toward the top of it. {_GRADED} It is worth keeping an eye on."
        elif status == ABOVE:
            headline, theme = "Worth working on", WORK_ON
            meaning = ("That matches a BMI of 25 to 30. The World Health Organization rates the chance of type 2 diabetes and heart disease as increased at that level. "
                       "The good news is that body fat can change. Bringing it down towards the healthy range is worth working on to support your long-term health. "
                       "We will talk through how.")
        elif status == WELL_ABOVE:
            headline, theme = "Worth working on", WORK_ON
            meaning = ("That matches a BMI of 30 or more. The World Health Organization rates the chance of type 2 diabetes and heart disease as moderate or higher. "
                       "This is worth taking seriously and working on steadily. Realistic, steady steps matter more than quick fixes. We will talk through how.")
        else:
            headline, theme = "Worth a mention to your clinician", DISCUSS
            meaning = ("A low body fat is common in people who train hard. If it is not intentional, please mention it to your clinician. "
                       "Please also mention it if you feel tired or run down, or have lost weight without trying.")
        return Comparison(
            key=key, label=label, assessment=a, status=status, source="gallagher_fat", value=v, value_text=f"{_fmt(v)}%",
            range_text=f"{low}% to under {over}%", group=who, headline=headline, sentence=sentence, meaning=meaning, position=pos, theme=theme, low=low, high=over,
            detail="These ranges are provisional and were worked out from BMI limits. Body fat from a body composition scale can differ from the laboratory methods used to make them.",
            also_sources=["who_bmi", "guh_comorbidities"] if status in (ABOVE, WELL_ABOVE, WITHIN) else [],
        )

    if key == "bmi":
        label, unit = "Body mass index (BMI)", ""
        if age is not None and age < 18:
            return _no_ref(key, label, a, v, unit, "The WHO adult groups are for people aged 18 and over.", calc)
        lo, over, obese = data.BMI_LIMITS
        status = BELOW if v < lo else WITHIN if v < over else ABOVE if v < obese else WELL_ABOVE
        where = {BELOW: "lower than the healthy range", WITHIN: "within the healthy range", ABOVE: "above the healthy range, in the overweight group",
                 WELL_ABOVE: "well above the healthy range, in the group the WHO calls obese"}[status]
        sentence = (f"Your BMI was {_fmt(v)}{' (worked out from your weight and height)' if calc else ''}. "
                    f"The World Health Organization's healthy range for adults is 18.5 to under 25. Yours is {where}.")
        if status == WITHIN:
            headline, theme = "A good result", DOING_WELL
            meaning = ("Well done. At this level the World Health Organization rates the chance of weight-related conditions as average. "
                       "BMI is only a rough guide, so we read it alongside your body fat.")
        elif status in (ABOVE, WELL_ABOVE):
            headline, theme = "Worth working on", WORK_ON
            meaning = (f"At this level, the chance of type 2 diabetes and heart disease is {'increased' if status == ABOVE else 'moderate or higher'}. "
                       "That is the World Health Organization's rating. BMI cannot tell muscle from fat, though. Please read it alongside your body fat.")
        else:
            headline, theme = "Worth a mention to your clinician", DISCUSS
            meaning = ("A low BMI can mean there is little reserve if you become unwell. If it is not intentional, please mention it to your clinician. "
                       "Please also mention it if you have lost weight without trying.")
        return Comparison(key=key, label=label, assessment=a, status=status, source="who_bmi", value=v, value_text=_fmt(v), calculated=calc,
                          range_text="18.5 to under 25", group="adults", headline=headline, sentence=sentence, meaning=meaning, theme=theme, low=lo, high=over,
                          detail="BMI is only a rough guide. It cannot tell muscle from fat, so it can mislead for very muscular people.",
                          also_sources=["guh_comorbidities"] if status in (ABOVE, WELL_ABOVE) else [])

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
        where = "within that range" if status == WITHIN else "lower than that range"
        if older:
            sentence = (f"Your blood oxygen level averaged {_fmt(v)}%. In a study of healthy adults over 65, 95 in 100 had a reading of {lower}% or higher. "
                        f"Yours is {where}.")
        else:
            sentence = f"Your blood oxygen level averaged {_fmt(v)}%. In healthy adults it is usually {lower}% or higher. Yours is {where}."
        if status == WITHIN:
            headline, theme = "A good result", DOING_WELL
            meaning = "That is a good sign that your blood is carrying oxygen well while you are at rest."
        else:
            headline, theme = "Worth discussing with your clinician", DISCUSS
            meaning = ("Your clinician will want to look at this properly. A short reading can be affected by cold hands, movement or nail polish. "
                       "It may be worth repeating.")
        return Comparison(
            key=key, label=label, assessment=a, status=status, source="spo2_older" if older else "spo2_adults", value=v, value_text=f"{_fmt(v)}%",
            range_text=f"{lower}% or higher", group="healthy adults aged 65 and over" if older else "healthy adults under 65", headline=headline,
            sentence=sentence, meaning=meaning, theme=theme, low=float(lower), high=100.0,
            detail=("If readings stay low, or you feel breathless, speak to your GP." if status == BELOW else ""),
        )

    if key == "asm_index":
        return _asm_index(m, sex)

    if key == "age_level":
        return _age_level(m, age)
    if key == "age_bodyage":
        return _age_bodyage(m, age)
    return _no_ref(key, key, a, v, "", "No reference data is available for this measure.")


def _asm_index(m, sex) -> Comparison:
    """EWGSOP2 low-muscle check: arm and leg muscle (from the Tanita's segments) divided by height squared, or in kg if there is no height."""
    a, asm, h = m["assessment"], m["asm"], m.get("height_cm")
    label = "Appendicular muscle (EWGSOP2 low-muscle check)"
    unit = "kg/m²" if h else "kg"
    if sex is None:
        return _no_ref("asm_index", label, a, m["value"], unit, "A sex (male or female) is needed: the cut-offs differ for men and women.", True)
    cut_kg, cut_idx = data.EWGSOP2_LOW_MUSCLE[sex]
    cut = cut_idx if h else cut_kg
    v = m["value"]
    status = WITHIN if v >= cut else BELOW
    who = "men" if sex == "male" else "women"
    if h:
        sentence = (f"The muscle in your arms and legs adds up to {_fmt(asm)} kg. Divided by your height squared, that is {_fmt(v)} kg/m². "
                    f"The European guidance marks under {_fmt(cut)} kg/m² as low muscle for {who}. Yours is {'above' if status == WITHIN else 'under'} that line.")
    else:
        sentence = (f"The muscle in your arms and legs adds up to {_fmt(asm)} kg. The European guidance marks under {_fmt(cut)} kg as low muscle for {who}. "
                    f"Yours is {'above' if status == WITHIN else 'under'} that line.")
    if status == WITHIN:
        headline, theme, words = "A good result", DOING_WELL, "Above the low-muscle line"
        meaning = "That is above the line the guidance uses for low muscle, which is good."
    else:
        headline, theme, words = "Worth working on", WORK_ON, "Under the low-muscle line"
        meaning = "That is under the line the guidance uses for low muscle. Your clinician will look at it together with your strength results."
    return Comparison(key="asm_index", label=label, assessment=a, status=status, source="ewgsop2", value=v, value_text=_unit_text(v, unit), calculated=True,
                      range_text=f"{_fmt(cut)} {unit} or more", group=who, headline=headline, sentence=sentence, meaning=meaning, theme=theme, status_text=words,
                      detail="These cut-offs come mainly from DXA scans. A body composition scale estimates muscle differently, and hydration can affect it.")


def _label_kind(label: str) -> str:
    """How the AGE Reader's own risk label reads: 'good' (no or low risk), 'bad' (moderate, medium, high or increased risk), or '' (anything else)."""
    if re.search(r"\b(no|low)\s+risk\b", label, re.I):
        return "good"
    if re.search(r"\b(moderate|medium|high|very high|increased|elevated)\s+risk\b", label, re.I):
        return "bad"
    return ""


def _age_level(m, age) -> Comparison:
    """The AGE Reader's own comparison, judged as the report prints it. The reference is the average the device gives for the person's age."""
    a, level, avg, pct, way = m["assessment"], m.get("level"), m.get("average"), m.get("pct"), m.get("direction") or ""
    age_used = m.get("age_used") or (float(age) if age else None)
    label, kind, pos = m.get("label") or "", _label_kind(m.get("label") or ""), m.get("position")
    lower = {"below": "lower", "above": "higher"}.get(way, "")
    if kind == "bad":
        status, theme, headline = ABOVE, DISCUSS, "Worth discussing with your clinician"
    elif kind == "good" or way == "below":
        status, theme, headline = WITHIN, DOING_WELL, "A good result" if way == "below" else "Within the AGE Reader's usual group"
    else:
        status, theme, headline = ABOVE, INFO, "For your information"
    if status == WITHIN:
        words = "Lower than average for your age" if way == "below" else "Within the AGE Reader's usual group"
    elif way == "above":
        words = "Higher than average for your age"
    else:
        words = "As reported by the AGE Reader"
    who = f"people aged {_fmt(age_used)}" if age_used else "your age group"
    if level is not None and avg:
        sentence = (f"Your skin AGE level was {_fmt(level)}. The AGE Reader's average for {who} is {_fmt(avg)}. "
                    + (f"Yours is {_fmt(pct)}% {lower} than average." if pct is not None and lower else "Yours is about the same as the average."))
        value_text, range_text = _fmt(level), f"the AGE Reader's average for {who}: {_fmt(avg)}"
    elif pct is not None and lower:
        sentence = f"Your AGE Scanner report says your AGE level is {_fmt(pct)}% {lower} than the average for {who}."
        value_text, range_text = f"{_fmt(pct)}% {way}", "the AGE Reader's average for your age"
    else:
        sentence = f"Your skin AGE level was {_fmt(level)}." if level is not None else "Your AGE Scanner report compares your skin AGE level with an average."
        value_text, range_text = (_fmt(level) if level is not None else "-"), "the AGE Reader's average for your age"
    quoted = f"\u201c{label}\u201d" if label else ""
    if theme == DOING_WELL and way == "below":
        meaning = "That is lower than average for your age, which is a good sign." + (f" The AGE Reader's own label for this result is {quoted}." if quoted else "")
    elif theme == DOING_WELL:
        meaning = f"That is a little above average for your age, but the AGE Reader's own label for it is {quoted}."
    elif theme == DISCUSS:
        meaning = f"The AGE Reader's own label for this result is {quoted}. Your clinician will talk through what this means for you."
    else:
        meaning = "That is higher than average for your age. We will talk it through with you."
    detail = "The average comes from the AGE Reader's own reference group, which the report does not publish."
    if pos is not None:
        detail += f" The report also places you at {_fmt(pos)}% within your age group."
    return Comparison(key="age_level", label="Skin AGE level (AGE Reader)", assessment=a, status=status, source="age_scanner_printed", value=level if level is not None else pct,
                      value_text=value_text, range_text=range_text, group=who, headline=headline, sentence=sentence, meaning=meaning, detail=detail, theme=theme,
                      status_text=words, calculated=bool(m.get("calculated")))


def _age_bodyage(m, age) -> Comparison:
    """BodyAge against the person's age: the device's own estimate, judged only by whether it is younger or older than their age."""
    a, body, diff = m["assessment"], m["value"], m.get("diff")
    age_used = m.get("age_used") or (float(age) if age else None)
    if age_used is None:
        return _no_ref("age_bodyage", "BodyAge (AGE Reader)", a, body, "years", "An age is needed to compare the BodyAge with.")
    years = diff if diff is not None else abs(age_used - body)
    way = "younger" if body < age_used else "older" if body > age_used else "same"
    sentence = f"The AGE Reader estimates your BodyAge at {_fmt(body)}. Your age is {_fmt(age_used)}. " + (
        "That is the same as your age." if way == "same" else f"That is {_fmt(years)} years {way} than your age.")
    if way in ("younger", "same"):
        status, theme, headline, words = WITHIN, DOING_WELL, "A good result", "Younger than your age" if way == "younger" else "The same as your age"
        meaning = "That is a good sign. BodyAge is the AGE Reader's own estimate, so treat it as a guide."
    else:
        status, theme, headline, words = ABOVE, INFO, "For your information", "Older than your age"
        meaning = "BodyAge is the AGE Reader's own estimate, so treat it as a guide. We will talk it through with you."
    return Comparison(key="age_bodyage", label="BodyAge (AGE Reader)", assessment=a, status=status, source="age_scanner_printed", value=body, value_text=f"{_fmt(body)} years",
                      range_text=f"your age: {_fmt(age_used)}", group="the AGE Reader's estimate", headline=headline, sentence=sentence, meaning=meaning, theme=theme,
                      status_text=words, detail="BodyAge comes from the AGE Reader's own reference group, which the report does not publish.")


_ORDER = ["pulse_avg", "spo2_avg", "ecg_hr", "ecg_pr", "ecg_qrs", "ecg_qtcf", "ecg_qtcb", "fat_pct", "bmi", "asm_index", "age_level", "age_bodyage"]


def _read_together(results: list):
    """BMI and body fat can disagree (a muscular person, or a slim person with more fat). Say so, so neither is misread."""
    by = {c.key: c for c in results}
    bmi, fat = by.get("bmi"), by.get("fat_pct")
    if not (bmi and fat):
        return
    if bmi.status in (ABOVE, WELL_ABOVE) and fat.status == WITHIN:
        bmi.headline, bmi.theme = "Read alongside your body fat", INFO
        bmi.meaning = ("Your BMI is above the healthy range, but your body fat is within it. "
                       "That can happen when someone carries a lot of muscle, so your body fat is the better guide for you.")
    elif bmi.status == WITHIN and fat.status in (ABOVE, WELL_ABOVE):
        fat.meaning += " Your BMI looks healthy. But body fat can be high even when BMI is, so body fat is the more telling number for you."


def compare(tests: list, age, sex, height_cm=None) -> list:
    """All the comparisons that can be made for this participant's tests, as a list of Comparison objects."""
    def positive(x, cast):
        try:
            return cast(x) if x not in (None, "") and float(x) > 0 else None
        except (TypeError, ValueError):
            return None

    age, height_cm, sex = positive(age, int), positive(height_cm, float), normalise_sex(sex)
    measures = measures_from_tests(tests, height_cm)
    results = [_compare_one(k, measures[k], age, sex, height_cm) for k in _ORDER if k in measures]
    _read_together(results)
    for c in results:
        c.patient_label, c.measures = PATIENT_TEXT.get(c.key, (c.label, ""))
    return results


# ------------------------------------------------------------------------------------------------ what a participant sees
def for_patient(comparisons: list) -> list:
    """The comparisons a participant reads, as dicts. The QTc is shown once (Fridericia, which holds up better at fast and slow heart rates),
    and the clinician's table keeps both."""
    comps = [c if isinstance(c, dict) else c.to_dict() for c in comparisons]
    keys = {c["key"] for c in comps if c["status"] != NO_REFERENCE}
    return [c for c in comps if not (c["key"] == "ecg_qtcb" and "ecg_qtcf" in keys)]


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
    parts = [f"{c[WITHIN]} within the expected range"]
    if c[BELOW]:
        parts.append(f"{c[BELOW]} lower")
    if c[ABOVE] + c[WELL_ABOVE]:
        parts.append(f"{c[ABOVE] + c[WELL_ABOVE]} higher")
    return f"We compared {compared} of your results with reference data: " + ", ".join(parts) + "."


def glance_verdict(comparisons: list) -> str:
    """One sentence for the top of the 'at a glance' page. Counts what the participant sees (the QTc once)."""
    comps = [c for c in for_patient(comparisons) if c["status"] not in (NO_REFERENCE, REPORTED)]
    if not comps:
        return ""
    n = len(comps)
    within = sum(1 for c in comps if c["status"] == WITHIN)
    work = sum(1 for c in comps if c.get("theme") == WORK_ON)
    talk = sum(1 for c in comps if c.get("theme") == DISCUSS)
    info = sum(1 for c in comps if c.get("theme") == INFO)
    watch = sum(1 for c in comps if c.get("theme") == WATCH)
    if within == n and not watch:
        return (f"Good news: all {n} results we could compare are within the expected range." if n > 1
                else "Good news: the result we could compare is within the expected range.")
    parts = [f"{within} of your {n} results {'is' if within == 1 else 'are'} within the expected range."]
    if watch:
        parts.append(f"{watch} {'is' if watch == 1 else 'are'} worth keeping an eye on.")
    if work:
        parts.append(f"{work} {'is' if work == 1 else 'are'} worth working on.")
    if talk:
        parts.append(f"{talk} {'is' if talk == 1 else 'are'} worth talking through with your clinician.")
    if info:
        parts.append(f"{info} {'is' if info == 1 else 'are'} best read alongside your other results.")
    return " ".join(parts)


# The groups on the 'at a glance' page, most important first: (theme, heading, a few plain words that apply to every result in it)
_GROUPS = [
    (WORK_ON, "Worth working on", "These can change. Steady, realistic steps add up. Bringing them towards the expected range is worth aiming for, to support your long-term health. "
                                  "Your clinician will talk through what could help you."),
    (DISCUSS, "To talk through with your clinician", "This is not a diagnosis. Your clinician will look at these with your other results and tell you if anything needs following up."),
    (WATCH, "Worth keeping an eye on", "These are within the healthy range but toward the top of it, so they are worth keeping an eye on."),
    (INFO, "Best read alongside your other results", "We have said why next to each one, and we will go through them with you."),
    (DOING_WELL, "Going well", "These are within the expected range. That is good news, and worth keeping up."),
]
CLOSING = ("These numbers show where you are today compared with groups of healthy people. "
           "They are a starting point for a conversation about your long-term health. They are not a verdict, and many of them can change.")
ALL_GOOD = "From the results we could compare, this is a good picture. The best thing to do is keep doing what you are doing."


def glance_groups(comparisons: list) -> list:
    """The grouped list for the 'at a glance' page: a list of dicts {theme, heading, text, items}. Only groups that have results appear."""
    comps = [c for c in for_patient(comparisons) if c["status"] not in (NO_REFERENCE, REPORTED)]
    out = []
    for theme, heading, text in _GROUPS:
        items = [c for c in comps if c.get("theme") == theme]
        if items:
            out.append({"theme": theme, "heading": heading, "text": text, "items": items})
    return out


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
            kind = "reference range" if c.get("low") is not None else "reference"      # a range for most; an average for the AGE Reader
            lines.append(f"- {c['label']}: {c['value_text']}; for {c['group']} the {kind} is {c['range_text']}; this is "
                         f"{(c.get('status_text') or c['status'].replace('_', ' ')).lower()} (source: {data.SOURCES[c['source']]['short']})")
    if not lines:
        return ""
    return ("Reference comparisons computed by the app from published tables. Use them exactly as given and do not add any other ranges:\n" + "\n".join(lines) + "\n")
