"""Turns comparisons into the "How you compare" page of the participant's report (HTML), and a short table for the clinician.

Every piece of text is escaped. The sentences come from fixed templates in engine.py, so nothing on this page is written by an AI.
The page is laid out as: a quick-view table, one card per result (the verdict, the facts, and what it means), then a
"Putting it all together" summary, the limits, and the sources.
"""
from __future__ import annotations

import html

from . import data
from .engine import ABOVE, BELOW, NO_REFERENCE, NORMS_VERSION, REPORTED, WELL_ABOVE, WITHIN, overview, summary_sentence

esc = lambda s: html.escape("" if s is None else str(s), quote=True)

_WORDS = {WITHIN: "Within the usual range", BELOW: "Lower than the usual range", ABOVE: "Higher than the usual range",
          WELL_ABOVE: "Well above the usual range", REPORTED: "As reported by the device", NO_REFERENCE: "Not compared"}
# soft colours, and every chip sets its own text colour so it reads on a light or a dark page
_CHIP = {WITHIN: ("#dcfce7", "#166534"), BELOW: ("#e0f2fe", "#075985"), ABOVE: ("#fef3c7", "#92400e"), WELL_ABOVE: ("#fef3c7", "#92400e"),
         REPORTED: ("#e2e8f0", "#334155"), NO_REFERENCE: ("#e2e8f0", "#334155")}
_HEAD = {"doing_well": "#166534", "watch": "#92400e", "work_on": "#92400e", "discuss": "#075985", "info": "#334155"}

INTRO = ("This page compares some of your results with published reference data for people of your age and sex, and explains what each one means for you. "
         "It shows where your results sit compared with groups of healthy people. It does not diagnose anything, and a result outside a range "
         "is not a sign that something is wrong. Your clinician will talk through what matters for you.")
LIMITS = [
    "The reference groups were studied in other places and at other times, mostly in white populations, and they may not look like you.",
    "People who are fitter or leaner than average often sit outside the usual range for good reasons.",
    "Different devices measure slightly differently, so a home or clinic device may not match the equipment used in the studies.",
    "A single measurement is a snapshot. It can change from day to day.",
    "Where we link a result to a health condition, that is a link seen in large groups of people. It is not a prediction for you.",
]


def _d(c):
    return c if isinstance(c, dict) else c.to_dict()


def _chip(status):
    bg, fg = _CHIP[status]
    return f'<span style="display:inline-block;padding:3px 10px;border-radius:12px;background:{bg};color:{fg};font-size:13px;font-weight:600;">{esc(_WORDS[status])}</span>'


def _card(c) -> str:
    colour = _HEAD.get(c.get("theme", ""), "#334155")
    parts = [
        '<div style="border:1px solid #e2e8f0;border-radius:10px;padding:14px 16px;margin-bottom:14px;background:#ffffff;">',
        f'<div style="margin-bottom:6px;"><b style="color:#0f382b;font-size:16px;">{esc(c["label"])}</b> &nbsp;{_chip(c["status"])}</div>',
    ]
    if c.get("headline"):
        parts.append(f'<p style="margin:6px 0;font-weight:700;color:{colour};font-size:15px;">{esc(c["headline"])}</p>')
    parts.append(f'<p style="margin:6px 0;color:#1e293b;line-height:1.6;">{esc(c["sentence"])}</p>')
    if c.get("meaning"):
        parts.append(f'<p style="margin:6px 0;color:#1e293b;line-height:1.6;"><b>What this means:</b> {esc(c["meaning"])}</p>')
    if c.get("detail"):
        parts.append(f'<p style="margin:6px 0;color:#475569;font-size:13px;line-height:1.5;"><i>{esc(c["detail"])}</i></p>')
    parts.append("</div>")
    return "".join(parts)


def render_section_html(comparisons: list, age=None, sex=None) -> str:
    """The report page. Returns '' when there is nothing to show."""
    comps = [_d(c) for c in comparisons]
    if not comps:
        return ""
    compared = [c for c in comps if c["status"] != NO_REFERENCE]
    skipped = [c for c in comps if c["status"] == NO_REFERENCE]
    th = 'style="text-align:left;padding:10px;border-bottom:2px solid #0f382b;color:#0f382b;font-size:14px;"'
    td = 'style="padding:10px;border-bottom:1px solid #e2e8f0;vertical-align:top;color:#1e293b;font-size:14px;"'
    rows = []
    for c in compared:
        rng = esc(c["range_text"]) + (f'<br><span style="color:#64748b;font-size:12px;">{esc(c["group"])}</span>' if c["group"] else "")
        rows.append(f'<tr><td {td}><b>{esc(c["label"])}</b></td><td {td}>{esc(c["value_text"])}</td><td {td}>{rng}</td><td {td}>{_chip(c["status"])}</td></tr>')
    table = (f'<table style="width:100%;border-collapse:collapse;margin:16px 0;"><thead><tr><th {th}>Measure</th><th {th}>Your result</th>'
             f'<th {th}>Usual range</th><th {th}>Where you sit</th></tr></thead><tbody>{"".join(rows)}</tbody></table>') if rows else ""

    h3 = '<h3 style="color:#0f382b;margin-top:26px;">'
    parts = [
        f'<p style="font-size:16px;color:#1e293b;line-height:1.6;">{esc(INTRO)}</p>',
        f'<p style="font-size:16px;color:#0f382b;"><b>{esc(summary_sentence(comps))}</b></p>' if compared else "",
        table,
        f'{h3}Your results in detail</h3>' + "".join(_card(c) for c in compared) if compared else "",
    ]
    blocks = overview(comps)
    if blocks:
        body = "".join(f'<h4 style="color:#0f382b;margin:16px 0 4px;">{esc(head)}</h4><p style="margin:0 0 6px;color:#1e293b;line-height:1.6;">{esc(text)}</p>' for head, text in blocks)
        parts.append(f'<div style="margin-top:28px;padding:18px 20px;border-radius:12px;background:#f0fdf4;border:1px solid #bbf7d0;">'
                     f'<h3 style="color:#0f382b;margin:0 0 4px;">Putting it all together</h3>{body}</div>')
    if skipped:
        items = "".join(f'<li style="color:#334155;margin-bottom:4px;">{esc(c["label"])} ({esc(c["value_text"])}): {esc(c["reason"])}</li>' for c in skipped)
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
    """A compact markdown table for the clinician's review screen."""
    comps = [_d(c) for c in comparisons]
    if not comps:
        return ""
    lines = ["| Measure | Result | Usual range | Group | Where it sits |", "|---|---|---|---|---|"]
    for c in comps:
        where = _WORDS[c["status"]] + (f": {c['reason']}" if c["status"] == NO_REFERENCE else "") + (f" ({c['headline']})" if c.get("headline") and c["status"] != NO_REFERENCE else "")
        cell = lambda s: str(s or "").replace("|", "/").replace("\n", " ")
        lines.append(f"| {cell(c['label'])} | {cell(c['value_text'])}{' (calculated)' if c.get('calculated') else ''} | {cell(c['range_text'])} | {cell(c['group'])} | {cell(where)} |")
    return "\n".join(lines)
