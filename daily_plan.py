"""The daily plan: a pre-written diary that runs alongside a patient's assessment and bespoke plan.

The clinician writes blocks once in a library (a strength session, an eating principle, a habit), sets each plan's weekly
rhythm phase by phase, and gives a patient the plan with a start date. Each day the patient sees one priority session
(with a shorter "busy day" version), the day's eating principles and habits to tick off, the clinician's note for the
phase, how consistent they have been, and a two-tap check-in. A pain flag switches the day to the busy version and shows
up on the clinician's "Who needs you" list. No AI writes any of it.

Stored in Firestore:
  daily_plan_library/{block_id}     one document per block
  daily_plan_templates/{plan_id}    one document per plan: name, length, retest days and phases
  longevity_reports/{key}.daily_plan        the plan a patient is on: template, start date, a note, last active, last pain
  longevity_reports/{key}/daily_log/{date}  what the patient did and how they felt on one day

The functions at the top are plain Python (tested in tests/test_daily_plan.py); the screens below them need Streamlit.
"""
import datetime
import re
import secrets

LIBRARY = "daily_plan_library"
TEMPLATES = "daily_plan_templates"
LOG = "daily_log"
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
BLOCK_TYPES = {"move": "Movement", "eat": "Eating", "habit": "Habit"}
PAIN_CHOICES = {"none": "None", "mild": "Mild", "flag": "Tell my clinician"}
QUIET_DAYS = 3          # this many days without a tick puts a patient on the "Who needs you" list
PAIN_DAYS = 7           # a pain flag in this many days does too
TITLE_MAX, TEXT_MAX, STEP_MAX, STEPS_MAX = 80, 600, 160, 15
_ID_RE = re.compile(r"[a-z0-9-]{1,40}")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


# --- Plain logic ---------------------------------------------------------------------------------------------------------

def as_date(value):
    """A date from a date, a datetime or 'YYYY-MM-DD'; None if it isn't one."""
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    if isinstance(value, str) and _DATE_RE.fullmatch(value.strip()):
        try:
            return datetime.date.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


def day_number(start, today) -> int:
    """Day 1 is the start date. Before the start it is 0 or less."""
    start, today = as_date(start), as_date(today)
    if not start or not today:
        return 0
    return (today - start).days + 1


def weekday(d) -> str:
    return DAYS[as_date(d).weekday()]


def phase_for(template: dict, n: int) -> dict:
    """The phase that day n falls in. Before day 1 it is the first phase; after the end, the last."""
    phases = (template or {}).get("phases") or []
    if not phases:
        return {}
    for ph in phases:
        if int(ph.get("from", 0)) <= n <= int(ph.get("to", 0)):
            return ph
    return phases[0] if n < int(phases[0].get("from", 1)) else phases[-1]


def move_for_day(template: dict, n: int, d) -> str:
    """The block id of the day's priority session, or '' for a rest day."""
    return (phase_for(template, n).get("week") or {}).get(weekday(d), "") or ""


def is_active(entry) -> bool:
    """A day counts if anything was ticked: the session or any eating principle or habit."""
    entry = entry or {}
    return bool(entry.get("done") or entry.get("checks"))


def consistency(logs: dict, today, days: int = 7) -> int:
    """How many of the last `days` days (today included) have a tick."""
    today = as_date(today)
    return sum(1 for i in range(days) if is_active(logs.get((today - datetime.timedelta(days=i)).isoformat())))


def last_active(logs: dict):
    """The most recent date with a tick, or None."""
    dates = [as_date(k) for k, v in logs.items() if is_active(v) and as_date(k)]
    return max(dates) if dates else None


def quiet_days(last, start, today) -> int:
    """Days in a row without a tick, counting back from today (not counting days before the plan started)."""
    today, start, last = as_date(today), as_date(start), as_date(last)
    if last and last >= today:
        return 0
    if last:
        return (today - last).days
    return max(0, (today - start).days + 1) if start else 0


def missed_two(logs: dict, start, today) -> bool:
    """Yesterday and the day before both empty, and both inside the plan."""
    today, start = as_date(today), as_date(start)
    days = [today - datetime.timedelta(days=i) for i in (1, 2)]
    if start and any(d < start for d in days):
        return False
    return not any(is_active(logs.get(d.isoformat())) for d in days)


def recent_pain(last_pain, today, days: int = PAIN_DAYS) -> bool:
    last_pain, today = as_date(last_pain), as_date(today)
    return bool(last_pain and 0 <= (today - last_pain).days < days)


def next_retest(template: dict, n: int):
    """The next retest day on or after day n, or None."""
    upcoming = [r for r in (template or {}).get("retests") or [] if r >= n]
    return min(upcoming) if upcoming else None


def flags(plan: dict, logs: dict, today) -> list:
    """What puts a patient on the clinician's list: ('quiet', days) and/or ('pain', date)."""
    plan = plan or {}
    out = []
    start = as_date(plan.get("start"))
    if start and start <= as_date(today):
        q = quiet_days(last_active(logs) or plan.get("last_active"), start, today)
        if q >= QUIET_DAYS:
            out.append(("quiet", q))
    lp = max([d for d in [as_date(plan.get("last_pain"))] + [as_date(k) for k, v in logs.items() if (v or {}).get("pain") == "flag"] if d],
             default=None)
    if recent_pain(lp, today):
        out.append(("pain", lp.isoformat()))
    return out


def clean_text(value, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def clean_lines(value) -> list:
    if isinstance(value, (list, tuple)):
        lines = value
    else:
        lines = str(value or "").splitlines()
    return [clean_text(x, STEP_MAX) for x in lines if clean_text(x, STEP_MAX)][:STEPS_MAX]


def clean_block(data: dict) -> dict:
    """A block as it is stored. Raises ValueError with a message for the clinician if it can't be saved."""
    data = data or {}
    kind = data.get("type")
    if kind not in BLOCK_TYPES:
        raise ValueError("Choose a type for the block.")
    title = clean_text(data.get("title"), TITLE_MAX)
    if not title:
        raise ValueError("Give the block a title.")
    return {
        "type": kind,
        "title": title,
        "full": clean_text(data.get("full"), TEXT_MAX),
        "busy": clean_text(data.get("busy"), TEXT_MAX) if kind == "move" else "",
        "marker": clean_text(data.get("marker"), TITLE_MAX),
        "why": clean_text(data.get("why"), TEXT_MAX),
        "steps": clean_lines(data.get("steps")) if kind == "move" else [],
        "busy_steps": clean_lines(data.get("busy_steps")) if kind == "move" else [],
    }


def clean_phases(phases, block_ids, length: int) -> list:
    """Phases as stored: names, day ranges inside the plan, and only blocks that exist."""
    out = []
    for ph in phases or []:
        f, t = max(1, int(ph.get("from", 1))), min(int(length), int(ph.get("to", length)))
        if t < f:
            raise ValueError(f"Phase '{clean_text(ph.get('name'), 40)}' ends before it starts.")
        week = {d: (ph.get("week") or {}).get(d, "") for d in DAYS}
        out.append({
            "name": clean_text(ph.get("name"), 40) or "Phase",
            "from": f, "to": t,
            "note": clean_text(ph.get("note"), TEXT_MAX * 2),
            "week": {d: (v if v in block_ids else "") for d, v in week.items()},
            "eat": [b for b in ph.get("eat") or [] if b in block_ids],
            "habits": [b for b in ph.get("habits") or [] if b in block_ids],
        })
    out.sort(key=lambda p: p["from"])
    return out


def new_id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(6)}"


def valid_id(value) -> bool:
    return bool(_ID_RE.fullmatch(str(value or "")))


# Sample wording so the screens aren't empty on the first day. The clinician rewrites each block in their own words.
STARTER_BLOCKS = {
    "s-strength-a": {"type": "move", "title": "Strength A", "full": "25 min", "busy": "10 min", "marker": "Grip strength",
                     "why": "Loaded carries and hinges build grip and the muscles along the back of the body.",
                     "steps": ["Warm up: 2 min marching and arm swings", "Split squat 3 x 8 each leg", "Hip hinge with a weight 3 x 10",
                               "Farmer carry 4 x 30 m", "Dead hang 3 x 20 s"],
                     "busy_steps": ["Split squat 2 x 8 each leg", "Farmer carry 3 x 30 m"]},
    "s-strength-b": {"type": "move", "title": "Strength B", "full": "25 min", "busy": "10 min", "marker": "Leg power",
                     "why": "Step-ups and push work for leg power and upper-body strength.",
                     "steps": ["Warm up: 2 min easy steps", "Step-up 3 x 8 each leg", "Press-up (incline if needed) 3 x 8",
                               "Single-leg balance 3 x 30 s each", "Glute bridge 3 x 12"],
                     "busy_steps": ["Step-up 2 x 8 each leg", "Glute bridge 2 x 12"]},
    "s-zone2": {"type": "move", "title": "Zone 2 walk", "full": "40 min", "busy": "15 min", "marker": "VO2 max",
                "why": "Steady walking where you can still talk builds the aerobic base behind VO2 max.",
                "steps": ["Brisk walk at a pace where you can talk but not sing", "Hills are welcome; keep the effort steady"],
                "busy_steps": ["15 min brisk walk, ideally after a meal"]},
    "s-mobility": {"type": "move", "title": "Mobility flow", "full": "15 min", "busy": "5 min", "marker": "",
                   "why": "Keeps hips, spine and shoulders moving between strength days.",
                   "steps": ["Cat-cow x 10", "90/90 hip switches x 10", "Thoracic rotations x 8 each side", "Deep squat hold 3 x 30 s"],
                   "busy_steps": ["Deep squat hold 2 x 30 s", "Cat-cow x 10"]},
    "s-protein": {"type": "eat", "title": "Protein at every meal", "full": "A palm-sized portion at breakfast, lunch and dinner", "marker": "Muscle mass"},
    "s-colours": {"type": "eat", "title": "Two colours on the plate", "full": "Veg or fruit of two colours with lunch and dinner"},
    "s-water": {"type": "eat", "title": "2 litres of water", "full": "Spread through the day, more on training days"},
    "s-fibre": {"type": "eat", "title": "Add a fibre swap", "full": "Oats, beans, lentils or wholegrain in one meal"},
    "s-walk-lunch": {"type": "habit", "title": "10 min walk after lunch", "full": "Straight after eating, before sitting back down"},
    "s-screens": {"type": "habit", "title": "Screens off by 10pm", "full": "Phone on charge outside the bedroom"},
    "s-daylight": {"type": "habit", "title": "Morning daylight", "full": "10 min outside before 10am"},
}
STARTER_TEMPLATE_ID = "t-60-foundations"
STARTER_TEMPLATE = {
    "name": "60-day foundations", "length": 60, "retests": [30, 60],
    "phases": [
        {"name": "Foundations", "from": 1, "to": 21,
         "note": "These first three weeks are about turning up, not intensity. If a day goes wrong, do the busy version and move on. Never miss twice.",
         "week": {"Mon": "s-strength-a", "Tue": "s-zone2", "Wed": "s-mobility", "Thu": "s-strength-b", "Fri": "s-zone2", "Sat": "s-mobility", "Sun": ""},
         "eat": ["s-protein", "s-colours", "s-water"], "habits": ["s-walk-lunch", "s-screens"]},
        {"name": "Build", "from": 22, "to": 42,
         "note": "You have the rhythm now. We add a little load each week and a fibre swap to your meals.",
         "week": {"Mon": "s-strength-a", "Tue": "s-zone2", "Wed": "s-strength-b", "Thu": "s-mobility", "Fri": "s-strength-a", "Sat": "s-zone2", "Sun": ""},
         "eat": ["s-protein", "s-colours", "s-water", "s-fibre"], "habits": ["s-walk-lunch", "s-screens", "s-daylight"]},
        {"name": "Consolidate", "from": 43, "to": 60,
         "note": "This is where it becomes part of who you are. Keep the routine going and we'll retest on day 60.",
         "week": {"Mon": "s-strength-a", "Tue": "s-zone2", "Wed": "s-strength-b", "Thu": "s-zone2", "Fri": "s-strength-a", "Sat": "s-mobility", "Sun": ""},
         "eat": ["s-protein", "s-colours", "s-water", "s-fibre"], "habits": ["s-walk-lunch", "s-screens", "s-daylight"]},
    ],
}


# --- Storage (Firestore) -------------------------------------------------------------------------------------------------

def _server_time():
    from google.cloud import firestore
    return firestore.SERVER_TIMESTAMP


def load_library(db) -> dict:
    return {d.id: (d.to_dict() or {}) for d in db.collection(LIBRARY).stream()}


def save_block(db, block_id: str, data: dict, who: str) -> str:
    block = clean_block(data)
    block_id = block_id if valid_id(block_id) else new_id("b")
    db.collection(LIBRARY).document(block_id).set({**block, "updated_by": who, "updated_at": _server_time()})
    return block_id


def delete_block(db, block_id: str):
    if valid_id(block_id):
        db.collection(LIBRARY).document(block_id).delete()


def load_templates(db) -> dict:
    return {d.id: (d.to_dict() or {}) for d in db.collection(TEMPLATES).stream()}


def save_template(db, template_id: str, template: dict, block_ids, who: str):
    length = max(7, min(365, int(template.get("length") or 60)))
    data = {
        "name": clean_text(template.get("name"), 60) or "Plan",
        "length": length,
        "retests": sorted({int(r) for r in template.get("retests") or [] if 1 <= int(r) <= length}),
        "phases": clean_phases(template.get("phases"), set(block_ids), length),
        "updated_by": who, "updated_at": _server_time(),
    }
    if not data["phases"]:
        raise ValueError("A plan needs at least one phase.")
    db.collection(TEMPLATES).document(template_id if valid_id(template_id) else new_id("t")).set(data)


def add_starter_content(db, who: str):
    """Writes the sample library and the 60-day plan, without touching anything already there."""
    have = load_library(db)
    for bid, b in STARTER_BLOCKS.items():
        if bid not in have:
            save_block(db, bid, b, who)
    if STARTER_TEMPLATE_ID not in load_templates(db):
        save_template(db, STARTER_TEMPLATE_ID, STARTER_TEMPLATE, set(have) | set(STARTER_BLOCKS), who)


def load_logs(db, reports: str, key: str, today, days: int = 35) -> dict:
    cutoff = (as_date(today) - datetime.timedelta(days=days)).isoformat()
    from google.cloud.firestore_v1.base_query import FieldFilter
    q = db.collection(reports).document(key).collection(LOG).where(filter=FieldFilter("date", ">=", cutoff))
    return {d.id: (d.to_dict() or {}) for d in q.stream()}


def save_log(db, reports: str, key: str, day, entry: dict):
    """Saves one day's entry and keeps last_active / last_pain on the patient's record for the clinician's list."""
    day = as_date(day).isoformat()
    entry = {**entry, "date": day}
    profile = db.collection(reports).document(key)
    profile.collection(LOG).document(day).set({**entry, "updated_at": _server_time()})
    summary = {}
    if is_active(entry):
        summary["daily_plan.last_active"] = day
    if entry.get("pain") == "flag":
        summary["daily_plan.last_pain"] = day
    if summary:
        profile.update(summary)


def assign_plan(db, reports: str, key: str, template_id: str, start, note: str, who: str):
    db.collection(reports).document(key).update({"daily_plan": {
        "template": template_id, "start": as_date(start).isoformat(), "note": clean_text(note, TEXT_MAX),
        "active": True, "assigned_by": who, "assigned_at": _server_time()}})


def stop_plan(db, reports: str, key: str):
    db.collection(reports).document(key).update({"daily_plan.active": False})


def patients_on_plans(db, reports: str) -> list:
    from google.cloud.firestore_v1.base_query import FieldFilter
    q = db.collection(reports).where(filter=FieldFilter("daily_plan.active", "==", True))
    return [(d.id, d.to_dict() or {}) for d in q.stream()]


# --- Screens (Streamlit) -------------------------------------------------------------------------------------------------

def _st():
    import streamlit as st
    return st


def _steps_md(steps) -> str:
    from helpers import esc
    return "\n".join(f"{i}. {esc(s)}" for i, s in enumerate(steps, 1))


def render_patient(db, reports: str, key: str, client_data: dict, fail, audit, phone: str, today=None):
    """The patient's 'Today' section. Shows nothing if no plan has been given to them."""
    st = _st()
    from helpers import esc
    plan = (client_data or {}).get("daily_plan") or {}
    if not plan.get("active") or not plan.get("template"):
        return
    today = as_date(today) or datetime.date.today()
    try:
        tsnap = db.collection(TEMPLATES).document(plan["template"]).get()
        template = (tsnap.to_dict() or {}) if tsnap.exists else {}
        library = load_library(db)
        logs = load_logs(db, reports, key, today)
    except Exception:
        fail("We couldn't load your daily plan right now. Please try again shortly.", "Daily plan load failed")
        return
    if not template:
        return
    start = as_date(plan.get("start"))
    n = day_number(start, today)
    length = int(template.get("length") or 60)
    st.subheader("📅 Your daily plan")
    if n < 1:
        st.info(f"Your plan, **{esc(template.get('name'))}**, starts on {start.strftime('%A %-d %B')}. Your first day will appear here.")
        return

    entry = dict(logs.get(today.isoformat()) or {})
    entry.setdefault("done", "")
    entry.setdefault("checks", [])
    ph = phase_for(template, n)

    def save(**changes):
        new = {**entry, **changes}
        try:
            save_log(db, reports, key, today, new)
            entry.update(changes)
            logs[today.isoformat()] = dict(entry)
        except Exception:
            fail("We couldn't save that right now. Please try again shortly.", "Daily plan save failed")

    with st.container(border=True):
        line = f"{today.strftime('%A %-d %B')} · Day {min(n, length)} of {length}"
        if ph.get("name"):
            line += f" · {ph['name']}"
        st.caption(line)
        st.progress(min(1.0, n / length))
        nr = next_retest(template, n)
        if n > length:
            st.caption("You've reached the end of this plan. Keep the routine going, and we'll talk about what comes next.")
        elif nr:
            st.caption("Your retest is today." if nr == n else f"Your retest is on day {nr}, in {nr - n} days.")

    # The one priority for the day, with a busy-day version
    block = library.get(move_for_day(template, n, today))
    with st.container(border=True):
        st.markdown("**Today's priority**")
        if not block:
            st.markdown("#### Rest day")
            st.caption("Nothing planned. A gentle walk is a bonus, not a job.")
        else:
            busy_forced = entry.get("pain") == "flag"
            choice = st.radio("Session length", ["Full", "Busy day"], horizontal=True, label_visibility="collapsed",
                              index=1 if (entry.get("version") == "busy" or busy_forced) else 0,
                              key=f"dp_ver::{today}::{'pain' if busy_forced else 'ok'}")  # a new switch once pain is flagged, so it starts on busy
            busy = choice == "Busy day"
            if busy != (entry.get("version") == "busy"):
                save(version="busy" if busy else "full", **({"done": "busy" if busy else "full"} if entry.get("done") else {}))
            length_txt = block.get("busy") if busy else block.get("full")
            st.markdown(f"#### {esc(block.get('title'))}" + (f" · {esc(length_txt)}" if length_txt else ""))
            steps = (block.get("busy_steps") if busy and block.get("busy_steps") else block.get("steps")) or []
            if steps:
                st.markdown(_steps_md(steps))
            if block.get("why"):
                st.caption(("🎯 " + esc(block["marker"]) + " · " if block.get("marker") else "") + esc(block["why"]))
            if entry.get("done"):
                st.success("Done. That counts towards your week.")
                if st.button("Undo", key=f"dp_undo::{today}"):
                    save(done="")
                    st.rerun()
            elif st.button("✅ Mark as done", key=f"dp_done::{today}", type="primary", use_container_width=True):
                save(done="busy" if busy else "full")
                st.rerun()

    # Eating principles and habits to tick off
    for title, ids in (("Eat", ph.get("eat") or []), ("Habits", ph.get("habits") or [])):
        items = [(bid, library[bid]) for bid in ids if bid in library]
        if not items:
            continue
        with st.container(border=True):
            st.markdown(f"**{title}**")
            for bid, b in items:
                was = bid in entry["checks"]
                now = st.checkbox(b.get("title", ""), value=was, key=f"dp_chk::{today}::{bid}")
                if b.get("full"):
                    st.caption(b["full"])
                if now != was:
                    save(checks=sorted(set(entry["checks"]) | {bid}) if now else [c for c in entry["checks"] if c != bid])

    notes = [x for x in (ph.get("note"), plan.get("note")) if x]
    if notes:
        st.markdown("<div class='portal-box'><h3>Note from your clinician</h3>" + "".join(f"<p>{esc(x)}</p>" for x in notes) + "</div>",
                    unsafe_allow_html=True)

    # Consistency, not streaks: a missed day doesn't undo the habit, so nothing here resets
    with st.container(border=True):
        c = consistency(logs, today)
        st.markdown(f"**Your consistency:** {c} of the last 7 days")
        cells = []
        for i in range(6, -1, -1):
            d = today - datetime.timedelta(days=i)
            on = is_active(logs.get(d.isoformat()))
            cells.append(f"<span style='flex:1;text-align:center;padding:4px 0;border-radius:6px;font-size:12px;font-weight:700;"
                         f"background:{'var(--ha-teal)' if on else 'var(--ha-mint)'};color:{'#fff' if on else 'var(--ha-muted)'}'>"
                         f"{DAYS[d.weekday()][0]}</span>")
        st.markdown(f"<div style='display:flex;gap:6px'>{''.join(cells)}</div>", unsafe_allow_html=True)
        if missed_two(logs, start, today) and not is_active(entry):
            st.caption("Two quiet days in a row. Do the busy version today and you're straight back on track.")

    # Two-tap check-in
    with st.container(border=True):
        st.markdown("**How are you today?**")
        scale = [None, 1, 2, 3, 4, 5]
        fmt = lambda v: "–" if v is None else str(v)  # noqa: E731
        for field, label in (("energy", "Energy"), ("sleep", "Sleep last night")):
            cur = entry.get(field) if entry.get(field) in scale else None
            val = st.radio(label, scale, index=scale.index(cur), horizontal=True, format_func=fmt, key=f"dp_{field}::{today}")
            if val != cur:
                save(**{field: val})
        pains = list(PAIN_CHOICES)
        cur = entry.get("pain") if entry.get("pain") in pains else "none"
        pain = st.radio("Any pain or niggles?", pains, index=pains.index(cur), horizontal=True, format_func=PAIN_CHOICES.get,
                        key=f"dp_pain::{today}")
        if pain != cur:
            save(pain=pain, **({"version": "busy"} if pain == "flag" else {}))
            if pain == "flag":
                audit("daily_plan_pain_flag", key)
            st.rerun()
        if entry.get("pain") == "flag":
            st.warning(f"Today is switched to the busy version and your clinician will see your flag. "
                       f"If the pain is severe or worrying, call us on {phone}.")

    with st.expander("This week"):
        monday = today - datetime.timedelta(days=today.weekday())
        rows = []
        for i in range(7):
            d = monday + datetime.timedelta(days=i)
            dn = n + (d - today).days
            b = library.get(move_for_day(template, dn, d)) if dn >= 1 else None
            done = (logs.get(d.isoformat()) or {}).get("done")
            what = f"{esc(b.get('title'))} · {esc(b.get('full'))}" if b else "Rest day"
            mark = " ✅" if done else ""
            rows.append(f"- **{DAYS[i]} {d.day}**{' (today)' if d == today else ''}: {what}{mark}")
        st.markdown("\n".join(rows))


def _template_editor(st, db, library: dict, templates: dict, who: str, fail):
    moves = {bid: b for bid, b in library.items() if b.get("type") == "move"}
    eats = {bid: b for bid, b in library.items() if b.get("type") == "eat"}
    habits = {bid: b for bid, b in library.items() if b.get("type") == "habit"}
    label = lambda bid, lib: lib.get(bid, {}).get("title", bid)  # noqa: E731
    options = list(templates) + ["__new__"]
    tid = st.selectbox("Plan", options, format_func=lambda t: "➕ New plan" if t == "__new__" else templates[t].get("name", t), key="dp_tpl")
    tpl = templates.get(tid) or {"name": "", "length": 60, "retests": [30, 60],
                                 "phases": [{"name": "Phase 1", "from": 1, "to": 60, "note": "", "week": {}, "eat": [], "habits": []}]}
    phases = [dict(p) for p in tpl.get("phases") or []]
    n_phases = st.number_input("Number of phases", min_value=1, max_value=6, value=max(1, len(phases)), step=1, key=f"dp_np::{tid}")
    with st.form(f"dp_tpl_form::{tid}"):
        c1, c2, c3 = st.columns([3, 1, 2])
        name = c1.text_input("Plan name", value=tpl.get("name", ""), max_chars=60)
        length = c2.number_input("Days", min_value=7, max_value=365, value=int(tpl.get("length") or 60), step=1)
        retests = c3.text_input("Retest days (comma separated)", value=", ".join(str(r) for r in tpl.get("retests") or []))
        while len(phases) < n_phases:
            last = phases[-1]["to"] if phases else 0
            phases.append({"name": f"Phase {len(phases) + 1}", "from": last + 1, "to": int(length), "note": "", "week": {}, "eat": [], "habits": []})
        phases = phases[:int(n_phases)]
        edited = []
        for i, ph in enumerate(phases):
            st.markdown(f"**Phase {i + 1}**")
            a, b, c = st.columns([3, 1, 1])
            pname = a.text_input("Name", value=ph.get("name", ""), key=f"dp_pn::{tid}::{i}", max_chars=40)
            pfrom = b.number_input("From day", min_value=1, max_value=365, value=int(ph.get("from", 1)), key=f"dp_pf::{tid}::{i}")
            pto = c.number_input("To day", min_value=1, max_value=365, value=int(ph.get("to", length)), key=f"dp_pt::{tid}::{i}")
            cols = st.columns(7)
            week = {}
            move_opts = [""] + list(moves)
            for d, col in zip(DAYS, cols):
                cur = (ph.get("week") or {}).get(d, "")
                week[d] = col.selectbox(d, move_opts, index=move_opts.index(cur) if cur in move_opts else 0,
                                        format_func=lambda v: "Rest" if not v else label(v, moves), key=f"dp_w::{tid}::{i}::{d}")
            eat = st.multiselect("Daily eating principles", list(eats), default=[x for x in ph.get("eat") or [] if x in eats],
                                 format_func=lambda v: label(v, eats), key=f"dp_e::{tid}::{i}")
            hab = st.multiselect("Daily habits", list(habits), default=[x for x in ph.get("habits") or [] if x in habits],
                                 format_func=lambda v: label(v, habits), key=f"dp_h::{tid}::{i}")
            note = st.text_area("Your note for this phase", value=ph.get("note", ""), key=f"dp_no::{tid}::{i}", max_chars=TEXT_MAX * 2)
            edited.append({"name": pname, "from": pfrom, "to": pto, "week": week, "eat": eat, "habits": hab, "note": note})
            st.divider()
        if st.form_submit_button("Save plan", type="primary"):
            try:
                rts = [int(x) for x in re.findall(r"\d+", retests)]
                save_template(db, "" if tid == "__new__" else tid, {"name": name, "length": length, "retests": rts, "phases": edited},
                              set(library), who)
                st.success("Plan saved. Everyone on it sees the change straight away.")
            except ValueError as e:
                st.warning(str(e))
            except Exception:
                fail("Couldn't save the plan. Please try again.", "Daily plan template save failed")


def _library_editor(st, db, library: dict, who: str, fail):
    if not library:
        st.info("Your library is empty. Add your first block below, or start from the sample library and rewrite it in your own words.")
        if st.button("Add the sample library and a 60-day plan", key="dp_starter"):
            try:
                add_starter_content(db, who)
            except Exception:
                fail("Couldn't add the sample library. Please try again.", "Daily plan starter content failed")
            else:
                st.rerun()
        st.caption("The sample wording is a starting point only. Edit each block before giving a plan to a patient.")
    for kind, title in BLOCK_TYPES.items():
        items = sorted(((bid, b) for bid, b in library.items() if b.get("type") == kind), key=lambda x: x[1].get("title", ""))
        if items:
            st.markdown(f"**{title}**")
            for bid, b in items:
                extra = f" · targets {b['marker']}" if b.get("marker") else ""
                st.markdown(f"- {b.get('title', '')} · {b.get('full', '')}{extra}")
    st.divider()
    options = ["__new__"] + sorted(library, key=lambda b: library[b].get("title", ""))
    bid = st.selectbox("Edit a block", options, format_func=lambda b: "➕ New block" if b == "__new__" else library[b].get("title", b), key="dp_blk")
    b = library.get(bid) or {"type": "move"}
    with st.form(f"dp_blk_form::{bid}"):
        kinds = list(BLOCK_TYPES)
        kind = st.selectbox("Type", kinds, index=kinds.index(b.get("type", "move")), format_func=BLOCK_TYPES.get)
        title = st.text_input("Title", value=b.get("title", ""), max_chars=TITLE_MAX, placeholder="Strength C")
        full = st.text_input("Full version or detail", value=b.get("full", ""), max_chars=TEXT_MAX, placeholder="30 min")
        busy = st.text_input("Busy day version (movement only)", value=b.get("busy", ""), max_chars=TEXT_MAX, placeholder="10 min")
        marker = st.text_input("Reading it targets (optional)", value=b.get("marker", ""), max_chars=TITLE_MAX, placeholder="Grip strength")
        why = st.text_area("Why it's in the plan (the patient sees this)", value=b.get("why", ""), max_chars=TEXT_MAX)
        steps = st.text_area("Steps, one per line (movement only)", value="\n".join(b.get("steps") or []))
        bsteps = st.text_area("Busy day steps, one per line (movement only)", value="\n".join(b.get("busy_steps") or []))
        c1, c2 = st.columns(2)
        saved = c1.form_submit_button("Save block", type="primary")
        deleted = c2.form_submit_button("Delete block") if bid != "__new__" else False
    if saved:
        try:
            save_block(db, "" if bid == "__new__" else bid,
                       {"type": kind, "title": title, "full": full, "busy": busy, "marker": marker, "why": why, "steps": steps, "busy_steps": bsteps}, who)
        except ValueError as e:
            st.warning(str(e))
        except Exception:
            fail("Couldn't save the block. Please try again.", "Daily plan block save failed")
        else:
            st.rerun()
    if deleted:
        try:
            delete_block(db, bid)
        except Exception:
            fail("Couldn't delete the block. Please try again.", "Daily plan block delete failed")
        else:
            st.rerun()


def render_clinician(db, reports: str, who: str, fail, pick_patient, today=None):
    """The clinician's daily plan tools: who needs a look, giving a patient a plan, the plan builder and the library."""
    st = _st()
    today = as_date(today) or datetime.date.today()
    try:
        library, templates = load_library(db), load_templates(db)
    except Exception:
        fail("Couldn't load the daily plans. Please try again.", "Daily plan clinician load failed")
        return
    t_need, t_assign, t_build, t_lib = st.tabs(["Who needs you", "Give a patient a plan", "Plan builder", "Library"])

    with t_need:
        st.caption(f"Patients who have been quiet for {QUIET_DAYS}+ days or flagged pain in the last {PAIN_DAYS} days come first.")
        try:
            people = patients_on_plans(db, reports)
        except Exception:
            people = []
            fail("Couldn't load the patients on plans.", "Daily plan patient list failed")
        if not people:
            st.info("Nobody is on a daily plan yet. Use 'Give a patient a plan'.")
        rows = []
        for key, prof in people:
            plan = prof.get("daily_plan") or {}
            try:
                logs = load_logs(db, reports, key, today, days=10)
            except Exception:
                logs = {}
            fl = flags(plan, logs, today)
            tname = templates.get(plan.get("template"), {}).get("name", "Plan")
            rows.append((0 if fl else 1, prof.get("name") or key, tname, day_number(plan.get("start"), today), consistency(logs, today), fl))
        for _, name, tname, n, c, fl in sorted(rows):
            text = []
            for kind, val in fl:
                text.append(f"🟠 quiet {val} days" if kind == "quiet" else f"🔴 pain flagged {val}")
            st.markdown(f"**{name}** · {tname} · day {n} · {c} of last 7 days · " + (", ".join(text) if text else "🟢 on track"))

    with t_assign:
        if not templates:
            st.info("Make a plan in the Plan builder first.")
        else:
            key, prof = pick_patient()
            if key:
                current = (prof or {}).get("daily_plan") or {}
                if current.get("active"):
                    st.caption(f"Currently on {templates.get(current.get('template'), {}).get('name', 'a plan')} since {current.get('start')}.")
                with st.form(f"dp_assign::{key}"):
                    tids = list(templates)
                    tid = st.selectbox("Plan", tids, format_func=lambda t: templates[t].get("name", t),
                                       index=tids.index(current.get("template")) if current.get("template") in tids else 0)
                    start = st.date_input("Start date (day 1)", value=as_date(current.get("start")) or today, format="DD/MM/YYYY")
                    note = st.text_area("A personal note they'll see every day (optional)", value=current.get("note", ""), max_chars=TEXT_MAX)
                    c1, c2 = st.columns(2)
                    go = c1.form_submit_button("Give them this plan", type="primary")
                    stop = c2.form_submit_button("Stop their plan") if current.get("active") else False
                if go:
                    try:
                        assign_plan(db, reports, key, tid, start, note, who)
                        st.success("Done. It appears in their patient portal under 'Your daily plan'.")
                    except Exception:
                        fail("Couldn't give them the plan. Please try again.", "Daily plan assign failed")
                if stop:
                    try:
                        stop_plan(db, reports, key)
                        st.success("Their daily plan is stopped. Their history is kept.")
                    except Exception:
                        fail("Couldn't stop the plan. Please try again.", "Daily plan stop failed")

    with t_build:
        if not library:
            st.info("Add some blocks to your Library first.")
        else:
            _template_editor(st, db, library, templates, who, fail)

    with t_lib:
        _library_editor(st, db, library, who, fail)
