"""End-to-end tests for the outer LangGraph + the multi_agent flag on /chat.

Stubs run_turn so the LLM is never called, then asserts:
  - supervisor's routing decision lands in the response trace
  - workers run when invoked, skip when not
  - timings_ms records each stage
  - audit log captures SUPERVISOR_ROUTING_DECISION + EVIDENCE_RETRIEVAL
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from agent import audit
from agent.agents import evidence_retriever_worker
from agent.db import connect


@pytest.fixture(autouse=True)
def _force_heuristic_supervisor_and_local_rerank(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_MODE", "heuristic")
    monkeypatch.setenv("RERANKER_FALLBACK", "local")
    monkeypatch.delenv("COHERE_API_KEY", raising=False)
    evidence_retriever_worker.reset_retriever()


def _audit_events(database_url: str, event_type: str) -> list[dict]:
    with connect(database_url) as conn:
        rows = conn.execute(
            "SELECT * FROM audit_log WHERE event_type = ? ORDER BY id",
            (event_type,),
        ).fetchall()
    return [
        {
            "user_id": r["user_id"],
            "details": json.loads(r["details"]) if r["details"] else None,
        }
        for r in rows
    ]


def _post_chat(client: TestClient, *, message: str, multi_agent: bool):
    return client.post(
        "/chat",
        json={
            "patient_id": "demo-001",
            "message": message,
            "multi_agent": multi_agent,
        },
    )


def test_chat_legacy_path_unchanged(authed_client, stub_run_turn):
    """multi_agent=false (default) MUST still go through the Week 1
    pipeline and not invoke the supervisor."""
    res = _post_chat(authed_client, message="Brief me on this patient.", multi_agent=False)
    assert res.status_code == 200
    body = res.json()
    assert body["trace"]["multi_agent"] is None
    assert len(stub_run_turn["calls"]) == 1


def test_chat_multi_agent_brief_only(authed_client, stub_run_turn, config):
    """A 'brief me' question should route to answer_pipeline ONLY —
    no prep workers, supervisor reason logged."""
    res = _post_chat(authed_client, message="Brief me on this patient.", multi_agent=True)
    assert res.status_code == 200, res.text
    body = res.json()
    multi = body["trace"]["multi_agent"]
    assert multi is not None
    assert multi["workers_invoked"] == ["answer_pipeline"]
    assert multi["stage_timings_ms"].get("supervisor_ms", 0) >= 0
    assert "answer_pipeline_ms" in multi["stage_timings_ms"]

    # Audit: supervisor routing decision was recorded.
    decisions = _audit_events(
        config.database_url, audit.AuditEvent.SUPERVISOR_ROUTING_DECISION
    )
    assert len(decisions) == 1
    assert decisions[0]["details"]["workers_to_invoke"] == ["answer_pipeline"]


def test_chat_multi_agent_guideline_question_invokes_evidence(
    authed_client, stub_run_turn, config
):
    """A guideline-grounded question routes through evidence_retriever
    BEFORE answer_pipeline; the user_message handed to run_turn is
    enriched with a <guideline_evidence> block."""
    res = _post_chat(
        authed_client,
        message="Is metformin still indicated for this patient?",
        multi_agent=True,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    workers = body["trace"]["multi_agent"]["workers_invoked"]
    assert "evidence_retriever" in workers
    assert workers[-1] == "answer_pipeline"

    # Stub captured the enriched user_message — assert evidence got in.
    last = stub_run_turn["calls"][-1]
    assert "<guideline_evidence>" in last["user_message"]

    # Audit: evidence retrieval recorded with non-empty top_chunk_ids.
    ev = _audit_events(config.database_url, audit.AuditEvent.EVIDENCE_RETRIEVAL)
    assert len(ev) == 1
    assert len(ev[0]["details"]["top_chunk_ids"]) > 0


def test_chat_multi_agent_intake_question_with_docs(
    authed_client, stub_run_turn, config, seed_user_mfa
):
    """If derived_observations exist for the patient AND the question
    is about document content, intake_extractor should run and inject
    the extracted block."""
    from datetime import date

    from agent import documents as doc_storage
    from agent.schemas.citation import BBox, Citation
    from agent.schemas.lab import LabReport, LabValue

    stored = doc_storage.insert_document(
        config.database_url,
        patient_id="demo-001",
        doc_type="lab_pdf",
        file_blob=b"%PDF-1.4\n%dummy",
        content_type="application/pdf",
        uploaded_by_user_id=seed_user_mfa["user"].id,
    )
    doc_storage.persist_lab_report(
        config.database_url,
        LabReport(
            patient_id="demo-001",
            document_id=stored.id,
            collection_date=date(2026, 1, 1),
            values=[
                LabValue(
                    test_name="HbA1c",
                    value=8.5,
                    unit="%",
                    collection_date=date(2026, 1, 1),
                    citation=Citation(
                        source_type="lab_pdf",
                        source_id=f"demo-001-doc-{stored.id}",
                        page_or_section="page-1",
                        field_or_chunk_id="p1-l000",
                        quote_or_value="HbA1c 8.5%",
                        bbox=BBox(x0=10, y0=20, x1=100, y1=40),
                    ),
                    confidence=0.9,
                )
            ],
        ),
    )

    res = _post_chat(
        authed_client,
        message="What does the intake form say about recent labs?",
        multi_agent=True,
    )
    assert res.status_code == 200
    workers = res.json()["trace"]["multi_agent"]["workers_invoked"]
    assert "intake_extractor" in workers

    last = stub_run_turn["calls"][-1]
    assert "<extracted_documents" in last["user_message"]


def test_chat_legacy_path_audits_no_routing_decision(
    authed_client, stub_run_turn, config
):
    """multi_agent=false should NOT write SUPERVISOR_ROUTING_DECISION
    audit rows — the supervisor never ran."""
    _post_chat(authed_client, message="Brief me.", multi_agent=False)
    decisions = _audit_events(
        config.database_url, audit.AuditEvent.SUPERVISOR_ROUTING_DECISION
    )
    assert decisions == []
