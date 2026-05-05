# Sample lab-report PDFs

Five synthetic lab reports — one per demo patient — for exercising the
Week 2 multimodal pipeline end-to-end.

## What's in here

| File | Patient | FHIR comparison | Demonstrates |
| --- | --- | --- | --- |
| `demo-001_lab_report.pdf` | Margaret Hayes | Matches FHIR exactly | "PDF confirms EMR" baseline. The agent should report consistent values from both sources. |
| `demo-002_lab_report.pdf` | James Whitaker | FHIR has no labs; PDF brings 5 new values | Supplementation. The PDF is the *only* source of recent labs for this patient — extraction unlocks data the EMR doesn't have. |
| `demo-003_lab_report.pdf` | Robert Mitchell | Matches FHIR exactly | Critical-findings confirmation. Both sources show A1c 10.5%, creatinine 1.8 — the agent's threshold-rule engine fires identically against either source. |
| `demo-004_lab_report.pdf` | Linda Chen | Matches FHIR exactly | Drug-interaction monitoring. Quarterly creatinine confirms renal function preserved on chronic NSAID + ACEi. |
| `demo-005_lab_report.pdf` | Sarah Martinez | **Drift**: PDF LDL 95 vs FHIR LDL 88, newer date | Verifier value-mismatch demo. When the agent cites both sources for LDL it should surface the discrepancy via the trace's `value_mismatches`. |

Every PDF carries: lab name, accession, patient demographics (name + DOB
+ MRN), ordering provider, collection date, report date, results table
with reference ranges and flags, provider notes, and an electronic
signature block. ~2 KB each.

## Generating

The PDFs are committed for convenience. To regenerate them after
editing patient data or lab content:

```bash
python scripts/generate_sample_lab_pdfs.py
```

Source: [`scripts/generate_sample_lab_pdfs.py`](../../scripts/generate_sample_lab_pdfs.py).
Uses `fpdf2` (already a dev dependency).

## Using them in the demo

1. Log in as `dr.pavan` (or any account assigned to the patient).
2. Pick the patient on the left.
3. Click **Upload** in the Documents card.
4. Choose `Lab PDF`, drop the matching `{patient_id}_lab_report.pdf`,
   click Upload.
5. Watch the status pill: `Queued -> Extracting -> Ready` (typically
   5-10 s — the Claude vision call dominates).
6. Click the document row to see source PDF beside the schema-validated
   extracted facts (with bbox coordinates).
7. Ask the agent: *"Compare the lab report I just uploaded against the
   chart values."* — for demo-005 in particular the agent should
   surface the LDL discrepancy.

## PHI policy

All values are synthetic. The patient names, MRNs, DOBs, and addresses
do not correspond to any real person. Safe to commit, share, or screen-
share publicly.
