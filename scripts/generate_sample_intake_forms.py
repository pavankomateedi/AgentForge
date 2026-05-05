"""Generate one sample patient-intake-form PDF per demo patient.

Output: `samples/intake_forms/{patient_id}_intake_form.pdf`

Each PDF is a realistic outpatient intake form with the sections
the IntakeForm Pydantic schema expects:

  - Patient demographics (name, DOB, sex, MRN, contact)
  - Reason for today's visit / chief concern
  - Current medications (table with name, dose, frequency)
  - Known allergies (table with substance, reaction, severity)
  - Family history (free text)
  - Patient signature + date

Each form carries one or two pieces of detail NOT in the FHIR
record so the agent can demo "intake form adds context the EMR
doesn't have" - preferred name, occupation, family-history color,
chief concern free text.

Re-run after editing demo_data.py:
    python scripts/generate_sample_intake_forms.py
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fpdf import FPDF


_OUT_DIR = Path(__file__).resolve().parent.parent / "samples" / "intake_forms"


@dataclass(frozen=True)
class IntakeMed:
    name: str
    dose: str
    frequency: str


@dataclass(frozen=True)
class IntakeAllergy:
    substance: str
    reaction: str
    severity: str  # Mild | Moderate | Severe | Anaphylactic


@dataclass(frozen=True)
class IntakeForm:
    patient_id: str
    name: str
    preferred_name: str
    dob: str
    sex: str
    mrn: str
    phone: str
    email: str
    occupation: str
    visit_date: str
    chief_concern: str
    current_medications: list[IntakeMed]
    allergies: list[IntakeAllergy]
    family_history: list[str]
    notes: str


FORMS: list[IntakeForm] = [
    IntakeForm(
        patient_id="demo-001",
        name="Margaret Hayes",
        preferred_name="Maggie",
        dob="1962-04-14",
        sex="Female",
        mrn="MRN-DEMO-001",
        phone="(555) 432-7891",
        email="m.hayes@example.com",
        occupation="Retired schoolteacher",
        visit_date="2026-03-15",
        chief_concern=(
            "Diabetes follow-up. Energy has been lower the past few "
            "weeks; sometimes feel shaky in late afternoon. Diet has "
            "been about the same."
        ),
        current_medications=[
            IntakeMed("Metformin", "1000 mg", "Twice daily"),
            IntakeMed("Lisinopril", "10 mg", "Once daily"),
            IntakeMed("Atorvastatin", "20 mg", "Once daily at bedtime"),
        ],
        allergies=[
            IntakeAllergy("Penicillin", "Hives", "Moderate"),
        ],
        family_history=[
            "Mother: Type 2 diabetes (dx age 58); died of MI age 72",
            "Father: Hypertension; died of stroke age 75",
            "Sister: Type 2 diabetes",
        ],
        notes=(
            "Walks 30 minutes 3-4 times per week. Quit smoking 2014. "
            "Drinks 1 glass of wine on weekends."
        ),
    ),
    IntakeForm(
        patient_id="demo-002",
        name="James Whitaker",
        preferred_name="Jim",
        dob="1955-11-02",
        sex="Male",
        mrn="MRN-DEMO-002",
        phone="(555) 219-5530",
        email="jwhitaker@example.com",
        occupation="Retired carpenter",
        visit_date="2026-04-22",
        chief_concern=(
            "Heart failure follow-up. Shortness of breath when climbing "
            "stairs has gotten worse in the last 2 weeks. Mild ankle "
            "swelling. Weight up about 4 pounds since last clinic visit."
        ),
        current_medications=[
            IntakeMed("Furosemide", "40 mg", "Once daily in the morning"),
        ],
        allergies=[],
        family_history=[
            "Father: Coronary artery disease, MI age 68",
            "Mother: Lived to 92, no major cardiac history",
            "Brother: Atrial fibrillation",
        ],
        notes=(
            "Sleeps with two pillows. No paroxysmal nocturnal dyspnea "
            "yet. Limits salt at home but eats out 2-3 times per week."
        ),
    ),
    IntakeForm(
        patient_id="demo-003",
        name="Robert Mitchell",
        preferred_name="Bob",
        dob="1955-08-22",
        sex="Male",
        mrn="MRN-DEMO-003",
        phone="(555) 887-1124",
        email="rmitchell@example.com",
        occupation="Retired truck driver",
        visit_date="2026-04-12",
        chief_concern=(
            "Diabetes appointment. Blood sugars at home have been "
            "running high (200s most mornings). More fatigue. "
            "Increased thirst the past month. Has been less consistent "
            "with diet - a lot of fast food during a recent move."
        ),
        current_medications=[
            IntakeMed("Metformin", "1000 mg", "Twice daily"),
            IntakeMed("Lisinopril", "20 mg", "Once daily"),
            IntakeMed("Atorvastatin", "40 mg", "Once daily at bedtime"),
        ],
        allergies=[
            IntakeAllergy("Sulfa drugs", "Rash", "Moderate"),
        ],
        family_history=[
            "Father: Type 2 diabetes; died of renal failure age 78",
            "Mother: Hypertension and CKD",
            "Two siblings with type 2 diabetes",
        ],
        notes=(
            "Reports occasional foot numbness at night. No vision "
            "changes. Last eye exam 18 months ago."
        ),
    ),
    IntakeForm(
        patient_id="demo-004",
        name="Linda Chen",
        preferred_name="Linda",
        dob="1971-03-15",
        sex="Female",
        mrn="MRN-DEMO-004",
        phone="(555) 552-9013",
        email="linda.chen@example.com",
        occupation="Office manager",
        visit_date="2026-04-08",
        chief_concern=(
            "Blood pressure check and back pain follow-up. The back "
            "pain is manageable with ibuprofen 2-3 times per week, but "
            "I've been taking it more often during work crunch periods."
        ),
        current_medications=[
            IntakeMed("Lisinopril", "10 mg", "Once daily"),
            IntakeMed("Ibuprofen", "400 mg", "Every 6 hours as needed"),
        ],
        allergies=[
            IntakeAllergy("Latex", "Skin rash", "Mild"),
        ],
        family_history=[
            "Mother: Hypertension",
            "Father: No major issues, alive age 78",
            "No diabetes in family",
        ],
        notes=(
            "Walks dog daily. Started yoga 3 months ago for back. "
            "Never smoker. Occasional glass of wine."
        ),
    ),
    IntakeForm(
        patient_id="demo-005",
        name="Sarah Martinez",
        preferred_name="Sarah",
        dob="1981-06-10",
        sex="Female",
        mrn="MRN-DEMO-005",
        phone="(555) 661-4408",
        email="sarah.martinez@example.com",
        occupation="Software engineer",
        visit_date="2026-05-01",
        chief_concern=(
            "Annual wellness visit. Generally feeling well. Wanted to "
            "check in on blood pressure and discuss whether I should "
            "keep taking lisinopril long-term."
        ),
        current_medications=[
            IntakeMed("Lisinopril", "5 mg", "Once daily"),
        ],
        allergies=[],
        family_history=[
            "Mother: Hypertension diagnosed age 50",
            "Father: Hypercholesterolemia",
            "Maternal grandmother: Type 2 diabetes",
        ],
        notes=(
            "Runs 3 times per week. Vegetarian diet. No tobacco, "
            "occasional alcohol. Travels for work approximately one "
            "week per month."
        ),
    ),
]


# ---- PDF rendering ----


def _render_one(form: IntakeForm, out_dir: Path) -> Path:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # --- Clinic masthead ---
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, "Westside Family Medicine", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, "Patient Intake Form", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, f"Visit Date: {form.visit_date}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    pdf.set_draw_color(180, 180, 180)
    pdf.set_line_width(0.2)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(3)

    # --- Demographics ---
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, "Patient Information", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)

    rows = [
        ("Name:", form.name),
        ("Preferred Name:", form.preferred_name),
        ("Date of Birth:", form.dob),
        ("Sex:", form.sex),
        ("MRN:", form.mrn),
        ("Phone:", form.phone),
        ("Email:", form.email),
        ("Occupation:", form.occupation),
    ]
    for label, value in rows:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(40, 6, label)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # --- Reason for visit ---
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, "Reason for Today's Visit / Chief Concern", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 5, form.chief_concern, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # --- Current medications ---
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, "Current Medications", new_x="LMARGIN", new_y="NEXT")
    pdf.set_fill_color(235, 235, 235)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(70, 7, "Name", border=1, fill=True)
    pdf.cell(35, 7, "Dose", border=1, fill=True)
    pdf.cell(0, 7, "Frequency", border=1, fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    if form.current_medications:
        for med in form.current_medications:
            pdf.cell(70, 7, med.name, border=1)
            pdf.cell(35, 7, med.dose, border=1)
            pdf.cell(0, 7, med.frequency, border=1, new_x="LMARGIN", new_y="NEXT")
    else:
        pdf.cell(0, 7, "(None reported)", border=1, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # --- Allergies ---
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, "Known Allergies", new_x="LMARGIN", new_y="NEXT")
    pdf.set_fill_color(235, 235, 235)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(60, 7, "Substance", border=1, fill=True)
    pdf.cell(60, 7, "Reaction", border=1, fill=True)
    pdf.cell(0, 7, "Severity", border=1, fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    if form.allergies:
        for allergy in form.allergies:
            pdf.cell(60, 7, allergy.substance, border=1)
            pdf.cell(60, 7, allergy.reaction, border=1)
            pdf.cell(0, 7, allergy.severity, border=1, new_x="LMARGIN", new_y="NEXT")
    else:
        pdf.cell(0, 7, "No known drug allergies (NKDA)", border=1, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # --- Family history ---
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, "Family History", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    if form.family_history:
        for line in form.family_history:
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(0, 5, f"- {line}", new_x="LMARGIN", new_y="NEXT")
    else:
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(0, 5, "Non-contributory.", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # --- Notes ---
    if form.notes:
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 6, "Lifestyle / Additional Notes", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(0, 5, form.notes, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

    # --- Signature ---
    pdf.set_font("Helvetica", "I", 9)
    pdf.cell(
        0, 5,
        f"Patient signature: {form.name}    "
        f"Date: {form.visit_date}",
        new_x="LMARGIN", new_y="NEXT",
    )
    pdf.set_font("Helvetica", "I", 8)
    pdf.cell(
        0, 5,
        "This form is a synthetic sample for demo use only - no real PHI.",
        new_x="LMARGIN", new_y="NEXT",
    )

    out_path = out_dir / f"{form.patient_id}_intake_form.pdf"
    pdf.output(out_path)
    return out_path


def main() -> None:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    for form in FORMS:
        path = _render_one(form, _OUT_DIR)
        print(f"  wrote {path.relative_to(_OUT_DIR.parent.parent)} ({path.stat().st_size} bytes)")
    print(f"\n{len(FORMS)} sample intake-form PDFs in {_OUT_DIR}")


if __name__ == "__main__":
    main()
