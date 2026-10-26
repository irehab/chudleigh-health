"""Tests for pdf_reader/vald_csv.py, on made-up exports in VALD Hub's Test Metrics format (no real person's data).

    python -I tests/test_vald_csv.py      (or pytest)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdf_reader import vald_csv  # noqa: E402

BOM = "﻿"
CMJ = BOM + '''"Name","ExternalId","Test Type","Date","Time","BW [KG]","Reps","Tags","Additional Load [kg]","Jump Height (Imp-Mom) [cm] ","RSI-modified [m/s] ","Countermovement Depth [cm] ","Concentric Impulse % (Asym) (%)","Peak Landing Force % (Asym) (%)","Some New Metric [N] "
"Test Athlete","","CMJ","26/10/2026","3:04 PM","70.5","5","","0","30.1","0.41","-28.0","7.5 R","12 L","999"
"Test Athlete","","CMJ","01/09/2026","9:15 AM","-1","3","","0","28.4","0.38","-26.5","0 ","3.3 L","998"
"Test Athlete","","CMJ","01/08/2026","12:05 PM","31.0","3","","0","27.0","0.35","-25.0","4 R","2 R","997"
'''
SLSB = BOM + '''"Name","ExternalId","Test Type","Date","Time","BW [KG]","Reps (L)","Reps (R)","Tags","Exercise Length [S] ","Mean Velocity [mm/s] ","Mean Velocity [mm/s] (L)","Mean Velocity [mm/s] (R)","Mean Velocity [mm/s] (Asym)(%)"
"Test Athlete","","SLSB","26/10/2026","1:30 PM","-1","2","2","","15","40.0","44.0","36.0","18 L"
"Test Athlete","","SLSB","26/10/2026","1:30 PM","-1","2","2","","15","40.0","44.0","36.0","18 L"
'''
NOT_VALD = "Date,Steps\n26/10/2026,8000\n"


def test_cmj():
    r = vald_csv.read_csv(CMJ.encode("utf-8"))
    assert not r.problems
    assert [t.date for t in r.tests] == ["2026-10-26", "2026-09-01", "2026-08-01"]
    latest = r.tests[0]
    assert latest.time == "15:04" and latest.body_weight == 70.5 and latest.doc_id == "2026-10-26_1504_CMJ"
    assert latest.metrics["jump_height"]["value"] == 30.1 and latest.metrics["jump_height"]["unit"] == "cm"
    assert latest.metrics["con_impulse_asym"]["value"] == 7.5           # right = positive
    assert latest.metrics["landing_force_asym"]["value"] == -12          # left = negative
    assert vald_csv.display(latest.metrics["landing_force_asym"]) == "12% L"
    assert r.tests[1].metrics["con_impulse_asym"]["value"] == 0 and r.tests[1].body_weight is None and not r.tests[1].notes
    assert r.tests[2].body_weight is None and r.tests[2].notes            # 31 kg: a mis-weigh, flagged
    assert r.tests[1].time == "09:15" and r.tests[2].time == "12:05"
    assert "Some New Metric [N]" in r.unknown_columns
    assert "Power for your body weight" in r.missing["CMJ"]


def test_single_leg_sides_and_duplicates():
    r = vald_csv.read_csv(SLSB.encode("utf-8"))
    assert len(r.tests) == 1                                               # the same test twice is kept once
    m = r.tests[0].metrics
    assert m["mean_velocity_l"]["value"] == 44.0 and m["mean_velocity_r"]["value"] == 36.0
    assert m["mean_velocity_asym"]["value"] == -18 and m["mean_velocity_asym"]["asymmetry"]
    assert "left" in m["mean_velocity_l"]["label"]


def test_not_a_vald_export():
    assert vald_csv.read_csv(NOT_VALD.encode("utf-8")).problems


def test_header_splitting():
    assert vald_csv.split_header("Mean Velocity [mm/s] (L)") == ("mean velocity", "mm/s", "L")
    assert vald_csv.split_header("Concentric Impulse % (Asym) (%)") == ("concentric impulse % (asym)", "%", None)
    assert vald_csv.split_header("Jump Height (Imp-Mom) [cm] ") == ("jump height (imp-mom)", "cm", None)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
