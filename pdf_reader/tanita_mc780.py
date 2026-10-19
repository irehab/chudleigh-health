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
_LIMBS = _SEGMENTS[1:]
VISCERAL_BANDS = ("Healthy", "High", "Very high")   # the three parts of the visceral fat bar, as printed above it


def visceral_band(level: float) -> str:
    """The band of Tanita's professional visceral fat scale, as drawn on this report: 1 to 9 healthy, 10 to 14 high, 15 and above very high."""
    return "Healthy" if level < 10 else ("High" if level < 15 else "Very high")


# ---- the coloured bars. Each bar has three grey parts (for a limb: below normal, normal, above normal), and a coloured fill
# drawn over them up to the person's result. Tanita colours the fill green when the result is in its normal band and orange when it is not.
def _fill_colour(curve):
    f = curve.get("non_stroking_color")
    if not isinstance(f, (list, tuple)) or len(f) != 3:
        return None
    r, g, b = (float(x) for x in f)
    if abs(r - g) < 0.06 and abs(g - b) < 0.06:
        return "grey"
    if r > g and r > b:
        return "orange"
    if g > r and g > b:
        return "green"
    return None


def _bars(data: bytes) -> list:
    """Every bar shape on the page (long and thin), with its colour."""
    import io
    import pdfplumber
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        curves = list(pdf.pages[0].curves)
    return [{"x0": c["x0"], "x1": c["x1"], "top": c["top"], "colour": _fill_colour(c)}
            for c in curves if (c["x1"] - c["x0"]) > 15 and (c["bottom"] - c["top"]) < 4]


def _bar_reading(bars: list, x0: float, x1: float, top: float, bottom: float):
    """(colour, part) for the one three-part bar in this box: part 0, 1 or 2 is the part the coloured fill ends in. None if it is not clear."""
    inside = [b for b in bars if x0 <= b["x0"] <= x1 and top <= b["top"] <= bottom]
    parts = sorted({(round(b["x0"], 1), round(b["x1"], 1)) for b in inside if b["colour"] == "grey"})
    fills = [b for b in inside if b["colour"] in ("green", "orange")]
    colours = {b["colour"] for b in fills}
    if len(parts) != 3 or len(colours) != 1:
        return None
    end = max(b["x1"] for b in fills)
    part = next((i for i, (_s0, s1) in enumerate(parts) if end <= s1 + 0.5), 2)
    return colours.pop(), part


def limb_verdict(reading) -> str | None:
    """'normal', 'low' or 'high' from a limb bar's colour and where its fill ends."""
    if not reading:
        return None
    colour, part = reading
    if colour == "green":
        return "normal"
    return {0: "low", 2: "high"}.get(part, "outside normal")


def limb_flags_text(verdicts: dict) -> str:
    """'left leg low' (or 'none'): the limbs the Tanita marks outside its normal band, in the words the dashboard reads."""
    flagged = [f"{limb} {v}" for limb, v in verdicts.items() if v and v != "normal"]
    return "; ".join(flagged) or "none"


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
    # the date and time printed in the header are not read: the only date used is the assessment date the clinician enters
    m = re.search(r"TANITA\s*(MC-\w+)", header, re.I)
    if m:
        v["Device model"] = Value(text=f"TANITA {m.group(1)}", number=None, unit="")
    m = re.search(r"([\d.]+)\s*kg\s*of\s*clothing", header.replace("kgof", "kg of"), re.I) or re.search(r"([\d.]+)kgofclothing", header.replace(" ", ""), re.I)
    if m:
        v["Clothing allowance (kg)"] = make_value(m.group(1) + "kg")

    # the coloured bars: which visceral fat band the result is drawn in, and the Tanita's verdict on each limb's muscle
    try:
        bars = _bars(data) if data else []
    except Exception:
        bars = []
    vlab = p.label("Visceralfat", A)
    drawn = _bar_reading(bars, 130, 345, vlab["top"] - 2, vlab["top"] + 14) if vlab else None
    if drawn:
        v["Visceral fat band (as drawn on the report)"] = Value(text=VISCERAL_BANDS[drawn[1]], number=None, unit="", source="graphic")
    else:
        res.notes.append("Could not read: the visceral fat bar (which band it is drawn in)")
    for key, lab in _LIMBS:
        anchor = p.label(lab, (30, 300, 440, 570))
        x0, x1 = (0, 150) if key.startswith("right") else (150, 300)       # muscle half of the page: right limbs on the left, left limbs on the right
        verdict = limb_verdict(_bar_reading(bars, x0, x1, anchor["top"] + 15, anchor["top"] + 40)) if anchor else None
        if verdict:
            v[f"Muscle, {key} (Tanita bar)"] = Value(text=verdict, number=None, unit="", source="graphic")
        else:
            res.notes.append(f"Could not read: the muscle bar for the {key}")

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
        "Of the coloured bars, this reader reads the visceral fat bar (which band it is drawn in) and the four limb muscle bars (green = in "
        "Tanita's normal band, orange = outside it). The other bars (weight, fat, BMI, muscle mass, body water, metabolic age) are not read."
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
    drawn = res.values.get("Visceral fat band (as drawn on the report)")
    if drawn and n("Visceral fat level") is not None:
        expected = visceral_band(n("Visceral fat level"))
        # a note, not an error: if this ever disagrees, Tanita's bands differ from the ones the dashboard uses (norms/measures.csv)
        checks.append(Check("visceral fat band drawn on the report matches the app's bands", drawn.text == expected,
                            f"level {n('Visceral fat level'):g}: drawn in '{drawn.text}', the app's bands say '{expected}'", severity="note"))
    return checks


def app_fields(res: ReadResult) -> dict:
    d = lambda k: res.values[k].display if k in res.values else ""
    water = f"{d('Water (kg)')} ({d('Total body water (%)')})" if d("Water (kg)") and d("Total body water (%)") else ""
    ratio = f"{res.values['ECW/TBW ratio (calculated)'].text} (calculated by the app from ECW and body water; not printed on the report)" if "ECW/TBW ratio (calculated)" in res.values else ""
    verdicts = {key: res.values[f"Muscle, {key} (Tanita bar)"].text for key, _lab in _LIMBS if f"Muscle, {key} (Tanita bar)" in res.values}
    flags = limb_flags_text(verdicts) if len(verdicts) == len(_LIMBS) else ""      # only when all four bars were read
    return {"Weight": d("Weight (kg)"), "Fat %": d("Fat (%)"), "FFM": d("Fat-free mass (kg)"), "Muscle Mass": d("Muscle mass (kg)"), "TBW": water,
            "ECW/TBW": ratio, "Visceral Fat": d("Visceral fat level"), "Metabolic Age": d("Metabolic age (years)"), "Phase Angle": d("Phase angle (°)"),
            "Right Arm Muscle": d("Muscle, right arm (kg)"), "Left Arm Muscle": d("Muscle, left arm (kg)"),
            "Right Leg Muscle": d("Muscle, right leg (kg)"), "Left Leg Muscle": d("Muscle, left leg (kg)"), "Limb Flags": flags}
