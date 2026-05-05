"""Synthetic demo patient data. NO REAL PHI.

Five patients, each engineered to exercise a different agent pathway:

  demo-001 — Margaret Hayes (64F, T2DM + HTN + HLD). The UC-1 demo gold.
             Recent A1c 7.4% above goal but not uncontrolled — fires
             the A1C_ABOVE_GOAL warning rule. Three encounters showing
             A1c drifting 6.7 → 6.9 → 7.4; the trend powers UC-6
             ("is this trend concerning?").
  demo-002 — James Whitaker (70M, CHF). Sparse data (no recent labs;
             one stale 2024 encounter). Tests the "data is silent"
             handling path; verifier passes vacuously, no rules fire.
  demo-003 — Robert Mitchell (70M, uncontrolled T2DM + CKD3 + HTN +
             HLD). Critical-findings demo. A1c 10.5%, creatinine 1.8,
             on metformin — fires four rules (A1C_UNCONTROLLED,
             CREATININE_ELEVATED, LDL_ABOVE_TARGET,
             METFORMIN_RENAL_CONTRAINDICATION). Trajectory across three
             encounters shows worsening DM + renal function — the
             clearest "what changed" / "is this concerning" pair.
  demo-004 — Linda Chen (55F, HTN + chronic back pain). Drug-
             interaction demo. On lisinopril + chronic NSAID
             (ibuprofen) — fires LISINOPRIL_NSAID interaction rule.
             Mid-2025 encounter records the NSAID start, anchoring
             "what changed since last visit?" with a specific event.
  demo-005 — Sarah Martinez (45F, well-controlled HTN). Stable-patient
             baseline. Single med (low-dose lisinopril), all labs
             normal. No rules fire — the "nothing changed since last
             visit" headline case. Two encounters a year apart confirm
             stability over time.

Each patient has a `recent_encounters` list (newest-first) that the
get_recent_encounters tool returns. Encounter records carry source_id,
date, type, provider, chief_complaint, and assessment_summary. The
verifier walks the same source_id field for citation grounding.
"""

from __future__ import annotations

DEMO_PATIENTS: dict[str, dict] = {
    "demo-001": {
        "patient": {
            "source_id": "patient-demo-001",
            "id": "demo-001",
            "name": "Margaret Hayes",
            "dob": "1962-04-14",
            "sex": "female",
            "mrn": "MRN-DEMO-001",
        },
        "problem_list": [
            {
                "source_id": "cond-001-1",
                "code": "E11.9",
                "description": "Type 2 diabetes mellitus without complications",
                "onset_date": "2018-03-22",
                "status": "active",
            },
            {
                "source_id": "cond-001-2",
                "code": "I10",
                "description": "Essential hypertension",
                "onset_date": "2014-09-08",
                "status": "active",
            },
            {
                "source_id": "cond-001-3",
                "code": "E78.5",
                "description": "Hyperlipidemia",
                "onset_date": "2018-03-22",
                "status": "active",
            },
        ],
        "medications": [
            {
                "source_id": "med-001-1",
                "name": "Metformin",
                "dose": "1000 mg",
                "frequency": "twice daily",
                "started": "2018-03-22",
                "prescriber": "Dr. Chen",
            },
            {
                "source_id": "med-001-2",
                "name": "Lisinopril",
                "dose": "10 mg",
                "frequency": "once daily",
                "started": "2014-09-08",
                "prescriber": "Dr. Chen",
            },
            {
                "source_id": "med-001-3",
                "name": "Atorvastatin",
                "dose": "20 mg",
                "frequency": "once daily at bedtime",
                "started": "2018-04-01",
                "prescriber": "Dr. Chen",
            },
        ],
        "recent_labs": [
            {
                "source_id": "lab-001-a1c-2026-03",
                "name": "Hemoglobin A1c",
                "value": 7.4,
                "unit": "%",
                "reference_range": "<7.0",
                "date": "2026-03-15",
                "flag": "high",
            },
            {
                "source_id": "lab-001-ldl-2026-03",
                "name": "LDL cholesterol",
                "value": 92,
                "unit": "mg/dL",
                "reference_range": "<100",
                "date": "2026-03-15",
                "flag": "normal",
            },
            {
                "source_id": "lab-001-cr-2026-03",
                "name": "Creatinine",
                "value": 1.0,
                "unit": "mg/dL",
                "reference_range": "0.6-1.2",
                "date": "2026-03-15",
                "flag": "normal",
            },
        ],
        # Per-test trend used by get_lab_history. Newest first; the
        # most-recent entry equals the corresponding row in recent_labs.
        # Source ids are unique per (patient, test, date) so each
        # historical value is independently citable by the verifier.
        "lab_history": {
            "a1c": [
                {
                    "source_id": "lab-001-a1c-2026-03",
                    "name": "Hemoglobin A1c",
                    "value": 7.4,
                    "unit": "%",
                    "reference_range": "<7.0",
                    "date": "2026-03-15",
                    "flag": "high",
                },
                {
                    "source_id": "lab-001-a1c-2025-09",
                    "name": "Hemoglobin A1c",
                    "value": 6.9,
                    "unit": "%",
                    "reference_range": "<7.0",
                    "date": "2025-09-12",
                    "flag": "normal",
                },
                {
                    "source_id": "lab-001-a1c-2025-03",
                    "name": "Hemoglobin A1c",
                    "value": 6.7,
                    "unit": "%",
                    "reference_range": "<7.0",
                    "date": "2025-03-08",
                    "flag": "normal",
                },
            ],
            "ldl": [
                {
                    "source_id": "lab-001-ldl-2026-03",
                    "name": "LDL cholesterol",
                    "value": 92,
                    "unit": "mg/dL",
                    "reference_range": "<100",
                    "date": "2026-03-15",
                    "flag": "normal",
                },
                {
                    "source_id": "lab-001-ldl-2025-09",
                    "name": "LDL cholesterol",
                    "value": 88,
                    "unit": "mg/dL",
                    "reference_range": "<100",
                    "date": "2025-09-12",
                    "flag": "normal",
                },
                {
                    "source_id": "lab-001-ldl-2025-03",
                    "name": "LDL cholesterol",
                    "value": 110,
                    "unit": "mg/dL",
                    "reference_range": "<100",
                    "date": "2025-03-08",
                    "flag": "high",
                },
            ],
            "creatinine": [
                {
                    "source_id": "lab-001-cr-2026-03",
                    "name": "Creatinine",
                    "value": 1.0,
                    "unit": "mg/dL",
                    "reference_range": "0.6-1.2",
                    "date": "2026-03-15",
                    "flag": "normal",
                },
                {
                    "source_id": "lab-001-cr-2025-09",
                    "name": "Creatinine",
                    "value": 1.0,
                    "unit": "mg/dL",
                    "reference_range": "0.6-1.2",
                    "date": "2025-09-12",
                    "flag": "normal",
                },
                {
                    "source_id": "lab-001-cr-2025-03",
                    "name": "Creatinine",
                    "value": 0.9,
                    "unit": "mg/dL",
                    "reference_range": "0.6-1.2",
                    "date": "2025-03-08",
                    "flag": "normal",
                },
            ],
        },
        # Newest first. Three encounters show the A1c drifting from
        # 6.7 → 6.9 → 7.4, perfect for UC-6 "is this trend concerning?"
        # follow-ups paired with the lab tool.
        "recent_encounters": [
            {
                "source_id": "enc-001-2026-03",
                "date": "2026-03-15",
                "type": "office visit",
                "provider": "Dr. Chen",
                "chief_complaint": "Diabetes follow-up",
                "assessment_summary": (
                    "T2DM with A1c 7.4 (up from 6.9 in Sept). "
                    "Reinforced dietary adherence and exercise. "
                    "Continue metformin, recheck A1c in 3 months."
                ),
            },
            {
                "source_id": "enc-001-2025-09",
                "date": "2025-09-12",
                "type": "office visit",
                "provider": "Dr. Chen",
                "chief_complaint": "Annual physical",
                "assessment_summary": (
                    "Diabetes well-controlled at A1c 6.9. BP and lipids at goal. "
                    "Continue current regimen."
                ),
            },
            {
                "source_id": "enc-001-2025-03",
                "date": "2025-03-08",
                "type": "office visit",
                "provider": "Dr. Chen",
                "chief_complaint": "Diabetes follow-up",
                "assessment_summary": (
                    "T2DM controlled at A1c 6.7. Statin tolerated. No new concerns."
                ),
            },
        ],
    },
    "demo-002": {
        "patient": {
            "source_id": "patient-demo-002",
            "id": "demo-002",
            "name": "James Whitaker",
            "dob": "1955-11-02",
            "sex": "male",
            "mrn": "MRN-DEMO-002",
        },
        "problem_list": [
            {
                "source_id": "cond-002-1",
                "code": "I50.32",
                "description": "Chronic diastolic heart failure",
                "onset_date": "2022-06-18",
                "status": "active",
            },
        ],
        "medications": [
            {
                "source_id": "med-002-1",
                "name": "Furosemide",
                "dose": "40 mg",
                "frequency": "once daily in the morning",
                "started": "2022-06-18",
                "prescriber": "Dr. Patel",
            },
        ],
        "recent_labs": [],
        # Sparse-data path: a single old encounter, no labs. Tests the
        # "data is silent" handling — the agent must say so without
        # fabricating recency.
        "recent_encounters": [
            {
                "source_id": "enc-002-2024-08",
                "date": "2024-08-22",
                "type": "office visit",
                "provider": "Dr. Patel",
                "chief_complaint": "CHF follow-up",
                "assessment_summary": (
                    "Diastolic CHF stable on furosemide. No new symptoms. "
                    "Patient declined lab work; recheck deferred."
                ),
            },
        ],
    },
    "demo-003": {
        "patient": {
            "source_id": "patient-demo-003",
            "id": "demo-003",
            "name": "Robert Mitchell",
            "dob": "1955-08-22",
            "sex": "male",
            "mrn": "MRN-DEMO-003",
        },
        "problem_list": [
            {
                "source_id": "cond-003-1",
                "code": "E11.65",
                "description": "Type 2 diabetes mellitus with hyperglycemia",
                "onset_date": "2015-04-10",
                "status": "active",
            },
            {
                "source_id": "cond-003-2",
                "code": "I10",
                "description": "Essential hypertension",
                "onset_date": "2010-02-14",
                "status": "active",
            },
            {
                "source_id": "cond-003-3",
                "code": "N18.3",
                "description": "Chronic kidney disease, stage 3",
                "onset_date": "2024-09-05",
                "status": "active",
            },
            {
                "source_id": "cond-003-4",
                "code": "E78.5",
                "description": "Hyperlipidemia",
                "onset_date": "2015-04-10",
                "status": "active",
            },
        ],
        "medications": [
            {
                "source_id": "med-003-1",
                "name": "Metformin",
                "dose": "1000 mg",
                "frequency": "twice daily",
                "started": "2015-04-10",
                "prescriber": "Dr. Patel",
            },
            {
                "source_id": "med-003-2",
                "name": "Lisinopril",
                "dose": "20 mg",
                "frequency": "once daily",
                "started": "2010-02-14",
                "prescriber": "Dr. Patel",
            },
            {
                "source_id": "med-003-3",
                "name": "Atorvastatin",
                "dose": "40 mg",
                "frequency": "once daily at bedtime",
                "started": "2015-04-10",
                "prescriber": "Dr. Patel",
            },
        ],
        "recent_labs": [
            {
                "source_id": "lab-003-a1c-2026-04",
                "name": "Hemoglobin A1c",
                "value": 10.5,
                "unit": "%",
                "reference_range": "<7.0",
                "date": "2026-04-12",
                "flag": "high",
            },
            {
                "source_id": "lab-003-cr-2026-04",
                "name": "Creatinine",
                "value": 1.8,
                "unit": "mg/dL",
                "reference_range": "0.6-1.2",
                "date": "2026-04-12",
                "flag": "high",
            },
            {
                "source_id": "lab-003-ldl-2026-04",
                "name": "LDL cholesterol",
                "value": 145,
                "unit": "mg/dL",
                "reference_range": "<100",
                "date": "2026-04-12",
                "flag": "high",
            },
        ],
        # Worsening trend across all three measures — A1c, creatinine,
        # LDL all rising. The classic "is this concerning?" pattern.
        "lab_history": {
            "a1c": [
                {
                    "source_id": "lab-003-a1c-2026-04",
                    "name": "Hemoglobin A1c",
                    "value": 10.5,
                    "unit": "%",
                    "reference_range": "<7.0",
                    "date": "2026-04-12",
                    "flag": "high",
                },
                {
                    "source_id": "lab-003-a1c-2025-10",
                    "name": "Hemoglobin A1c",
                    "value": 9.2,
                    "unit": "%",
                    "reference_range": "<7.0",
                    "date": "2025-10-04",
                    "flag": "high",
                },
                {
                    "source_id": "lab-003-a1c-2025-04",
                    "name": "Hemoglobin A1c",
                    "value": 8.5,
                    "unit": "%",
                    "reference_range": "<7.0",
                    "date": "2025-04-18",
                    "flag": "high",
                },
            ],
            "creatinine": [
                {
                    "source_id": "lab-003-cr-2026-04",
                    "name": "Creatinine",
                    "value": 1.8,
                    "unit": "mg/dL",
                    "reference_range": "0.6-1.2",
                    "date": "2026-04-12",
                    "flag": "high",
                },
                {
                    "source_id": "lab-003-cr-2025-10",
                    "name": "Creatinine",
                    "value": 1.5,
                    "unit": "mg/dL",
                    "reference_range": "0.6-1.2",
                    "date": "2025-10-04",
                    "flag": "high",
                },
                {
                    "source_id": "lab-003-cr-2025-04",
                    "name": "Creatinine",
                    "value": 1.3,
                    "unit": "mg/dL",
                    "reference_range": "0.6-1.2",
                    "date": "2025-04-18",
                    "flag": "high",
                },
            ],
            "ldl": [
                {
                    "source_id": "lab-003-ldl-2026-04",
                    "name": "LDL cholesterol",
                    "value": 145,
                    "unit": "mg/dL",
                    "reference_range": "<100",
                    "date": "2026-04-12",
                    "flag": "high",
                },
                {
                    "source_id": "lab-003-ldl-2025-10",
                    "name": "LDL cholesterol",
                    "value": 140,
                    "unit": "mg/dL",
                    "reference_range": "<100",
                    "date": "2025-10-04",
                    "flag": "high",
                },
                {
                    "source_id": "lab-003-ldl-2025-04",
                    "name": "LDL cholesterol",
                    "value": 138,
                    "unit": "mg/dL",
                    "reference_range": "<100",
                    "date": "2025-04-18",
                    "flag": "high",
                },
            ],
        },
        # Trajectory: A1c 8.5 → 9.2 → 10.5 and creatinine 1.3 → 1.5 → 1.8
        # over a year. Demonstrates the trend question with a clear
        # worsening signature. Most recent encounter calls out the
        # metformin-renal contraindication, mirrored by the rule engine.
        "recent_encounters": [
            {
                "source_id": "enc-003-2026-04",
                "date": "2026-04-12",
                "type": "office visit",
                "provider": "Dr. Patel",
                "chief_complaint": "Diabetes uncontrolled, fatigue",
                "assessment_summary": (
                    "Diabetes worsening: A1c 10.5 (was 9.2). "
                    "Renal function declining: creatinine 1.8 (was 1.5). "
                    "Discussed metformin contraindication with eGFR <45; "
                    "transitioning off metformin, starting basal insulin. "
                    "Nephrology referral placed."
                ),
            },
            {
                "source_id": "enc-003-2025-10",
                "date": "2025-10-04",
                "type": "office visit",
                "provider": "Dr. Patel",
                "chief_complaint": "Diabetes follow-up",
                "assessment_summary": (
                    "A1c 9.2 (was 8.5). Creatinine 1.5 — early stage CKD "
                    "noted. Continue metformin for now, increase to twice "
                    "daily, recheck in 6 months."
                ),
            },
            {
                "source_id": "enc-003-2025-04",
                "date": "2025-04-18",
                "type": "office visit",
                "provider": "Dr. Patel",
                "chief_complaint": "Annual physical",
                "assessment_summary": (
                    "A1c 8.5, suboptimal. Creatinine 1.3, borderline. "
                    "Counseled on diet; medication unchanged."
                ),
            },
        ],
    },
    "demo-004": {
        "patient": {
            "source_id": "patient-demo-004",
            "id": "demo-004",
            "name": "Linda Chen",
            "dob": "1971-03-15",
            "sex": "female",
            "mrn": "MRN-DEMO-004",
        },
        "problem_list": [
            {
                "source_id": "cond-004-1",
                "code": "I10",
                "description": "Essential hypertension",
                "onset_date": "2018-06-20",
                "status": "active",
            },
            {
                "source_id": "cond-004-2",
                "code": "M54.5",
                "description": "Low back pain",
                "onset_date": "2023-01-12",
                "status": "active",
            },
        ],
        "medications": [
            {
                "source_id": "med-004-1",
                "name": "Lisinopril",
                "dose": "10 mg",
                "frequency": "once daily",
                "started": "2018-06-20",
                "prescriber": "Dr. Chen",
            },
            {
                "source_id": "med-004-2",
                "name": "Ibuprofen",
                "dose": "400 mg",
                "frequency": "every 6 hours as needed",
                "started": "2023-01-12",
                "prescriber": "Dr. Chen",
            },
        ],
        "recent_labs": [
            {
                "source_id": "lab-004-cr-2026-04",
                "name": "Creatinine",
                "value": 1.0,
                "unit": "mg/dL",
                "reference_range": "0.6-1.2",
                "date": "2026-04-08",
                "flag": "normal",
            },
            {
                "source_id": "lab-004-ldl-2026-04",
                "name": "LDL cholesterol",
                "value": 95,
                "unit": "mg/dL",
                "reference_range": "<100",
                "date": "2026-04-08",
                "flag": "normal",
            },
        ],
        # Stable creatinine pre/post NSAID start — the trend itself is
        # the answer to "is the NSAID hurting her kidneys yet?".
        "lab_history": {
            "creatinine": [
                {
                    "source_id": "lab-004-cr-2026-04",
                    "name": "Creatinine",
                    "value": 1.0,
                    "unit": "mg/dL",
                    "reference_range": "0.6-1.2",
                    "date": "2026-04-08",
                    "flag": "normal",
                },
                {
                    "source_id": "lab-004-cr-2025-08",
                    "name": "Creatinine",
                    "value": 0.9,
                    "unit": "mg/dL",
                    "reference_range": "0.6-1.2",
                    "date": "2025-08-15",
                    "flag": "normal",
                },
                {
                    "source_id": "lab-004-cr-2025-02",
                    "name": "Creatinine",
                    "value": 0.9,
                    "unit": "mg/dL",
                    "reference_range": "0.6-1.2",
                    "date": "2025-02-22",
                    "flag": "normal",
                },
            ],
            "ldl": [
                {
                    "source_id": "lab-004-ldl-2026-04",
                    "name": "LDL cholesterol",
                    "value": 95,
                    "unit": "mg/dL",
                    "reference_range": "<100",
                    "date": "2026-04-08",
                    "flag": "normal",
                },
                {
                    "source_id": "lab-004-ldl-2025-02",
                    "name": "LDL cholesterol",
                    "value": 102,
                    "unit": "mg/dL",
                    "reference_range": "<100",
                    "date": "2025-02-22",
                    "flag": "high",
                },
            ],
        },
        # Mid-2025 encounter is when the NSAID was prescribed — gives
        # the agent a "what changed since last visit" answer with a
        # specific medication-onset event and an interaction that the
        # rule engine flags concurrently.
        "recent_encounters": [
            {
                "source_id": "enc-004-2026-04",
                "date": "2026-04-08",
                "type": "office visit",
                "provider": "Dr. Chen",
                "chief_complaint": "BP check, low back pain",
                "assessment_summary": (
                    "BP well-controlled on lisinopril. Back pain ongoing, "
                    "managed with PRN ibuprofen. Reviewed NSAID-ACEi "
                    "interaction risk; patient prefers to continue and "
                    "monitor renal function quarterly."
                ),
            },
            {
                "source_id": "enc-004-2025-08",
                "date": "2025-08-15",
                "type": "office visit",
                "provider": "Dr. Chen",
                "chief_complaint": "Persistent low back pain",
                "assessment_summary": (
                    "Mechanical low back pain, no red flags. Started PRN "
                    "ibuprofen 400mg q6h. Counseled on physical therapy."
                ),
            },
            {
                "source_id": "enc-004-2025-02",
                "date": "2025-02-22",
                "type": "office visit",
                "provider": "Dr. Chen",
                "chief_complaint": "Annual physical",
                "assessment_summary": (
                    "Hypertension well-controlled. No new concerns."
                ),
            },
        ],
    },
    "demo-005": {
        "patient": {
            "source_id": "patient-demo-005",
            "id": "demo-005",
            "name": "Sarah Martinez",
            "dob": "1981-06-10",
            "sex": "female",
            "mrn": "MRN-DEMO-005",
        },
        "problem_list": [
            {
                "source_id": "cond-005-1",
                "code": "I10",
                "description": "Essential hypertension",
                "onset_date": "2020-11-03",
                "status": "active",
            },
        ],
        "medications": [
            {
                "source_id": "med-005-1",
                "name": "Lisinopril",
                "dose": "5 mg",
                "frequency": "once daily",
                "started": "2020-11-03",
                "prescriber": "Dr. Chen",
            },
        ],
        "recent_labs": [
            {
                "source_id": "lab-005-cr-2026-03",
                "name": "Creatinine",
                "value": 0.9,
                "unit": "mg/dL",
                "reference_range": "0.6-1.2",
                "date": "2026-03-22",
                "flag": "normal",
            },
            {
                "source_id": "lab-005-ldl-2026-03",
                "name": "LDL cholesterol",
                "value": 88,
                "unit": "mg/dL",
                "reference_range": "<100",
                "date": "2026-03-22",
                "flag": "normal",
            },
        ],
        # Two normal readings a year apart — the "nothing has changed"
        # baseline that makes the trend tools work for a stable patient.
        "lab_history": {
            "creatinine": [
                {
                    "source_id": "lab-005-cr-2026-03",
                    "name": "Creatinine",
                    "value": 0.9,
                    "unit": "mg/dL",
                    "reference_range": "0.6-1.2",
                    "date": "2026-03-22",
                    "flag": "normal",
                },
                {
                    "source_id": "lab-005-cr-2025-04",
                    "name": "Creatinine",
                    "value": 0.9,
                    "unit": "mg/dL",
                    "reference_range": "0.6-1.2",
                    "date": "2025-04-15",
                    "flag": "normal",
                },
            ],
            "ldl": [
                {
                    "source_id": "lab-005-ldl-2026-03",
                    "name": "LDL cholesterol",
                    "value": 88,
                    "unit": "mg/dL",
                    "reference_range": "<100",
                    "date": "2026-03-22",
                    "flag": "normal",
                },
                {
                    "source_id": "lab-005-ldl-2025-04",
                    "name": "LDL cholesterol",
                    "value": 90,
                    "unit": "mg/dL",
                    "reference_range": "<100",
                    "date": "2025-04-15",
                    "flag": "normal",
                },
            ],
        },
        # Two clean encounters a year apart — the "stable patient,
        # nothing changed" headline answer for UC-2.
        "recent_encounters": [
            {
                "source_id": "enc-005-2026-03",
                "date": "2026-03-22",
                "type": "office visit",
                "provider": "Dr. Chen",
                "chief_complaint": "Annual physical",
                "assessment_summary": (
                    "BP 122/78, well-controlled on lisinopril. Labs at goal. "
                    "No new concerns. Continue current regimen."
                ),
            },
            {
                "source_id": "enc-005-2025-04",
                "date": "2025-04-15",
                "type": "office visit",
                "provider": "Dr. Chen",
                "chief_complaint": "Annual physical",
                "assessment_summary": (
                    "Hypertension well-controlled. All labs normal. "
                    "No medication changes."
                ),
            },
        ],
    },
}
