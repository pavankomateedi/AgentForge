"""Generate one sample lab-report PDF per demo patient.

Output: `samples/lab_pdfs/{patient_id}_lab_report.pdf`

Each PDF carries one lab event (date + ordering provider + values).
Three deliberate states across the five patients so the agent's demo
covers all the comparison cases:

  - demo-001 / demo-003 / demo-004:
      Values MATCH the corresponding FHIR records exactly
      (the "PDF confirms EMR" baseline case).

  - demo-002:
      FHIR has NO labs on file (sparse-data patient). The PDF brings
      in CHF-relevant labs the EMR doesn't have - the file-based
      extraction supplements FHIR rather than confirming it.

  - demo-005:
      PDF has a SLIGHT DRIFT vs FHIR (LDL 95 vs FHIR 88), with a
      newer collection date. Demonstrates the agent surfacing
      "PDF and EMR disagree on LDL" via the verifier's value-mismatch
      pass when both are cited.

Re-run after editing demo_data.py:
    python scripts/generate_sample_lab_pdfs.py
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fpdf import FPDF


_OUT_DIR = Path(__file__).resolve().parent.parent / "samples" / "lab_pdfs"


@dataclass(frozen=True)
class LabRow:
    test_name: str
    value: str  # carry as string so units like '7.4 %' render clean
    unit: str
    reference_range: str
    flag: str  # 'Normal' | 'High' | 'Low' | 'Critical'


@dataclass(frozen=True)
class SamplePatient:
    patient_id: str
    name: str
    dob: str
    mrn: str
    ordering_provider: str
    lab_name: str
    collection_date: str
    report_date: str
    accession: str
    notes: str
    results: list[LabRow]


PATIENTS: list[SamplePatient] = [
    SamplePatient(
        patient_id="demo-001",
        name="Margaret Hayes",
        dob="1962-04-14",
        mrn="MRN-DEMO-001",
        ordering_provider="Dr. Chen",
        lab_name="Quest Diagnostics",
        collection_date="2026-03-15",
        report_date="2026-03-16",
        accession="ACC-001-2026-03-15",
        notes=(
            "Diabetes follow-up panel. A1c above goal but improved over "
            "two prior readings."
        ),
        results=[
            LabRow("Hemoglobin A1c", "7.4", "%", "< 7.0", "High"),
            LabRow("LDL Cholesterol", "92", "mg/dL", "< 100", "Normal"),
            LabRow("Creatinine", "1.0", "mg/dL", "0.6 - 1.2", "Normal"),
            LabRow("eGFR", "78", "mL/min/1.73m2", "> 60", "Normal"),
        ],
    ),
    SamplePatient(
        patient_id="demo-002",
        name="James Whitaker",
        dob="1955-11-02",
        mrn="MRN-DEMO-002",
        ordering_provider="Dr. Patel",
        lab_name="LabCorp",
        collection_date="2026-04-22",
        report_date="2026-04-23",
        accession="ACC-002-2026-04-22",
        notes=(
            "First labs in 18 months. CHF management labs. NT-proBNP "
            "elevated as expected for chronic HFrEF."
        ),
        results=[
            LabRow("NT-proBNP", "1450", "pg/mL", "< 300", "High"),
            LabRow("Sodium", "138", "mEq/L", "135 - 145", "Normal"),
            LabRow("Potassium", "4.6", "mEq/L", "3.5 - 5.0", "Normal"),
            LabRow("Creatinine", "1.2", "mg/dL", "0.6 - 1.2", "Normal"),
            LabRow("BUN", "22", "mg/dL", "8 - 24", "Normal"),
        ],
    ),
    SamplePatient(
        patient_id="demo-003",
        name="Robert Mitchell",
        dob="1955-08-22",
        mrn="MRN-DEMO-003",
        ordering_provider="Dr. Patel",
        lab_name="LabCorp",
        collection_date="2026-04-12",
        report_date="2026-04-13",
        accession="ACC-003-2026-04-12",
        notes=(
            "Worsening glycemic control and renal function. eGFR < 45 "
            "supports holding metformin per package insert."
        ),
        results=[
            LabRow("Hemoglobin A1c", "10.5", "%", "< 7.0", "High"),
            LabRow("Creatinine", "1.8", "mg/dL", "0.6 - 1.2", "High"),
            LabRow("eGFR", "39", "mL/min/1.73m2", "> 60", "Low"),
            LabRow("LDL Cholesterol", "145", "mg/dL", "< 100", "High"),
        ],
    ),
    SamplePatient(
        patient_id="demo-004",
        name="Linda Chen",
        dob="1971-03-15",
        mrn="MRN-DEMO-004",
        ordering_provider="Dr. Chen",
        lab_name="Quest Diagnostics",
        collection_date="2026-04-08",
        report_date="2026-04-09",
        accession="ACC-004-2026-04-08",
        notes=(
            "Quarterly renal monitoring per chronic NSAID + ACEi "
            "combination. Renal function preserved."
        ),
        results=[
            LabRow("Creatinine", "1.0", "mg/dL", "0.6 - 1.2", "Normal"),
            LabRow("LDL Cholesterol", "95", "mg/dL", "< 100", "Normal"),
            LabRow("Potassium", "4.2", "mEq/L", "3.5 - 5.0", "Normal"),
            LabRow("eGFR", "82", "mL/min/1.73m2", "> 60", "Normal"),
        ],
    ),
    SamplePatient(
        patient_id="demo-005",
        name="Sarah Martinez",
        dob="1981-06-10",
        mrn="MRN-DEMO-005",
        ordering_provider="Dr. Chen",
        lab_name="Quest Diagnostics",
        collection_date="2026-05-01",
        report_date="2026-05-02",
        accession="ACC-005-2026-05-01",
        notes=(
            "Annual screening labs. LDL up modestly from prior "
            "(88 -> 95 mg/dL) - drift demo for the agent's verifier."
        ),
        results=[
            LabRow("Creatinine", "0.9", "mg/dL", "0.6 - 1.2", "Normal"),
            LabRow("LDL Cholesterol", "95", "mg/dL", "< 100", "Normal"),
            LabRow("Glucose (fasting)", "92", "mg/dL", "70 - 99", "Normal"),
            LabRow("TSH", "2.1", "mIU/L", "0.4 - 4.5", "Normal"),
        ],
    ),
]


# ---- PDF rendering ----


_COL_WIDTHS = (60.0, 25.0, 30.0, 35.0, 25.0)
_HEADER_GREY = (235, 235, 235)


def _render_one(p: SamplePatient, out_dir: Path) -> Path:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # --- Lab masthead ---
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, p.lab_name, new_x="LMARGIN", new_y="NEXT", align="L")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, "Outpatient Laboratory Report", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(
        0, 5, f"Accession {p.accession}",
        new_x="LMARGIN", new_y="NEXT",
    )
    pdf.ln(2)

    # --- Patient block ---
    pdf.set_draw_color(180, 180, 180)
    pdf.set_line_width(0.2)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(2)

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(40, 6, "Patient:")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, p.name, new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(40, 6, "Date of Birth:")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, p.dob, new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(40, 6, "MRN:")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, p.mrn, new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(40, 6, "Ordering Provider:")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, p.ordering_provider, new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(40, 6, "Collection Date:")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, p.collection_date, new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(40, 6, "Report Date:")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, p.report_date, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    # --- Results table ---
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Results", new_x="LMARGIN", new_y="NEXT")

    pdf.set_fill_color(*_HEADER_GREY)
    pdf.set_font("Helvetica", "B", 10)
    headers = ("Test", "Value", "Unit", "Reference Range", "Flag")
    for w, label in zip(_COL_WIDTHS, headers):
        pdf.cell(w, 7, label, border=1, fill=True)
    pdf.ln()

    pdf.set_font("Helvetica", "", 10)
    for row in p.results:
        cells = (
            row.test_name,
            row.value,
            row.unit,
            row.reference_range,
            row.flag,
        )
        for w, val in zip(_COL_WIDTHS, cells):
            pdf.cell(w, 7, val, border=1)
        pdf.ln()
    pdf.ln(3)

    # --- Notes ---
    if p.notes:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, "Provider Notes", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(0, 5, p.notes)
        pdf.ln(2)

    # --- Sig block ---
    pdf.set_font("Helvetica", "I", 8)
    pdf.cell(
        0, 5,
        "Electronically signed by Pathology Lab Director. "
        "This report is a synthetic sample for demo use only - no real PHI.",
        new_x="LMARGIN", new_y="NEXT",
    )

    out_path = out_dir / f"{p.patient_id}_lab_report.pdf"
    pdf.output(out_path)
    return out_path


def main() -> None:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    for p in PATIENTS:
        path = _render_one(p, _OUT_DIR)
        print(f"  wrote {path.relative_to(_OUT_DIR.parent.parent)} ({path.stat().st_size} bytes)")
    print(f"\n{len(PATIENTS)} sample lab-report PDFs in {_OUT_DIR}")


if __name__ == "__main__":
    main()
