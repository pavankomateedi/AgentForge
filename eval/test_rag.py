"""Tests for the hybrid RAG retriever.

Two test layers:
  1. Unit tests for corpus loader + BM25 + dense + reranker.
  2. End-to-end: HybridRetriever against the live corpus, with the
     local cross-encoder as the deterministic-and-free reranker.

The local cross-encoder is forced via env so CI doesn't depend on a
Cohere API key. A separate live-marked test exercises the Cohere path
when COHERE_API_KEY is set.
"""

from __future__ import annotations

import pytest

from agent.rag.bm25 import BM25Index
from agent.rag.corpus import Chunk, _parse_frontmatter, load_corpus
from agent.rag.dense import DenseIndex
from agent.rag.rerank import get_reranker
from agent.rag.retriever import HybridRetriever


# ---- Force local-fallback reranker for the entire module ----


@pytest.fixture(autouse=True)
def _force_local_reranker(monkeypatch):
    monkeypatch.setenv("RERANKER_FALLBACK", "local")
    monkeypatch.delenv("COHERE_API_KEY", raising=False)


# ---- Frontmatter parsing ----


def test_parse_frontmatter_extracts_keys():
    text = "---\nchunk_id: foo\ntitle: Bar\n---\nbody text here\n"
    meta, body = _parse_frontmatter(text)
    assert meta["chunk_id"] == "foo"
    assert meta["title"] == "Bar"
    assert "body text here" in body


def test_parse_frontmatter_no_frontmatter():
    meta, body = _parse_frontmatter("just body, no frontmatter")
    assert meta == {}
    assert body == "just body, no frontmatter"


# ---- Corpus loader ----


def test_load_corpus_finds_at_least_15_chunks():
    chunks = load_corpus()
    assert len(chunks) >= 15
    ids = {c.chunk_id for c in chunks}
    # Spot-check the load brought in some demo-relevant ones.
    assert "ada-2024-a1c-targets" in ids
    assert "metformin-ckd-contraindication" in ids
    assert "nsaid-acei-aki-interaction" in ids


def test_load_corpus_chunks_have_unique_ids():
    chunks = load_corpus()
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids)), "chunk_ids must be unique"


# ---- BM25 ----


def _toy_chunks() -> list[Chunk]:
    return [
        Chunk(
            "c1", "Apples and oranges", "test", None,
            "Apples are red. Oranges are orange.",
        ),
        Chunk(
            "c2", "Bananas", "test", None,
            "Bananas are yellow fruit.",
        ),
        Chunk(
            "c3", "Cars", "test", None,
            "Cars have wheels and engines.",
        ),
    ]


def test_bm25_search_returns_relevant_chunk_first():
    idx = BM25Index.build(_toy_chunks())
    hits = idx.search("yellow fruit banana", top_k=3)
    assert hits[0][0].chunk_id == "c2"


def test_bm25_search_empty_query():
    idx = BM25Index.build(_toy_chunks())
    assert idx.search("", top_k=3) == []


# ---- Dense ----


def test_dense_search_returns_paraphrased_match():
    idx = DenseIndex.build(_toy_chunks())
    # "automobile" doesn't appear in the corpus — only the dense index
    # can match it to "Cars" via embedding similarity.
    hits = idx.search("automobile motor", top_k=3)
    assert hits[0][0].chunk_id == "c3"


# ---- Reranker selection ----


def test_get_reranker_picks_local_when_no_key(monkeypatch):
    monkeypatch.delenv("COHERE_API_KEY", raising=False)
    r = get_reranker()
    assert r.name == "local-cross-encoder"


def test_get_reranker_picks_local_when_fallback_forced(monkeypatch):
    monkeypatch.setenv("COHERE_API_KEY", "would-be-real")
    monkeypatch.setenv("RERANKER_FALLBACK", "local")
    r = get_reranker()
    assert r.name == "local-cross-encoder"


# ---- Hybrid retriever ----


@pytest.fixture(scope="module")
def retriever() -> HybridRetriever:
    """Build once per module — both index loads are slow (model downloads
    on first run)."""
    return HybridRetriever()


def test_retriever_returns_top3(retriever: HybridRetriever):
    hits = retriever.retrieve("A1c target type 2 diabetes", top_k=3)
    assert len(hits) == 3
    assert hits[0].chunk.chunk_id == "ada-2024-a1c-targets"


def test_retriever_metformin_ckd(retriever: HybridRetriever):
    hits = retriever.retrieve("metformin contraindication kidney function", top_k=3)
    top_ids = [h.chunk.chunk_id for h in hits]
    assert "metformin-ckd-contraindication" in top_ids


def test_retriever_drug_interaction(retriever: HybridRetriever):
    hits = retriever.retrieve(
        "NSAID and ACE inhibitor combination acute kidney injury",
        top_k=3,
    )
    top_ids = [h.chunk.chunk_id for h in hits]
    assert "nsaid-acei-aki-interaction" in top_ids


def test_retriever_returns_citation_shape(retriever: HybridRetriever):
    hits = retriever.retrieve("statin intensity", top_k=2)
    assert len(hits) > 0
    citation = hits[0].to_citation()
    assert citation.source_type == "guideline_chunk"
    assert citation.source_id == hits[0].chunk.chunk_id
    assert citation.field_or_chunk_id == hits[0].chunk.chunk_id
    assert citation.bbox is None  # guideline chunks have no PDF bbox


def test_retriever_records_index_provenance(retriever: HybridRetriever):
    """At least one hit should be in BOTH bm25 and dense top-N — the
    point of hybrid is the union, not strict intersection, but the
    overlap is the strongest signal that both indexes are working."""
    hits = retriever.retrieve("A1c target type 2 diabetes", top_k=3)
    in_both = [h for h in hits if h.bm25_rank and h.dense_rank]
    assert len(in_both) >= 1
