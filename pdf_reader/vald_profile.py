"""Reader for the VALD Hub one-page 'Profile' summary (portrait A4): a tile per test with its headline result.

Each tile has the test's name, the measure shown (e.g. 'Max Peak Power / BM'), the result in large type, and sometimes a
percentile, a left and right result, or a left/right asymmetry. The small numbers on each tile's chart axis are ignored.
Only results that mean the same as one of the app's boxes fill it: the squat's 'Max Peak Force' is the best rep, so it fills
'Peak Force, best rep'; the sit-to-stand's 'Max Time to Stand' is not the average of reps the box asks for, so it is left empty.

It deliberately never reads the person's name or date of birth.
"""
from __future__ import annotations

import io
import re

from .base import Check, ReadResult, Value, status_from

DEVICE = "vald_profile"
LABEL = "VALD Hub profile summary"
APP_ASSESSMENT = ""     # covers several tests: see ReadResult.app_assessments
TILES = {   # tile title as printed -> (test code, the app's assessment)
    "Countermovement Jump": ("CMJ", "VALD ForceDecks - Countermovement Jump (CMJ)"),
    "Squat Assessment": ("SQT", "VALD ForceDecks - Multi-Rep Squat"),
    "Sit to Stand to Sit": ("STSTS", "VALD ForceDecks - Sit-to-Stand"),
    "Single Leg Stand": ("SLSB", "VALD ForceDecks - Single Leg Stance / Balance"),
    "Quiet Stand": ("QSB", "VALD ForceDecks - Quiet Stand (Balance)"),
    "Drop Jump": ("DJ", ""),
}
# (test code, measure as printed on the tile, side or None) -> the app's box. Only measures that mean the same as the box.
BOXES = {
    ("CMJ", "Max Peak Power / BM", None): "Peak Power/Mass",
    ("SQT", "Max Peak Force - Bilateral Total", None): "Peak Force",
    ("SLSB", "Avg Total Excursion", "Left"): "Left Total Excursion",
    ("SLSB", "Avg Total Excursion", "Right"): "Right Total Excursion",
    ("QSB", "Avg Total Excursion - Bilateral Avg", None): "Total Path Length",
}
_NUM = re.compile(r"-?\d+(?:\.\d+)?")
_PCT = re.compile(r"(\d{1,3})(?:st|nd|rd|th)")
_DATE = re.compile(r"Report Date:\s*(\d{1,2} \w{3} \d{4})")


def matches(text_without_spaces: str) -> bool:
    t = text_without_spaces.replace(" ", "")
    return "Profile:" in t and "ReportDate:" in t and "poweredby" in t and any(k.replace(" ", "") in t for k in TILES) \
        and "CalculationType" not in t


def _lines(words, tol=2.5):
    """Group words into lines (same top), each a list sorted left to right."""
    lines = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if lines and abs(lines[-1][0]["top"] - w["top"]) <= tol:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [sorted(line, key=lambda w: w["x0"]) for line in lines]


def read(pages: list, data: bytes | None = None) -> ReadResult:
    import pdfplumber
    res = ReadResult(device=DEVICE, device_label=LABEL, has_text_layer=True)
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        page = pdf.pages[0]
        width = page.width
        words = page.extract_words(extra_attrs=["size", "fontname"])
        text = page.extract_text() or ""
    m = _DATE.search(text)
    res.report_date = m.group(1) if m else ""
    mid = width / 2

    # tile titles: 12-point medium type, on its own line within one half of the page
    titles = []
    for line in _lines([w for w in words if 11 <= w["size"] <= 13 and "Medium" in w["fontname"]]):
        for half in (0, 1):
            part = [w for w in line if (w["x0"] >= mid) == bool(half)]
            name = " ".join(w["text"] for w in part)
            if name in TILES:
                titles.append({"name": name, "x0": part[0]["x0"], "top": part[0]["top"], "half": half})
    tiles = []
    for t in titles:
        below = [o["top"] for o in titles if o["half"] == t["half"] and o["top"] > t["top"]]
        bottom = min(below) if below else 9e9
        x_lo, x_hi = (0, mid) if t["half"] == 0 else (mid, width)
        inside = [w for w in words if x_lo <= w["x0"] < x_hi and t["top"] + 5 < w["top"] < bottom - 5]
        metric_line = next((ln for ln in _lines([w for w in inside if 8.5 <= w["size"] <= 9.5 and "Regular" in w["fontname"]])
                            if ln[0]["top"] < t["top"] + 30), [])
        metric = " ".join(w["text"] for w in metric_line)
        code, assessment = TILES[t["name"]]
        tile = {"title": t["name"], "code": code, "assessment": assessment, "metric": metric, "results": [], "percentile": None, "asymmetry": None}
        # results: the large light type (16 pt and over); the unit is the light word just after it; a 'Left' / 'Right' label above names the side
        big = [w for w in inside if w["size"] >= 15 and "Light" in w["fontname"] and _NUM.fullmatch(w["text"])]
        sides = [w for w in inside if w["text"] in ("Left", "Right") and 11 <= w["size"] <= 13]
        for b in big:
            unit = next((w["text"] for w in inside if "Light" in w["fontname"] and not _NUM.fullmatch(w["text"])
                         and 0 <= w["x0"] - b["x1"] <= 14 and abs(w["top"] - b["top"]) <= 8), "")
            side = next((s["text"] for s in sides if abs(s["x0"] - b["x0"]) <= 6 and 0 < b["top"] - s["top"] <= 30), None)
            tile["results"].append({"value": float(b["text"]), "text": b["text"], "unit": unit, "side": side})
        pct = next((w for w in inside if "Bold" in w["fontname"] and _PCT.fullmatch(w["text"])), None)
        if pct:
            tile["percentile"] = int(_PCT.fullmatch(pct["text"]).group(1))
        for line in _lines(inside):
            joined = " ".join(w["text"] for w in line)
            a = re.search(r"Asym\.\s*([\d.]+)%\s*(Left|Right)", joined)
            if a:
                tile["asymmetry"] = {"value": float(a.group(1)), "side": a.group(2)[0]}
        bold_pct = [w for w in inside if "Bold" in w["fontname"] and re.fullmatch(r"[\d.]+%", w["text"])]
        if tile["asymmetry"] is None and bold_pct and any(w["text"] == "Asymmetry" for w in inside):
            tile["asymmetry"] = {"value": float(bold_pct[0]["text"].rstrip("%")), "side": None}
        tiles.append(tile)
    res.tiles = tiles
    res.app_assessments = [t["assessment"] for t in tiles if t["assessment"]]

    v = {}
    if res.report_date:
        v["Report date"] = Value(text=res.report_date, number=None, unit="")
    for t in tiles:
        for r in t["results"]:
            label = f"{t['title']}: {t['metric']}" + (f" ({r['side'].lower()})" if r["side"] else "") + (f" [{r['unit']}]" if r["unit"] else "")
            v[label] = Value(text=f"{r['text']} {r['unit']}".strip(), number=r["value"], unit=r["unit"])
        if t["percentile"] is not None:
            v[f"{t['title']}: VALD percentile"] = Value(text=str(t["percentile"]), number=t["percentile"], unit="")
        if t["asymmetry"]:
            a = t["asymmetry"]
            v[f"{t['title']}: asymmetry"] = Value(text=f"{a['value']:g}%" + (f" {a['side']}" if a["side"] else ""), number=a["value"], unit="%")
    res.values = v
    res.checks = run_checks(res)
    if not tiles:
        res.notes.append("Could not read: no test tiles were found on this profile")
    res.notes.append("This is VALD's one-page summary: it shows one headline result per test. Results that mean something different "
                     "from the app's boxes (such as the sit-to-stand's slowest time) are shown but not used to fill them.")
    res.status = status_from(res) if tiles else "check"
    return res


def run_checks(res: ReadResult) -> list:
    checks = []
    for t in getattr(res, "tiles", []):
        n_expected = 2 if t["code"] == "SLSB" else 1
        checks.append(Check(f"{t['title']}: headline result read", len(t["results"]) == n_expected,
                            f"{len(t['results'])} result(s) found, expected {n_expected}"))
        if t["code"] == "SLSB":
            checks.append(Check(f"{t['title']}: left and right results named", sorted(r["side"] or "" for r in t["results"]) == ["Left", "Right"],
                                "each result should sit under a 'Left' or 'Right' label"))
        if t["percentile"] is not None:
            checks.append(Check(f"{t['title']}: percentile between 0 and 100", 0 <= t["percentile"] <= 100, f"{t['percentile']}"))
    return checks


def tile_for(res: ReadResult, assessment: str):
    return next((t for t in getattr(res, "tiles", []) if t["assessment"] == assessment), None)


def field_numbers_for(tile: dict) -> dict:
    """One tile's results as the app's boxes, as numbers: {box: {"value", "unit", "asymmetry"}} (only boxes the tile can fill),
    plus the tile's own headline result under its printed measure for tests the app has no boxes for yet (the drop jump)."""
    out = {}
    for r in tile["results"]:
        box = BOXES.get((tile["code"], tile["metric"], r["side"]))
        if box:
            out[box] = {"value": r["value"], "unit": r["unit"], "asymmetry": False}
        elif tile["code"] == "DJ":
            out[tile["metric"]] = {"value": r["value"], "unit": r["unit"], "asymmetry": False}
    if tile["percentile"] is not None and tile["code"] in ("CMJ", "SQT"):
        out["VALD Percentile"] = {"value": tile["percentile"], "unit": "", "asymmetry": False}
    a = tile["asymmetry"]
    if a and a["side"] and tile["code"] == "SQT":       # the squat tile's asymmetry is for its peak force
        out["L/R Asymmetry"] = {"value": a["value"] if a["side"] == "R" else -a["value"], "unit": "%", "asymmetry": True}
    return out


def app_fields(res: ReadResult, assessment: str = "") -> dict:
    """The app's boxes for one of the profile's tests, filled where the profile's result means the same as the box."""
    tile = tile_for(res, assessment)
    if not tile:
        return {}
    out = {}
    for box, n in field_numbers_for(tile).items():
        if n["asymmetry"]:
            out[box] = "0%" if n["value"] == 0 else f"{abs(n['value']):g}% {'L' if n['value'] < 0 else 'R'}"
        elif box == "VALD Percentile":
            out[box] = f"{n['value']:g}"
        else:
            out[box] = f"{n['value']:g} {n['unit']}".strip()
    return out
