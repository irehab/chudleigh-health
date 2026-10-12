"""Compare a participant's results with published reference data for their age and sex.

    from norms import compare, render_section_html
    comparisons = compare(tests, age=73, sex="male", height_cm=177)   # a list of Comparison objects
    html = render_section_html(comparisons)

All the reference tables, and the full citation for each, are in norms/data.py. See NORMS.md for how to add one.

The participant's traffic-light dashboard is norms/dashboard.py. Its words are in norms/measures.csv and norms/summary.csv. See DASHBOARD.md.
"""
from . import dashboard, data
from .engine import (ABOVE, BELOW, NO_REFERENCE, NORMS_VERSION, REPORTED, WELL_ABOVE, WITHIN, Comparison, compare, comparison_context,
                     for_patient, glance_groups, glance_verdict, measures_from_tests, normalise_sex, summary_sentence, tally)
from .render import bar_html, clinician_table, render_glance_html, render_section_html

__all__ = ["compare", "Comparison", "render_section_html", "clinician_table", "comparison_context", "summary_sentence", "tally",
           "measures_from_tests", "normalise_sex", "for_patient", "glance_groups", "glance_verdict", "render_glance_html", "bar_html", "dashboard", "data", "NORMS_VERSION"]
