"""Clinical rule engine tests (ARCHITECTURE.md §2.5).

Pure-Python, deterministic. These tests exercise every rule path —
fires-when-it-should and doesn't-fire-when-it-shouldn't — for the
threshold rules, dosage rules, interaction rules, and the cross-rule
that combines metformin status with renal labs.

The rules engine is a domain-constraint enforcement layer alongside the
verifier; together they answer the "grounded outputs beyond basic
filtering" requirement from the case-study doc.
"""

from __future__ import annotations

from agent.demo_data import DEMO_PATIENTS
from agent.rules import (
    RuleFinding,
    _check_dosage,
    _check_interactions,
    _check_lab_thresholds,
    _check_metformin_with_renal,
    _parse_dose_mg,
    evaluate_clinical_rules,
)


# --- Helpers ---


def _ids_by_rule(findings: list[RuleFinding]) -> dict[str, RuleFinding]:
    """Index findings by rule_id; assumes uniqueness in test fixtures."""
    return {f.rule_id: f for f in findings}


def _make_lab(name: str, value: float, source_id: str = "lab-x") -> dict:
    return {"source_id": source_id, "name": name, "value": value}


def _make_med(
    name: str, dose: str = "100 mg", source_id: str = "med-x"
) -> dict:
    return {"source_id": source_id, "name": name, "dose": dose}


# --- Lab thresholds ---


def test_a1c_uncontrolled_fires_above_9() -> None:
    findings = _check_lab_thresholds(
        [_make_lab("Hemoglobin A1c", 9.5, "lab-1")]
    )
    by_id = _ids_by_rule(findings)
    assert "A1C_UNCONTROLLED" in by_id
    assert by_id["A1C_UNCONTROLLED"].severity == "critical"
    assert "9.5" in by_id["A1C_UNCONTROLLED"].message
    assert by_id["A1C_UNCONTROLLED"].evidence_source_ids == ("lab-1",)


def test_a1c_above_goal_fires_in_band() -> None:
    findings = _check_lab_thresholds(
        [_make_lab("Hemoglobin A1c", 7.4)]
    )
    by_id = _ids_by_rule(findings)
    assert "A1C_ABOVE_GOAL" in by_id
    assert "A1C_UNCONTROLLED" not in by_id
    assert by_id["A1C_ABOVE_GOAL"].severity == "warning"


def test_a1c_at_goal_does_not_fire() -> None:
    """Predicate is strictly > 7.0 — exactly 7.0 should not flag."""
    findings = _check_lab_thresholds(
        [_make_lab("Hemoglobin A1c", 7.0)]
    )
    assert findings == []


def test_a1c_just_above_goal_fires_warning_not_critical() -> None:
    findings = _check_lab_thresholds(
        [_make_lab("Hemoglobin A1c", 7.1)]
    )
    by_id = _ids_by_rule(findings)
    assert "A1C_ABOVE_GOAL" in by_id
    assert "A1C_UNCONTROLLED" not in by_id


def test_a1c_at_uncontrolled_threshold_fires_critical() -> None:
    """Predicate is strictly > 9 (so 9.0 → warning), 9.1 → critical."""
    above = _check_lab_thresholds([_make_lab("Hemoglobin A1c", 9.1)])
    assert "A1C_UNCONTROLLED" in _ids_by_rule(above)
    at = _check_lab_thresholds([_make_lab("Hemoglobin A1c", 9.0)])
    # 9.0 is in the warning band (7.0 < v <= 9.0)
    assert "A1C_ABOVE_GOAL" in _ids_by_rule(at)
    assert "A1C_UNCONTROLLED" not in _ids_by_rule(at)


def test_ldl_severe_fires_at_or_above_190() -> None:
    high = _check_lab_thresholds([_make_lab("LDL cholesterol", 200)])
    assert "LDL_SEVERE" in _ids_by_rule(high)
    boundary = _check_lab_thresholds([_make_lab("LDL cholesterol", 190)])
    assert "LDL_SEVERE" in _ids_by_rule(boundary)


def test_ldl_above_target_fires_in_band() -> None:
    findings = _check_lab_thresholds([_make_lab("LDL cholesterol", 150)])
    by_id = _ids_by_rule(findings)
    assert "LDL_ABOVE_TARGET" in by_id
    assert "LDL_SEVERE" not in by_id


def test_ldl_normal_does_not_fire() -> None:
    findings = _check_lab_thresholds([_make_lab("LDL cholesterol", 92)])
    assert findings == []


def test_creatinine_elevated_above_1_5() -> None:
    findings = _check_lab_thresholds([_make_lab("Creatinine", 1.8)])
    assert "CREATININE_ELEVATED" in _ids_by_rule(findings)


def test_creatinine_borderline_in_band() -> None:
    findings = _check_lab_thresholds([_make_lab("Creatinine", 1.3)])
    by_id = _ids_by_rule(findings)
    assert "CREATININE_BORDERLINE" in by_id
    assert "CREATININE_ELEVATED" not in by_id


def test_creatinine_normal_does_not_fire() -> None:
    findings = _check_lab_thresholds([_make_lab("Creatinine", 1.0)])
    assert findings == []


def test_lab_with_no_value_skips_rule_evaluation() -> None:
    """Defensive: a lab that has no `value` shouldn't crash the
    threshold check or produce a finding."""
    findings = _check_lab_thresholds(
        [{"source_id": "lab-1", "name": "Hemoglobin A1c"}]
    )
    assert findings == []


# --- Dosage ---


def test_metformin_in_range_does_not_fire() -> None:
    findings = _check_dosage([_make_med("Metformin", "1000 mg", "m-1")])
    assert findings == []


def test_metformin_above_typical_fires_warning() -> None:
    findings = _check_dosage([_make_med("Metformin", "2200 mg")])
    by_id = _ids_by_rule(findings)
    assert "METFORMIN_DOSE_ABOVE_TYPICAL" in by_id
    assert by_id["METFORMIN_DOSE_ABOVE_TYPICAL"].severity == "warning"


def test_metformin_above_max_fires_critical() -> None:
    findings = _check_dosage([_make_med("Metformin", "3000 mg")])
    by_id = _ids_by_rule(findings)
    assert "METFORMIN_DOSE_ABOVE_MAX" in by_id
    assert by_id["METFORMIN_DOSE_ABOVE_MAX"].severity == "critical"


def test_metformin_below_min_fires_warning() -> None:
    findings = _check_dosage([_make_med("Metformin", "250 mg")])
    by_id = _ids_by_rule(findings)
    assert "METFORMIN_DOSE_BELOW_MIN" in by_id


def test_lisinopril_above_typical_fires_warning() -> None:
    findings = _check_dosage([_make_med("Lisinopril", "60 mg")])
    assert "LISINOPRIL_DOSE_ABOVE_TYPICAL" in _ids_by_rule(findings)


def test_lisinopril_above_hard_max_fires_critical() -> None:
    findings = _check_dosage([_make_med("Lisinopril", "100 mg")])
    assert "LISINOPRIL_DOSE_ABOVE_MAX" in _ids_by_rule(findings)


def test_atorvastatin_in_range_does_not_fire() -> None:
    findings = _check_dosage([_make_med("Atorvastatin", "20 mg")])
    assert findings == []


def test_unparsable_dose_string_is_safe() -> None:
    """Dose like '5 mcg' explicitly returns None from the parser; no
    finding; no crash."""
    findings = _check_dosage([_make_med("Metformin", "5 mcg")])
    assert findings == []


def test_parse_dose_mg_extracts_leading_number() -> None:
    assert _parse_dose_mg("1000 mg") == 1000.0
    assert _parse_dose_mg("10 mg twice daily") == 10.0
    assert _parse_dose_mg("2.5 mg") == 2.5
    assert _parse_dose_mg("not a dose") is None
    assert _parse_dose_mg(None) is None
    assert _parse_dose_mg("5 mcg") is None  # unit mismatch — refuse


# --- Interactions ---


def test_lisinopril_nsaid_interaction_fires() -> None:
    findings = _check_interactions(
        [
            _make_med("Lisinopril", "10 mg", "m-1"),
            _make_med("Ibuprofen", "400 mg", "m-2"),
        ]
    )
    by_id = _ids_by_rule(findings)
    assert "LISINOPRIL_NSAID" in by_id
    # Both source ids surfaced as evidence.
    assert set(by_id["LISINOPRIL_NSAID"].evidence_source_ids) == {
        "m-1",
        "m-2",
    }


def test_metformin_contrast_interaction_is_critical() -> None:
    findings = _check_interactions(
        [
            _make_med("Metformin", "1000 mg"),
            _make_med("Iohexol", "100 mL"),
        ]
    )
    by_id = _ids_by_rule(findings)
    assert "METFORMIN_CONTRAST" in by_id
    assert by_id["METFORMIN_CONTRAST"].severity == "critical"


def test_no_interaction_when_only_one_drug_present() -> None:
    findings = _check_interactions(
        [_make_med("Metformin", "1000 mg")]
    )
    assert findings == []


# --- Cross-rule: metformin + renal ---


def test_metformin_with_elevated_creatinine_is_critical() -> None:
    findings = _check_metformin_with_renal(
        labs=[_make_lab("Creatinine", 1.8, "lab-cr")],
        medications=[_make_med("Metformin", "1000 mg", "m-met")],
    )
    by_id = _ids_by_rule(findings)
    assert "METFORMIN_RENAL_CONTRAINDICATION" in by_id
    assert by_id["METFORMIN_RENAL_CONTRAINDICATION"].severity == "critical"
    # Both records cited as evidence.
    assert set(by_id["METFORMIN_RENAL_CONTRAINDICATION"].evidence_source_ids) == {
        "lab-cr",
        "m-met",
    }


def test_metformin_with_borderline_creatinine_is_warning() -> None:
    findings = _check_metformin_with_renal(
        labs=[_make_lab("Creatinine", 1.3)],
        medications=[_make_med("Metformin", "1000 mg")],
    )
    by_id = _ids_by_rule(findings)
    assert "METFORMIN_RENAL_CAUTION" in by_id


def test_metformin_with_normal_creatinine_no_finding() -> None:
    findings = _check_metformin_with_renal(
        labs=[_make_lab("Creatinine", 1.0)],
        medications=[_make_med("Metformin", "1000 mg")],
    )
    assert findings == []


def test_no_metformin_means_no_cross_rule_even_with_high_creatinine() -> None:
    """The cross-rule is metformin-conditional. High creatinine alone is
    caught by the threshold rule, not the cross-rule."""
    findings = _check_metformin_with_renal(
        labs=[_make_lab("Creatinine", 1.8)],
        medications=[_make_med("Lisinopril", "10 mg")],
    )
    assert findings == []


# --- Top-level evaluate against demo data ---


def _demo_records(patient_id: str) -> list[dict]:
    p = DEMO_PATIENTS[patient_id]
    return [
        {"patient": p["patient"]},
        {"problems": p["problem_list"]},
        {"medications": p["medications"]},
        {"labs": p["recent_labs"]},
    ]


def test_demo_001_fires_only_a1c_above_goal() -> None:
    """Margaret Hayes: A1c 7.4 (warning band), LDL 92 (normal),
    Cr 1.0 (normal), metformin 1000 mg, lisinopril 10 mg, atorvastatin
    20 mg — all in-range. The only finding should be A1C_ABOVE_GOAL.
    This is the rule engine's smoke test against real demo data."""
    findings = evaluate_clinical_rules(_demo_records("demo-001"))
    rule_ids = [f.rule_id for f in findings]
    assert rule_ids == ["A1C_ABOVE_GOAL"]


def test_demo_002_fires_no_rules() -> None:
    """James Whitaker: one condition, one med (furosemide 40 mg in
    range), no labs. No rules should fire."""
    findings = evaluate_clinical_rules(_demo_records("demo-002"))
    assert findings == []


def test_demo_003_fires_four_critical_rules() -> None:
    """Robert Mitchell: uncontrolled diabetic with renal impairment on
    metformin. Designed to fire the maximal set of clinically-relevant
    rules without contrived numbers."""
    findings = evaluate_clinical_rules(_demo_records("demo-003"))
    rule_ids = sorted(f.rule_id for f in findings)
    assert rule_ids == sorted([
        "A1C_UNCONTROLLED",
        "CREATININE_ELEVATED",
        "LDL_ABOVE_TARGET",
        "METFORMIN_RENAL_CONTRAINDICATION",
    ])
    # Three of the four are critical; the LDL one is the lone warning.
    severities = {f.rule_id: f.severity for f in findings}
    assert severities["A1C_UNCONTROLLED"] == "critical"
    assert severities["CREATININE_ELEVATED"] == "critical"
    assert severities["METFORMIN_RENAL_CONTRAINDICATION"] == "critical"
    assert severities["LDL_ABOVE_TARGET"] == "warning"


def test_demo_004_fires_lisinopril_nsaid_interaction() -> None:
    """Linda Chen: hypertension + chronic back pain on lisinopril +
    ibuprofen. Drug-interaction rule should fire; no lab rules."""
    findings = evaluate_clinical_rules(_demo_records("demo-004"))
    rule_ids = [f.rule_id for f in findings]
    assert rule_ids == ["LISINOPRIL_NSAID"]
    assert findings[0].severity == "warning"


def test_demo_005_fires_no_rules() -> None:
    """Sarah Martinez: well-controlled HTN on low-dose lisinopril, all
    labs normal. The 'nothing to see here' baseline."""
    findings = evaluate_clinical_rules(_demo_records("demo-005"))
    assert findings == []


def test_evaluate_is_deterministic() -> None:
    """Same input → identical output every time. Critical for replay
    tests + Langfuse trace stability."""
    records = _demo_records("demo-001")
    a = evaluate_clinical_rules(records)
    b = evaluate_clinical_rules(records)
    assert a == b


def test_evaluate_handles_empty_input() -> None:
    assert evaluate_clinical_rules([]) == []
    assert evaluate_clinical_rules([{}]) == []
    assert evaluate_clinical_rules([{"problems": []}]) == []


def test_synthetic_uncontrolled_diabetes_with_renal_impairment() -> None:
    """A worst-case patient: A1c 10.5, Creatinine 1.8, on metformin.
    Should fire: A1C_UNCONTROLLED (critical), CREATININE_ELEVATED
    (critical), METFORMIN_RENAL_CONTRAINDICATION (critical). This
    exercises the full multi-rule path."""
    records = [
        {
            "labs": [
                {
                    "source_id": "lab-a1c",
                    "name": "Hemoglobin A1c",
                    "value": 10.5,
                },
                {
                    "source_id": "lab-cr",
                    "name": "Creatinine",
                    "value": 1.8,
                },
            ]
        },
        {
            "medications": [
                {
                    "source_id": "med-met",
                    "name": "Metformin",
                    "dose": "1000 mg",
                }
            ]
        },
    ]
    findings = evaluate_clinical_rules(records)
    rule_ids = {f.rule_id for f in findings}
    assert rule_ids == {
        "A1C_UNCONTROLLED",
        "CREATININE_ELEVATED",
        "METFORMIN_RENAL_CONTRAINDICATION",
    }
    # Every finding for this patient is critical.
    assert all(f.severity == "critical" for f in findings)
