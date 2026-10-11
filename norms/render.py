"""Turns comparisons into the "How you compare" section of the participant's report (HTML), and a short table for the clinician.

Every piece of text is escaped. The sentences were written by the engine from fixed templates, so nothing in this section is
written by an AI.
"""
from __future__ import annotations

import html

from . import data
from .engine import ABOVE, BELOW, NO_REFERENCE, NORMS_VERSION, REPORTED, WELL_ABOVE, WITHIN, summary_sentence

esc = lambda s: html.escape("" if s is None else str(s), quote=True)

_WORDS = {WITHIN: "Within the usual range", BELOW: "Lower than the usual range", ABOVE: "Higher than the usual range",
          WELL_ABOVE: "Well above the usual range", REPORTED: "As reported by the device", NO_REFERENCE: "Not compared"}
# soft colours, and every chip sets its own text colour so it reads on a light or a dark page
_CHIP = {WITHIN: ("#dcfce7", "#166534"), BELOW: ("#e0f2fe", "#075985"), ABOVE: ("#fef3c7", "#92400e"), WELL_ABOVE: ("#fef3c7", "#92400e"),
         REPORTED: ("#e2e8f0", "#334155"), NO_REFERENCE: ("#e2e8f0", "#334155")}

INTRO = ("This page compares some of your results with published reference data for people of your age and sex. "
         "It shows where your results sit compared with groups of healthy people. It does not diagnose anything, and a result outside a range "
         "is not a sign that something is wrong. Your clinician will talk through what matters for you.")
LIMITS = [
    "The reference groups were studied in other places and at other times, mostly in white populations, and they may not look like you.",
    "People who are fitter or leaner than average often sit outside the usual range for good reasons.",
    "Different devices measure slightly differently, so a home or clinic device may not match the equipment used in the studies.",
    "A single measurement is a snapshot. It can change from day to day.",
]


def _d(c):
    return c if isinstance(c, dict) else c.to_dict()


def _chip(status):
    bg, fg = _CHIP[status]
    return f'<span style="display:inline-block;padding:3px 10px;border-radius:12px;background:{bg};color:{fg};font-size:13px;font-weight:600;">{esc(_WORDS[status])}</span>'


def render_section_html(comparisons: list, age=None, sex=None) -> str:
    """The report section. Returns '' when there is nothing to show."""
    comps = [_d(c) for c in comparisons]
    if not comps:
        return ""
    compared = [c for c in comps if c["status"] not in (NO_REFERENCE,)]
    skipped = [c for c in comps if c["status"] == NO_REFERENCE]
    th = 'style="text-align:left;padding:10px;border-bottom:2px solid #0f382b;color:#0f382b;font-size:14px;"'
    td = 'style="padding:10px;border-bottom:1px solid #e2e8f0;vertical-align:top;color:#1e293b;font-size:14px;"'
    rows = []
    for c in compared:
        rng = esc(c["range_text"]) + (f'<br><span style="color:#64748b;font-size:12px;">{esc(c["group"])}</span>' if c["group"] else "")
        rows.append(f'<tr><td {td}><b>{esc(c["label"])}</b></td><td {td}>{esc(c["value_text"])}</td><td {td}>{rng}</td><td {td}>{_chip(c["status"])}</td></tr>')
    table = (f'<table style="width:100%;border-collapse:collapse;margin:16px 0;"><thead><tr><th {th}>Measure</th><th {th}>Your result</th>'
             f'<th {th}>Usual range</th><th {th}>Where you sit</th></tr></thead><tbody>{"".join(rows)}</tbody></table>') if rows else ""

    meaning = []
    for c in compared:
        extra = f' <i style="color:#475569;">{esc(c["detail"])}</i>' if c["detail"] else ""
        meaning.append(f'<li style="margin-bottom:10px;color:#1e293b;">{esc(c["sentence"])}{extra}</li>')

    parts = [
        f'<p style="font-size:16px;color:#1e293b;line-height:1.6;">{esc(INTRO)}</p>',
        f'<p style="font-size:16px;color:#0f382b;"><b>{esc(summary_sentence(comps))}</b></p>' if compared else "",
        table,
        f'<h3 style="color:#0f382b;">What this means</h3><ul style="padding-left:20px;line-height:1.6;">{"".join(meaning)}</ul>' if meaning else "",
    ]
    if skipped:
        items = "".join(f'<li style="color:#334155;margin-bottom:4px;">{esc(c["label"])} ({esc(c["value_text"])}): {esc(c["reason"])}</li>' for c in skipped)
        parts.append(f'<h3 style="color:#0f382b;">Results we could not compare</h3><ul style="padding-left:20px;line-height:1.5;">{items}</ul>')
    parts.append('<h3 style="color:#0f382b;">Things to keep in mind</h3><ul style="padding-left:20px;line-height:1.6;color:#1e293b;">'
                 + "".join(f"<li>{esc(x)}</li>" for x in LIMITS) + "</ul>")

    used = []
    for c in compared:
        if c["source"] and c["source"] not in used:
            used.append(c["source"])
    if used:
        src = []
        for sid in used:
            s = data.SOURCES[sid]
            link = f' <a href="{esc(s["url"])}" target="_blank" rel="noopener noreferrer" style="color:#0f382b;">{esc(s["url"])}</a>' if s["url"] else ""
            src.append(f'<li style="margin-bottom:8px;color:#334155;font-size:13px;"><b>{esc(s["short"])}.</b> {esc(s["citation"])}{link}<br>'
                       f'<span style="color:#64748b;">Who was studied: {esc(s["population"])} {esc(s["note"])}</span></li>')
        parts.append(f'<h3 style="color:#0f382b;">Where these ranges come from</h3><ul style="padding-left:20px;line-height:1.5;">{"".join(src)}</ul>')
    parts.append(f'<p style="font-size:12px;color:#64748b;">Reference data version {esc(NORMS_VERSION)}, checked {esc(data.DATA_CHECKED)}.</p>')
    return "".join(p for p in parts if p)


def clinician_table(comparisons: list) -> str:
    """A compact markdown table for the clinician's review screen."""
    comps = [_d(c) for c in comparisons]
    if not comps:
        return ""
    lines = ["| Measure | Result | Usual range | Group | Where it sits |", "|---|---|---|---|---|"]
    for c in comps:
        where = _WORDS[c["status"]] + (f": {c['reason']}" if c["status"] == NO_REFERENCE else "")
        cell = lambda s: str(s or "").replace("|", "/").replace("\n", " ")
        lines.append(f"| {cell(c['label'])} | {cell(c['value_text'])}{' (calculated)' if c.get('calculated') else ''} | {cell(c['range_text'])} | {cell(c['group'])} | {cell(where)} |")
    return "\n".join(lines)
