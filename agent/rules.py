"""Clinical rule engine — domain constraint enforcement
(ARCHITECTURE.md §2.5; case-study doc "Verification & Trust").

Pure Python, deterministic, no LLM. Walks the per-turn retrieval bundle
and emits structured `RuleFinding` objects for any clinical rule that
matches: lab thresholds (A1c, LDL, creatinine), dosage ranges for the
demo medications, and a small drug-interaction table.

The engine is read-only and side-effect-free — same input always
produces the same output. That property is what lets the verifier and
the Langfuse trace report rule violations as deterministically as
source-id matches.

Why this is separate from the verifier:
  - The verifier asks "did the LLM cite real records and quote them
    correctly?" — a faithfulness check on the LLM's output.
  - The rule engine asks "given the retrieved records, what clinical
    constraints apply?" — a check on the records themselves.

Both are deterministic; both feed the orchestrator's reasoning context
and the trace. Together they answer "grounded outputs beyond basic
filtering" — you cite real records AND respect domain rules over those
records.

Scope: rules are intentionally a small, defensible set. RxNorm-driven
interactions and full dosing tables are flagged as week-2 work in
ARCHITECTURE.md §9.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable


# --- Domain types ---


@dataclass(frozen=True)
class RuleFinding:
    """One rule that matched on the per-turn retrieval bundle."""

    rule_id: str  # stable identifier e.g. "A1C_UNCONTROLLED"
    category: str  # "lab_threshold" | "dosage" | "interaction"
    severity: str  # "info" | "warning" | "critical"
    message: str  # one-line clinician-facing description
    evidence_source_ids: tuple[str, ...]  # records that triggered the rule

    def describe(self) -> str:
        return f"[{self.severity.upper()}] {self.rule_id}: {self.message}"


# --- Lab threshold rules ---
# Each rule fires when a single lab record's `value` matches `predicate`.
# Severities:
#   info     — within target / informational
#   warning  — above goal, monitor
#   critical — uncontrolled / urgent attention


@dataclass(frozen=True)
class _LabRule:
    rule_id: str
    severity: str
    lab_name_substr: str  # case-insensitive substring match against record["name"]
    predicate: Callable[[float], bool]
    message_template: str  # "{value}" gets the actual numeric value


LAB_RULES: list[_LabRule] = [
    # --- Hemoglobin A1c (diabetes control) ---
    _LabRule(
        rule_id="A1C_UNCONTROLLED",
        severity="critical",
        lab_name_substr="A1c",
        predicate=lambda v: v > 9.0,
        message_template=(
            "Uncontrolled type 2 diabetes: A1c {value}% exceeds the 9.0% "
            "threshold (target <7.0%)."
        ),
    ),
    _LabRule(
        rule_id="A1C_ABOVE_GOAL",
        severity="warning",
        lab_name_substr="A1c",
        predicate=lambda v: 7.0 < v <= 9.0,
        message_template=(
            "A1c {value}% is above the standard <7.0% goal but not in the "
            "uncontrolled range."
        ),
    ),
    # --- LDL cholesterol ---
    _LabRule(
        rule_id="LDL_SEVERE",
        severity="critical",
        lab_name_substr="LDL",
        predicate=lambda v: v >= 190,
        message_template=(
            "Severe hyperlipidemia: LDL {value} mg/dL meets the ≥190 "
            "threshold for high-intensity statin candidacy."
        ),
    ),
    _LabRule(
        rule_id="LDL_ABOVE_TARGET",
        severity="warning",
        lab_name_substr="LDL",
        predicate=lambda v: 100 <= v < 190,
        message_template=(
            "LDL {value} mg/dL is above the <100 mg/dL target."
        ),
    ),
    # --- Creatinine (renal function) — paired with metformin caution below ---
    _LabRule(
        rule_id="CREATININE_ELEVATED",
        severity="critical",
        lab_name_substr="Creatinine",
        predicate=lambda v: v > 1.5,
        message_template=(
            "Renal impairment: creatinine {value} mg/dL (>1.5)."
        ),
    ),
    _LabRule(
        rule_id="CREATININE_BORDERLINE",
        severity="warning",
        lab_name_substr="Creatinine",
        predicate=lambda v: 1.2 < v <= 1.5,
        message_template=(
            "Borderline creatinine {value} mg/dL — monitor renal function."
        ),
    ),
]


# --- Dosage rules ---
# Demo set only. A real implementation would key by RxNorm and pull
# from a maintained dose table. Format: med-name-substring → (min, max,
# unit) for the *single dose* form recorded in demo_data.py. We don't
# attempt to reconstruct mg/day from frequency strings here — that's a
# week-2 normalization step.


@dataclass(frozen=True)
class _DosageRule:
    rule_id: str
    med_name_substr: str  # case-insensitive
    min_dose_mg: float
    max_dose_mg: float
    typical_max_mg: float | None = None  # if exceeded → warning, not critical


DOSAGE_RULES: list[_DosageRule] = [
    _DosageRule(
        rule_id="METFORMIN_DOSE",
        med_name_substr="Metformin",
        min_dose_mg=500,
        max_dose_mg=2550,  # FDA max for IR formulation
        typical_max_mg=2000,
    ),
    _DosageRule(
        rule_id="LISINOPRIL_DOSE",
        med_name_substr="Lisinopril",
        min_dose_mg=2.5,
        max_dose_mg=80,  # outpatient ceiling
        typical_max_mg=40,
    ),
    _DosageRule(
        rule_id="ATORVASTATIN_DOSE",
        med_name_substr="Atorvastatin",
        min_dose_mg=10,
        max_dose_mg=80,
    ),
    _DosageRule(
        rule_id="FUROSEMIDE_DOSE",
        med_name_substr="Furosemide",
        min_dose_mg=20,
        max_dose_mg=600,
        typical_max_mg=200,
    ),
]


# --- Drug-interaction rules ---
# A small, hand-curated pair list. Each entry fires when BOTH drugs are
# present in the medication list. This is an intentionally conservative
# stub — the full implementation pulls from an interaction database
# (e.g. RxNorm + DrugBank), which is week-2 work.


@dataclass(frozen=True)
class _InteractionRule:
    rule_id: str
    drug_a_substr: str
    drug_b_substr: str
    severity: str  # warning / critical
    message: str


INTERACTION_RULES: list[_InteractionRule] = [
    _InteractionRule(
        rule_id="LISINOPRIL_NSAID",
        drug_a_substr="Lisinopril",
        drug_b_substr="Ibuprofen",
        severity="warning",
        message=(
            "Lisinopril + NSAID (ibuprofen): may reduce antihypertensive "
            "effect and worsen renal function. Monitor BP and creatinine."
        ),
    ),
    _InteractionRule(
        rule_id="LISINOPRIL_NAPROXEN",
        drug_a_substr="Lisinopril",
        drug_b_substr="Naproxen",
        severity="warning",
        message=(
            "Lisinopril + NSAID (naproxen): may reduce antihypertensive "
            "effect and worsen renal function. Monitor BP and creatinine."
        ),
    ),
    _InteractionRule(
        rule_id="METFORMIN_CONTRAST",
        drug_a_substr="Metformin",
        drug_b_substr="Iohexol",  # IV contrast agent
        severity="critical",
        message=(
            "Metformin + iodinated IV contrast: hold metformin around "
            "contrast administration to reduce risk of contrast-induced "
            "lactic acidosis in patients with renal impairment."
        ),
    ),
    _InteractionRule(
        rule_id="ATORVASTATIN_CLARITHROMYCIN",
        drug_a_substr="Atorvastatin",
        drug_b_substr="Clarithromycin",
        severity="critical",
        message=(
            "Atorvastatin + clarithromycin: CYP3A4 inhibition can raise "
            "atorvastatin levels and increase rhabdomyolysis risk. Hold "
            "or switch the statin during the antibiotic course."
        ),
    ),
]


# --- Cross-rules (combine labs + meds) ---
# These are the rules where a lab finding is only clinically meaningful
# in the context of an active medication. Implemented as a separate
# pass so the threshold logic above stays single-record.


def _check_metformin_with_renal(
    labs: list[dict[str, Any]],
    medications: list[dict[str, Any]],
) -> list[RuleFinding]:
    findings: list[RuleFinding] = []
    on_metformin = [
        m for m in medications if _name_contains(m, "Metformin")
    ]
    if not on_metformin:
        return findings

    for lab in labs:
        if not _name_contains(lab, "Creatinine"):
            continue
        value = _coerce_float(lab.get("value"))
        if value is None:
            continue
        evidence = (
            *(_source_id(lab),),
            *(_source_id(m) for m in on_metformin),
        )
        evidence = tuple(s for s in evidence if s)
        if value > 1.5:
            findings.append(
                RuleFinding(
                    rule_id="METFORMIN_RENAL_CONTRAINDICATION",
                    category="interaction",
                    severity="critical",
                    message=(
                        f"Patient on metformin with creatinine "
                        f"{value} mg/dL (>1.5): consider holding "
                        f"metformin and reassessing — risk of lactic "
                        f"acidosis."
                    ),
                    evidence_source_ids=evidence,
                )
            )
        elif value > 1.2:
            findings.append(
                RuleFinding(
                    rule_id="METFORMIN_RENAL_CAUTION",
                    category="interaction",
                    severity="warning",
                    message=(
                        f"Patient on metformin with borderline "
                        f"creatinine {value} mg/dL: monitor renal "
                        f"function."
                    ),
                    evidence_source_ids=evidence,
                )
            )
    return findings


# --- Public entry point ---


def evaluate_clinical_rules(
    parsed_results: list[dict[str, Any]],
) -> list[RuleFinding]:
    """Top-level rule evaluation. Walks the per-turn retrieval bundle
    (the same `parsed_results` the verifier sees) and returns every
    finding that fires.

    Order of findings is deterministic: lab thresholds (in lab order),
    dosage rules (in medication order), interactions (in
    INTERACTION_RULES order), then cross-rules. This keeps Langfuse
    traces and tests stable."""
    labs = _gather_records(parsed_results, key="labs")
    medications = _gather_records(parsed_results, key="medications")

    findings: list[RuleFinding] = []
    findings.extend(_check_lab_thresholds(labs))
    findings.extend(_check_dosage(medications))
    findings.extend(_check_interactions(medications))
    findings.extend(_check_metformin_with_renal(labs, medications))
    return findings


# --- Threshold + dosage check helpers ---


def _check_lab_thresholds(labs: list[dict[str, Any]]) -> list[RuleFinding]:
    out: list[RuleFinding] = []
    for lab in labs:
        value = _coerce_float(lab.get("value"))
        if value is None:
            continue
        for rule in LAB_RULES:
            if not _name_contains(lab, rule.lab_name_substr):
                continue
            try:
                matched = rule.predicate(value)
            except Exception:
                matched = False
            if matched:
                source_id = _source_id(lab)
                out.append(
                    RuleFinding(
                        rule_id=rule.rule_id,
                        category="lab_threshold",
                        severity=rule.severity,
                        message=rule.message_template.format(value=value),
                        evidence_source_ids=(source_id,) if source_id else (),
                    )
                )
    return out


def _check_dosage(meds: list[dict[str, Any]]) -> list[RuleFinding]:
    """Compare the parsed `dose` (in mg) against the rule's range. Demo
    `dose` strings are plain like '1000 mg' or '10 mg'; we extract the
    leading number. Below-min → warning (sub-therapeutic for the
    indication assumed in the rule); above-typical-max →
    warning; above-hard-max → critical."""
    out: list[RuleFinding] = []
    for med in meds:
        dose_mg = _parse_dose_mg(med.get("dose"))
        if dose_mg is None:
            continue
        for rule in DOSAGE_RULES:
            if not _name_contains(med, rule.med_name_substr):
                continue
            source_id = _source_id(med)
            evidence = (source_id,) if source_id else ()
            if dose_mg > rule.max_dose_mg:
                out.append(
                    RuleFinding(
                        rule_id=f"{rule.rule_id}_ABOVE_MAX",
                        category="dosage",
                        severity="critical",
                        message=(
                            f"{rule.med_name_substr} {dose_mg} mg exceeds "
                            f"the outpatient maximum of "
                            f"{rule.max_dose_mg} mg."
                        ),
                        evidence_source_ids=evidence,
                    )
                )
            elif (
                rule.typical_max_mg is not None
                and dose_mg > rule.typical_max_mg
            ):
                out.append(
                    RuleFinding(
                        rule_id=f"{rule.rule_id}_ABOVE_TYPICAL",
                        category="dosage",
                        severity="warning",
                        message=(
                            f"{rule.med_name_substr} {dose_mg} mg is above "
                            f"the typical {rule.typical_max_mg} mg "
                            f"ceiling — verify intent."
                        ),
                        evidence_source_ids=evidence,
                    )
                )
            elif dose_mg < rule.min_dose_mg:
                out.append(
                    RuleFinding(
                        rule_id=f"{rule.rule_id}_BELOW_MIN",
                        category="dosage",
                        severity="warning",
                        message=(
                            f"{rule.med_name_substr} {dose_mg} mg is below "
                            f"the typical minimum of "
                            f"{rule.min_dose_mg} mg."
                        ),
                        evidence_source_ids=evidence,
                    )
                )
    return out


def _check_interactions(meds: list[dict[str, Any]]) -> list[RuleFinding]:
    out: list[RuleFinding] = []
    for rule in INTERACTION_RULES:
        a = next(
            (m for m in meds if _name_contains(m, rule.drug_a_substr)),
            None,
        )
        b = next(
            (m for m in meds if _name_contains(m, rule.drug_b_substr)),
            None,
        )
        if a is None or b is None:
            continue
        evidence = tuple(
            s for s in (_source_id(a), _source_id(b)) if s
        )
        out.append(
            RuleFinding(
                rule_id=rule.rule_id,
                category="interaction",
                severity=rule.severity,
                message=rule.message,
                evidence_source_ids=evidence,
            )
        )
    return out


# --- Walking helpers ---


def _gather_records(
    parsed_results: list[dict[str, Any]], *, key: str
) -> list[dict[str, Any]]:
    """Collect every list-of-records under `key` across all parsed tool
    results. Demo tools return shapes like {"labs": [...]},
    {"medications": [...]} — we union them so a follow-up turn that
    calls only the labs tool still gets evaluated correctly."""
    out: list[dict[str, Any]] = []
    for r in parsed_results:
        if not isinstance(r, dict):
            continue
        records = r.get(key)
        if isinstance(records, list):
            for item in records:
                if isinstance(item, dict):
                    out.append(item)
    return out


def _name_contains(record: dict[str, Any], substr: str) -> bool:
    name = record.get("name") or ""
    if not isinstance(name, str):
        return False
    return substr.lower() in name.lower()


def _source_id(record: dict[str, Any]) -> str | None:
    sid = record.get("source_id")
    return sid if isinstance(sid, str) else None


_DOSE_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _parse_dose_mg(dose_str: object) -> float | None:
    """Extract the leading number from a dose string like '1000 mg'.
    Returns None for unparsable inputs. We assume mg unless the string
    explicitly contains another unit; cross-unit dosing is week-2."""
    if not isinstance(dose_str, str):
        return None
    lowered = dose_str.lower()
    if "mcg" in lowered or "ug" in lowered:
        # Avoid a 1000-mcg-vs-1-mg false reading. Skip rather than
        # half-translate.
        return None
    m = _DOSE_NUMBER_RE.search(dose_str)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def _coerce_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None
