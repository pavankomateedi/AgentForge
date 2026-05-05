"""Reranker: Cohere rerank-v3.5 with local cross-encoder fallback.

The architecture doc names Cohere as the chosen vendor. We honor the
fallback contract literally: when COHERE_API_KEY is unset OR
RERANKER_FALLBACK=local is set explicitly, we use a local
cross-encoder (sentence-transformers/cross-encoder/ms-marco-MiniLM-L-6-v2).

Both reranker paths take the same inputs and return the same shape, so
the retriever code stays straight.
"""

from __future__ import annotations

import logging
import os
from typing import Protocol

from agent.rag.corpus import Chunk

log = logging.getLogger(__name__)


_COHERE_MODEL = "rerank-v3.5"
_LOCAL_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

_local_model = None


class Reranker(Protocol):
    name: str

    def rerank(
        self, query: str, candidates: list[Chunk], top_k: int = 3
    ) -> list[tuple[Chunk, float]]:
        ...


class CohereReranker:
    name = "cohere"

    def __init__(self, api_key: str):
        # Lazy import so the dep is optional at startup.
        import cohere

        self._client = cohere.ClientV2(api_key=api_key)

    def rerank(
        self, query: str, candidates: list[Chunk], top_k: int = 3
    ) -> list[tuple[Chunk, float]]:
        if not candidates:
            return []
        documents = [f"{c.title}\n{c.text}" for c in candidates]
        try:
            response = self._client.rerank(
                model=_COHERE_MODEL,
                query=query,
                documents=documents,
                top_n=min(top_k, len(candidates)),
            )
        except Exception as e:
            log.warning(
                "rerank: cohere call failed (%s) — caller should fall back", e
            )
            raise
        out: list[tuple[Chunk, float]] = []
        for r in response.results:
            out.append((candidates[r.index], float(r.relevance_score)))
        return out


class LocalCrossEncoderReranker:
    name = "local-cross-encoder"

    def __init__(self):
        global _local_model
        if _local_model is None:
            from sentence_transformers import CrossEncoder

            log.info("rerank: loading local %s", _LOCAL_MODEL)
            _local_model = CrossEncoder(_LOCAL_MODEL)
        self._model = _local_model

    def rerank(
        self, query: str, candidates: list[Chunk], top_k: int = 3
    ) -> list[tuple[Chunk, float]]:
        if not candidates:
            return []
        pairs = [(query, f"{c.title}\n{c.text}") for c in candidates]
        scores = self._model.predict(pairs)
        ranked = sorted(
            zip(candidates, scores), key=lambda x: float(x[1]), reverse=True
        )
        return [(c, float(s)) for c, s in ranked[:top_k]]


def get_reranker() -> Reranker:
    """Pick a reranker based on env. Cohere when COHERE_API_KEY is set
    AND the fallback flag isn't forced. Local cross-encoder otherwise."""
    fallback_forced = os.environ.get("RERANKER_FALLBACK", "").lower() == "local"
    api_key = os.environ.get("COHERE_API_KEY", "").strip()

    if fallback_forced or not api_key:
        log.info(
            "rerank: using local cross-encoder (fallback_forced=%s, "
            "cohere_key_set=%s)",
            fallback_forced, bool(api_key),
        )
        return LocalCrossEncoderReranker()

    log.info("rerank: using Cohere (%s)", _COHERE_MODEL)
    return CohereReranker(api_key=api_key)
