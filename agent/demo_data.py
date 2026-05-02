"""Synthetic demo patient data. NO REAL PHI.

Five patients, each engineered to exercise a different agent pathway:

  demo-001 — Margaret Hayes (64F, T2DM + HTN + HLD). The UC-1 demo gold.
             Recent A1c 7.4% above goal but not uncontrolled — fires
             the A1C_ABOVE_GOAL warning rule.
  demo-002 — James Whitaker (70M, CHF). Sparse data (no recent labs).
             Tests the "data is silent" handling path; verifier passes
             vacuously, no rules fire.
  demo-003 — Robert Mitchell (70M, uncontrolled T2DM + CKD3 + HTN +
             HLD). Critical-findings demo. A1c 10.5%, creatinine 1.8,
             on metformin — fires four rules (A1C_UNCONTROLLED,
             CREATININE_ELEVATED, LDL_ABOVE_TARGET,
             METFORMIN_RENAL_CONTRAINDICATION). Demonstrates the rule
             engine catching a dangerous med-condition combination.
  demo-004 — Linda Chen (55F, HTN + chronic back pain). Drug-
             interaction demo. On lisinopril + chronic NSAID
             (ibuprofen) — fires LISINOPRIL_NSAID interaction rule.
  demo-005 — Sarah Martinez (45F, well-controlled HTN). Stable-patient
             baseline. Single med (low-dose lisinopril), all labs
             normal. No rules fire — the "nothing changed since last
             visit" headline case.
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
    },
}
