"""Dense embedding index for the guideline corpus.

Uses `sentence-transformers/all-MiniLM-L6-v2` — small (90MB), fast on
CPU, good enough for 25-chunk corpus. The model is lazy-loaded so app
startup isn't blocked on model download; the first build of the index
pays the load cost.

Cosine similarity over L2-normalized vectors. We L2-normalize at index
time so query-time scoring is a single dot product.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from agent.rag.corpus import Chunk

log = logging.getLogger(__name__)


_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
_model = None  # lazy-loaded singleton


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        log.info("dense: loading %s (first call)", _MODEL_NAME)
        _model = SentenceTransformer(_MODEL_NAME)
    return _model


def _l2_normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


@dataclass
class DenseIndex:
    chunks: list[Chunk]
    matrix: np.ndarray  # shape (n_chunks, embedding_dim), L2-normalized

    @classmethod
    def build(cls, chunks: list[Chunk]) -> "DenseIndex":
        model = _get_model()
        texts = [f"{c.title}\n{c.text}" for c in chunks]
        embeddings = model.encode(
            texts, convert_to_numpy=True, show_progress_bar=False
        ).astype(np.float32)
        return cls(chunks=chunks, matrix=_l2_normalize(embeddings))

    def search(self, query: str, top_k: int = 10) -> list[tuple[Chunk, float]]:
        if not query.strip():
            return []
        model = _get_model()
        q_vec = model.encode(
            [query], convert_to_numpy=True, show_progress_bar=False
        ).astype(np.float32)
        q_vec = _l2_normalize(q_vec)
        scores = (self.matrix @ q_vec.T).flatten()
        idx_sorted = np.argsort(-scores)[:top_k]
        return [(self.chunks[i], float(scores[i])) for i in idx_sorted]
