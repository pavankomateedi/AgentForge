"""Synthetic demo patient data. NO REAL PHI.

Two patients:
  demo-001 — Margaret Hayes, T2DM + HTN + HLD, recent A1c above goal. The UC-1 demo gold.
  demo-002 — James Whitaker, CHF, sparse data. Tests the "data is silent" handling path.
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
}
