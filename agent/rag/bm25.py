"""BM25 sparse index over the guideline corpus.

Wraps `rank_bm25.BM25Okapi`. Tokenization is intentionally simple:
lowercase, split on non-word characters, drop very short tokens. The
corpus is small enough that fancier preprocessing buys nothing —
correctness wins over recall theatre.

The index is built once and held in memory; `BM25Index` is a value
object. Callers re-build by re-instantiating, not by mutation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from agent.rag.corpus import Chunk


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if len(t) > 1]


@dataclass
class BM25Index:
    chunks: list[Chunk]
    _bm25: BM25Okapi

    @classmethod
    def build(cls, chunks: list[Chunk]) -> "BM25Index":
        tokenized = [_tokenize(c.title + "\n" + c.text) for c in chunks]
        return cls(chunks=chunks, _bm25=BM25Okapi(tokenized))

    def search(self, query: str, top_k: int = 10) -> list[tuple[Chunk, float]]:
        q_tokens = _tokenize(query)
        if not q_tokens:
            return []
        scores = self._bm25.get_scores(q_tokens)
        ranked = sorted(
            zip(self.chunks, scores), key=lambda x: x[1], reverse=True
        )
        return [(c, float(s)) for c, s in ranked[:top_k] if s > 0]
