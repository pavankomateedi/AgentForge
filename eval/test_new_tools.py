"""Tests for the four Week-1-feedback-driven tools.

  - get_lab_history     — historical timeline per test
  - get_changes_since   — deltas keyed off ISO date
  - get_recent_documents — wraps the documents storage layer
  - check_clinical_thresholds — callable wrapper over the rules engine

Each test pins:
  - the result shape (so the LLM has a stable contract)
  - the patient-subject lock (cross-patient calls REFUSED)
  - rich-data + sparse-data behavior (so no spurious crashes)
"""

from __future__ import annotations

import pytest

from agent.tools import PatientSubjectMismatch, execute_tool


# ---- get_lab_history ----


async def test_lab_history_resolves_alias():
    """`A1c`, `HbA1c`, `Hemoglobin A1c` should all resolve to the same
    history series — alias resolution is the contract."""
    out_a = await execute_tool(
        "get_lab_history",
        {"patient_id": "demo-001", "test_name": "A1c"},
        locked_patient_id="demo-001",
    )
    out_b = await execute_tool(
        "get_lab_history",
        {"patient_id": "demo-001", "test_name": "HbA1c"},
        locked_patient_id="demo-001",
    )
    out_c = await execute_tool(
        "get_lab_history",
        {"patient_id": "demo-001", "test_name": "Hemoglobin A1c"},
        locked_patient_id="demo-001",
    )
    assert out_a["resolved_test_key"] == "a1c"
    assert out_b["resolved_test_key"] == "a1c"
    assert out_c["resolved_test_key"] == "a1c"
    assert len(out_a["history"]) == 3


async def test_lab_history_newest_first_with_unique_source_ids():
    """Trend-style answers depend on chronological order. Source ids
    must be unique per (patient, test, date) so each measurement is
    independently citable."""
    out = await execute_tool(
        "get_lab_history",
        {"patient_id": "demo-003", "test_name": "A1c"},
        locked_patient_id="demo-003",
    )
    history = out["history"]
    dates = [r["date"] for r in history]
    assert dates == sorted(dates, reverse=True), "history must be newest-first"
    sids = [r["source_id"] for r in history]
    assert len(sids) == len(set(sids))
    # Worsening trend is the demo-003 hallmark.
    values = [r["value"] for r in history]
    assert values == [10.5, 9.2, 8.5]


async def test_lab_history_unknown_test_returns_note():
    out = await execute_tool(
        "get_lab_history",
        {"patient_id": "demo-001", "test_name": "TSH"},
        locked_patient_id="demo-001",
    )
    assert out["history"] == []
    assert "No history" in out["note"]


async def test_lab_history_no_test_name_returns_all():
    out = await execute_tool(
        "get_lab_history",
        {"patient_id": "demo-001"},
        locked_patient_id="demo-001",
    )
    histories = out["all_histories"]
    assert set(histories.keys()) >= {"a1c", "ldl", "creatinine"}


async def test_lab_history_sparse_patient_returns_empty():
    """demo-002 (CHF, sparse data) has no historical labs. Tool must
    return empty cleanly — not crash."""
    out = await execute_tool(
        "get_lab_history",
        {"patient_id": "demo-002"},
        locked_patient_id="demo-002",
    )
    assert out["all_histories"] == {}


async def test_lab_history_subject_lock():
    with pytest.raises(PatientSubjectMismatch):
        await execute_tool(
            "get_lab_history",
            {"patient_id": "demo-002", "test_name": "A1c"},
            locked_patient_id="demo-001",
        )


# ---- get_changes_since ----


async def test_changes_since_picks_up_post_cutoff_records():
    """Cutoff in mid-2025 should pick up the 2025-09 + 2026-03 encounters
    on demo-001 plus any labs in lab_history dated on/after the cutoff."""
    out = await execute_tool(
        "get_changes_since",
        {"patient_id": "demo-001", "since_date": "2025-09-01"},
        locked_patient_id="demo-001",
    )
    enc_dates = sorted(e["date"] for e in out["new_encounters"])
    assert enc_dates == ["2025-09-12", "2026-03-15"]
    # Lab history should bring in the 2025-09 + 2026-03 measurements
    # for each tracked test.
    assert len(out["new_labs"]) >= 6


async def test_changes_since_far_future_returns_nothing():
    out = await execute_tool(
        "get_changes_since",
        {"patient_id": "demo-001", "since_date": "2099-01-01"},
        locked_patient_id="demo-001",
    )
    assert out["new_problems"] == []
    assert out["new_medications"] == []
    assert out["new_labs"] == []
    assert out["new_encounters"] == []


async def test_changes_since_invalid_date_returns_error():
    out = await execute_tool(
        "get_changes_since",
        {"patient_id": "demo-001", "since_date": "not-a-date"},
        locked_patient_id="demo-001",
    )
    assert "error" in out


async def test_changes_since_picks_up_new_med_on_demo_004():
    """demo-004's ibuprofen was started 2023-01-12. A cutoff before that
    should include it; after that should exclude."""
    before = await execute_tool(
        "get_changes_since",
        {"patient_id": "demo-004", "since_date": "2022-01-01"},
        locked_patient_id="demo-004",
    )
    after = await execute_tool(
        "get_changes_since",
        {"patient_id": "demo-004", "since_date": "2023-06-01"},
        locked_patient_id="demo-004",
    )
    before_meds = {m["name"] for m in before["new_medications"]}
    after_meds = {m["name"] for m in after["new_medications"]}
    assert "Ibuprofen" in before_meds
    assert "Ibuprofen" not in after_meds


# ---- get_recent_documents ----


async def test_recent_documents_empty_when_no_uploads(config, seed_user):  # noqa: ARG001
    out = await execute_tool(
        "get_recent_documents",
        {"patient_id": "demo-001"},
        locked_patient_id="demo-001",
    )
    assert out["total_count"] == 0
    assert out["documents"] == []


async def test_recent_documents_after_upload(config, seed_user):
    from agent import documents as doc_storage

    doc_storage.insert_document(
        config.database_url,
        patient_id="demo-001",
        doc_type="lab_pdf",
        file_blob=b"%PDF-1.4\n%dummy",
        content_type="application/pdf",
        uploaded_by_user_id=seed_user.id,
    )
    out = await execute_tool(
        "get_recent_documents",
        {"patient_id": "demo-001"},
        locked_patient_id="demo-001",
    )
    assert out["total_count"] == 1
    doc = out["documents"][0]
    assert doc["doc_type"] == "lab_pdf"
    assert doc["extraction_status"] == "pending"
    assert doc["source_id"].startswith("doc-"), "must be citable as doc-<id>"


async def test_recent_documents_subject_lock():
    with pytest.raises(PatientSubjectMismatch):
        await execute_tool(
            "get_recent_documents",
            {"patient_id": "demo-002"},
            locked_patient_id="demo-001",
        )


# ---- check_clinical_thresholds ----


async def test_thresholds_demo_001_warning():
    """Margaret Hayes — A1c 7.4 above goal, fires A1C_ABOVE_GOAL warning."""
    out = await execute_tool(
        "check_clinical_thresholds",
        {"patient_id": "demo-001"},
        locked_patient_id="demo-001",
    )
    rule_ids = {f["rule_id"] for f in out["findings"]}
    assert "A1C_ABOVE_GOAL" in rule_ids


async def test_thresholds_demo_003_critical_stack():
    """Robert Mitchell — 4 critical/warning rules per demo data."""
    out = await execute_tool(
        "check_clinical_thresholds",
        {"patient_id": "demo-003"},
        locked_patient_id="demo-003",
    )
    rule_ids = {f["rule_id"] for f in out["findings"]}
    assert "A1C_UNCONTROLLED" in rule_ids
    assert "CREATININE_ELEVATED" in rule_ids
    assert "LDL_ABOVE_TARGET" in rule_ids
    assert "METFORMIN_RENAL_CONTRAINDICATION" in rule_ids


async def test_thresholds_demo_004_drug_interaction():
    """Linda Chen — lisinopril + ibuprofen → LISINOPRIL_NSAID."""
    out = await execute_tool(
        "check_clinical_thresholds",
        {"patient_id": "demo-004"},
        locked_patient_id="demo-004",
    )
    rule_ids = {f["rule_id"] for f in out["findings"]}
    assert "LISINOPRIL_NSAID" in rule_ids


async def test_thresholds_demo_005_no_findings():
    """Sarah Martinez — stable, well-controlled. No rules fire."""
    out = await execute_tool(
        "check_clinical_thresholds",
        {"patient_id": "demo-005"},
        locked_patient_id="demo-005",
    )
    assert out["n_findings"] == 0


async def test_thresholds_findings_are_serializable():
    """The tool result is JSON-serialized into the tool_result content
    block. Must not contain non-serializable types."""
    import json

    out = await execute_tool(
        "check_clinical_thresholds",
        {"patient_id": "demo-003"},
        locked_patient_id="demo-003",
    )
    json.dumps(out)  # raises if anything's non-serializable
