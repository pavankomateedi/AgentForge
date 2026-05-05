"""Pytest entry for the 50-case golden suite.

Two suites:
  1. `test_each_case_matches_expected_rubric` — parametrized across all
     cases, asserts the rubric outcomes match the case's expectations.
     A failing case here means EITHER the case is wrong OR the agent
     regressed.

  2. `test_baseline_pass_rate_holds` — runs aggregate, compares to
     committed baseline.json, fails if ANY category drops or falls
     below the floor. Mirrors `check_regression.py` behavior in-test.

  3. Synthetic-regression catch tests — applies known mutations and
     asserts the rubric notices. Pins the gate's catch-rate so a
     defanged rubric (e.g., `score_factually_consistent` always
     returning ok) is itself caught by these tests.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.golden_w2.rubric import aggregate_pass_rates
from eval.golden_w2.runner import (
    BASELINE_PATH,
    load_cases,
    run,
    synthesize_response,
)
from eval.golden_w2.rubric import score_case


_CASES = load_cases()


def _audit_details_for(case: dict, response: dict) -> list[dict]:
    return [
        {
            "patient_id": case["patient_id"],
            "trace_id": response["trace"]["trace_id"],
            "verified": response["verified"],
            "refused": response["trace"]["refused"],
        }
    ]


@pytest.mark.parametrize("case", _CASES, ids=[c["id"] for c in _CASES])
def test_each_case_matches_expected_rubric(case: dict):
    response = synthesize_response(case)
    score = score_case(
        case_id=case["id"],
        response_payload=response,
        audit_details=_audit_details_for(case, response),
        expected_rubric=case["expected_rubric"],
        expects_refusal=case["expects_refusal"],
        min_cited_count=case["expected_signals"].get("min_cited_count", 0),
        phi_markers=case["phi_markers"],
        expected_signals=case["expected_signals"],
    )
    failed = [
        f"{cat}: expected {exp}, got {score.rubric[cat].passed} "
        f"({score.rubric[cat].reason})"
        for cat, exp in score.expected.items()
        if score.rubric[cat].passed != exp
    ]
    if score.signal_check is not None and not score.signal_check.passed:
        failed.append(f"signals: {score.signal_check.reason}")
    assert not failed, f"case {case['id']}: {failed}"


def test_baseline_pass_rate_holds():
    """The committed baseline says 100% pass when healthy. Any drop is
    an automatic CI fail."""
    baseline = json.loads(Path(BASELINE_PATH).read_text())
    scores = run()
    rates = aggregate_pass_rates(scores)

    failures: list[str] = []
    max_drop = 0.05
    min_pass = 0.80
    for cat, current in rates.items():
        if cat.startswith("_"):
            continue
        base = baseline.get(cat)
        if base is None:
            continue
        if current < min_pass:
            failures.append(f"{cat}: {current:.1%} < floor {min_pass:.0%}")
        elif current < base - max_drop:
            failures.append(f"{cat}: dropped {(base-current):.1%}")

    assert not failures, f"regression: {failures}"


# ---- Synthetic-regression catch tests ----
# These pin the gate's actual catch-rate. If anyone defangs the rubric
# (e.g., score_factually_consistent always returns OK), THESE tests
# catch it because the mutated runs would still pass.


def test_gate_catches_stripped_citations():
    scores = run(mutate={"strip_citations": True})
    rates = aggregate_pass_rates(scores)
    # Most cases require >=1 citation; refusal cases survive.
    assert rates["citation_present"] < 0.5, (
        f"expected citation_present to drop sharply, got {rates['citation_present']}"
    )


def test_gate_catches_broken_verifier():
    scores = run(mutate={"break_verifier": True})
    rates = aggregate_pass_rates(scores)
    assert rates["factually_consistent"] < 0.7, (
        f"expected factually_consistent to drop, got {rates['factually_consistent']}"
    )


def test_gate_catches_flipped_refusal():
    scores = run(mutate={"flip_refusal": True})
    rates = aggregate_pass_rates(scores)
    # Every case's refused flag flips; safe_refusal should fail across
    # the board.
    assert rates["safe_refusal"] < 0.2, (
        f"expected safe_refusal to drop near zero, got {rates['safe_refusal']}"
    )
