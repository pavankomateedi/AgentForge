"""Golden cases — synthetic LLM-response fixtures with expected
verifier + rule-engine outcomes (ARCHITECTURE.md §5.1).

Each case is a 5-tuple: (case_id, retrieval_records, response_text,
expected_verified, expected_rule_ids). The deterministic parts of the
pipeline (verifier + rules engine) are run over the synthetic
response; we assert what verification outcome and rule findings the
case produces.

Why synthetic instead of live LLM calls: the goal here is to
regression-test the deterministic logic across many scenarios cheaply.
Live-LLM coverage lives in eval/live/ (paid, slow); replay cassettes
sit in between (recorded LLM responses, free to replay). This file
covers the edge cases the LLM is most likely to wander into and the
verifier needs to catch — fabrications, transcription errors, vacuous
refusals, sparse data, uncontrolled rule violations.

Use cases covered (mapped to USERS.md):
  UC-1 — pre-visit briefing (multi-tool, full happy path)
  UC-2 — changes since last visit (subset retrieval)
  UC-3 — lab interpretation in context
  UC-4 — medication reconciliation
  UC-5 — authorization-boundary / refusal
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from agent.demo_data import DEMO_PATIENTS
from agent.rules import evaluate_clinical_rules
from agent.verifier import (
    build_record_index,
    collect_source_ids,
    verify_response,
)


# --- Synthetic patient bundles for cases beyond the 2 demo patients ---


def _bundle_demo_001() -> list[dict]:
    p = DEMO_PATIENTS["demo-001"]
    return [
        {"patient": p["patient"]},
        {"problems": p["problem_list"]},
        {"medications": p["medications"]},
        {"labs": p["recent_labs"]},
    ]


def _bundle_demo_002() -> list[dict]:
    p = DEMO_PATIENTS["demo-002"]
    return [
        {"patient": p["patient"]},
        {"problems": p["problem_list"]},
        {"medications": p["medications"]},
        {"labs": p["recent_labs"]},
    ]


def _bundle_uncontrolled_dm() -> list[dict]:
    """Synthetic worst-case: A1c 10.5 + Cr 1.8 + on metformin. Should
    fire three critical rules (A1C_UNCONTROLLED, CREATININE_ELEVATED,
    METFORMIN_RENAL_CONTRAINDICATION)."""
    return [
        {
            "patient": {
                "source_id": "patient-syn-uc",
                "id": "syn-uc",
                "name": "Synthetic Patient",
                "dob": "1955-01-01",
                "sex": "male",
                "mrn": "MRN-SYN-UC",
            }
        },
        {
            "labs": [
                {
                    "source_id": "lab-syn-a1c",
                    "name": "Hemoglobin A1c",
                    "value": 10.5,
                    "unit": "%",
                    "date": "2026-04-01",
                    "flag": "high",
                },
                {
                    "source_id": "lab-syn-cr",
                    "name": "Creatinine",
                    "value": 1.8,
                    "unit": "mg/dL",
                    "date": "2026-04-01",
                    "flag": "high",
                },
            ]
        },
        {
            "medications": [
                {
                    "source_id": "med-syn-met",
                    "name": "Metformin",
                    "dose": "1000 mg",
                    "frequency": "twice daily",
                }
            ]
        },
    ]


def _bundle_meds_only() -> list[dict]:
    """Three meds, no labs, no problems. Tests UC-4 medication
    reconciliation in isolation."""
    return [
        {
            "patient": {
                "source_id": "patient-syn-meds",
                "id": "syn-meds",
                "name": "Med Patient",
                "dob": "1970-01-01",
                "sex": "female",
                "mrn": "MRN-MEDS",
            }
        },
        {
            "medications": [
                {
                    "source_id": "med-syn-lis",
                    "name": "Lisinopril",
                    "dose": "10 mg",
                    "frequency": "daily",
                },
                {
                    "source_id": "med-syn-ibu",
                    "name": "Ibuprofen",
                    "dose": "400 mg",
                    "frequency": "every 6 hours",
                },
            ]
        },
    ]


# --- Case definition ---


@dataclass(frozen=True)
class GoldenCase:
    case_id: str
    use_case: str  # "UC-1" .. "UC-5"
    description: str
    bundle: list[dict]
    response_text: str
    expected_verified: bool
    expected_rule_ids: tuple[str, ...]
    # If non-None, the verifier MUST flag exactly these unknown source ids.
    expected_unknown_ids: tuple[str, ...] | None = None
    # If non-None, the verifier MUST flag a value mismatch on these source ids.
    expected_value_mismatch_ids: tuple[str, ...] | None = None


GOLDEN_CASES: list[GoldenCase] = [
    # ===== UC-1: Pre-visit briefing =====
    GoldenCase(
        case_id="uc1_demo_001_full_briefing",
        use_case="UC-1",
        description="Margaret Hayes happy-path briefing — all 4 tools cited.",
        bundle=_bundle_demo_001(),
        response_text=(
            "Margaret Hayes (DOB 1962-04-14) <source id=\"patient-demo-001\"/> "
            "has T2DM <source id=\"cond-001-1\"/>, HTN <source id=\"cond-001-2\"/>, "
            "and HLD <source id=\"cond-001-3\"/>. On metformin 1000 mg BID "
            "<source id=\"med-001-1\"/>, lisinopril 10 mg daily "
            "<source id=\"med-001-2\"/>, atorvastatin 20 mg qHS "
            "<source id=\"med-001-3\"/>. A1c 7.4% on 2026-03-15 above goal "
            "<source id=\"lab-001-a1c-2026-03\"/>. LDL 92 mg/dL "
            "<source id=\"lab-001-ldl-2026-03\"/> and creatinine 1.0 mg/dL "
            "<source id=\"lab-001-cr-2026-03\"/> normal."
        ),
        expected_verified=True,
        expected_rule_ids=("A1C_ABOVE_GOAL",),
    ),
    GoldenCase(
        case_id="uc1_demo_002_sparse_briefing",
        use_case="UC-1",
        description="James Whitaker briefing — sparse data, no labs section.",
        bundle=_bundle_demo_002(),
        response_text=(
            "James Whitaker <source id=\"patient-demo-002\"/> has chronic "
            "diastolic heart failure <source id=\"cond-002-1\"/>, on "
            "furosemide 40 mg daily <source id=\"med-002-1\"/>. No recent "
            "labs on file — consider rechecking renal function and "
            "electrolytes given diuretic therapy."
        ),
        expected_verified=True,
        expected_rule_ids=(),  # no labs, no rules fire
    ),
    GoldenCase(
        case_id="uc1_uncontrolled_dm_with_renal",
        use_case="UC-1",
        description="Worst-case: critical findings should trigger 3 rules.",
        bundle=_bundle_uncontrolled_dm(),
        response_text=(
            "Patient <source id=\"patient-syn-uc\"/> has uncontrolled type 2 "
            "diabetes with A1c 10.5% <source id=\"lab-syn-a1c\"/>. "
            "Creatinine 1.8 mg/dL indicates renal impairment "
            "<source id=\"lab-syn-cr\"/>, and patient is on metformin "
            "1000 mg twice daily <source id=\"med-syn-met\"/> — risk of "
            "lactic acidosis warrants holding metformin and reassessing."
        ),
        expected_verified=True,
        expected_rule_ids=(
            "A1C_UNCONTROLLED",
            "CREATININE_ELEVATED",
            "METFORMIN_RENAL_CONTRAINDICATION",
        ),
    ),
    # ===== UC-2: Changes since last visit (subset retrieval) =====
    GoldenCase(
        case_id="uc2_meds_only_short_briefing",
        use_case="UC-2",
        description="Subset retrieval — only meds tool. Response cites only meds.",
        bundle=_bundle_meds_only(),
        response_text=(
            "Active medications: lisinopril 10 mg daily "
            "<source id=\"med-syn-lis\"/> and ibuprofen 400 mg q6h "
            "<source id=\"med-syn-ibu\"/>."
        ),
        expected_verified=True,
        expected_rule_ids=("LISINOPRIL_NSAID",),
    ),
    # ===== UC-3: Lab interpretation =====
    GoldenCase(
        case_id="uc3_a1c_focused_answer",
        use_case="UC-3",
        description="Narrow lab question, single-record citation.",
        bundle=_bundle_demo_001(),
        response_text=(
            "Most recent A1c is 7.4% on 2026-03-15 "
            "<source id=\"lab-001-a1c-2026-03\"/>, above the standard "
            "<7.0% goal."
        ),
        expected_verified=True,
        expected_rule_ids=("A1C_ABOVE_GOAL",),
    ),
    GoldenCase(
        case_id="uc3_ldl_focused_answer",
        use_case="UC-3",
        description="LDL within range — no rule fires.",
        bundle=_bundle_demo_001(),
        response_text=(
            "Most recent LDL is 92 mg/dL "
            "<source id=\"lab-001-ldl-2026-03\"/>, at goal."
        ),
        expected_verified=True,
        expected_rule_ids=("A1C_ABOVE_GOAL",),  # rule still fires from full bundle
    ),
    # ===== UC-4: Medication reconciliation =====
    GoldenCase(
        case_id="uc4_med_list_recap",
        use_case="UC-4",
        description="Pure med-list summary, no labs cited.",
        bundle=_bundle_demo_001(),
        response_text=(
            "Active meds: metformin 1000 mg BID "
            "<source id=\"med-001-1\"/>, lisinopril 10 mg daily "
            "<source id=\"med-001-2\"/>, atorvastatin 20 mg qHS "
            "<source id=\"med-001-3\"/>."
        ),
        expected_verified=True,
        expected_rule_ids=("A1C_ABOVE_GOAL",),
    ),
    GoldenCase(
        case_id="uc4_drug_interaction_surfaced",
        use_case="UC-4",
        description="Lisinopril + ibuprofen — interaction rule must fire.",
        bundle=_bundle_meds_only(),
        response_text=(
            "Lisinopril <source id=\"med-syn-lis\"/> and ibuprofen "
            "<source id=\"med-syn-ibu\"/>: NSAIDs may reduce "
            "antihypertensive effect and worsen renal function. Monitor "
            "BP and creatinine."
        ),
        expected_verified=True,
        expected_rule_ids=("LISINOPRIL_NSAID",),
    ),
    # ===== UC-5: Refusal =====
    GoldenCase(
        case_id="uc5_no_data_vacuous_pass",
        use_case="UC-5",
        description="Plain refusal text — no citations, vacuously verified.",
        bundle=_bundle_demo_002(),
        response_text=(
            "I can only answer about the patient currently open in your "
            "chart (demo-002). To look up another patient, please open "
            "their record first."
        ),
        expected_verified=True,
        expected_rule_ids=(),
    ),
    # ===== Failure-mode cases =====
    GoldenCase(
        case_id="fail_fabricated_source_id",
        use_case="UC-1",
        description="LLM cites a record that wasn't in the bundle.",
        bundle=_bundle_demo_001(),
        response_text=(
            "Margaret has an outstanding finding "
            "<source id=\"lab-fabricated-999\"/> that requires follow-up."
        ),
        expected_verified=False,
        expected_rule_ids=("A1C_ABOVE_GOAL",),
        expected_unknown_ids=("lab-fabricated-999",),
    ),
    GoldenCase(
        case_id="fail_value_mismatch_a1c",
        use_case="UC-3",
        description=(
            "Real source id, wrong number — verifier pass-2 must catch."
        ),
        bundle=_bundle_demo_001(),
        response_text=(
            "Most recent A1c is 8.4% "
            "<source id=\"lab-001-a1c-2026-03\"/> — uncontrolled."
        ),
        expected_verified=False,
        expected_rule_ids=("A1C_ABOVE_GOAL",),
        expected_value_mismatch_ids=("lab-001-a1c-2026-03",),
    ),
    GoldenCase(
        case_id="fail_value_mismatch_ldl",
        use_case="UC-3",
        description="LDL transcribed as 192 instead of 92 — caught.",
        bundle=_bundle_demo_001(),
        response_text=(
            "LDL is 192 mg/dL "
            "<source id=\"lab-001-ldl-2026-03\"/>, severely elevated."
        ),
        expected_verified=False,
        expected_rule_ids=("A1C_ABOVE_GOAL",),
        expected_value_mismatch_ids=("lab-001-ldl-2026-03",),
    ),
    GoldenCase(
        case_id="fail_two_unknown_ids",
        use_case="UC-1",
        description="Multiple fabricated ids in one response.",
        bundle=_bundle_demo_001(),
        response_text=(
            "Lab finding <source id=\"lab-ghost-1\"/> and condition "
            "<source id=\"cond-ghost-2\"/> need attention."
        ),
        expected_verified=False,
        expected_rule_ids=("A1C_ABOVE_GOAL",),
        expected_unknown_ids=("cond-ghost-2", "lab-ghost-1"),
    ),
    GoldenCase(
        case_id="pass_real_id_within_tolerance",
        use_case="UC-3",
        description=(
            "Creatinine written as 1.04 (record is 1.0) — within "
            "0.05-absolute tolerance for one-decimal display rounding."
        ),
        bundle=_bundle_demo_001(),
        response_text=(
            "Creatinine is 1.04 mg/dL "
            "<source id=\"lab-001-cr-2026-03\"/>, normal."
        ),
        expected_verified=True,
        expected_rule_ids=("A1C_ABOVE_GOAL",),
    ),
    GoldenCase(
        case_id="pass_no_numeric_claim_with_real_id",
        use_case="UC-1",
        description=(
            "Cites a numeric record but doesn't quote a number in prose — "
            "attribution-only is fine, no value-check fires."
        ),
        bundle=_bundle_demo_001(),
        response_text=(
            "Recent A1c is on file "
            "<source id=\"lab-001-a1c-2026-03\"/> and above goal."
        ),
        expected_verified=True,
        expected_rule_ids=("A1C_ABOVE_GOAL",),
    ),
]


# --- Test runner ---


@pytest.mark.parametrize(
    "case", GOLDEN_CASES, ids=lambda c: f"{c.use_case}:{c.case_id}"
)
def test_golden_case(case: GoldenCase) -> None:
    """For each golden case, run the deterministic verifier + rule
    engine over the synthetic LLM response and the bundle, and assert
    the expected outcomes."""
    retrieved_ids = collect_source_ids(case.bundle)
    record_index = build_record_index(case.bundle)
    verification = verify_response(
        case.response_text, retrieved_ids, record_index
    )

    assert verification.passed == case.expected_verified, (
        f"{case.case_id}: verified drift "
        f"(got {verification.passed}, expected {case.expected_verified}) "
        f"— {verification.note}"
    )

    if case.expected_unknown_ids is not None:
        assert sorted(verification.unknown_ids) == sorted(
            case.expected_unknown_ids
        ), (
            f"{case.case_id}: unknown_ids mismatch "
            f"(got {verification.unknown_ids}, "
            f"expected {case.expected_unknown_ids})"
        )

    if case.expected_value_mismatch_ids is not None:
        actual_mm_ids = sorted(
            mm.source_id for mm in verification.value_mismatches
        )
        assert actual_mm_ids == sorted(
            case.expected_value_mismatch_ids
        ), (
            f"{case.case_id}: value-mismatch ids mismatch "
            f"(got {actual_mm_ids}, "
            f"expected {case.expected_value_mismatch_ids})"
        )

    findings = evaluate_clinical_rules(case.bundle)
    actual_rule_ids = tuple(f.rule_id for f in findings)
    assert sorted(actual_rule_ids) == sorted(case.expected_rule_ids), (
        f"{case.case_id}: rule findings mismatch "
        f"(got {actual_rule_ids}, expected {case.expected_rule_ids})"
    )


def test_golden_case_count_per_uc_meets_minimum() -> None:
    """Coverage check — every UC has at least one golden case. The
    target from the architecture spec is 10/UC * 5 UCs; this test
    makes the gap visible without forcing 50 hand-curated cases
    upfront. Bumping the threshold is the eval-driven improvement
    signal."""
    by_uc: dict[str, int] = {}
    for c in GOLDEN_CASES:
        by_uc[c.use_case] = by_uc.get(c.use_case, 0) + 1

    for uc in ("UC-1", "UC-2", "UC-3", "UC-4", "UC-5"):
        assert by_uc.get(uc, 0) >= 1, (
            f"No golden cases for {uc} — expected at least 1."
        )
    # Total minimum: 15 cases (3x the count of UCs).
    assert sum(by_uc.values()) >= 15, (
        f"Total golden cases ({sum(by_uc.values())}) below threshold (15)."
    )
