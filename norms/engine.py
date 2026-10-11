"""Compares a participant's measured values with published reference data for their age and sex, and says what that means.

Everything here is a table look-up, a sum, or wording chosen from fixed templates. No model is involved. A comparison is only made
when the reference data covers the participant's age and (where it matters) sex. Otherwise the measure is listed as "not compared",
with the reason.

The wording follows three rules. It states the fact first, then says plainly whether it is good news or something to work on, and
then explains why. It only links a result to a health outcome where a source says so (WHO, the NCHS pulse report, the systematic
review in data.SOURCES), and it never promises an outcome.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from . import data

NORMS_VERSION = "2026-10-11.2"

# statuses
WITHIN, BELOW, ABOVE, WELL_ABOVE, REPORTED, NO_REFERENCE = "within", "below", "above", "well_above", "reported", "no_reference"
# themes: how a result is described in the overall summary
DOING_WELL, WATCH, WORK_ON, DISCUSS, INFO = "doing_well", "watch", "work_on", "discuss", "info"

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
    headline: str = ""   # a short verdict: "A good result", "Worth working on"
    sentence: str = ""   # the facts: your value, the range, and where you sit
    meaning: str = ""    # what it means, in plain words
    detail: str = ""     # a caution, where one is needed
    position: str = ""   # for a result within its range: lower, middle or upper
    theme: str = ""      # doing_well, watch, work_on, discuss or info
    reason: str = ""     # why a measure could not be compared
    calculated: bool = False
    also_sources: list = field(default_factory=list)

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


def _missing(age, sex, need_sex=True) -> str:
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


def _position(v, lo, hi) -> str:
    """Where a value inside a range sits: the lower, middle or upper third."""
    if hi <= lo:
        return "middle"
    f = (v - lo) / (hi - lo)
    return "lower" if f < 1 / 3 else "middle" if f < 2 / 3 else "upper"


_POS_TEXT = {"lower": "toward the lower end", "middle": "around the middle", "upper": "toward the upper end"}


def _where(status, pos) -> str:
    return {WITHIN: f"within that range, {_POS_TEXT.get(pos, 'inside it')}", BELOW: "lower than that range", ABOVE: "higher than that range"}[status]


# ------------------------------------------------------------------------------------------------ the wording
_CAUTION = "Your clinician will look at this closely with the rest of your ECG. A value outside the usual range is not a diagnosis, and there are often harmless explanations."
_PULSE_LINK = "Studies have linked a higher resting pulse with a higher chance of heart disease"

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
        pos = _position(v, lo, hi) if status == WITHIN else ""
        sentence = (f"Your resting pulse averaged {_fmt(v)} beats per minute. In a large US health survey, 9 in 10 healthy {who} had a resting pulse "
                    f"between {lo} and {hi}, so yours is {_where(status, pos)}.")
        if status == WITHIN and v <= med:
            headline, theme = "A good result", DOING_WELL
            meaning = f"That is in the lower half of the typical range, which is a good place to be. {_PULSE_LINK}, so a lower one is the better direction."
        elif status == WITHIN:
            headline, theme = "Within the typical range", DOING_WELL
            meaning = (f"That is in the upper half of the typical range, which is fine. {_PULSE_LINK}, so if you would like to bring it down, "
                       "regular exercise, good sleep and managing stress can all help.")
        elif status == ABOVE:
            headline, theme = "Worth working on", WORK_ON
            meaning = (f"A higher resting pulse can follow caffeine, poor sleep, stress, illness or being less fit. {_PULSE_LINK}, so it is worth working on, "
                       "and worth mentioning to your clinician if it stays high.")
        else:
            headline, theme = "Worth a mention to your clinician", DISCUSS
            meaning = "A low resting pulse is common in people who exercise regularly. If you also feel dizzy, faint or breathless, speak to your clinician or GP."
        return Comparison(key=key, label=label, assessment=a, status=status, source="nhanes_pulse", value=v, value_text=f"{_fmt(v)} bpm",
                          range_text=f"{lo} to {hi} bpm", group=who, headline=headline, sentence=sentence, meaning=meaning, position=pos, theme=theme)

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
        name = label[0].lower() + label[1:] if not label.startswith("ECG") else label
        sentence = (f"Your {name} was {_fmt(v)} {unit_long}. In a study of healthy adults, about 96 in 100 {who} were between {lo} and {hi}, "
                    f"so yours is {_where(status, pos)}.")
        if status == WITHIN:
            headline, theme = "Within the range seen in healthy adults", DOING_WELL
            meaning = "Good news. Your clinician reads this together with the rest of your ECG."
        else:
            headline, theme = "Worth discussing with your clinician", DISCUSS
            meaning = _CAUTION
        return Comparison(key=key, label=label, assessment=a, status=status, source="rijnbeek_ecg", value=v, value_text=f"{_fmt(v)} {unit}",
                          range_text=f"{lo} to {hi} {unit}", group=who, headline=headline, sentence=sentence, meaning=meaning, position=pos, theme=theme)

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
        sentence = f"Your body fat was {_fmt(v)}%. For {who}, the healthy range in the study is {low}% to under {over}%, so yours is {where}."
        graded = "The chance of weight-related conditions such as type 2 diabetes and heart disease generally rises step by step as body fat goes up"
        if status == WITHIN and pos in ("lower", "middle"):
            headline, theme = "A good result", DOING_WELL
            meaning = f"Well done. {graded}, so being {'toward the lower end of' if pos == 'lower' else 'around the middle of'} the healthy range is a good place to be."
        elif status == WITHIN:
            headline, theme = "Within the healthy range, toward the top", WATCH
            meaning = f"You are still within the healthy range, which is good, but toward the top of it. {graded}, so it is worth keeping an eye on."
        elif status == ABOVE:
            headline, theme = "Worth working on", WORK_ON
            meaning = ("That range matches a BMI of 25 to 30, where the World Health Organization says the chance of conditions such as type 2 diabetes and heart disease is increased. "
                       "The good news is that body fat can change. Bringing it down towards the healthy range is worth working on to support your long-term health, and we will talk through how.")
        elif status == WELL_ABOVE:
            headline, theme = "Worth working on", WORK_ON
            meaning = ("That range matches a BMI of 30 or more, where the World Health Organization says the chance of conditions such as type 2 diabetes and heart disease is moderate or higher. "
                       "This is worth taking seriously and working on steadily. Realistic, steady steps matter more than quick fixes, and we will talk through how.")
        else:
            headline, theme = "Worth a mention to your clinician", DISCUSS
            meaning = "A low body fat is common in people who train hard. If it is not intentional, or you feel tired or run down, or have lost weight without trying, please mention it to your clinician."
        return Comparison(
            key=key, label=label, assessment=a, status=status, source="gallagher_fat", value=v, value_text=f"{_fmt(v)}%",
            range_text=f"{low}% to under {over}%", group=who, headline=headline, sentence=sentence, meaning=meaning, position=pos, theme=theme,
            detail=("These ranges are provisional and were worked out from BMI limits. Body fat from a bioimpedance scale can differ from the laboratory methods used to make them."),
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
        sentence = (f"Your BMI was {_fmt(v)}{' (worked out from your weight and height)' if calc else ''}. The World Health Organization's healthy range for adults "
                    f"is 18.5 to under 25, so yours is {where}.")
        if status == WITHIN:
            headline, theme = "A good result", DOING_WELL
            meaning = "Well done. At this level the WHO rates the chance of weight-related conditions as average. BMI is only a rough guide, so we read it alongside your body fat."
        elif status in (ABOVE, WELL_ABOVE):
            headline, theme = "Worth working on", WORK_ON
            meaning = ("At this level the World Health Organization says the chance of conditions such as type 2 diabetes and heart disease is "
                       f"{'increased' if status == ABOVE else 'moderate or higher'}. BMI cannot tell muscle from fat, though, so please read it alongside your body fat.")
        else:
            headline, theme = "Worth a mention to your clinician", DISCUSS
            meaning = "A low BMI can mean there is little reserve if you become unwell. If it is not intentional, or you have lost weight without trying, please mention it to your clinician."
        return Comparison(key=key, label=label, assessment=a, status=status, source="who_bmi", value=v, value_text=_fmt(v), calculated=calc,
                          range_text="18.5 to under 25", group="adults", headline=headline, sentence=sentence, meaning=meaning, theme=theme,
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
        if older:
            sentence = (f"Your blood oxygen level averaged {_fmt(v)}%. In a study of healthy adults over 65, 95 in 100 had a reading of {lower}% or higher, "
                        f"so yours is {'within that range' if status == WITHIN else 'lower than that range'}.")
        else:
            sentence = (f"Your blood oxygen level averaged {_fmt(v)}%. In healthy adults it is usually {lower}% or higher, "
                        f"so yours is {'within that range' if status == WITHIN else 'lower than that range'}.")
        if status == WITHIN:
            headline, theme = "A good result", DOING_WELL
            meaning = "That is a good sign that your blood is carrying oxygen well while you are at rest."
        else:
            headline, theme = "Worth discussing with your clinician", DISCUSS
            meaning = "Your clinician will want to look at this properly. A short reading can be affected by cold hands, movement or nail polish, so it may be worth repeating."
        return Comparison(
            key=key, label=label, assessment=a, status=status, source="spo2_older" if older else "spo2_adults", value=v, value_text=f"{_fmt(v)}%",
            range_text=f"{lower}% or higher", group="healthy adults aged 65 and over" if older else "healthy adults under 65", headline=headline,
            sentence=sentence, meaning=meaning, theme=theme,
            detail=("If readings stay low, or you feel breathless, speak to your GP." if status == BELOW else ""),
        )

    if key == "age_pos":
        return Comparison(
            key=key, label="Skin AGE level compared with others of your age", assessment=a, status=REPORTED, source="age_scanner_printed", value=v,
            value_text=f"{_fmt(v)}%", range_text="the device's own comparison", headline="For your information", theme=INFO,
            sentence=f"Your AGE Scanner report places you at {_fmt(v)}% within your age group, using the device maker's own reference group.",
            meaning="This comes from the device maker's own comparison group, so treat it as a guide. We will talk it through with you.",
        )
    if key == "age_vs_avg":
        way = m.get("direction") or ""
        age_used = m.get("age_used")
        if way not in ("below", "above"):
            return _no_ref(key, "Skin AGE level compared with the average", a, v, "%", "The report's wording about above or below the average could not be read.")
        return Comparison(
            key=key, label="Skin AGE level compared with the average", assessment=a, status=REPORTED, source="age_scanner_printed", value=v,
            value_text=f"{_fmt(v)}% {way}", range_text="the device's own comparison", headline="For your information", theme=INFO,
            sentence=(f"Your AGE Scanner report says your AGE level is {_fmt(v)}% {way} the average for "
                      f"{str(int(age_used)) + '-year-olds' if age_used else 'your age group'}, using the device maker's own reference group."),
            meaning="This comes from the device maker's own comparison group, so treat it as a guide. We will talk it through with you.",
        )
    return _no_ref(key, key, a, v, "", "No reference data is available for this measure.")


_ORDER = ["pulse_avg", "spo2_avg", "ecg_hr", "ecg_pr", "ecg_qrs", "ecg_qtcf", "ecg_qtcb", "fat_pct", "bmi", "age_pos", "age_vs_avg"]


def _read_together(results: list):
    """BMI and body fat can disagree (a muscular person, or a slim person with more fat). Say so, so neither is misread."""
    by = {c.key: c for c in results}
    bmi, fat = by.get("bmi"), by.get("fat_pct")
    if not (bmi and fat):
        return
    if bmi.status in (ABOVE, WELL_ABOVE) and fat.status == WITHIN:
        bmi.headline, bmi.theme = "Read alongside your body fat", INFO
        bmi.meaning = ("Your BMI is above the healthy range, but your body fat is within it. That can happen when someone carries a lot of muscle, "
                       "so your body fat is the better guide for you.")
    elif bmi.status == WITHIN and fat.status in (ABOVE, WELL_ABOVE):
        fat.meaning += " Your BMI looks healthy, but body fat can be high even when BMI is, so body fat is the more telling number for you."


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
    return results


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


_SHORT = {"pulse_avg": "resting pulse", "spo2_avg": "blood oxygen level", "ecg_hr": "heart rate at your ECG", "ecg_pr": "ECG PR interval", "ecg_qrs": "ECG QRS duration",
          "ecg_qtcf": "ECG QTc interval", "ecg_qtcb": "ECG QTc interval", "fat_pct": "body fat", "bmi": "BMI"}


def _names(items) -> list:
    seen, out = [], []
    for c in items:
        n = _SHORT.get(c["key"], c["label"].lower())
        if n not in seen:
            seen.append(n)
            out.append(n)
    return out


def _join(names) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def overview(comparisons: list) -> list:
    """The 'putting it all together' part: a list of (heading, text). Built only from the comparisons' statuses and themes."""
    comps = [c if isinstance(c, dict) else c.to_dict() for c in comparisons]
    compared = [c for c in comps if c["status"] not in (NO_REFERENCE, REPORTED)]
    if not compared:
        return []
    well = [c for c in compared if c.get("theme") == DOING_WELL]
    watch = [c for c in compared if c.get("theme") == WATCH]
    work = [c for c in compared if c.get("theme") == WORK_ON]
    talk = [c for c in compared if c.get("theme") == DISCUSS]
    info = [c for c in compared if c.get("theme") == INFO]

    def is_are(names):
        return "is" if len(names) == 1 else "are"

    blocks = [("The big picture", summary_sentence(comps))]
    if well:
        n = _names(well)
        blocks.append(("Where you are doing well", f"Your {_join(n)} {is_are(n)} within the usual range for your age and sex. That is good news, and worth keeping up."))
    if watch:
        n = _names(watch)
        blocks.append(("Worth keeping an eye on", f"Your {_join(n)} {is_are(n)} within the healthy range but toward the top of it, so it is worth keeping an eye on."))
    if work:
        n = _names(work)
        blocks.append(("Worth working on", f"Your {_join(n)} {is_are(n)} above the usual range. Each of these can change. Steady, realistic steps add up, and bringing "
                                           f"{'it' if len(n) == 1 else 'them'} towards the usual range is worth aiming for to support your long-term health. Your clinician will talk through what could help you."))
    if talk:
        n = _names(talk)
        blocks.append(("To talk through with your clinician", f"Your {_join(n)} {'sits' if len(n) == 1 else 'sit'} outside the usual range. This is not a diagnosis. Your clinician will look at "
                                                              f"{'it' if len(n) == 1 else 'them'} with your other results and tell you if anything needs following up."))
    if info:
        blocks.append(("Read together", "Some results are best read alongside others. We have said so next to each one, and we will go through them with you."))
    if not work and not talk:
        blocks.append(("What this adds up to", "From the results we could compare, this is a good picture. The best thing to do is keep doing what you are doing."))
    blocks.append(("Where this leaves you", "These numbers show where you are today compared with groups of healthy people. They are a starting point for a conversation about your long-term health, "
                                            "not a verdict, and many of them can change."))
    return blocks


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
