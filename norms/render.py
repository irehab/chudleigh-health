"""Turns comparisons into the participant's two pages (HTML), and a short table for the clinician.

    render_glance_html(...)   "Your results at a glance": the clinician's note, one sentence, and a grouped list with traffic lights.
    render_section_html(...)  "Your results in detail": a card for each result, with a bar showing where you sit, then the limits and sources.

Every piece of text is escaped. The sentences come from fixed templates in engine.py, so nothing on either page is written by an AI.
Colour is never the only signal: every result also says in words where it sits, and has a symbol.
"""
from __future__ import annotations

import html

from . import data
from .engine import (ABOVE, BELOW, CLOSING, ALL_GOOD, DISCUSS, INFO, NO_REFERENCE, NORMS_VERSION, REPORTED, WATCH, WELL_ABOVE, WITHIN, WORK_ON,
                     for_patient, glance_groups, glance_verdict)

esc = lambda s: html.escape("" if s is None else str(s), quote=True)

_WORDS = {WITHIN: "Within the usual range", BELOW: "Lower than the usual range", ABOVE: "Higher than the usual range",
          WELL_ABOVE: "Well above the usual range", REPORTED: "As reported by the device", NO_REFERENCE: "Not compared"}
# soft colours, and every chip sets its own text colour so it reads on a light or a dark page
_CHIP = {WITHIN: ("#dcfce7", "#166534"), BELOW: ("#e0f2fe", "#075985"), ABOVE: ("#fef3c7", "#92400e"), WELL_ABOVE: ("#fef3c7", "#92400e"),
         REPORTED: ("#e2e8f0", "#334155"), NO_REFERENCE: ("#e2e8f0", "#334155")}
_HEAD = {"doing_well": "#166534", "watch": "#92400e", "work_on": "#92400e", "discuss": "#075985", "info": "#334155"}
_SYMBOL = {WORK_ON: "\u25b2", DISCUSS: "\u25cf", WATCH: "\u25c6", INFO: "i", "doing_well": "\u2713"}   # triangle, dot, diamond, i, tick

INTRO = [
    "This page compares some of your results with published data for people of your age and sex.",
    "It explains what each result means for you.",
    "It shows where you sit compared with groups of healthy people.",
    "It does not diagnose anything, and a result outside a range is not a sign that something is wrong.",
    "Your clinician will talk through what matters for you.",
]
LIMITS = [
    "The people studied were mostly white and lived elsewhere, so they may not look like you.",
    "People who are fitter or leaner than average often sit outside the usual range for good reasons.",
    "Devices differ slightly, so yours may not match the equipment used in the studies.",
    "A single measurement is a snapshot. It can change from day to day.",
    "Where we link a result to a health condition, that is a link seen in large groups of people. It is not a prediction for you.",
]


def _label(c) -> str:
    return c.get("patient_label") or c["label"]   # a comparison saved by an earlier version has no plain name


def _chip(status, text=""):
    bg, fg = _CHIP[status]
    return f'<span style="display:inline-block;padding:3px 10px;border-radius:12px;background:{bg};color:{fg};font-size:13px;font-weight:600;">{esc(text or _WORDS[status])}</span>'


def note_to_html(text: str) -> str:
    """A clinician's note as safe HTML: a blank line starts a new paragraph, a single new line is a line break, and everything is escaped."""
    paras = [p.strip() for p in str(text or "").replace("\r\n", "\n").split("\n\n") if p.strip()]
    return "".join(f'<p style="margin:0 0 10px;color:#1e293b;line-height:1.7;">{"<br>".join(esc(line) for line in p.split(chr(10)))}</p>' for p in paras)


def bar_html(c) -> str:
    """A simple bar: the usual range in green, lower in blue, higher in amber, and a marker for where the result sits. '' if there is no range."""
    lo, hi, v = c.get("low"), c.get("high"), c.get("value")
    if c["status"] in (REPORTED, NO_REFERENCE) or lo is None or hi is None or v is None or hi <= lo:
        return ""
    pad = 0.6 * (hi - lo)
    axis_min = lo - pad
    axis_max = hi if c["key"] == "spo2_avg" else hi + pad      # an oxygen level cannot go above 100
    width = axis_max - axis_min
    a = (lo - axis_min) / width * 100
    b = (hi - axis_min) / width * 100
    p = min(98.0, max(2.0, (v - axis_min) / width * 100))
    say = f"Your result of {c['value_text']} is {_WORDS[c['status']].lower()}. The usual range is {c['range_text']}."
    return (f'<div role="img" aria-label="{esc(say)}" style="margin:12px 4px 6px;">'
            '<div style="position:relative;height:16px;">'
            '<div style="display:flex;height:14px;border-radius:7px;overflow:hidden;border:1px solid #cbd5e1;">'
            f'<div style="width:{a:.1f}%;background:#bae6fd;"></div>'
            f'<div style="width:{b - a:.1f}%;background:#86efac;"></div>'
            f'<div style="width:{100 - b:.1f}%;background:#fcd34d;"></div></div>'
            f'<div style="position:absolute;top:-4px;left:{p:.1f}%;width:5px;height:22px;margin-left:-2px;background:#0f382b;border-radius:3px;border:1px solid #ffffff;"></div></div>'
            '<div style="display:flex;justify-content:space-between;font-size:12px;color:#64748b;margin-top:8px;">'
            f'<span>Lower</span><span>Usual range: {esc(c["range_text"])}</span><span>Higher</span></div></div>')


def _card(c) -> str:
    colour = _HEAD.get(c.get("theme", ""), "#334155")
    parts = [
        '<div style="border:1px solid #e2e8f0;border-radius:10px;padding:14px 16px;margin-bottom:14px;background:#ffffff;">',
        f'<div style="margin-bottom:4px;"><b style="color:#0f382b;font-size:16px;">{esc(_label(c))}</b> &nbsp;{_chip(c["status"], c.get("status_text"))}</div>',
    ]
    if c.get("measures"):
        parts.append(f'<p style="margin:2px 0 8px;color:#64748b;font-size:13px;line-height:1.5;">{esc(c["measures"])}</p>')
    if c.get("headline"):
        parts.append(f'<p style="margin:6px 0;font-weight:700;color:{colour};font-size:15px;">{esc(c["headline"])}</p>')
    parts.append(bar_html(c))
    parts.append(f'<p style="margin:6px 0;color:#1e293b;line-height:1.6;">{esc(c["sentence"])}</p>')
    if c.get("meaning"):
        parts.append(f'<p style="margin:6px 0;color:#1e293b;line-height:1.6;"><b>What this means:</b> {esc(c["meaning"])}</p>')
    if c.get("detail"):
        parts.append(f'<p style="margin:6px 0;color:#475569;font-size:13px;line-height:1.5;"><i>{esc(c["detail"])}</i></p>')
    parts.append("</div>")
    return "".join(parts)


def render_glance_html(comparisons: list, note: str = "", note_by: str = "") -> str:
    """'Your results at a glance'. Returns '' when nothing could be compared."""
    comps = for_patient(comparisons)
    verdict = glance_verdict(comps)
    if not verdict:
        return ""
    parts = []
    if str(note or "").strip():
        parts.append('<div style="margin:0 0 22px;padding:18px 20px;border-radius:12px;background:#ffffff;border:1px solid #e2e8f0;border-left:5px solid #0f382b;">'
                     '<h3 style="color:#0f382b;margin:0 0 10px;">A note from your clinician</h3>'
                     f'{note_to_html(note)}'
                     f'<p style="margin:12px 0 0;color:#0f382b;font-weight:700;">{esc("- " + (str(note_by).strip() or "Your clinician"))}</p></div>')
    parts.append(f'<p style="font-size:19px;line-height:1.5;color:#0f382b;font-weight:700;margin:0 0 20px;">{esc(verdict)}</p>')
    groups = glance_groups(comps)
    for g in groups:
        colour = _HEAD.get(g["theme"], "#334155")
        rows = "".join(
            f'<div style="padding:8px 0;border-top:1px solid #e2e8f0;display:flex;flex-wrap:wrap;gap:8px;align-items:center;justify-content:space-between;">'
            f'<span style="color:#1e293b;font-size:15px;"><b>{esc(_label(c))}</b>: {esc(c["value_text"])}</span>{_chip(c["status"], c.get("status_text"))}</div>'
            for c in g["items"])
        parts.append(f'<div style="margin:0 0 16px;padding:14px 16px;border-radius:10px;background:#ffffff;border:1px solid #e2e8f0;border-left:5px solid {colour};">'
                     f'<h3 style="margin:0 0 4px;color:{colour};font-size:17px;"><span aria-hidden="true">{_SYMBOL[g["theme"]]}</span> {esc(g["heading"])}</h3>'
                     f'<p style="margin:0 0 8px;color:#475569;font-size:14px;line-height:1.6;">{esc(g["text"])}</p>{rows}</div>')
    if not any(g["theme"] in (WORK_ON, DISCUSS) for g in groups):
        parts.append(f'<p style="color:#1e293b;font-size:16px;line-height:1.6;"><b>{esc(ALL_GOOD)}</b></p>')
    parts.append(f'<p style="color:#475569;font-size:14px;line-height:1.6;">{esc(CLOSING)}</p>')
    parts.append('<p style="color:#0f382b;font-size:15px;"><b>Want to know what each result means?</b> Open <b>Your results in detail</b> above.</p>')
    return "".join(parts)


def render_section_html(comparisons: list, age=None, sex=None, note: str = "", note_by: str = "") -> str:
    """'Your results in detail'. Returns '' when there is nothing to show.

    note and note_by are accepted and ignored: the clinician's note now goes on 'at a glance' (render_glance_html). They are still accepted
    so that an older app.py, during an update, keeps working with this file."""
    comps = for_patient(comparisons)
    if not comps:
        return ""
    compared = [c for c in comps if c["status"] != NO_REFERENCE]
    skipped = [c for c in comps if c["status"] == NO_REFERENCE]
    h3 = '<h3 style="color:#0f382b;margin-top:26px;">'
    parts = [f'<p style="font-size:16px;color:#1e293b;line-height:1.6;">{esc(" ".join(INTRO))}</p>']
    if compared:
        parts.append(f'{h3}Your results</h3>' + "".join(_card(c) for c in compared))
    if skipped:
        items = "".join(f'<li style="color:#334155;margin-bottom:4px;">{esc(_label(c))} ({esc(c["value_text"])}): {esc(c["reason"])}</li>' for c in skipped)
        parts.append(f'{h3}Results we could not compare</h3><ul style="padding-left:20px;line-height:1.5;">{items}</ul>')
    parts.append(f'{h3}Things to keep in mind</h3><ul style="padding-left:20px;line-height:1.6;color:#1e293b;">' + "".join(f"<li>{esc(x)}</li>" for x in LIMITS) + "</ul>")

    used = []
    for c in compared:
        for sid in ([c["source"]] if c["source"] else []) + list(c.get("also_sources") or []):
            if sid not in used:
                used.append(sid)
    if used:
        src = []
        for sid in used:
            s = data.SOURCES[sid]
            link = f' <a href="{esc(s["url"])}" target="_blank" rel="noopener noreferrer" style="color:#0f382b;">{esc(s["url"])}</a>' if s["url"] else ""
            src.append(f'<li style="margin-bottom:8px;color:#334155;font-size:13px;"><b>{esc(s["short"])}.</b> {esc(s["citation"])}{link}<br>'
                       f'<span style="color:#64748b;">Who was studied: {esc(s["population"])} {esc(s["note"])}</span></li>')
        parts.append(f'{h3}Where these ranges come from</h3><ul style="padding-left:20px;line-height:1.5;">{"".join(src)}</ul>')
    parts.append(f'<p style="font-size:12px;color:#64748b;">Reference data version {esc(NORMS_VERSION)}, checked {esc(data.DATA_CHECKED)}.</p>')
    return "".join(p for p in parts if p)


def clinician_table(comparisons: list) -> str:
    """A compact markdown table for the clinician's review screen (with the technical names, and both QTc corrections)."""
    comps = [c if isinstance(c, dict) else c.to_dict() for c in comparisons]
    if not comps:
        return ""
    lines = ["| Measure | Result | Usual range | Group | Where it sits |", "|---|---|---|---|---|"]
    for c in comps:
        where = (c.get("status_text") or _WORDS[c["status"]]) + (f": {c['reason']}" if c["status"] == NO_REFERENCE else "") + (f" ({c['headline']})" if c.get("headline") and c["status"] != NO_REFERENCE else "")
        cell = lambda s: str(s or "").replace("|", "/").replace("\n", " ")
        lines.append(f"| {cell(c['label'])} | {cell(c['value_text'])}{' (calculated)' if c.get('calculated') else ''} | {cell(c['range_text'])} | {cell(c['group'])} | {cell(where)} |")
    return "\n".join(lines)
