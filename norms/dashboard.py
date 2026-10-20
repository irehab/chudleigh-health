"""The traffic-light dashboard a participant sees.

What goes in: the values read from the devices' reports (already checked by the clinician) and the comparisons worked out by the engine.
What comes out: a page of tiles, each with a traffic light, the number, what it means in everyday words, and what to do about it, then a short
summary and the top things to work on.

Where the words come from: two files a clinician edits, with no code involved.
    measures.csv   one row per result: its name, a plain 'what is this', and for each light what it means and what to do.
    summary.csv    the lines at the top and bottom of the page.
Nothing is written by an AI. The numbers and the 'your result was X, the expected range is Y' sentence come from fixed templates in engine.py.
A row is only shown to participants when its 'approved' column says yes.

The lights: green (doing well), amber (room to improve), red (a good place to focus first), and grey (shown for information only).
"""
from __future__ import annotations

import csv
import hashlib
import html
import json
import os
import re
from dataclasses import asdict, dataclass, field

from . import data
from .engine import (A_AGE, A_ECG, A_GRIP, A_PAR, A_SPO2, A_TANITA, ABOVE, BELOW, DISCUSS, DOING_WELL, INFO, NO_REFERENCE, NORMS_VERSION, PATIENT_TEXT, WATCH, WELL_ABOVE, WORK_ON, _num, for_patient)
from .render import bar_html

esc = lambda s: html.escape("" if s is None else str(s), quote=True)

HERE = os.path.dirname(os.path.abspath(__file__))
LIBRARY_FILE = os.path.join(HERE, "measures.csv")
SUMMARY_FILE = os.path.join(HERE, "summary.csv")

GREEN, AMBER, RED, GREY = "green", "amber", "red", "info"
SEVERITY = {GREEN: 0, GREY: 0, AMBER: 1, RED: 2}
SYMBOL = {GREEN: "\u2713", AMBER: "\u25b2", RED: "!", GREY: "i"}      # a tick, a triangle, an exclamation mark, an i: the light is never colour alone
RULES = ("engine", "range", "info", "composite", "limbs", "zone", "parts", "fp_balance", "spiro")
# rule 'spiro': the spirometer's own z-scores for FVC, FEV1 and FEV1/FVC, each given a light from the row's ranges (ERS/ATS 2022: -1.645 or above
# is within the expected range). A caution is added when the test quality grades are below C.
SPIRO_PARTS = [("FVC", "FVC z-score", "FVC % Predicted", "Total air you blew out (FVC)"),
               ("FEV1", "FEV1 z-score", "FEV1 % Predicted", "Air out in the first second (FEV1)"),
               ("FEV1/FVC Ratio", "FEV1/FVC z-score", "", "Share blown out in the first second (FEV1/FVC)")]
SPIRO_GOOD_GRADES = ("A", "B", "C")
# rule 'fp_balance': left-right balance across the VALD force plate tests. Each test's asymmetry (e.g. '11% R': VALD's letter is the
# side that produced MORE, checked against the left/right force traces on a squat report) gets a light from the row's ranges, and
# single-leg stance compares the sway on each leg. The tile says which side was weaker, and whether that was the same in every test.
FP_ASYMMETRY = [("vald_sts", "Limb Asymmetry", "sit-to-stand", "standing up"),
                ("vald_squat", "L/R Asymmetry", "squat", "pushing up from the squat"),
                ("vald_cmj", "Peak Force Asymmetry", "jump", "pushing off for the jump"),
                ("vald_cmj", "Braking Impulse Asymmetry", "jump", "dipping down before the jump")]
# rule 'zone': a value whose light is the colour the device itself draws it in. 'members' names the box holding that colour (green or orange).
# rule 'parts': several boxes from the same device, each given a light from the row's ranges; the tile shows the worst. 'members' lists the boxes.
ZONE_LIGHTS = {"green": "green", "orange": "amber", "normal": "green", "high": "green", "low": "amber"}   # chart colours, or the band the device prints
# rule 'limbs': left-right muscle balance from the Tanita's segmental analysis. The light for arms and for legs comes from the difference
# between the two sides (as a % of the bigger side) against the row's green/amber ranges, and is at least amber when the Tanita itself
# marks a limb outside its normal band (the 'Limb Flags' box, e.g. 'left leg low').
LIMB_PAIRS = [("Arms", "arm", "Right Arm Muscle", "Left Arm Muscle"), ("Legs", "leg", "Right Leg Muscle", "Left Leg Muscle")]
LIMB_FLAGS_BOX = "Limb Flags"
A_VALD_CMJ = "VALD ForceDecks - Countermovement Jump (CMJ)"
A_VALD_SQUAT = "VALD ForceDecks - Multi-Rep Squat"
A_VALD_STS = "VALD ForceDecks - Sit-to-Stand"
A_VALD_SLSB = "VALD ForceDecks - Single Leg Stance / Balance"
A_SPIRO = "Spirometry (Pulmonary Function)"
VALUE_DEVICES = {"tanita": A_TANITA, "vald_cmj": A_VALD_CMJ, "vald_squat": A_VALD_SQUAT, "vald_sts": A_VALD_STS, "vald_slsb": A_VALD_SLSB, "spiro": A_SPIRO, "grip": A_GRIP}
DEVICE_NAMES = {"vald_cmj": "Jump (CMJ)", "vald_squat": "Squat", "vald_sts": "Sit-to-stand", "vald_slsb": "Single-leg balance"}
COVERED_ASSESSMENTS = {A_TANITA, A_ECG, A_AGE, A_SPO2, A_PAR, A_GRIP, A_SPIRO, A_VALD_CMJ, A_VALD_SQUAT, A_VALD_STS, A_VALD_SLSB}      # the devices that have dashboard tiles so far
TEXT_FIELDS = ("headline", "text", "do")
REQUIRED_COLUMNS = ["key", "group", "order", "priority", "approved", "title", "what_it_is", "rule", "members", "green_min", "green_max", "amber_min", "amber_max",
                    "facts", "value_from", "green_headline", "green_text", "green_do", "amber_headline", "amber_text", "amber_do", "red_headline", "red_text",
                    "red_do", "low_headline", "low_text", "low_do", "info_headline", "info_text", "info_do", "book", "sources", "notes"]
REQUIRED_SUMMARY = ["library_version", "page_title", "all_green", "all_green_one", "mixed_lead", "no_green", "amber_clause", "red_clause", "priorities_heading",
                    "priorities_intro", "no_priorities", "legend_green", "legend_amber", "legend_red", "legend_info", "note_heading", "tap_hint",
                    "how_to_read_heading", "how_to_read_1", "how_to_read_2", "how_to_read_3", "sources_heading", "disclosure", "book_label"]
LIGHT_NAMES = {"green": "Green", "amber": "Amber", "red": "Red", "low": "Lower than expected", "info": "For information"}
# Only the WORDS can be edited in the app. The rule, the ranges, the sources and the order stay in the file, because they decide the lights.
EDITABLE_COLUMNS = ["title", "what_it_is", "facts", "book"] + [f"{light}_{f}" for light in LIGHT_NAMES for f in TEXT_FIELDS]
FIELD_LIMITS = {"title": 80, "what_it_is": 300, "facts": 200, "book": 160, "headline": 80, "text": 400, "do": 400}
COLUMN_LABELS = {"title": "Name the participant sees", "what_it_is": "What it is", "facts": "Sentence of facts (must include {value})", "book": "Booklet line"}
COLUMN_LABELS.update({f"{light}_{f}": f"{name}: {label}" for light, name in LIGHT_NAMES.items() for f, label in (("headline", "headline"), ("text", "what it means"), ("do", "what to do"))})
DEFAULT_REPORTS_HINT = "Your original reports from your devices are below this page, ready to open."
MAX_SENTENCE_WORDS = 25            # longer than this is flagged to the clinician as hard to read (a warning, not a block)
BANNED = re.compile(r"\b(guarantee[ds]?|will improve|cures?|abnormal|you have (?:a|an) )\b", re.I)


# ------------------------------------------------------------------------------------------------------------------------ the library
@dataclass
class Row:
    key: str
    group: str = ""
    order: int = 0
    priority: int = 99
    approved: bool = False
    title: str = ""
    what_it_is: str = ""
    rule: str = "engine"
    members: list = field(default_factory=list)
    green_min: float | None = None
    green_max: float | None = None
    amber_min: float | None = None
    amber_max: float | None = None
    facts: str = ""
    value_from: str = ""
    text: dict = field(default_factory=dict)       # {"green": {"headline":..., "text":..., "do":...}, "amber": ..., "red": ..., "low": ..., "info": ...}
    book: str = ""
    sources: list = field(default_factory=list)
    notes: str = ""
    broken: bool = False                           # a row with an error is never shown to participants, even if approved
    gaps: list = field(default_factory=list)       # the wording still missing (a row with gaps can be a draft, but cannot be approved)
    hash: str = ""                                 # a fingerprint of the wording: an approval only counts while it still matches


@dataclass
class Library:
    rows: list
    summary: dict
    problems: list                                 # strings starting ERROR or WARNING, for the clinician
    path: str = ""
    file_raw: dict = field(default_factory=dict)   # {key: the row exactly as it is in the file}, so an edit can be compared with it and undone
    file_hash: dict = field(default_factory=dict)  # {key: fingerprint of the file's own wording}, for the rows that have been edited in the app
    overridden: dict = field(default_factory=dict) # {key: the edit saved in the app}

    @property
    def errors(self):
        return [p for p in self.problems if p.startswith("ERROR")]

    @property
    def warnings(self):
        return [p for p in self.problems if p.startswith("WARNING")]

    @property
    def version(self):
        return self.summary.get("library_version", "")


def _number(text, problems, label):
    t = (text or "").strip()
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        problems.append(f"ERROR: {label}: '{t}' is not a number.")
        return None


def _sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if s]


def _check_words(label, text, problems):
    for s in _sentences(text):
        if len(s.split()) > MAX_SENTENCE_WORDS:
            problems.append(f"WARNING: {label}: a sentence is {len(s.split())} words long. Shorter is easier to read: '{s[:60]}...'")
    if BANNED.search(text or ""):
        problems.append(f"WARNING: {label}: avoid words that promise or diagnose ('{BANNED.search(text).group(0).strip()}').")


def wording_hash(row: Row) -> str:
    """A short fingerprint of everything a participant could read or that decides a light: the words, the ranges, the sources. Not the order, the priority,
    the notes or the approved column, so re-ordering the page does not undo an approval but changing a word does."""
    payload = {"title": row.title, "group": row.group, "what_it_is": row.what_it_is, "rule": row.rule, "members": row.members, "facts": row.facts,
               "value_from": row.value_from, "ranges": [row.green_min, row.green_max, row.amber_min, row.amber_max], "text": row.text, "book": row.book, "sources": row.sources}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def approval_status(row: Row, approvals: dict | None) -> str:
    """'file' (approved in the CSV), 'approved' (approved in the app, and the wording is unchanged), 'changed' (it was approved but the wording has changed since),
    'incomplete' (words still missing, so it cannot be approved), 'error' (a problem in its row), or 'none'."""
    if row.broken:
        return "error"
    if row.gaps:
        return "incomplete"
    if row.approved:
        return "file"
    mine = (approvals or {}).get(row.key)
    if mine and mine == row.hash:
        return "approved"
    return "changed" if mine else "none"


def wording_for_review(row: Row) -> list:
    """What a participant would read for each light, for the clinician to check before approving: [(light, headline, text, do)]."""
    names = {"green": "Green", "amber": "Amber", "red": "Red", "low": "Lower than expected", "info": "For information"}
    return [(names[l], row.text[l]["headline"], row.text[l]["text"], row.text[l]["do"]) for l in ("green", "amber", "red", "low", "info") if any(row.text[l].values())]


def _parse_row(raw, line, problems):
    key = (raw.get("key") or "").strip()
    label = f"Row {line} ({key or 'no key'})"
    row = Row(key=key, group=(raw.get("group") or "").strip(), title=(raw.get("title") or "").strip(), what_it_is=(raw.get("what_it_is") or "").strip(),
              rule=(raw.get("rule") or "").strip().lower(), facts=(raw.get("facts") or "").strip(), value_from=(raw.get("value_from") or "").strip(),
              book=(raw.get("book") or "").strip(), notes=(raw.get("notes") or "").strip())
    start = len(problems)
    if not key:
        problems.append(f"ERROR: {label}: the key is empty.")
    appr = (raw.get("approved") or "").strip().lower()
    if appr not in ("yes", "no", ""):
        problems.append(f"ERROR: {label}: 'approved' must be yes or no, not '{appr}'.")
    row.approved = appr == "yes"
    for name in ("order", "priority"):
        t = (raw.get(name) or "").strip()
        try:
            setattr(row, name, int(float(t)) if t else (0 if name == "order" else 99))
        except ValueError:
            problems.append(f"ERROR: {label}: '{name}' must be a whole number, not '{t}'.")
    for name in ("green_min", "green_max", "amber_min", "amber_max"):
        setattr(row, name, _number(raw.get(name), problems, f"{label}: {name}"))
    row.members = [m.strip() for m in (raw.get("members") or "").split("|") if m.strip()]
    row.sources = [s.strip() for s in (raw.get("sources") or "").split(",") if s.strip()]
    for light in ("green", "amber", "red", "low", "info"):
        row.text[light] = {f: (raw.get(f"{light}_{f}") or "").strip() for f in TEXT_FIELDS}
    if row.rule not in RULES:
        problems.append(f"ERROR: {label}: 'rule' must be one of {', '.join(RULES)}, not '{row.rule}'.")
    if row.rule == "engine" and key not in PATIENT_TEXT:
        problems.append(f"ERROR: {label}: '{key}' is not a result the app can work out. Known results: {', '.join(sorted(PATIENT_TEXT))}.")
    if row.rule == "composite":
        bad = [m for m in row.members if m not in PATIENT_TEXT]
        if not row.members or bad:
            problems.append(f"ERROR: {label}: 'members' must list known results separated by | (problem: {', '.join(bad) or 'none listed'}).")
    if row.rule in ("zone", "parts") and not row.members:
        problems.append(f"ERROR: {label}: a '{row.rule}' row needs 'members': the box name(s), separated by |.")
    if row.rule == "parts" and row.value_from.split(":")[0] not in VALUE_DEVICES and not all(m.split(":")[0] in VALUE_DEVICES for m in row.members if ":" in m):
        problems.append(f"ERROR: {label}: 'value_from' must name the device, for example tanita: (the boxes are listed in 'members').")
    if row.rule == "parts" and any(":" in m and m.split(":")[0] not in VALUE_DEVICES for m in row.members):
        problems.append(f"ERROR: {label}: a member names an unknown device. Known: {', '.join(VALUE_DEVICES)}.")
    if row.rule == "parts" and not row.value_from and not all(":" in m for m in row.members):
        problems.append(f"ERROR: {label}: give 'value_from' (the device), or put the device before each member, like vald_cmj:VALD Percentile.")
    if row.rule in ("range", "info", "zone"):
        dev = row.value_from.split(":")[0] if ":" in row.value_from else ""
        if dev not in VALUE_DEVICES or not row.value_from.split(":", 1)[1].strip():
            problems.append(f"ERROR: {label}: 'value_from' must look like tanita:Visceral Fat (device, then the box name).")
        if "{value}" not in row.facts:
            problems.append(f"ERROR: {label}: 'facts' must include {{value}}, for example 'Your rating was {{value}}.'")
    if row.rule in ("range", "limbs", "parts", "fp_balance", "spiro") and row.green_min is None and row.green_max is None:
        problems.append(f"ERROR: {label}: a '{row.rule}' row needs a green range (green_min and/or green_max).")
    for sid in row.sources:
        if sid not in data.SOURCES:
            problems.append(f"ERROR: {label}: unknown source '{sid}'. Known sources: {', '.join(sorted(data.SOURCES))}.")
    needs = [("title", row.title), ("what_it_is", row.what_it_is), ("group", row.group)]
    if row.rule == "info":
        needs += [("info_text", row.text["info"]["text"])]
    else:
        needs += [(f"{light}_{f}", row.text[light][f]) for light in ("green", "amber", "red") for f in TEXT_FIELDS]
    row.gaps = [n for n, v in needs if not v]
    if row.approved and row.gaps:
        problems.append(f"ERROR: {label}: approved, but these are empty: {', '.join(row.gaps)}.")
    row.hash = wording_hash(row)
    texts = [row.what_it_is, row.facts] + [v for light in row.text.values() for v in light.values()]
    for t in texts:
        _check_words(label, t, problems)
    row.broken = len(problems) > start and any(p.startswith("ERROR") for p in problems[start:])
    return row


def _read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:        # utf-8-sig so a file saved by Excel (with its invisible marker) still reads
        reader = csv.DictReader(f)
        return list(reader), list(reader.fieldnames or [])


def fmt_pair(template, count, **kw):
    """'{count} has room to improve.|{count} have room to improve.' -> the first for one, the second for any other number."""
    parts = template.split("|")
    chosen = parts[0] if (count == 1 or len(parts) == 1) else parts[1]
    return chosen.format(count=count, **kw)


def clean_field(column: str, value) -> str:
    """Wording is kept on one line: no control characters, spaces tidied, cut to the limit for that kind of field."""
    t = re.sub(r"[\x00-\x1f\x7f]", " ", str(value if value is not None else ""))
    limit = FIELD_LIMITS.get(column) or FIELD_LIMITS.get(column.split("_", 1)[-1], 400)      # 'green_headline' is limited like 'headline'
    return " ".join(t.split())[:limit].strip()


def apply_overrides(raw: dict, override: dict | None) -> dict:
    """The file's row with an edit made in the app laid over it. Only the editable wording can be changed this way: never the rule, the ranges or the sources."""
    out = dict(raw)
    for column, value in ((override or {}).get("fields") or {}).items():
        if column in EDITABLE_COLUMNS:
            out[column] = clean_field(column, value)
    return out


def effective_fields(row: Row) -> dict:
    """The editable wording as it is now (the file's, with any edit laid over it): what the editor shows."""
    out = {"title": row.title, "what_it_is": row.what_it_is, "facts": row.facts, "book": row.book}
    out.update({f"{light}_{f}": row.text[light][f] for light in LIGHT_NAMES for f in TEXT_FIELDS})
    return out


def file_fields(raw: dict) -> dict:
    return {c: clean_field(c, raw.get(c)) for c in EDITABLE_COLUMNS}


def diff_fields(raw: dict, new_fields: dict) -> dict:
    """Only what differs from the file, so a later change to the file in a field you did not touch still comes through."""
    base = file_fields(raw)
    return {c: clean_field(c, new_fields[c]) for c in EDITABLE_COLUMNS if c in new_fields and clean_field(c, new_fields[c]) != base[c]}


def check_edit(library: Library, key: str, new_fields: dict):
    """Check an edit before it is saved. Returns (errors, warnings): errors stop it being saved, warnings are advice."""
    raw = library.file_raw.get(key)
    if raw is None:
        return ["That result is not in the library."], []
    merged = apply_overrides(raw, {"fields": {c: v for c, v in new_fields.items() if c in EDITABLE_COLUMNS}})
    problems: list = []
    row = _parse_row(merged, 0, problems)
    tidy = lambda p: re.sub(r"^(?:ERROR|WARNING): Row \d+ \([^)]*\): ", "", p)
    errors = [tidy(p) for p in problems if p.startswith("ERROR")]
    if row.gaps:
        errors.append("These cannot be left empty: " + ", ".join(COLUMN_LABELS.get(g, g) for g in row.gaps) + ".")
    return errors, [tidy(p) for p in problems if p.startswith("WARNING")]


def load_library(path=None, summary_path=None, overrides: dict | None = None) -> Library:
    """Read and check measures.csv and summary.csv, with any edits made in the app laid over the file's wording.
    Never raises: problems come back in the list, and a broken row is never shown."""
    path, summary_path = path or LIBRARY_FILE, summary_path or SUMMARY_FILE
    overrides = overrides or {}
    problems: list = []
    rows: list = []
    summary: dict = {}
    file_raw: dict = {}
    file_hash: dict = {}
    overridden: dict = {}
    try:
        raw_rows, header = _read_csv(path)
    except Exception as e:
        return Library([], {}, [f"ERROR: the measure library could not be read ({type(e).__name__}). Check that {os.path.basename(path)} is there and saved as CSV UTF-8."], path)
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        return Library([], {}, [f"ERROR: the measure library is missing these columns: {', '.join(missing)}. Do not rename or remove the header row."], path)
    seen = set()
    for i, raw in enumerate(raw_rows, start=2):
        if not any((v or "").strip() for v in raw.values()):
            continue
        key = (raw.get("key") or "").strip()
        file_raw[key] = dict(raw)
        if key in overrides and (overrides[key] or {}).get("fields"):
            file_hash[key] = _parse_row(dict(raw), i, []).hash
            overridden[key] = overrides[key]
            raw = apply_overrides(raw, overrides[key])
        row = _parse_row(raw, i, problems)
        if row.key in seen:
            problems.append(f"ERROR: Row {i} ({row.key}): this key is used twice.")
            row.broken = True
        seen.add(row.key)
        rows.append(row)
    try:
        with open(summary_path, newline="", encoding="utf-8-sig") as f:
            for rec in csv.DictReader(f):
                if (rec.get("key") or "").strip():
                    summary[rec["key"].strip()] = (rec.get("text") or "").strip()
    except Exception as e:
        problems.append(f"ERROR: the summary lines could not be read ({type(e).__name__}). Check {os.path.basename(summary_path)}.")
    for k in REQUIRED_SUMMARY:
        if not summary.get(k):
            problems.append(f"ERROR: summary.csv has no line called '{k}'.")
    if all(summary.get(k) for k in ("mixed_lead", "no_green", "amber_clause", "red_clause", "all_green", "all_green_one")):
        try:
            for k in ("mixed_lead", "no_green", "amber_clause", "red_clause"):
                fmt_pair(summary[k], 2, green=1, n=3)
            summary["all_green"].format(n=4)
        except (KeyError, IndexError, ValueError) as e:
            problems.append(f"ERROR: a summary line uses a placeholder it should not ({e}). Only {{n}}, {{green}} and {{count}} are allowed.")
    for k in ("all_green", "all_green_one", "mixed_lead", "no_green", "amber_clause", "red_clause", "priorities_intro", "no_priorities", "how_to_read_1", "how_to_read_2", "how_to_read_3", "reports_hint"):
        _check_words(f"summary '{k}'", summary.get(k, ""), problems)
    return Library(rows, summary, problems, path, file_raw, file_hash, overridden)


# ------------------------------------------------------------------------------------------------------------------------ the tiles
@dataclass
class Tile:
    key: str
    group: str
    title: str
    light: str
    value_text: str
    what_it_is: str
    facts: list
    headline: str
    text: str
    do: str
    book: str = ""
    sources: list = field(default_factory=list)
    approved: bool = True
    priority: int = 99
    order: int = 0
    bar: str = ""
    parts: list = field(default_factory=list)         # for a tile that sums up several results: [{"label", "value_text", "light", "words"}]
    words: str = ""                                   # the chip's own words, when the usual ones do not fit (a result that is lower than expected)
    hash: str = ""                                    # the fingerprint of the wording that was shown, kept with the saved report

    def record(self) -> dict:
        """What is kept with the saved report (no long text, which is re-created from the library)."""
        return {"key": self.key, "title": self.title, "light": self.light, "value_text": self.value_text, "group": self.group, "wording": self.hash}


def engine_light(c: dict) -> str:
    """How a comparison from the engine becomes a light. Green = doing well, amber = something you can work on, red = well above or worth discussing."""
    theme, status = c.get("theme"), c.get("status")
    if theme == DOING_WELL:
        return GREEN
    if theme == WATCH:
        return AMBER
    if theme == WORK_ON:
        return RED if status == WELL_ABOVE else AMBER
    if theme == DISCUSS:
        return RED
    return GREY


def range_light(value: float, row: Row) -> str:
    def inside(lo, hi):
        return (lo is not None or hi is not None) and (lo is None or value >= lo) and (hi is None or value <= hi)
    if inside(row.green_min, row.green_max):
        return GREEN
    if inside(row.amber_min, row.amber_max):
        return AMBER
    return RED


def read_value(spec: str, tests: list):
    """('58.8 kg', 58.8) for 'tanita:Muscle Mass', from the last test of that device that has the box filled in. None if there is no number."""
    device, box = spec.split(":", 1)
    assessment = VALUE_DEVICES.get(device)
    found = None
    for t in tests or []:
        if t.get("type") == assessment:
            shown = str((t.get("data") or {}).get(box.strip(), "")).strip()
            if shown and _num(shown) is not None:
                found = (shown, _num(shown))
    return found


def _limb_flags(text: str) -> dict:
    """'left leg low; right arm high' -> {('left', 'leg'): 'low', ('right', 'arm'): 'high'}. Anything else (such as 'none') is ignored."""
    return {(side, limb): way for side, limb, way in re.findall(r"\b(right|left)\s+(arm|leg)\s+(low|high)\b", (text or "").lower())}


def _kg(shown: str) -> str:
    s = (shown or "").strip()
    return s if re.search(r"[a-z]", s, re.I) else f"{s} kg"


def limb_balance(row: Row, tests: list, S: dict):
    """(light, facts, parts) for the left-right muscle balance tile, or None if no arm or leg pair was entered. Uses the last Tanita test."""
    data = None
    for t in tests or []:
        if t.get("type") == A_TANITA:
            data = t.get("data") or {}
    if not data:
        return None
    flags = _limb_flags(data.get(LIMB_FLAGS_BOX, ""))
    facts, parts = [], []
    for name, limb, right_box, left_box in LIMB_PAIRS:
        r_shown, l_shown = str(data.get(right_box, "")).strip(), str(data.get(left_box, "")).strip()
        r, l = _num(r_shown), _num(l_shown)
        if r is None or l is None or max(r, l) <= 0:
            continue
        diff = round(abs(r - l) / max(r, l) * 100, 1)
        light = range_light(diff, row)
        marked = [(side, flags[(side, limb)]) for side in ("right", "left") if (side, limb) in flags]
        if marked and light == GREEN:
            light = AMBER
        if r == l:
            facts.append(f"Right {limb} {_kg(r_shown)}, left {limb} {_kg(l_shown)}: the same.")
        else:
            facts.append(f"Right {limb} {_kg(r_shown)}, left {limb} {_kg(l_shown)}. Your {'right' if r < l else 'left'} {limb} has {diff:.0f}% less muscle.")
        for side, way in marked:
            facts.append(f"The Tanita marks your {side} {limb} muscle as {'lower' if way == 'low' else 'higher'} than its normal range.")
        words = f"{diff:.0f}% difference" if r != l else "even"
        if marked:
            words += "; " + ", ".join(f"{side} {limb} {'low' if way == 'low' else 'high'}" for side, way in marked)
        parts.append({"label": name, "value_text": f"R {_kg(r_shown)} · L {_kg(l_shown)}", "light": light, "words": words})
    if not parts:
        return None
    return max((p["light"] for p in parts), key=lambda x: SEVERITY[x]), facts, parts


def _device_data(spec: str, tests: list) -> dict:
    """The boxes of the last test from the device named in 'tanita:...' (empty if none)."""
    assessment = VALUE_DEVICES.get(spec.split(":", 1)[0].strip())
    found = {}
    for t in tests or []:
        if assessment and t.get("type") == assessment:
            found = t.get("data") or {}
    return found


def zone_reading(row: Row, tests: list):
    """(light, value_text, zone) for a 'zone' row, or None if the value was not entered. Grey if the colour was not entered."""
    got = read_value(row.value_from, tests)
    if not got:
        return None
    zone = str(_device_data(row.value_from, tests).get(row.members[0], "")).strip().lower()
    return ZONE_LIGHTS.get(zone, GREY), got[0], zone


def _ordinal(n: float) -> str:
    n = int(round(n))
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


# For a percentile tile: the force each test is about, so it can also be shown against body weight (N / (kg x 9.81) = times body weight)
RELATIVE_FORCE = {"vald_squat": ("Peak Force", "your best squat"), "vald_sts": ("Peak Standing Force", "your strongest stand")}


def parts_reading(row: Row, tests: list, S: dict | None = None):
    """(light, parts, facts) for a 'parts' row: each box that has a number gets its own light from the row's ranges. None if none has a number.
    A member is a box of the row's device ('Right Arm Phase Angle'), or 'device:box' to take it from another test ('vald_squat:VALD Percentile')."""
    parts, facts = [], []
    for member in row.members:
        dev, box = member.split(":", 1) if ":" in member else (row.value_from.split(":")[0], member)
        data = _device_data(f"{dev}:", tests)
        shown = str(data.get(box, "")).strip()
        number = _num(shown)
        if number is None:
            continue
        light = range_light(number, row)
        if box == "VALD Percentile":
            label, shown = DEVICE_NAMES.get(dev, dev), f"{_ordinal(number)} percentile"
            words = _words(S or {}, light)
            force_box, what = RELATIVE_FORCE.get(dev, (None, ""))
            force, bw = _num(str(data.get(force_box, ""))) if force_box else None, _num(str(data.get("Body Weight", "")))
            if force and bw:
                facts.append(f"{label}: {what} was {force:g} N, about {force / (bw * 9.81):.1f} times your body weight.")
        else:
            label = re.sub(r"\s+phase angle$", "", box, flags=re.I)
            words = {GREEN: "healthy", AMBER: "below the healthy mark", RED: "low"}[light]
        parts.append({"label": label, "value_text": shown, "light": light, "words": words})
    if not parts:
        return None
    return max((p["light"] for p in parts), key=lambda x: SEVERITY[x]), parts, facts


def _asym(text: str):
    """'11% R' -> (11.0, 'R'); '0%' -> (0.0, None); anything else -> None."""
    m = re.fullmatch(r"\s*([\d.]+)\s*%?\s*([LR])?\s*", str(text or ""), re.I)
    return (float(m.group(1)), (m.group(2) or "").upper() or None) if m else None


def spirometry_reading(row: Row, tests: list):
    """(light, facts, parts) for the 'spiro' tile, or None if no z-score was entered."""
    d = _device_data("spiro:", tests)
    words = {GREEN: "within the expected range", AMBER: "a little below the expected range", RED: "below the expected range"}
    parts, facts = [], []
    for box, zbox, pbox, label in SPIRO_PARTS:
        z = _num(str(d.get(zbox, "")))
        if z is None:
            continue
        light = range_light(z, row)
        shown, pct = str(d.get(box, "")).strip(), _num(str(d.get(pbox, ""))) if pbox else None
        value = shown + (f", {pct:g}% of predicted" if pct is not None else "")
        facts.append(f"{label}: {value}. That is {words[light]} for your age, sex and height.")
        parts.append({"label": label, "value_text": value, "light": light, "words": f"{words[light]} (z {z:g})"})
    if not parts:
        return None
    grades = {k: str(d.get(f"{k} Grade", "")).strip().upper() for k in ("FEV1", "FVC")}
    poor = {k: g for k, g in grades.items() if g and g not in SPIRO_GOOD_GRADES}
    if poor:
        facts.append("The test was not as complete as it could be (quality grades: " + ", ".join(f"{k} {g}" for k, g in poor.items())
                     + "). These numbers may read lower than your true values, so your clinician may repeat the test.")
    return max((p["light"] for p in parts), key=lambda x: SEVERITY[x]), facts, parts


def force_plate_balance(row: Row, tests: list):
    """(light, facts, parts) for the 'fp_balance' tile, or None if no force plate asymmetry was entered."""
    parts, facts, weaker = [], [], []
    for dev, box, test, action in FP_ASYMMETRY:
        got = _asym(_device_data(f"{dev}:", tests).get(box, ""))
        if not got:
            continue
        pct, more = got
        light = range_light(pct, row)
        if not more or pct == 0:
            facts.append(f"{test.capitalize()} ({action}): both sides did the same.")
            words = "even"
        else:
            weak, strong = ("right", "left") if more == "L" else ("left", "right")
            if pct >= (row.amber_min or 10) / 2:      # only a real difference counts towards 'the weaker side' (half the amber line, 5%)
                weaker.append(weak)
            facts.append(f"{test.capitalize()} ({action}): your {weak} side did {pct:g}% less than your {strong} side.")
            words = f"{weak} {pct:g}% less"
        parts.append({"label": f"{test.capitalize()}: {action}", "value_text": f"{pct:g}%", "light": light, "words": words})
    slsb = _device_data("vald_slsb:", tests)
    left, right = _num(str(slsb.get("Left Sway Velocity", ""))), _num(str(slsb.get("Right Sway Velocity", "")))
    if left and right:
        pct = round(abs(left - right) / max(left, right) * 100, 1)
        light = range_light(pct, row)
        worse = "left" if left > right else "right"
        if left == right:
            facts.append("Standing on one leg: you swayed the same on each leg.")
        else:
            facts.append(f"Standing on one leg: you swayed {pct:.0f}% more on your {worse} leg.")
        parts.append({"label": "Balance on one leg", "value_text": f"L {left:g} · R {right:g} mm/s", "light": light,
                      "words": "even" if left == right else f"{worse} sways {pct:.0f}% more"})
    if not parts:
        return None
    if len(weaker) >= 2:
        side = max(("left", "right"), key=weaker.count)
        n = weaker.count(side)
        if n == len(weaker):
            facts.insert(0, f"Your {side} side was the weaker side in all {n} force plate measures.")
        elif n * 2 > len(weaker):                                   # a clear majority only; a tie says nothing
            facts.insert(0, f"Your {side} side was the weaker side in {n} of {len(weaker)} force plate measures.")
    return max((p["light"] for p in parts), key=lambda x: SEVERITY[x]), facts, parts


# ------------------------------------------------------------------------------------------------------------------------ linked findings
# Results from different tests that point the same way, shown side by side. Nothing here claims a cause: it only puts them together,
# and the clinician adds their own interpretation. Each finding belongs to the tile it comes from, so a tile that is not shown
# (not approved, or left out) adds nothing to the participant's report.
LINK_MIN_PCT = 5.0          # a left/right difference smaller than this is not counted as one side being lower
LINK_MIN_DEGREES = 0.5      # phase angle difference between limbs
GRIP_LINK_PCT = 20.0        # hands commonly differ by about 10% (the dominant hand is stronger), so only a bigger gap is linked


def _side_findings(tests: list) -> list:
    """[(side, limb, source, tile key, sentence)]: every result that points to one side's arm or leg."""
    out = []
    tan = _device_data("tanita:", tests)
    flags = _limb_flags(tan.get(LIMB_FLAGS_BOX, ""))
    for limb in ("arm", "leg"):
        r, l = _num(str(tan.get(f"Right {limb.capitalize()} Muscle", ""))), _num(str(tan.get(f"Left {limb.capitalize()} Muscle", "")))
        marked = {side for side in ("right", "left") if flags.get((side, limb)) == "low"}
        if r and l:
            diff = abs(r - l) / max(r, l) * 100
            lower = "left" if l < r else ("right" if r < l else None)
            for side in ({lower} if lower and diff >= LINK_MIN_PCT else set()) | marked:
                mine, other = (l, r) if side == "left" else (r, l)
                text = f"Tanita: less muscle in the {side} {limb} ({mine:g} kg against {other:g} kg)"
                out.append((side, limb, "tanita", "limb_balance", text + (", and the Tanita marks it as lower than normal" if side in marked else "")))
        else:
            for side in marked:
                out.append((side, limb, "tanita", "limb_balance", f"Tanita: the {side} {limb} muscle is marked as lower than normal"))
        pr, pl = _num(str(tan.get(f"Right {limb.capitalize()} Phase Angle", ""))), _num(str(tan.get(f"Left {limb.capitalize()} Phase Angle", "")))
        if pr and pl and abs(pr - pl) >= LINK_MIN_DEGREES:
            side = "left" if pl < pr else "right"
            mine, other = (pl, pr) if side == "left" else (pr, pl)
            out.append((side, limb, "tanita_phase", "phase_angle_limbs", f"Tanita: lower phase angle in the {side} {limb} ({mine:g}° against {other:g}°)"))
    for dev, box, test, action in FP_ASYMMETRY:
        got = _asym(_device_data(f"{dev}:", tests).get(box, ""))
        if got and got[1] and got[0] >= LINK_MIN_PCT:
            side = "right" if got[1] == "L" else "left"
            out.append((side, "leg", dev, "fp_balance", f"{test.capitalize()} ({action}): the {side} side did {got[0]:g}% less"))
    grip = _device_data("grip:", tests) if "grip" in VALUE_DEVICES else {}
    gr, gl = _num(str(grip.get("Right Grip", ""))), _num(str(grip.get("Left Grip", "")))
    if gr and gl and abs(gr - gl) / max(gr, gl) * 100 >= GRIP_LINK_PCT:
        side = "left" if gl < gr else "right"
        mine, other = (gl, gr) if side == "left" else (gr, gl)
        out.append((side, "arm", "grip", "grip", f"Grip strength: the {side} hand is weaker ({mine:g} kg against {other:g} kg)"))
    slsb = _device_data("vald_slsb:", tests)
    left, right = _num(str(slsb.get("Left Sway Velocity", ""))), _num(str(slsb.get("Right Sway Velocity", "")))
    if left and right and left != right:
        pct = abs(left - right) / max(left, right) * 100
        if pct >= LINK_MIN_PCT:
            side = "left" if left > right else "right"
            out.append((side, "leg", "vald_slsb", "fp_balance", f"Single-leg balance: more sway standing on the {side} leg ({pct:.0f}% more)"))
    return out


def _strength_findings(tests: list, comparisons=None) -> list:
    """[(source, tile key, sentence)]: results that relate to muscle or strength being on the low side (EWGSOP2 looks at both together)."""
    out = []
    tan = _device_data("tanita:", tests)
    if str(tan.get("Muscle Mass Band", "")).strip().lower() == "low":
        out.append(("tanita_muscle", "muscle_mass", f"Tanita: muscle mass{' ' + str(tan.get('Muscle Mass', '')).strip() if tan.get('Muscle Mass') else ''} "
                                                    "is rated low for your age, sex and height"))
    grip = next((c for c in comparisons or [] if c.get("key") == "grip" and c.get("status") == BELOW), None)
    if grip:
        out.append(("grip", "grip", f"Grip strength: {grip['value_text']}, {grip['status_text'].lower()}"))
    asm = next((c for c in comparisons or [] if c.get("key") == "asm_index" and c.get("status") == BELOW), None)
    if asm:
        out.append(("tanita_asm", "asm_index", f"Arm and leg muscle: {asm['value_text']}, under the European low-muscle line"))
    if str(tan.get("Leg Muscle Score Zone", "")).strip().lower() == "orange":
        score = str(tan.get("Leg Muscle Score", "")).strip()
        out.append(("tanita", "leg_score", f"Tanita: leg muscle score{' ' + score if score else ''} is below the line for your age"))
    legs = [(_num(str(tan.get(f"{s} Leg Phase Angle", ""))), s.lower()) for s in ("Right", "Left")]
    low = [f"{side} {v:g}°" for v, side in legs if v is not None and v < 7]
    if low:
        out.append(("tanita_phase", "phase_angle_limbs", "Tanita: leg phase angle below the healthy mark of 7° (" + ", ".join(low) + ")"))
    for dev in ("vald_cmj", "vald_squat", "vald_sts"):
        p = _num(str(_device_data(f"{dev}:", tests).get("VALD Percentile", "")))
        if p is not None and p < 25:
            out.append((dev, "fp_strength", f"{DEVICE_NAMES[dev]}: {_ordinal(p)} percentile for your age and sex"))
    return out


def linked_findings(tests: list, shown_keys=None, comparisons=None) -> list:
    """Groups of results from at least two different tests that point the same way:
    [{"title": "Your left leg", "items": [sentence, ...]}]. shown_keys: only use findings from these tiles (None = all, for the clinician)."""
    keep = (lambda key: True) if shown_keys is None else (lambda key: key in shown_keys)
    groups = {}
    for side, limb, source, key, text in _side_findings(tests):
        if keep(key):
            groups.setdefault(f"Your {side} {limb}", []).append((source, text))
    strength = [(source, text) for source, key, text in _strength_findings(tests, comparisons) if keep(key)]
    out = [{"title": title, "items": [t for _s, t in items]} for title, items in groups.items() if len({s for s, _t in items}) >= 2]
    if len({s for s, _t in strength}) >= 2:
        out.append({"title": "Muscle and strength", "items": [t for _s, t in strength]})
    return out


def _pick(row: Row, light: str, status: str = ""):
    if light == GREY:
        t = row.text["info"]
        return t["headline"] or "For your information", t["text"], t["do"]
    low = row.text["low"]
    t = low if (status == BELOW and low["text"]) else row.text[light]
    return t["headline"], t["text"], t["do"]


def _words(S: dict, light: str) -> str:
    return S.get(f"legend_{'info' if light == GREY else light}", light)


def build_tiles(tests: list, comparisons: list, library: Library, include_drafts: bool = False, exclude=(), approvals: dict | None = None):
    """Turn the results into tiles. Returns (tiles, hidden): hidden lists the rows left out because they are not approved yet (or have an error).

    approvals: {result key: fingerprint of the wording approved in the app}. A row is approved if the CSV says yes, or if the app holds an approval whose
    fingerprint still matches the row's wording. Incomplete or broken rows are never shown."""
    exclude = set(exclude or ())
    comps = {c["key"]: c for c in for_patient(comparisons or []) if c.get("status") != NO_REFERENCE}
    S = library.summary
    tiles, hidden = [], []
    for row in sorted(library.rows, key=lambda r: (r.order, r.key)):
        if row.key in exclude:
            continue
        status = approval_status(row, approvals)
        shown = status in ("file", "approved")
        tile = None
        if row.rule == "engine":
            c = comps.get(row.key)
            if c:
                light = engine_light(c)
                low = c["status"] == BELOW and bool(row.text["low"]["text"])
                if low and light == RED:
                    light = AMBER                                       # lower than expected is 'worth a mention', not 'focus first'
                head, text, do = _pick(row, light, c["status"])
                src = [c["source"]] if c.get("source") else []          # only the table the range came from; other sources are named in the row's 'sources' column
                tile = Tile(row.key, row.group, row.title, light, c["value_text"], row.what_it_is, [c["sentence"]], head, text, do, row.book, src + row.sources,
                            shown, row.priority, row.order, bar_html(c), [], (row.text["low"]["headline"] if low else ""), row.hash)
        elif row.rule == "composite":
            members = [comps[m] for m in row.members if m in comps and m not in exclude]
            if members:
                lights = [engine_light(m) for m in members]
                lit = [x for x in lights if x != GREY]                  # the worst of the results that have a light; grey only if none has one
                light = max(lit, key=lambda x: SEVERITY[x]) if lit else GREY
                head, text, do = _pick(row, light)
                parts = [{"label": m.get("patient_label") or m["label"], "value_text": m["value_text"], "light": lt, "words": m.get("status_text") or _words(S, lt)}
                         for m, lt in zip(members, lights)]
                src = [m["source"] for m in members if m.get("source")]
                tile = Tile(row.key, row.group, row.title, light, "", row.what_it_is, [], head, text, do, row.book, src + row.sources, shown, row.priority, row.order, "", parts, "", row.hash)
        elif row.rule == "zone":
            got = zone_reading(row, tests)
            if got:
                light, shown_text, zone = got
                head, text, do = _pick(row, light)
                facts = [row.facts.replace("{value}", shown_text)]
                if zone in ("green", "orange"):
                    facts.append(f"On the Tanita's chart it sits in the {zone} area, "
                                 + ("at or above the line expected for your age." if zone == "green" else "below the line expected for your age."))
                elif zone in ZONE_LIGHTS:
                    facts.append(f"The Tanita rates this as {zone} for your age, sex and height.")
                tile = Tile(row.key, row.group, row.title, light, shown_text, row.what_it_is, facts, head, text, do, row.book, list(row.sources), shown,
                            row.priority, row.order, hash=row.hash)
        elif row.rule == "parts":
            got = parts_reading(row, tests, S)
            if got:
                light, parts, extra = got
                head, text, do = _pick(row, light)
                tile = Tile(row.key, row.group, row.title, light, "", row.what_it_is, ([row.facts] if row.facts else []) + extra, head, text, do, row.book,
                            list(row.sources), shown, row.priority, row.order, "", parts, "", row.hash)
        elif row.rule == "spiro":
            got = spirometry_reading(row, tests)
            if got:
                light, facts, parts = got
                head, text, do = _pick(row, light)
                tile = Tile(row.key, row.group, row.title, light, "", row.what_it_is, facts, head, text, do, row.book, list(row.sources), shown,
                            row.priority, row.order, "", parts, "", row.hash)
        elif row.rule == "fp_balance":
            got = force_plate_balance(row, tests)
            if got:
                light, facts, parts = got
                head, text, do = _pick(row, light)
                tile = Tile(row.key, row.group, row.title, light, "", row.what_it_is, facts, head, text, do, row.book, list(row.sources), shown,
                            row.priority, row.order, "", parts, "", row.hash)
        elif row.rule == "limbs":
            got = limb_balance(row, tests, S)
            if got:
                light, facts, parts = got
                head, text, do = _pick(row, light)
                tile = Tile(row.key, row.group, row.title, light, "", row.what_it_is, facts, head, text, do, row.book, list(row.sources), shown, row.priority, row.order,
                            "", parts, "", row.hash)
        else:
            got = read_value(row.value_from, tests) if row.value_from else None
            if got:
                shown_text, number = got
                light = GREY if row.rule == "info" else range_light(number, row)
                head, text, do = _pick(row, light)
                tile = Tile(row.key, row.group, row.title, light, shown_text, row.what_it_is, [row.facts.replace("{value}", shown_text)], head, text, do, row.book,
                            list(row.sources), shown, row.priority, row.order, hash=row.hash)
        if tile is None:
            continue
        if tile.approved or include_drafts:
            tiles.append(tile)
        else:
            hidden.append({"key": row.key, "title": row.title, "reason": {"error": "an error in its row", "incomplete": "its wording is not finished", "changed": "its wording has changed since it was approved"}.get(status, "not approved yet")})
    return tiles, hidden


def uncovered(tests: list) -> list:
    """The assessments entered that have no dashboard tiles yet (their values are saved, but the participant's page does not show them)."""
    return sorted({t.get("type", "") for t in tests or []} - COVERED_ASSESSMENTS - {""})


# ------------------------------------------------------------------------------------------------------------------------ the summary
def summarize(tiles: list, S: dict) -> dict:
    lit = [t for t in tiles if t.light in (GREEN, AMBER, RED)]
    n, g = len(lit), sum(1 for t in lit if t.light == GREEN)
    a, r = sum(1 for t in lit if t.light == AMBER), sum(1 for t in lit if t.light == RED)
    if not n:
        headline = ""
    elif a == 0 and r == 0:
        headline = S["all_green"].format(n=n) if n > 1 else S["all_green_one"]
    else:
        lead = fmt_pair(S["no_green"], n, green=g, n=n) if g == 0 else fmt_pair(S["mixed_lead"], g, green=g, n=n)
        headline = " ".join([lead] + ([fmt_pair(S["amber_clause"], a)] if a else []) + ([fmt_pair(S["red_clause"], r)] if r else []))
    todo = sorted([t for t in lit if t.light != GREEN], key=lambda t: (-SEVERITY[t.light], t.priority, t.order))[:3]
    return {"headline": headline, "green": g, "amber": a, "red": r, "n": n,
            "priorities": [{"key": t.key, "title": t.title, "light": t.light, "do": t.do} for t in todo]}


# ------------------------------------------------------------------------------------------------------------------------ the page
CSS = """
:root{--primary:#0f382b;--secondary:#2b6a52;--bg:#f8fafc;--card:#ffffff;--text:#1e293b;--muted:#64748b;--border:#e2e8f0;
--green:#15803d;--amber:#b45309;--red:#b91c1c;--grey:#475569;--green-bg:#f0fdf4;--amber-bg:#fffbeb;--red-bg:#fef2f2;--grey-bg:#f1f5f9;}
*{box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;background:var(--bg);color:var(--text);line-height:1.6;margin:0;padding:16px;}
.report{max-width:950px;margin:0 auto;background:var(--card);border-radius:12px;box-shadow:0 4px 20px rgba(0,0,0,.05);overflow:hidden;border:1px solid var(--border);}
.header{background:var(--primary);color:#fff;padding:26px;text-align:center}
.header h1{margin:0 0 4px;font-size:24px;color:#fff}.header p{margin:0;color:#94a3b8;font-size:13px;text-transform:uppercase;letter-spacing:1px}
.content{padding:24px}
.meta{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;background:#f1f5f9;padding:16px;border-radius:8px;margin-bottom:22px}
.meta label{display:block;font-size:11px;color:var(--muted);text-transform:uppercase;font-weight:600}.meta span{font-size:15px;font-weight:700;color:var(--primary)}
.draft-banner{background:#fee2e2;border:2px solid var(--red);color:#7f1d1d;border-radius:8px;padding:12px 14px;margin-bottom:18px;font-weight:600}
.note{margin:0 0 20px;padding:16px 18px;border-radius:12px;background:#fff;border:1px solid var(--border);border-left:5px solid var(--primary)}
.note h3{margin:0 0 8px;color:var(--primary)}.note p{margin:0 0 9px}.note .by{font-weight:700;color:var(--primary);margin-top:10px}
.summary{background:linear-gradient(to bottom right,#f0fdf4,#ecfdf5);border:2px solid #10b981;border-radius:12px;padding:20px;margin-bottom:20px}
.summary h2{margin:0 0 10px;color:var(--primary);font-size:20px}.summary .headline{font-size:19px;font-weight:700;color:var(--primary);margin:0 0 12px;line-height:1.45}
.pills{display:flex;flex-wrap:wrap;gap:8px}.pill{display:inline-flex;align-items:center;gap:6px;padding:5px 12px;border-radius:999px;font-weight:700;font-size:14px;color:#fff}
.pill.green{background:var(--green)}.pill.amber{background:var(--amber)}.pill.red{background:var(--red)}.pill.info{background:var(--grey)}
.priorities{background:#fff;border:1px solid var(--border);border-radius:12px;padding:18px 20px;margin-bottom:24px}
.priorities h2{margin:0 0 4px;color:var(--primary);font-size:19px}.priorities .intro{margin:0 0 10px;color:var(--muted);font-size:14px}
.priorities ol{margin:0;padding-left:0;list-style:none}.priorities li{display:flex;gap:12px;align-items:flex-start;padding:10px 0;border-top:1px solid var(--border)}
.priorities li b{color:var(--primary)}
.group h2{color:var(--primary);font-size:19px;margin:26px 0 10px;border-bottom:3px solid var(--primary);padding-bottom:4px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px;align-items:start}
.tile{border:1px solid var(--border);border-left:6px solid var(--grey);border-radius:10px;background:#fff;overflow:hidden}
.tile.green{border-left-color:var(--green)}.tile.amber{border-left-color:var(--amber)}.tile.red{border-left-color:var(--red)}
.tile summary{list-style:none;cursor:pointer;display:flex;gap:12px;align-items:center;padding:12px 14px;flex-wrap:wrap}
.tile summary::-webkit-details-marker{display:none}
.tile summary::after{content:"\\25BE";margin-left:auto;color:var(--muted);font-size:14px}.tile[open] summary::after{content:"\\25B4"}
.dot{flex:none;display:inline-flex;width:34px;height:34px;border-radius:50%;align-items:center;justify-content:center;color:#fff;font-weight:800;font-size:17px;background:var(--grey)}
.dot.small{width:26px;height:26px;font-size:14px}.dot.green{background:var(--green)}.dot.amber{background:var(--amber)}.dot.red{background:var(--red)}
.main{flex:1;min-width:150px}.title{display:block;font-weight:700;color:var(--primary);font-size:16px}.what{display:block;color:var(--muted);font-size:13px;line-height:1.4}
.side{display:flex;flex-direction:column;align-items:flex-end;gap:3px}.val{font-weight:800;font-size:17px;color:var(--text)}
.chip{display:inline-block;padding:2px 10px;border-radius:12px;font-size:12.5px;font-weight:700}
.chip.green{background:var(--green-bg);color:#166534}.chip.amber{background:var(--amber-bg);color:#92400e}.chip.red{background:var(--red-bg);color:#991b1b}.chip.info{background:var(--grey-bg);color:#334155}
.body{padding:2px 16px 14px 16px;border-top:1px solid var(--border)}.body p{margin:8px 0}
.facts{color:var(--text)}.headline{font-weight:800;margin-top:10px}.headline.green{color:var(--green)}.headline.amber{color:var(--amber)}.headline.red{color:var(--red)}.headline.info{color:var(--grey)}
.parts{list-style:none;margin:8px 0;padding:0}.parts li{display:flex;gap:8px;align-items:center;margin:5px 0;font-size:14.5px}
.book{color:var(--muted);font-size:13px}.draft-badge{display:inline-block;background:var(--red);color:#fff;font-size:11px;font-weight:800;padding:2px 8px;border-radius:6px;margin-top:8px}
.how{margin-top:28px;padding:16px 18px;background:#f8fafc;border:1px solid var(--border);border-radius:8px;font-size:14px;color:#334155}.how h2{margin:0 0 8px;font-size:17px;color:var(--primary)}.how p{margin:0 0 8px}
.sources{margin-top:18px;font-size:13px;color:#334155}.sources h2{font-size:16px;color:var(--primary)}.sources ul{padding-left:20px}.sources li{margin-bottom:8px}
.footer{text-align:center;padding:18px;background:#f1f5f9;font-size:12px;color:var(--muted);border-top:1px solid var(--border)}
.legend{display:flex;flex-wrap:wrap;gap:14px;font-size:13px;color:var(--muted);margin:8px 0 0}
.links{background:#f8fafc;border:1px solid var(--border);border-left:5px solid var(--secondary);border-radius:12px;padding:18px 20px;margin-bottom:24px}
.links h2{margin:0 0 4px;color:var(--primary);font-size:19px}.links .intro{margin:0 0 12px;color:var(--muted);font-size:14px}
.link-group{background:#fff;border:1px solid var(--border);border-radius:10px;padding:10px 14px;margin-bottom:10px}
.link-group h3{margin:0 0 6px;font-size:16px;color:var(--primary)}.link-group ul{margin:0;padding-left:20px}.link-group li{margin:3px 0}
.interp{margin-top:12px;padding:12px 14px;background:#fff;border:1px dashed var(--secondary);border-radius:10px}
.interp h3{margin:0 0 6px;color:var(--primary);font-size:16px}.interp p{margin:0 0 8px}.interp .by{font-weight:700;color:var(--primary)}
"""


def _dot(light, small=False):
    return f'<span class="dot {light}{" small" if small else ""}" aria-hidden="true">{SYMBOL[light]}</span>'


def _tile_html(t: Tile, S: dict, draft_marker: bool) -> str:
    words = t.words or _words(S, t.light)
    is_open = " open" if t.light in (AMBER, RED) else ""
    facts = "".join(f'<p class="facts">{esc(f)}</p>' for f in t.facts)
    parts = ""
    if t.parts:
        parts = '<ul class="parts">' + "".join(f'<li>{_dot(p["light"], True)}<span><b>{esc(p["label"])}</b>: {esc(p["value_text"])} <span class="chip {p["light"]}">{esc(p["words"])}</span></span></li>' for p in t.parts) + "</ul>"
    head = f'<p class="headline {t.light}">{esc(t.headline)}</p>' if t.headline else ""
    meaning = f'<p><b>What this means:</b> {esc(t.text)}</p>' if t.text else ""
    todo = f'<p><b>What you can do:</b> {esc(t.do)}</p>' if t.do else ""
    book = f'<p class="book">{esc(S.get("book_label", ""))} {esc(t.book)}</p>' if t.book else ""
    badge = '<span class="draft-badge">DRAFT: not shown to the participant yet</span>' if draft_marker and not t.approved else ""
    value = f'<span class="val">{esc(t.value_text)}</span>' if t.value_text else ""
    return (f'<details class="tile {t.light}"{is_open}><summary>{_dot(t.light)}<span class="main"><span class="title">{esc(t.title)}</span>'
            f'<span class="what">{esc(t.what_it_is)}</span></span><span class="side">{value}<span class="chip {t.light}">{esc(words)}</span></span></summary>'
            f'<div class="body">{badge}{facts}{parts}{t.bar}{head}{meaning}{todo}{book}</div></details>')


def _note_html(note: str, by: str, S: dict) -> str:
    paras = [p.strip() for p in str(note or "").replace("\r\n", "\n").split("\n\n") if p.strip()]
    if not paras:
        return ""
    body = "".join("<p>" + "<br>".join(esc(line) for line in p.split("\n")) + "</p>" for p in paras)
    return f'<div class="note"><h3>{esc(S.get("note_heading", ""))}</h3>{body}<p class="by">{esc("- " + (str(by).strip() or "Your clinician"))}</p></div>'


LINKS_HEADING = "Results that point the same way"
LINKS_INTRO = "Some of your results from different tests point in the same direction. They are shown together so you and your clinician can look at them side by side. On their own they do not explain why."
INTERPRETATION_HEADING = "Your clinician's interpretation"


def _links_html(links: list, interpretation: str, by: str, S: dict) -> str:
    """The linked findings and the clinician's interpretation of them. Empty if there is neither."""
    paras = [p.strip() for p in str(interpretation or "").replace("\r\n", "\n").split("\n\n") if p.strip()]
    if not links and not paras:
        return ""
    groups = "".join(f'<div class="link-group"><h3>{esc(g["title"])}</h3><ul>' + "".join(f"<li>{esc(i)}</li>" for i in g["items"]) + "</ul></div>"
                     for g in links or [])
    note = ""
    if paras:
        body = "".join("<p>" + "<br>".join(esc(line) for line in p.split("\n")) + "</p>" for p in paras)
        note = f'<div class="interp"><h3>{esc(S.get("interpretation_heading") or INTERPRETATION_HEADING)}</h3>{body}<p class="by">{esc("- " + (str(by).strip() or "Your clinician"))}</p></div>'
    intro = f'<p class="intro">{esc(S.get("links_intro") or LINKS_INTRO)}</p>' if links else ""
    return f'<div class="links"><h2>{esc(S.get("links_heading") or LINKS_HEADING)}</h2>{intro}{groups}{note}</div>'


def _sources_html(tiles: list, S: dict) -> str:
    used = []
    for t in tiles:
        for sid in t.sources:
            if sid in data.SOURCES and sid not in used:
                used.append(sid)
    if not used:
        return ""
    items = []
    for sid in used:
        s = data.SOURCES[sid]
        link = f' <a href="{esc(s["url"])}" target="_blank" rel="noopener noreferrer">{esc(s["url"])}</a>' if s["url"] else ""
        items.append(f'<li><b>{esc(s["short"])}.</b> {esc(s["citation"])}{link}<br><span style="color:#64748b">Who was studied: {esc(s["population"])} {esc(s["note"])}</span></li>')
    return f'<div class="sources"><h2>{esc(S.get("sources_heading", ""))}</h2><ul>{"".join(items)}</ul></div>'


def render_report(meta: dict, tiles: list, library: Library, note: str = "", note_by: str = "", hidden: list | None = None, preview: bool = False,
                  files_shared: bool = False, links: list | None = None, interpretation: str = "", interpretation_by: str = "") -> str:
    """The whole page, as one self-contained HTML document. meta: participant_name, age_gender, assessment_date, body_mass_height."""
    S = library.summary
    summary = summarize(tiles, S)
    drafts = [t for t in tiles if not t.approved]
    banner = ""
    if preview and (drafts or hidden):
        names = ", ".join(sorted({t.title for t in drafts} | {h["title"] for h in (hidden or [])}))
        banner = (f'<div class="draft-banner">PREVIEW ONLY. These results are drafts and will not be shown to the participant until they are approved '
                  f'(approve them in the dashboard section of the clinician screen): {esc(names)}.</div>' if drafts else "")
    pills = "".join(f'<span class="pill {lt}">{_dot(lt, True)} {summary[lt]} {esc(_words(S, lt))}</span>' for lt in (GREEN, AMBER, RED) if summary[lt])
    head = (f'<div class="summary"><h2>{esc(S.get("page_title", ""))}</h2><p class="headline">{esc(summary["headline"])}</p><div class="pills">{pills}</div>'
            f'<p class="legend">' + "".join(f'<span>{_dot(lt, True)} {esc(_words(S, lt))}</span>' for lt in (GREEN, AMBER, RED, GREY)) + f'</p></div>') if summary["n"] else ""
    if summary["n"]:
        if summary["priorities"]:
            items = "".join(f'<li>{_dot(p["light"], True)}<span><b>{esc(p["title"])}</b>: {esc(p["do"])}</span></li>' for p in summary["priorities"])
            prio = f'<div class="priorities"><h2>{esc(S["priorities_heading"])}</h2><p class="intro">{esc(S["priorities_intro"])}</p><ol>{items}</ol></div>'
        else:
            prio = f'<div class="priorities"><p style="margin:0;font-weight:700;color:#0f382b">{esc(S["no_priorities"])}</p></div>'
    else:
        prio = ""
    groups: dict = {}
    for t in sorted(tiles, key=lambda x: (x.order, x.key)):
        groups.setdefault(t.group, []).append(t)
    sections = "".join(f'<div class="group"><h2>{esc(g)}</h2><div class="grid">{"".join(_tile_html(t, S, preview) for t in ts)}</div></div>' for g, ts in groups.items())
    tap = f'<p class="book" style="margin-top:14px">{esc(S.get("tap_hint", ""))}</p>' if tiles else ""
    if tiles and files_shared:
        tap += f'<p class="book" style="margin-top:4px">&#128196; {esc(S.get("reports_hint") or DEFAULT_REPORTS_HINT)}</p>'
    how = (f'<div class="how"><h2>{esc(S["how_to_read_heading"])}</h2>' + "".join(f'<p>{esc(S[k])}</p>' for k in ("how_to_read_1", "how_to_read_2", "how_to_read_3")) + "</div>") if tiles else ""
    version = f'Reference data version {esc(NORMS_VERSION)} &middot; Wording version {esc(library.version)}'
    return (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">'
            f'<title>Chudleigh Health Hub - {esc(S.get("page_title", "Your results"))}</title><style>{CSS}</style></head><body><div class="report">'
            f'<div class="header"><h1>Chudleigh Health Hub</h1><p>Health Autonomy &bull; Your longevity results</p></div><div class="content">'
            f'<div class="meta"><div><label>Participant</label><span>{esc(meta.get("participant_name", ""))}</span></div>'
            f'<div><label>Age / sex</label><span>{esc(meta.get("age_gender", ""))}</span></div>'
            f'<div><label>Assessment date</label><span>{esc(meta.get("assessment_date", ""))}</span></div>'
            f'<div><label>Body mass / height</label><span>{esc(meta.get("body_mass_height", ""))}</span></div></div>'
            f'{banner}{_note_html(note, note_by, S)}{head}{prio}{_links_html(links, interpretation, interpretation_by or note_by, S)}{tap}{sections}{how}'
            f'{_sources_html(tiles, S)}</div>'
            f'<div class="footer">{esc(S.get("disclosure", ""))}<br>{version}</div></div></body></html>')
