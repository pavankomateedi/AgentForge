"""Evidence retriever worker.

Wraps `agent.rag.retriever.HybridRetriever`. Singleton-cached so we
only pay the index-build cost once per process. Returns a list of
RetrievalHit (chunk + scores + provenance) that the answer pipeline
folds into its prompt as `<guideline_evidence>` blocks.
"""

from __future__ import annotations

import logging

from agent.rag.retriever import HybridRetriever, RetrievalHit

log = logging.getLogger(__name__)

_retriever: HybridRetriever | None = None


def _get_retriever() -> HybridRetriever:
    global _retriever
    if _retriever is None:
        _retriever = HybridRetriever()
    return _retriever


def reset_retriever() -> None:
    """Clear the singleton — used by tests to inject a different corpus."""
    global _retriever
    _retriever = None


async def run_evidence_retriever_worker(
    *, query: str, top_k: int = 3
) -> list[RetrievalHit]:
    retriever = _get_retriever()
    hits = retriever.retrieve(query, top_k=top_k)
    log.info(
        "evidence_retriever: query=%r returned %d hits",
        query[:80], len(hits),
    )
    return hits


def render_evidence_block(hits: list[RetrievalHit]) -> str:
    """Format hits for inclusion in the answer pipeline's user_message
    as a `<guideline_evidence>` block. The Week 1 prompt already
    treats `<source ...>` tags specially; this is the parallel."""
    if not hits:
        return ""
    lines = ["<guideline_evidence>"]
    for h in hits:
        c = h.chunk
        lines.append(
            f"  <source id='{c.chunk_id}' title='{c.title}' "
            f"source='{c.source}' rerank_score='{h.rerank_score:.3f}'>"
        )
        lines.append(f"    {c.text}")
        lines.append("  </source>")
    lines.append("</guideline_evidence>")
    return "\n".join(lines)
