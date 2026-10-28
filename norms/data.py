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
                     "the visceral fat scale (1 to 9 healthy, 10 to 14 high, 15 and above very high), whether each arm and leg's muscle is within Tanita's normal range, "
                     "and the leg muscle score chart (the line expected for each age)."),
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
    "ewgsop2": {
        "short": "Low muscle: the European sarcopenia guidance (EWGSOP2, 2019)",
        "citation": ("Cruz-Jentoft AJ, Bahat G, Bauer J, et al. Sarcopenia: revised European consensus on definition and diagnosis. "
                     "Age and Ageing 2019;48(1):16-31. Table 3: low muscle quantity is arm and leg muscle (appendicular skeletal muscle) under 20 kg "
                     "for men and 15 kg for women, or under 7.0 kg/m2 for men and 5.5 kg/m2 for women once divided by height squared."),
        "url": "https://doi.org/10.1093/ageing/afy169",
        "population": "A consensus of European experts, drawing on studies of older adults. The cut-offs come mainly from DXA scans.",
        "note": ("A body composition scale estimates muscle in a different way from DXA, and hydration can affect it, so the result is a guide. "
                 "The guidance looks at muscle strength first, and muscle quantity second."),
    },
    "dodds_2014": {
        "short": "Grip strength for your age and sex (UK, Dodds 2014)",
        "citation": ("Dodds RM, Syddall HE, Cooper R, et al. Grip strength across the life course: normative data from twelve British studies. "
                     "PLoS One 2014;9(12):e113637. Table 2."),
        "url": "https://doi.org/10.1371/journal.pone.0113637",
        "population": "About 50,000 people in Great Britain aged 4 to 90, from 12 studies. Most were measured seated, and the best try was used.",
        "note": ("The line for low grip (27 kg for men, 16 kg for women) is 2.5 standard deviations below young adult peak strength. "
                 "The European sarcopenia guidance uses the same line."),
    },
    "spiro_printed": {
        "short": "Breathing test: the predicted values printed by your spirometer",
        "citation": ("The predicted value, lower limit of normal and z-score for each result are worked out by your spirometer's software from your age, "
                     "sex, height and ethnic origin, and printed on your report."),
        "url": "",
        "population": "The reference group set in the spirometer's software.",
        "note": "A z-score of -1.645 or above is within the expected range: about 95 in 100 healthy people of your age, sex and height are above that line.",
    },
    "ers_ats_2022": {
        "short": "How breathing test results are judged (ERS/ATS 2022)",
        "citation": ("Stanojevic S, Kaminsky DA, Miller MR, et al. ERS/ATS technical standard on interpretive strategies for routine lung function tests. "
                     "European Respiratory Journal 2022;60(1):2101499."),
        "url": "https://doi.org/10.1183/13993003.01499-2021",
        "population": "An international standard from the European Respiratory Society and the American Thoracic Society.",
        "note": ("Results are judged by z-scores. -1.645 or above is within the expected range. Between -1.65 and -2.5 is mildly below it, "
                 "-2.5 to -4 moderately, and under -4 severely."),
    },
    "friend_2015": {
        "short": "Fitness for your age and sex (FRIEND registry 2015)",
        "citation": ("Kaminsky LA, Arena R, Myers J. Reference standards for cardiorespiratory fitness measured with cardiopulmonary exercise testing: "
                     "data from the Fitness Registry and the Importance of Exercise National Database. Mayo Clinic Proceedings 2015;90(11):1515-1523. Table 3."),
        "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC4919021/",
        "population": "7,783 maximal treadmill tests of US adults aged 20 to 79 without heart disease, with oxygen use measured directly.",
        "note": "Your number is an estimate, while these people were measured on a treadmill, so where you sit is a guide. People aged 80 and over are compared with the 70 to 79 group.",
    },
    "jackson_1990": {
        "short": "Estimating fitness without an exercise test (Jackson 1990)",
        "citation": ("Jackson AS, Blair SN, Mahar MT, Wier LT, Ross RM, Stuteville JE. Prediction of functional aerobic capacity without exercise testing. "
                     "Medicine and Science in Sports and Exercise 1990;22(6):863-870. It uses your activity rating (0 to 7), age, sex and body fat (or BMI)."),
        "url": "https://pubmed.ncbi.nlm.nih.gov/2287267/",
        "population": "2,009 adults, mostly men (about 1 in 10 were women). The estimates were within about 5 ml/kg/min of the measured values for most people.",
        "note": ("An estimate, not a measurement. Body fat in the original study was measured with skinfolds, and a body composition scale can differ. "
                 "A treadmill or bike test with breathing measurement gives the real number."),
    },
    "clinic_longevity_age": {
        "short": "Longevity age: an average of your device age estimates",
        "citation": ("Chudleigh Health Hub takes the average of the age estimates your devices give, the Tanita's metabolic age and the AGE Reader's BodyAge, "
                     "and compares it with your actual age."),
        "url": "",
        "population": "Not taken from a study. Each device uses its own reference group.",
        "note": "A simple summary to follow over time. It is not a validated measure of biological ageing.",
    },
    "ace_essential_fat": {
        "short": "Essential body fat (American Council on Exercise)",
        "citation": ("The American Council on Exercise body fat categories: essential fat is about 2 to 5% for men and 10 to 13% for women, "
                     "athletes about 6 to 13% for men and 14 to 20% for women."),
        "url": "https://www.acefitness.org/resources/everyone/tools-calculators/percent-body-fat-calculator/",
        "population": "Not a single study. A widely used guide from a fitness education body.",
        "note": ("Chudleigh Health Hub uses the top of the essential range (5% for men, 13% for women) as its line for very low body fat. "
                 "Between that line and the healthy range is shown as lean, not as something to work on: the clinic's own working guide."),
    },
    "clinic_age_profile": {
        "short": "Longevity age: the age your results match",
        "citation": ("Chudleigh Health Hub turns each result into the age at which an average person of your sex has that result, using the published "
                     "data listed here. Your longevity age is a weighted average of those ages: fitness counts 3 times (2 when it is estimated), "
                     "strength twice, and lungs, skin and the Tanita's metabolic age once each. Ages are kept between 20 and 80."),
        "url": "",
        "population": "Not taken from a single study. Each part uses its own reference data.",
        "note": ("A summary to follow over time, and a starting point for a conversation. It is not a validated measure of biological ageing, "
                 "and the weights are the clinic's own choice. Fitness counts most because it is one of the strongest signs of long-term health."),
    },
    "nes_fitness_age": {
        "short": "Fitness age (Nes 2014, the HUNT study)",
        "citation": ("Nes BM, Vatten LJ, Nauman J, Janszky I, Wisloff U. A simple nonexercise model of cardiorespiratory fitness predicts long-term mortality. "
                     "Medicine and Science in Sports and Exercise 2014;46(6):1159-1165."),
        "url": "https://doi.org/10.1249/MSS.0000000000000219",
        "population": "About 37,000 Norwegian adults followed for around 24 years.",
        "note": ("The idea of a fitness age: the age at which your fitness is average. Here it is worked out from the FRIEND treadmill medians, "
                 "not from the HUNT tables."),
    },
    "morris_lung_age": {
        "short": "Lung age (Morris and Temple 1985)",
        "citation": ("Morris JF, Temple W. Spirometric 'lung age' estimation for motivating smoking cessation. Preventive Medicine 1985;14(5):655-662. "
                     "Lung age from height and FEV1: men 2.87 x height (inches) - 31.25 x FEV1 (litres) - 39.375; "
                     "women 3.56 x height (inches) - 40 x FEV1 (litres) - 77.28."),
        "url": "https://doi.org/10.1016/0091-7435(85)90085-4",
        "population": "Healthy non-smoking adults in Oregon, USA.",
        "note": "A guide to follow over time. A poor-quality breathing test can make the lung age read older than it is.",
    },
    "vald_hub_norms": {
        "short": "VALD Hub: percentiles for your age and sex",
        "citation": ("The percentiles shown in VALD Hub for your ForceDecks results, which compare them with VALD's own reference data for people "
                     "of the same age and sex. Your clinician copies them into this report."),
        "url": "",
        "population": "VALD's own database of ForceDecks tests. Its make-up is not shown in the report.",
        "note": "Used as shown in VALD Hub. The 25th percentile or above is shown green, the 10th to 24th amber and below the 10th red: the clinic's own choice.",
    },
    "vald_asymmetry": {
        "short": "Left and right sides on the force plates",
        "citation": ("VALD ForceDecks measures each leg on its own plate. The difference between the sides is given as a percentage of the stronger side. "
                     "A difference of 10% or more is marked as room to improve, and 20% or more as a place to focus first."),
        "url": "",
        "population": "Not taken from a study.",
        "note": "These cut-offs are the clinic's own working guide. They are not a published standard.",
    },
    "asymmetry_review": {
        "short": "How big a difference between sides matters (Parkinson 2021)",
        "citation": ("Parkinson AO, Apps CL, Morris JG, Barnett CT, Lewis MGC. The calculation, thresholds and reporting of inter-limb strength asymmetry: "
                     "a systematic review. Journal of Sports Science and Medicine 2021;20:594-617."),
        "url": "https://doi.org/10.52082/jssm.2021.594",
        "population": "A review of 53 studies of strength differences between the left and right sides.",
        "note": ("Cut-offs of 10 to 15% are widely used, but the review found they are not always backed by evidence. "
                 "A difference is most useful compared with your own earlier results in the same test."),
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

# ---- Very low body fat: the top of the American Council on Exercise's essential fat range. Below the healthy range but at or above this is 'lean'.
ESSENTIAL_FAT_LINE = {"male": 5.0, "female": 13.0}

# ---- Longevity age (the clinic's age profile): the weight each part carries, and the youngest and oldest age shown
AGE_WEIGHTS = {"fitness": 3.0, "fitness_est": 2.0, "strength": 2.0, "lungs": 1.0, "skin": 1.0, "body": 1.0}
AGE_LIMITS = (20, 80)
# Morris and Temple 1985 lung age: (x height in inches, x FEV1 in litres, constant)
MORRIS_LUNG_AGE = {"male": (2.87, -31.25, -39.375), "female": (3.56, -40.0, -77.28)}

# ---- BMI, WHO adult groups
BMI_LIMITS = (18.5, 25.0, 30.0)
# ---- EWGSOP2 (Cruz-Jentoft 2019) Table 3: low muscle quantity. {sex: (ASM kg below which is low, ASM / height squared kg/m2 below which is low)}
EWGSOP2_LOW_MUSCLE = {"male": (20.0, 7.0), "female": (15.0, 5.5)}
# EWGSOP2 Table 3: low muscle strength, grip under 27 kg for men and 16 kg for women (Dodds 2014: 2.5 SD below the young adult peak)
EWGSOP2_LOW_GRIP = {"male": 27.0, "female": 16.0}
# ---- Grip strength, UK: Dodds et al. PLoS One 2014;9(12):e113637, Table 2 (kg). {age: (10th, 25th, 50th, 75th, 90th centile)} at each exact age.
DODDS_CENTILES = (10, 25, 50, 75, 90)
DODDS_GRIP = {
    "male": {20: (30, 35, 40, 46, 52), 25: (36, 41, 48, 55, 61), 30: (38, 44, 51, 58, 64), 35: (39, 45, 51, 58, 64), 40: (38, 44, 50, 57, 63),
             45: (36, 42, 49, 56, 61), 50: (35, 41, 48, 54, 60), 55: (34, 40, 47, 53, 59), 60: (33, 39, 45, 51, 56), 65: (31, 37, 43, 48, 53),
             70: (29, 34, 39, 44, 49), 75: (26, 31, 35, 41, 45), 80: (23, 27, 32, 37, 42), 85: (19, 24, 29, 33, 38), 90: (16, 20, 25, 29, 33)},
    "female": {20: (21, 24, 28, 32, 36), 25: (23, 26, 30, 35, 38), 30: (24, 27, 31, 35, 39), 35: (23, 27, 31, 35, 39), 40: (23, 27, 31, 35, 39),
               45: (22, 26, 30, 34, 38), 50: (21, 25, 29, 33, 37), 55: (19, 23, 28, 32, 35), 60: (18, 22, 27, 31, 34), 65: (17, 21, 25, 29, 33),
               70: (16, 20, 24, 27, 31), 75: (14, 18, 21, 25, 28), 80: (13, 16, 19, 23, 26), 85: (11, 14, 17, 20, 23), 90: (9, 11, 14, 17, 20)},
}

# ---- VO2max reference: FRIEND registry 2015 (Kaminsky et al., Mayo Clin Proc 2015;90(11):1515-23), Table 3, treadmill, directly measured,
# 7783 maximal tests of US adults aged 20-79 without cardiovascular disease. Percentiles 5, 10, 25, 50, 75, 90, 95 (mL O2/kg/min).
FRIEND_PERCENTILES = (5, 10, 25, 50, 75, 90, 95)
FRIEND_TREADMILL = {
    "male": {(20, 29): (29.0, 32.1, 40.1, 48.0, 55.2, 61.8, 66.3), (30, 39): (27.2, 30.2, 35.9, 42.4, 49.2, 56.5, 59.8),
             (40, 49): (24.2, 26.8, 31.9, 37.8, 45.0, 52.1, 55.6), (50, 59): (20.9, 22.8, 27.1, 32.6, 39.7, 45.6, 50.7),
             (60, 69): (17.4, 19.8, 23.7, 28.2, 34.5, 40.3, 43.0), (70, 79): (16.3, 17.1, 20.4, 24.4, 30.4, 36.6, 39.7)},
    "female": {(20, 29): (21.7, 23.9, 30.5, 37.6, 44.7, 51.3, 56.0), (30, 39): (19.0, 20.9, 25.3, 30.2, 36.1, 41.4, 45.8),
               (40, 49): (17.0, 18.8, 22.1, 26.7, 32.4, 38.4, 41.7), (50, 59): (16.0, 17.3, 19.9, 23.4, 27.6, 32.0, 35.9),
               (60, 69): (13.4, 14.6, 17.2, 20.0, 23.8, 27.0, 29.4), (70, 79): (13.1, 13.6, 15.6, 18.3, 20.8, 23.1, 24.1)},
}
# ---- VO2max estimated without exercise (Jackson et al. 1990, Med Sci Sports Exerc 22:863-870), from the physical activity rating (PA-R, 0-7),
# age, sex (1 men, 0 women) and percent body fat, or BMI when there is no body fat. (constant, PA-R, age, body fat or BMI, sex)
JACKSON_FAT = (50.513, 1.589, -0.289, -0.522, 5.863)
JACKSON_BMI = (56.363, 1.921, -0.381, -0.754, 10.987)

# ---- Oxygen level (SpO2): lowest value that is usual
SPO2_ADULT_LOWER = 95   # healthy adults under 65 (typical range 95 to 99%)
SPO2_OLDER_LOWER = 91   # healthy adults over 65: 95 in 100 were at or above 91%
SPO2_OLDER_AGE = 65
