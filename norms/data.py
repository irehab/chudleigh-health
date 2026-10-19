"""Published reference data used to compare a participant's results with people of the same age and sex.

Every number below was copied from the source named beside it, and each source's full citation is kept here so a report can
show it. Nothing here is estimated or remembered: if a table could not be read from the original, it is not included.
When you add a table, add its source to SOURCES, and say in `note` what it can and cannot be used for.

The data is only ever used by comparing a value with a table. No model is asked for a range.
"""

DATA_CHECKED = "11 October 2026"

SOURCES = {
    "nhanes_pulse": {
        "short": "US national health survey (NHANES 1999 to 2008), resting pulse",
        "citation": (
            "Ostchega Y, Porter KS, Hughes J, Dillon CF, Nwankwo T. Resting pulse rate reference data for children, adolescents, and adults: "
            "United States, 1999-2008. National Health Statistics Reports no 41. Hyattsville, MD: National Center for Health Statistics; 2011."
        ),
        "url": "https://www.cdc.gov/nchs/data/nhsr/nhsr041.pdf",
        "population": "About 14,200 US adults aged 20 and over who had no condition or medicine that affects pulse. Pulse counted by a doctor for 30 seconds after 4 minutes seated.",
        "note": "The range used is the 5th to 95th percentile, so 9 in 10 healthy people fall inside it. The report notes that studies have linked a higher resting pulse with a higher chance of cardiovascular disease and of death from any cause.",
    },
    "rijnbeek_ecg": {
        "short": "Dutch healthy-adult ECG study (Rijnbeek 2014)",
        "citation": (
            "Rijnbeek PR, van Herpen G, Bots ML, Man S, Verweij N, Hofman A, Hillege H, Numans ME, Swenne CA, Witteman JCM, Kors JA. "
            "Normal values of the electrocardiogram for ages 16-90 years. Journal of Electrocardiology 2014;47:914-921."
        ),
        "url": "https://doi.org/10.1016/j.jelectrocard.2014.07.022",
        "population": "13,354 cardiologically healthy adults aged 16 to 90 from four Dutch population studies, mostly white. ECGs measured by one computer program.",
        "note": "The range used is the 2nd to 98th percentile, so about 96 in 100 healthy people fall inside it. The oldest group (80 to 89) is too small for reliable limits and is not used. Different ECG machines measure intervals slightly differently.",
    },
    "gallagher_fat": {
        "short": "Healthy body fat ranges (Gallagher 2000)",
        "citation": (
            "Gallagher D, Heymsfield SB, Heo M, Jebb SA, Murgatroyd PR, Sakamoto Y. Healthy percentage body fat ranges: an approach for developing "
            "guidelines based on body mass index. American Journal of Clinical Nutrition 2000;72(3):694-701."
        ),
        "url": "https://doi.org/10.1093/ajcn/72.3.694",
        "population": "1,626 adults with a BMI of 35 or less, measured by laboratory methods. Table 4 (white and African American adults) is used.",
        "note": "The authors call these provisional ranges worked out from BMI limits, not definitive ones. Asian adults have a different table. Body fat from a home or clinic bioimpedance scale can differ from the laboratory methods used here.",
    },
    "who_bmi": {
        "short": "World Health Organization BMI groups",
        "citation": "World Health Organization. Obesity: preventing and managing the global epidemic. WHO Technical Report Series 894. Geneva: WHO; 2000.",
        "url": "https://www.who.int/publications/i/item/9241208945",
        "population": "Adults aged 18 and over.",
        "note": ("BMI is a rough guide. It cannot tell muscle from fat. The WHO table rates the chance of weight-related conditions as average at 18.5 to 24.9, increased at 25 to 29.9 and moderate or higher at 30 and over. "
                 "It says the risk is graded, begins below 25, and can differ between populations."),
    },
    "guh_comorbidities": {
        "short": "Overweight, obesity and related conditions (systematic review 2009)",
        "citation": "The incidence of co-morbidities related to obesity and overweight: a systematic review and meta-analysis. BMC Public Health 2009;9:88.",
        "url": "https://doi.org/10.1186/1471-2458-9-88",
        "population": "A systematic review of studies in adults, covering 18 related conditions.",
        "note": "It found that overweight and obesity are linked with a higher chance of conditions including type 2 diabetes, cardiovascular disease and some cancers. A link in groups of people is not a prediction for one person.",
    },
    "spo2_older": {
        "short": "Oxygen levels in healthy older adults (Rodriguez-Molinero 2013)",
        "citation": (
            "Rodriguez-Molinero A, Narvaiza L, Ruiz J, Galvez-Barron C. Normal respiratory rate and peripheral blood oxygen saturation in the elderly "
            "population. Journal of the American Geriatrics Society 2013;61(12):2238-2240."
        ),
        "url": "https://doi.org/10.1111/jgs.12580",
        "population": "Healthy adults aged over 65 measured at rest with a pulse oximeter. 95% had a reading of 91% or higher.",
        "note": "The limit used is the level that 95 in 100 healthy people in the study were at or above.",
    },
    "spo2_adults": {
        "short": "Typical oxygen levels in healthy adults",
        "citation": (
            "Pulse oximetry values from 33,080 participants in the Apple Heart & Movement Study. npj Digital Medicine 2023 "
            "(introduction: among healthy awake individuals, typical SpO2 values lie in the range of 95 to 99%)."
        ),
        "url": "https://www.nature.com/articles/s41746-023-00851-6",
        "population": "Healthy awake adults at rest.",
        "note": "This is a widely used typical range and not an age- and sex-specific study. A single short reading can be affected by cold hands, movement or nail polish.",
    },
    "age_scanner_printed": {
        "short": "The AGE Reader (Diagnoptics): its own norms, as printed on your report",
        "citation": ("Printed on the participant's AGE Reader (Diagnoptics) measurement report: the average AGE level for their age, how far above or below it they are, "
                     "the BodyAge, and the device's own label."),
        "url": "",
        "population": "The device maker's own reference group, which the report does not publish.",
        "note": "Used exactly as printed on the report. It is not checked against any other reference data.",
    },
    "tanita_bands": {
        "short": "Tanita MC-780MA: the bands on your report",
        "citation": ("Printed on the participant's Tanita MC-780MA report: the phase angle marks (7 degrees healthy, 5 'in-risk/ageing', 2 'severely malnourished'), "
                     "the visceral fat scale (1 to 9 healthy, 10 to 14 high, 15 and above very high), and whether each arm and leg's muscle is within Tanita's normal range."),
        "url": "",
        "population": "The device maker's own reference bands.",
        "note": "Used as printed by Tanita. They are not checked against any other reference data.",
    },
    "clinic_limb_balance": {
        "short": "Left and right muscle balance: the clinic's own guide",
        "citation": ("Chudleigh Health Hub compares the muscle in your left and right arms, and your left and right legs, from your Tanita report. "
                     "A difference of 10% or more is marked as room to improve, and 20% or more as a place to focus first."),
        "url": "",
        "population": "Not taken from a study.",
        "note": "These cut-offs are the clinic's own working guide. They are not a published standard.",
    },
}

# ---- Resting pulse, NHANES 1999-2008, Tables 2 (men) and 3 (women): 5th percentile, median, 95th percentile (beats per minute)
# Age groups as published: 20-39, 40-59, 60-79, 80 and over.
PULSE_GROUPS = [(20, 39, "20 to 39"), (40, 59, "40 to 59"), (60, 79, "60 to 79"), (80, 150, "80 and over")]
PULSE = {
    "male": {"20 to 39": (52, 69, 89), "40 to 59": (52, 68, 90), "60 to 79": (50, 67, 91), "80 and over": (51, 68, 94)},
    "female": {"20 to 39": (57, 74, 95), "40 to 59": (56, 71, 92), "60 to 79": (56, 70, 92), "80 and over": (56, 71, 93)},
}

# ---- ECG, Rijnbeek 2014, Table 2: (lower limit = 2nd percentile, median, upper limit = 98th percentile)
ECG_GROUPS = [(16, 19, "16 to 19"), (20, 29, "20 to 29"), (30, 39, "30 to 39"), (40, 49, "40 to 49"), (50, 59, "50 to 59"), (60, 69, "60 to 69"), (70, 79, "70 to 79")]
_AGE_KEYS = [g[2] for g in ECG_GROUPS]


def _rows(male, female):
    """male and female are lists of (median, 2nd, 98th) in the age-group order above."""
    return {
        "male": {k: (lo, med, hi) for k, (med, lo, hi) in zip(_AGE_KEYS, male)},
        "female": {k: (lo, med, hi) for k, (med, lo, hi) in zip(_AGE_KEYS, female)},
    }


ECG = {
    "ecg_hr": _rows(
        [(73, 49, 107), (65, 45, 94), (65, 46, 95), (66, 47, 95), (67, 48, 94), (67, 48, 95), (67, 50, 99)],
        [(72, 47, 105), (67, 48, 98), (66, 47, 95), (67, 47, 90), (69, 52, 94), (71, 53, 94), (72, 55, 98)],
    ),
    "ecg_pr": _rows(  # the paper's "PQ duration"
        [(148, 118, 200), (150, 118, 196), (152, 118, 198), (152, 115, 200), (160, 124, 206), (164, 126, 220), (164, 129, 228)],
        [(144, 112, 190), (144, 110, 190), (146, 114, 196), (148, 112, 200), (156, 120, 206), (158, 120, 206), (162, 121, 210)],
    ),
    "ecg_qrs": _rows(
        [(100, 82, 126), (100, 80, 126), (100, 78, 124), (100, 78, 122), (100, 80, 124), (100, 80, 124), (101, 80, 131)],
        [(92, 74, 112), (90, 76, 110), (92, 74, 114), (90, 76, 114), (92, 76, 114), (92, 76, 115), (92, 74, 114)],
    ),
    "ecg_qtcb": _rows(  # corrected with the Bazett formula
        [(416, 379, 460), (409, 364, 453), (413, 365, 458), (416, 372, 462), (418, 375, 463), (419, 379, 463), (421, 379, 478)],
        [(429, 382, 473), (418, 374, 458), (419, 377, 464), (421, 379, 468), (427, 391, 472), (429, 391, 473), (432, 396, 476)],
    ),
    "ecg_qtcf": _rows(  # corrected with the Fridericia formula (spelt "Frederica" in the paper's table)
        [(403, 375, 452), (404, 366, 440), (408, 372, 445), (408, 374, 446), (411, 376, 449), (412, 380, 451), (414, 378, 464)],
        [(415, 377, 452), (409, 375, 446), (413, 378, 452), (414, 377, 449), (417, 385, 456), (419, 386, 460), (419, 387, 464)],
    ),
}

# ---- Body fat, Gallagher 2000, Table 4 (white and African American adults): percentage body fat at BMI 18.5, 25 and 30
FAT_GROUPS = [(20, 39, "20 to 39"), (40, 59, "40 to 59"), (60, 79, "60 to 79")]
FAT = {  # (at BMI 18.5, at BMI 25, at BMI 30)
    "female": {"20 to 39": (21, 33, 39), "40 to 59": (23, 34, 40), "60 to 79": (24, 36, 42)},
    "male": {"20 to 39": (8, 20, 25), "40 to 59": (11, 22, 28), "60 to 79": (13, 25, 30)},
}

# ---- BMI, WHO adult groups
BMI_LIMITS = (18.5, 25.0, 30.0)

# ---- Oxygen level (SpO2): lowest value that is usual
SPO2_ADULT_LOWER = 95   # healthy adults under 65 (typical range 95 to 99%)
SPO2_OLDER_LOWER = 91   # healthy adults over 65: 95 in 100 were at or above 91%
SPO2_OLDER_AGE = 65
