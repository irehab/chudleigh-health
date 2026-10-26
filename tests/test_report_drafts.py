"""Tests for report_drafts.py (synthetic data only). Run: python tests/test_report_drafts.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import report_drafts as rd  # noqa: E402
from pdf_reader import vald_csv  # noqa: E402


def test_halves():
    assert rd.half_of("VALD ForceDecks - Countermovement Jump (CMJ)") == rd.FORCE_PLATES
    assert rd.half_of("Tanita Body Composition (MC-780MA)") == rd.HEALTH_CHECKS
    c = rd.counts([{"type": "VALD ForceDecks - Sit-to-Stand"}, {"type": "12-Lead ECG (Electrocardiogram)"}, {"type": "Grip Strength (Dynamometer)"}])
    assert c == {rd.HEALTH_CHECKS: 2, rd.FORCE_PLATES: 1}


def test_merge_keeps_both_devices_and_honours_removals():
    saved = [{"uid": "a", "type": "x"}, {"uid": "b", "type": "y"}]
    local = [{"uid": "a", "type": "x"}, {"uid": "c", "type": "z"}]
    assert [t["uid"] for t in rd.merge_tests(saved, local, set())] == ["a", "b", "c"]
    assert [t["uid"] for t in rd.merge_tests(saved, local, {"b"})] == ["a", "c"]


def test_for_storage_drops_pdf_bytes():
    t = rd.for_storage({"uid": "a", "type": "x", "data": {"k": "1"}, "pdf_bytes": b"%PDF-", "pdf_ref": "fs:a"})
    assert "pdf_bytes" not in t and t["pdf_ref"] == "fs:a"


def test_boxes_from_csv_row():
    row = vald_csv.TestRow(code="CMJ", date="2026-10-26", time="15:04", name="Test Athlete", body_weight=80.0, reps="5",
                           metrics={"jump_height": {"value": 30.0, "unit": "cm"},
                                    "ecc_decel_impulse_asym": {"value": -4.2, "unit": "%", "asymmetry": True},
                                    "con_impulse_asym": {"value": 11.0, "unit": "%", "asymmetry": True}})
    assessment, data = rd.boxes_from_csv_row(row, vald_csv.display)
    assert assessment == "VALD ForceDecks - Countermovement Jump (CMJ)"
    assert data == {"Jump Height": "30 cm", "Braking Impulse Asymmetry": "4.2% L", "Body Weight": "80"}
    only_weight = vald_csv.TestRow(code="STSTS", date="2026-10-26", time="", name="", body_weight=80.0, reps="", metrics={})
    assert rd.boxes_from_csv_row(only_weight, vald_csv.display) is None
    assert rd.boxes_from_csv_row(vald_csv.TestRow(code="PUSHUPT", date="", time="", name="", body_weight=None, reps=""), vald_csv.display) is None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
