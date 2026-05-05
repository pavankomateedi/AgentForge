"""Tests for the intake_extractor + evidence_retriever workers.

The intake worker is purely a read-side helper over derived_observations.
The evidence worker calls the singleton HybridRetriever with the
local-fallback reranker.
"""

from __future__ import annotations

import pytest

from agent import documents as doc_storage
from agent.agents.evidence_retriever_worker import (
    render_evidence_block,
    reset_retriever,
    run_evidence_retriever_worker,
)
from agent.agents.intake_extractor_worker import (
    count_derived_for_patient,
    count_unprocessed_docs,
    run_intake_extractor_worker,
)


@pytest.fixture(autouse=True)
def _force_local_reranker(monkeypatch):
    monkeypatch.setenv("RERANKER_FALLBACK", "local")
    monkeypatch.delenv("COHERE_API_KEY", raising=False)


# ---- intake_extractor_worker ----


async def test_intake_worker_returns_empty_when_no_docs(config):
    text = await run_intake_extractor_worker(
        database_url=config.database_url, patient_id="demo-001"
    )
    assert text == ""


async def test_intake_worker_renders_extracted_block(
    config, seed_user, monkeypatch
):
    pdf_bytes = b"%PDF-1.4\n%dummy"
    stored = doc_storage.insert_document(
        config.database_url,
        patient_id="demo-001",
        doc_type="lab_pdf",
        file_blob=pdf_bytes,
        content_type="application/pdf",
        uploaded_by_user_id=seed_user.id,
    )

    # Persist a synthetic LabReport directly (no extractor call).
    from datetime import date

    from agent.schemas.citation import BBox, Citation
    from agent.schemas.lab import LabReport, LabValue

    report = LabReport(
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
    )
    doc_storage.persist_lab_report(config.database_url, report)

    text = await run_intake_extractor_worker(
        database_url=config.database_url, patient_id="demo-001"
    )
    assert "<extracted_documents" in text
    assert "lab_observation" in text
    assert "HbA1c" in text


def test_count_helpers(config, seed_user):
    assert count_derived_for_patient(config.database_url, "demo-001") == 0
    assert count_unprocessed_docs(config.database_url, "demo-001") == 0

    # Insert a doc still in 'pending' state.
    doc_storage.insert_document(
        config.database_url,
        patient_id="demo-001",
        doc_type="lab_pdf",
        file_blob=b"x",
        content_type="application/pdf",
        uploaded_by_user_id=seed_user.id,
    )
    assert count_unprocessed_docs(config.database_url, "demo-001") == 1


# ---- evidence_retriever_worker ----


async def test_evidence_worker_returns_top3():
    reset_retriever()
    hits = await run_evidence_retriever_worker(
        query="A1c target type 2 diabetes", top_k=3
    )
    assert len(hits) == 3
    assert hits[0].chunk.chunk_id == "ada-2024-a1c-targets"


async def test_evidence_worker_renders_block_with_citations():
    reset_retriever()
    hits = await run_evidence_retriever_worker(
        query="metformin contraindication kidney function", top_k=3
    )
    block = render_evidence_block(hits)
    assert "<guideline_evidence>" in block
    assert "metformin-ckd-contraindication" in block


def test_render_evidence_block_empty():
    assert render_evidence_block([]) == ""
