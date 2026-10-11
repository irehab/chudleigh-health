"""Reader for the Tanita MC-780MA 'Personal Body Composition Report' (one page, made by software with a text layer).

It reads from the position of each label on the page, and then checks the numbers against each other, because this
report contains several sums that must add up. A misread digit makes at least one check fail.
It deliberately never reads the person's name or sex.
"""
from __future__ import annotations

import re

from .base import Check, Page, ReadResult, Value, close, make_value, status_from

DEVICE = "tanita_mc780"
LABEL = "Tanita MC-780MA body composition report"
APP_ASSESSMENT = "Tanita Body Composition (MC-780MA)"

KG, PCT, NUM, DEG = r"[\d.]+kg", r"[\d.]+%", r"[\d.]+", r"[\d.]+°"
_SEGMENTS = [("trunk", "Trunk"), ("right arm", "Rightarm"), ("left arm", "Leftarm"), ("right leg", "Rightleg"), ("left leg", "Leftleg")]


def matches(text_without_spaces: str) -> bool:
    t = text_without_spaces.upper()
    return "TANITA" in t and "BODYCOMPOSITION" in t


def read(pages: list, data: bytes | None = None) -> ReadResult:
    res = ReadResult(device=DEVICE, device_label=LABEL, has_text_layer=True)
    p = Page(pages[0])
    v: dict = {}

    def put(key, raw, unit=None):
        val = make_value(raw, unit) if raw else None
        if val:
            v[key] = val
        else:
            res.notes.append(f"Could not read: {key}")

    # analysis results (left column)
    A = (30, 150, 85, 260)
    for key, lab, pat, unit in [
        ("Weight (kg)", "Weight", KG, None), ("Fat (%)", "Fat", PCT, None), ("BMI", "BMI", NUM, None),
        ("Total body water (%)", "TBW", PCT, None), ("Phase angle (°)", "Phaseangle", NUM, "°"),
        ("Metabolic age (years)", "Metabolic", NUM, "years"), ("Visceral fat level", "Visceralfat", NUM, None),
        ("Muscle mass (kg)", "Musclemass", NUM, "kg"),
    ]:
        put(key, p.right_of(p.label(lab, A), pat), unit)

    # body composition block (value printed below its label)
    B = (30, 260, 285, 410)
    for key, lab in [("Fat mass (kg)", "Fat"), ("Bone mass (kg)", "Bonemass"), ("Protein (kg)", "Protein"), ("Weight, body composition chart (kg)", "Weight"),
                     ("Fat-free mass (kg)", "FatFree"), ("Muscle mass, body composition chart (kg)", "Muscle"), ("ECW (kg)", "ECW"),
                     ("Water (kg)", "Water"), ("ICW (kg)", "ICW")]:
        put(key, p.below(p.label(lab, B), KG))

    # phase angle by body part
    P = (450, 520, 295, 410)
    for key, lab in [("Phase angle, whole body (°)", "Whole"), ("Phase angle, right arm (°)", "RA"), ("Phase angle, left arm (°)", "LA"),
                     ("Phase angle, right leg (°)", "RL"), ("Phase angle, left leg (°)", "LL")]:
        put(key, p.right_of(p.label(lab, P), DEG, dy=14, dx=60))

    # leg muscle score: the number inside the black circle on the chart
    circle = [w for w in p.in_region((380, 440, 300, 405)) if re.fullmatch(r"\d{2,3}", w["text"])]
    put("Leg muscle score", circle[0]["text"] if circle else None)

    # segmental analysis: muscle on the left half, fat (kg and %) on the right half
    for side, x0, x1 in [("Muscle", 30, 300), ("Fat", 300, 595)]:
        for key, lab in _SEGMENTS:
            anchor = p.label(lab, (x0, x1, 440, 570))
            if side == "Muscle":
                put(f"Muscle, {key} (kg)", p.below(anchor, KG, dy=16, dx=30))
            else:
                m = re.fullmatch(r"([\d.]+kg).*?([\d.]+%)", p.text_below(anchor) or "")  # whatever separator the PDF used between kg and %
                put(f"Fat, {key} (kg)", m.group(1) if m else None)
                put(f"Fat, {key} (%)", m.group(2) if m else None)

    # header: age and height only. The name and sex are never read.
    header = " ".join(w["text"] for w in p.in_region((0, 600, 0, 70)))
    m = re.search(r"(\d+)years·(\d+)cm", header.replace(" ", ""))
    put("Age (years)", f"{m.group(1)}years" if m else None)
    put("Height (cm)", f"{m.group(2)}cm" if m else None)
    m = re.search(r"(\d{1,2}/\d{1,2}/\d{4})\s*(\d{1,2}:\d{2})", header)
    if m:
        v["Measured"] = Value(text=f"{m.group(1)} {m.group(2)}", number=None, unit="")
    m = re.search(r"TANITA\s*(MC-\w+)", header, re.I)
    if m:
        v["Device model"] = Value(text=f"TANITA {m.group(1)}", number=None, unit="")
    m = re.search(r"([\d.]+)\s*kg\s*of\s*clothing", header.replace("kgof", "kg of"), re.I) or re.search(r"([\d.]+)kgofclothing", header.replace(" ", ""), re.I)
    if m:
        v["Clothing allowance (kg)"] = make_value(m.group(1) + "kg")

    res.values = {k: x for k, x in v.items() if x}

    # reference text the report itself prints (phase angle bands)
    legend = " ".join(w["text"] for w in sorted(p.in_region((505, 600, 290, 415)), key=lambda w: (w["top"], w["x0"])))
    res.printed_ranges = [f"Phase angle: {a}° {b.strip()}" for a, b in re.findall(r"(\d+(?:-\d+)?)°\s*(\S+(?:\s+(?!\d)\S+)?)", legend)]

    # a number people ask for that this report does not print
    ecw, water = res.number("ECW (kg)"), res.number("Water (kg)")
    if ecw is not None and water:
        res.values["ECW/TBW ratio (calculated)"] = Value(text=f"{ecw / water:.3f}", number=round(ecw / water, 3), unit="", source="calculated")
    res.not_printed.append("ECW/TBW ratio (the report prints ECW and ICW, not the ratio; a calculated value is provided and marked as calculated)")
    res.notes.append(
        "The coloured bars (weight, fat, BMI, muscle mass, body water, visceral fat, metabolic age, phase angle) show which band "
        "the person is in only as a graphic. This reader cannot tell which band, so it makes no statement about it."
    )
    res.notes.append("Sex is drawn as a symbol on this report, not printed as text, so it is not read. Enter it separately.")

    res.checks = run_checks(res)
    res.status = status_from(res)
    return res


def run_checks(res: ReadResult) -> list:
    n = res.number
    checks: list = []

    def check(name, inputs, fn, detail):
        missing = [k for k in inputs if n(k) is None]
        if missing:
            checks.append(Check(name, False, "could not check: missing " + ", ".join(missing)))
            return
        ok, text = fn()
        checks.append(Check(name, ok, text))

    seg_m = [f"Muscle, {k} (kg)" for k, _ in _SEGMENTS]
    seg_f = [f"Fat, {k} (kg)" for k, _ in _SEGMENTS]
    check("weight = fat mass + fat-free mass", ["Weight (kg)", "Fat mass (kg)", "Fat-free mass (kg)"],
          lambda: (close(n("Weight (kg)"), n("Fat mass (kg)") + n("Fat-free mass (kg)"), 0.16),
                   f"{n('Weight (kg)')} vs {n('Fat mass (kg)')} + {n('Fat-free mass (kg)')} = {n('Fat mass (kg)') + n('Fat-free mass (kg)'):.1f}"), "")
    check("fat-free mass = muscle + bone", ["Fat-free mass (kg)", "Muscle mass (kg)", "Bone mass (kg)"],
          lambda: (close(n("Fat-free mass (kg)"), n("Muscle mass (kg)") + n("Bone mass (kg)"), 0.16),
                   f"{n('Fat-free mass (kg)')} vs {n('Muscle mass (kg)')} + {n('Bone mass (kg)')} = {n('Muscle mass (kg)') + n('Bone mass (kg)'):.1f}"), "")
    check("water = ECW + ICW", ["Water (kg)", "ECW (kg)", "ICW (kg)"],
          lambda: (close(n("Water (kg)"), n("ECW (kg)") + n("ICW (kg)"), 0.16),
                   f"{n('Water (kg)')} vs {n('ECW (kg)')} + {n('ICW (kg)')} = {n('ECW (kg)') + n('ICW (kg)'):.1f}"), "")
    check("muscle mass = sum of the five muscle segments", ["Muscle mass (kg)", *seg_m],
          lambda: (close(n("Muscle mass (kg)"), sum(n(k) for k in seg_m), 0.26), f"{n('Muscle mass (kg)')} vs {sum(n(k) for k in seg_m):.1f}"), "")
    check("fat mass = sum of the five fat segments", ["Fat mass (kg)", *seg_f],
          lambda: (close(n("Fat mass (kg)"), sum(n(k) for k in seg_f), 0.26), f"{n('Fat mass (kg)')} vs {sum(n(k) for k in seg_f):.1f}"), "")
    check("fat % = fat mass / weight", ["Fat (%)", "Fat mass (kg)", "Weight (kg)"],
          lambda: (close(n("Fat (%)"), n("Fat mass (kg)") / n("Weight (kg)") * 100, 0.11), f"{n('Fat (%)')} vs {n('Fat mass (kg)') / n('Weight (kg)') * 100:.2f}"), "")
    check("body water % = water / weight", ["Total body water (%)", "Water (kg)", "Weight (kg)"],
          lambda: (close(n("Total body water (%)"), n("Water (kg)") / n("Weight (kg)") * 100, 0.11),
                   f"{n('Total body water (%)')} vs {n('Water (kg)') / n('Weight (kg)') * 100:.2f}"), "")
    check("BMI = weight / height squared", ["BMI", "Weight (kg)", "Height (cm)"],
          lambda: (close(n("BMI"), n("Weight (kg)") / (n("Height (cm)") / 100) ** 2, 0.06),
                   f"{n('BMI')} vs {n('Weight (kg)') / (n('Height (cm)') / 100) ** 2:.2f}"), "")
    check("weight printed twice agrees", ["Weight (kg)", "Weight, body composition chart (kg)"],
          lambda: (n("Weight (kg)") == n("Weight, body composition chart (kg)"), f"{n('Weight (kg)')} / {n('Weight, body composition chart (kg)')}"), "")
    check("muscle mass printed twice agrees", ["Muscle mass (kg)", "Muscle mass, body composition chart (kg)"],
          lambda: (n("Muscle mass (kg)") == n("Muscle mass, body composition chart (kg)"), f"{n('Muscle mass (kg)')} / {n('Muscle mass, body composition chart (kg)')}"), "")
    return checks


def app_fields(res: ReadResult) -> dict:
    d = lambda k: res.values[k].display if k in res.values else ""
    water = f"{d('Water (kg)')} ({d('Total body water (%)')})" if d("Water (kg)") and d("Total body water (%)") else ""
    ratio = f"{res.values['ECW/TBW ratio (calculated)'].text} (calculated by the app from ECW and body water; not printed on the report)" if "ECW/TBW ratio (calculated)" in res.values else ""
    return {"Weight": d("Weight (kg)"), "Fat %": d("Fat (%)"), "FFM": d("Fat-free mass (kg)"), "Muscle Mass": d("Muscle mass (kg)"), "TBW": water,
            "ECW/TBW": ratio, "Visceral Fat": d("Visceral fat level"), "Metabolic Age": d("Metabolic age (years)"), "Phase Angle": d("Phase angle (°)")}
