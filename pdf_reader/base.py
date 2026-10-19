"""Shared pieces for reading device reports (PDF) from their text layer, without AI.

Nothing here talks to the internet. A reader returns a ReadResult: the values it found, the automatic checks it ran on
them, and notes about anything it could not read. It never reads or keeps a person's name.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

MAX_PDF_BYTES = 20 * 1024 * 1024
MAX_PAGES = 10
_UNITS = {"kg", "%", "°", "cm", "years", "mm", "ms", "s", "bpm", "l", "mmhg"}
_NUMBER_WORD = re.compile(r"-?\d+(?:\.\d+)?")


@dataclass
class Value:
    text: str  # tidied, as printed: "75.8 kg"
    number: float | None
    unit: str
    source: str = "text"  # "text" = read from the PDF's text layer; "ocr" = read from a picture by text recognition; "calculated" = worked out by code

    @property
    def display(self) -> str:
        """How to show it: '75.8 kg', '18.3%', '6.0°'."""
        return self.text.replace(" %", "%").replace(" °", "°")


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    severity: str = "error"  # "error": a sum that must add up. "note": worth knowing, not a sign of a misread


@dataclass
class ReadResult:
    device: str = "unknown"
    device_label: str = ""
    status: str = "error"  # ok | check | unknown_device | no_text | error
    values: dict = field(default_factory=dict)
    checks: list = field(default_factory=list)
    printed_ranges: list = field(default_factory=list)  # reference text the report itself prints
    not_printed: list = field(default_factory=list)  # things people ask for that this report does not print
    notes: list = field(default_factory=list)
    statements: list = field(default_factory=list)  # the device's own wording, e.g. a machine interpretation: [{"text","kind","caution"}]
    used_ocr: bool = False
    has_text_layer: bool = False
    text_lines: list = field(default_factory=list)  # only when asked for; NOT cleaned of names
    app_assessment: str = ""  # for readers that cover several of the app's assessments (VALD Hub): the one this report belongs to

    def to_dict(self) -> dict:
        return {
            "device": self.device, "device_label": self.device_label, "status": self.status,
            "values": {k: {"text": v.text, "number": v.number, "unit": v.unit, "source": v.source} for k, v in self.values.items()},
            "checks": [{"name": c.name, "ok": c.ok, "detail": c.detail, "severity": c.severity} for c in self.checks],
            "statements": list(self.statements), "used_ocr": self.used_ocr,
            "printed_ranges": list(self.printed_ranges), "not_printed": list(self.not_printed), "notes": list(self.notes),
            "has_text_layer": self.has_text_layer, "text_lines": list(self.text_lines),
        }

    def number(self, key: str):
        v = self.values.get(key)
        return v.number if v else None


def make_value(raw: str, unit: str | None = None, source: str = "text") -> Value | None:
    """Turn a printed token such as '75.8kg', '18.3%' or '6.0°' into a Value. Returns None if it has no number."""
    raw = (raw or "").strip()
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)\s*([A-Za-z%°/]*)", raw)
    if not m:
        return None
    number, printed_unit = float(m.group(1)), (m.group(2) or unit or "")
    text = f"{m.group(1)} {printed_unit}".strip()
    return Value(text=text, number=number, unit=printed_unit, source=source)


def load_pages(data: bytes):
    """Return a list of pages; each page is a list of words {'text','x0','x1','top'}. Raises ValueError for unusable files."""
    if not data or len(data) > MAX_PDF_BYTES:
        raise ValueError("The PDF is empty or too large")
    try:
        import pdfplumber
    except ImportError as e:
        raise ValueError("The PDF reading software (pdfplumber) is not installed on this server") from e
    try:
        pages = []
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            if len(pdf.pages) > MAX_PAGES:
                raise ValueError(f"The PDF has more than {MAX_PAGES} pages")
            for page in pdf.pages:
                words = page.extract_words(x_tolerance=3, y_tolerance=3)
                pages.append(merge_units([{"text": w["text"], "x0": w["x0"], "x1": w["x1"], "top": w["top"]} for w in words]))
        return pages
    except ValueError:
        raise
    except Exception as e:  # damaged or encrypted files, odd encodings
        raise ValueError("The PDF could not be opened") from e


def merge_units(words: list) -> list:
    """Join a number to a unit printed just after it ('75.8' + 'kg'), so '75.8kg' reads the same however the PDF spaced it."""
    out, skip = [], set()
    ordered = sorted(range(len(words)), key=lambda i: (round(words[i]["top"] / 3), words[i]["x0"]))
    for pos, i in enumerate(ordered):
        if i in skip:
            continue
        w = dict(words[i])
        if _NUMBER_WORD.fullmatch(w["text"]) and pos + 1 < len(ordered):
            n = words[ordered[pos + 1]]
            if n["text"].lower() in _UNITS and 0 <= n["x0"] - w["x1"] <= 8 and abs(n["top"] - w["top"]) <= 3:
                w["raw"] = f"{w['text']} {n['text']}" if n["x0"] - w["x1"] > 1 else w["text"] + n["text"]  # keep the original spacing
                w["text"], w["x1"] = w["text"] + n["text"], n["x1"]
                skip.add(ordered[pos + 1])
        out.append(w)
    return out


class Page:
    """Helpers for finding a label on a page and the value printed to its right or below it."""

    def __init__(self, words: list):
        self.words = sorted(words, key=lambda w: (round(w["top"] / 3), w["x0"]))

    def in_region(self, region):
        x0, x1, t0, t1 = region
        return [w for w in self.words if x0 <= w["x0"] <= x1 and t0 <= w["top"] <= t1]

    def label(self, text: str, region):
        """Find a label, whether the PDF printed it as one word ('Musclemass') or several ('Muscle', 'mass')."""
        target = text.replace(" ", "").lower()
        words = self.in_region(region)
        for i, w in enumerate(words):
            joined, last = "", w
            for n in words[i:i + 4]:
                if abs(n["top"] - w["top"]) > 3:
                    break
                joined, last = joined + n["text"].lower(), n
                if joined == target:
                    return {"x0": w["x0"], "x1": last["x1"], "top": w["top"]}
                if not target.startswith(joined):
                    break
        return None

    def right_of(self, anchor, pattern: str, dy: float = 8, dx: float = 110):
        if not anchor:
            return None
        found = [w for w in self.words if 0 <= w["x0"] - anchor["x1"] <= dx and abs(w["top"] - anchor["top"]) <= dy and re.fullmatch(pattern, w["text"])]
        return min(found, key=lambda w: w["x0"])["text"] if found else None

    def below(self, anchor, pattern: str, dy: float = 26, dx: float = 14):
        if not anchor:
            return None
        found = [w for w in self.words if abs(w["x0"] - anchor["x0"]) <= dx and 2 <= w["top"] - anchor["top"] <= dy and re.fullmatch(pattern, w["text"])]
        return min(found, key=lambda w: w["top"])["text"] if found else None


    def text_below(self, anchor, dy: float = 16, dx_left: float = 30, span: float = 120):
        """The first line of text under a label, joined without spaces (so '8.3', 'kg', '•', '19.0', '%' reads as '8.3kg•19.0%')."""
        if not anchor:
            return None
        under = [w for w in self.words if -dx_left <= w["x0"] - anchor["x0"] <= span and 2 <= w["top"] - anchor["top"] <= dy]
        if not under:
            return None
        first_line = min(w["top"] for w in under)
        return "".join(w["text"] for w in sorted((w for w in under if abs(w["top"] - first_line) <= 3), key=lambda w: w["x0"]))


def hms_to_seconds(text: str):
    m = re.fullmatch(r"(\d{1,2}):(\d{2}):(\d{2})", (text or "").strip())
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3)) if m else None


def seconds_to_hms(sec: int) -> str:
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def status_from(res: "ReadResult") -> str:
    """ok if everything was read and no sum that must add up failed. Advisory notes never change the status."""
    unread = [n for n in res.notes if n.startswith("Could not read")]
    failed = [c for c in res.checks if not c.ok and c.severity == "error"]
    return "ok" if not unread and not failed else "check"


def close(a, b, tol: float) -> bool:
    return a is not None and b is not None and abs(a - b) <= tol


def line_text(words: list) -> list:
    """All text on a page grouped into lines, top to bottom. For unknown devices only."""
    lines: dict = {}
    for w in words:
        lines.setdefault(round(w["top"] / 4), []).append(w)
    return [" ".join(x.get("raw", x["text"]) for x in sorted(ws, key=lambda x: x["x0"])) for _, ws in sorted(lines.items())]
