"""Tests for daily_plan.py's plain logic (synthetic data only). Run: python tests/test_daily_plan.py"""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import daily_plan as dp  # noqa: E402

D = datetime.date
TPL = dp.STARTER_TEMPLATE


def logs_for(*days_ago, today=D(2026, 11, 24), **extra):
    return {(today - datetime.timedelta(days=i)).isoformat(): {"done": "full", **extra} for i in days_ago}


def test_day_number_and_phase():
    assert dp.day_number("2026-11-13", D(2026, 11, 24)) == 12
    assert dp.day_number("2026-11-25", D(2026, 11, 24)) == 0
    assert dp.phase_for(TPL, 12)["name"] == "Foundations"
    assert dp.phase_for(TPL, 22)["name"] == "Build"
    assert dp.phase_for(TPL, 75)["name"] == "Consolidate"   # after the end: the last phase
    assert dp.phase_for(TPL, 0)["name"] == "Foundations"    # before the start: the first


def test_move_for_day_follows_the_weekday():
    assert dp.move_for_day(TPL, 12, D(2026, 11, 23)) == "s-strength-a"   # a Monday
    assert dp.move_for_day(TPL, 12, D(2026, 11, 29)) == ""               # Sunday is a rest day


def test_consistency_counts_ticks_not_streaks():
    today = D(2026, 11, 24)
    logs = logs_for(0, 1, 3, 4, 6)
    assert dp.consistency(logs, today) == 5
    logs[(today - datetime.timedelta(days=2)).isoformat()] = {"done": "", "checks": ["s-water"]}
    assert dp.consistency(logs, today) == 6   # a ticked habit counts too
    assert dp.consistency({}, today) == 0


def test_quiet_days_and_missed_two():
    today = D(2026, 11, 24)
    assert dp.quiet_days(D(2026, 11, 20), "2026-11-01", today) == 4
    assert dp.quiet_days(today, "2026-11-01", today) == 0
    assert dp.quiet_days(None, "2026-11-22", today) == 3          # never ticked since starting 3 days ago
    assert dp.missed_two(logs_for(3), "2026-11-01", today)
    assert not dp.missed_two(logs_for(1), "2026-11-01", today)
    assert not dp.missed_two({}, "2026-11-23", today)              # the plan only started yesterday


def test_flags_for_the_clinician():
    today = D(2026, 11, 24)
    assert dp.flags({"start": "2026-11-01"}, logs_for(0, 1), today) == []
    assert dp.flags({"start": "2026-11-01"}, logs_for(5), today) == [("quiet", 5)]
    pain = {"2026-11-22": {"done": "busy", "pain": "flag"}}
    assert ("pain", "2026-11-22") in dp.flags({"start": "2026-11-01"}, pain, today)
    assert dp.flags({"start": "2026-11-01", "last_pain": "2026-11-01"}, logs_for(0), today) == []   # old pain drops off
    assert dp.flags({"start": "2026-12-01"}, {}, today) == []     # not started yet: not quiet


def test_next_retest():
    assert dp.next_retest(TPL, 12) == 30
    assert dp.next_retest(TPL, 30) == 30
    assert dp.next_retest(TPL, 61) is None


def test_clean_block():
    b = dp.clean_block({"type": "move", "title": "  Strength   C ", "steps": "Squat 3 x 8\n\n  Row 3 x 10 ", "busy": "10 min"})
    assert b["title"] == "Strength C" and b["steps"] == ["Squat 3 x 8", "Row 3 x 10"] and b["busy"] == "10 min"
    h = dp.clean_block({"type": "habit", "title": "Bed by 10", "steps": "x", "busy": "y"})
    assert h["steps"] == [] and h["busy"] == ""
    for bad in ({"type": "move", "title": " "}, {"type": "nope", "title": "x"}):
        try:
            dp.clean_block(bad)
            raise AssertionError("should have refused")
        except ValueError:
            pass


def test_clean_phases_drops_missing_blocks_and_clamps_days():
    ph = dp.clean_phases([{"name": "B", "from": 30, "to": 99, "week": {"Mon": "gone", "Tue": "a"}, "eat": ["a", "gone"]},
                          {"name": "A", "from": 0, "to": 29}], {"a"}, 60)
    assert [p["name"] for p in ph] == ["A", "B"]
    assert ph[0]["from"] == 1 and ph[1]["to"] == 60
    assert ph[1]["week"]["Mon"] == "" and ph[1]["week"]["Tue"] == "a" and ph[1]["eat"] == ["a"]
    try:
        dp.clean_phases([{"name": "X", "from": 20, "to": 10}], set(), 60)
        raise AssertionError("should have refused")
    except ValueError:
        pass


def test_starter_template_only_uses_starter_blocks():
    ids = set(dp.STARTER_BLOCKS)
    for ph in TPL["phases"]:
        assert all(v in ids for v in ph["week"].values() if v)
        assert set(ph["eat"]) <= ids and set(ph["habits"]) <= ids
    for b in dp.STARTER_BLOCKS.values():
        dp.clean_block(b)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
