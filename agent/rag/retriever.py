"""Hybrid RAG retriever: BM25 + dense -> reranker -> top-k.

Design (per W2_ARCHITECTURE.md §6):
  1. Top-10 from BM25 + Top-10 from dense → union, dedup by chunk_id
  2. Cohere rerank (or local cross-encoder fallback) over the union
  3. Return top-3 with citation-ready metadata

The retriever is constructed once per process. Both indexes are built
on first construction and held in memory. ~50MB total at corpus size.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from agent.rag.bm25 import BM25Index
from agent.rag.corpus import Chunk, load_corpus
from agent.rag.dense import DenseIndex
from agent.rag.rerank import LocalCrossEncoderReranker, Reranker, get_reranker
from agent.schemas.citation import Citation

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetrievalHit:
    chunk: Chunk
    rerank_score: float
    bm25_rank: int | None  # 1-indexed; None if missed
    dense_rank: int | None

    def to_citation(self) -> Citation:
        return Citation(
            source_type="guideline_chunk",
            source_id=self.chunk.chunk_id,
            page_or_section=self.chunk.title[:127] or self.chunk.chunk_id,
            field_or_chunk_id=self.chunk.chunk_id,
            quote_or_value=self.chunk.text[:1024],
            bbox=None,
        )


class HybridRetriever:
    def __init__(
        self,
        *,
        chunks: list[Chunk] | None = None,
        corpus_root: Path | None = None,
        reranker: Reranker | None = None,
    ):
        if chunks is None:
            chunks = load_corpus(corpus_root)
        if not chunks:
            raise RuntimeError(
                "HybridRetriever: corpus is empty — check corpus/guidelines/"
            )
        self.chunks = chunks
        self.bm25 = BM25Index.build(chunks)
        self.dense = DenseIndex.build(chunks)
        self.reranker = reranker or get_reranker()
        log.info(
            "retriever: ready (n_chunks=%d reranker=%s)",
            len(chunks), self.reranker.name,
        )

    def retrieve(
        self, query: str, *, top_k: int = 3, candidate_pool: int = 10
    ) -> list[RetrievalHit]:
        bm25_hits = self.bm25.search(query, top_k=candidate_pool)
        dense_hits = self.dense.search(query, top_k=candidate_pool)

        bm25_rank: dict[str, int] = {
            c.chunk_id: i + 1 for i, (c, _) in enumerate(bm25_hits)
        }
        dense_rank: dict[str, int] = {
            c.chunk_id: i + 1 for i, (c, _) in enumerate(dense_hits)
        }

        seen: dict[str, Chunk] = {}
        for c, _ in bm25_hits:
            seen.setdefault(c.chunk_id, c)
        for c, _ in dense_hits:
            seen.setdefault(c.chunk_id, c)

        candidates = list(seen.values())
        if not candidates:
            return []

        try:
            reranked = self.reranker.rerank(query, candidates, top_k=top_k)
        except Exception as e:
            log.warning(
                "retriever: reranker failed (%s) — falling back to local "
                "cross-encoder for this call",
                e,
            )
            fallback = LocalCrossEncoderReranker()
            reranked = fallback.rerank(query, candidates, top_k=top_k)

        out: list[RetrievalHit] = []
        for chunk, score in reranked:
            out.append(
                RetrievalHit(
                    chunk=chunk,
                    rerank_score=score,
                    bm25_rank=bm25_rank.get(chunk.chunk_id),
                    dense_rank=dense_rank.get(chunk.chunk_id),
                )
            )
        return out
