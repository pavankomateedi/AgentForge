# Sample patient-intake-form PDFs

Five synthetic intake forms — one per demo patient — for exercising
the multimodal intake-form extraction path end-to-end.

## What's in here

| File | Patient | What the agent extracts | Adds (vs FHIR) |
| --- | --- | --- | --- |
| `demo-001_intake_form.pdf` | Margaret Hayes | Demographics, 3 meds, penicillin allergy (moderate), 3 family-history items, lifestyle notes | Preferred name "Maggie", occupation, energy/shakiness chief concern (not in EMR encounter notes) |
| `demo-002_intake_form.pdf` | James Whitaker | Demographics, 1 med, no allergies, 3 family-history items | Worsening dyspnea + 4 lb weight gain — supplements the sparse FHIR record for this patient |
| `demo-003_intake_form.pdf` | Robert Mitchell | Demographics, 3 meds, sulfa allergy (moderate), 3 family-history items | Diet-disruption context (recent move, fast food) explaining the worsening A1c trend |
| `demo-004_intake_form.pdf` | Linda Chen | Demographics, lisinopril + ibuprofen, latex allergy (mild), family history | NSAID-frequency self-report (more often during work crunch) — context for the LISINOPRIL_NSAID rule |
| `demo-005_intake_form.pdf` | Sarah Martinez | Demographics, lisinopril, no allergies, 3 family-history items | Patient-initiated question about whether to keep lisinopril long-term |

Every form carries: clinic masthead, visit date, demographics block,
chief-concern free text, current-medications table, allergies table,
family-history bullets, lifestyle notes, signature line. ~2.5 KB each.

## Generating

The PDFs are committed for convenience. To regenerate them after
editing the source data:

```bash
python scripts/generate_sample_intake_forms.py
```

Source: [`scripts/generate_sample_intake_forms.py`](../../scripts/generate_sample_intake_forms.py).
Uses `fpdf2`.

## Using them in the demo

1. Log in as `dr.pavan` (or any account assigned to the patient).
2. Pick the patient on the left.
3. Click **Upload** in the Documents card.
4. Switch the document-type dropdown to **Intake form (PDF or image)**.
5. Click **"Use synthetic sample intake form for {patient_id}"** —
   the file pre-fills automatically.
6. Click **Upload**. Status pill: `Queued -> Extracting -> Ready`
   (~5-10 s — Claude vision dominates).
7. Click the document row to see source PDF beside the schema-
   validated extracted facts: `intake_demographics`,
   `intake_chief_concern`, one `intake_medication` per med, one
   `intake_allergy` per allergy, and `intake_family_history` rolled up.
8. Ask the agent: *"What does the intake form say about allergies?"*
   The supervisor should route via `intake_extractor`; the answer
   will cite the `intake-doc-{id}-allergy-{idx}` source IDs from
   `derived_observations`.

## PHI policy

All values are synthetic. Names, MRNs, DOBs, addresses, phone
numbers, and email addresses do not correspond to any real person.
Safe to commit, share, or screen-share publicly.
