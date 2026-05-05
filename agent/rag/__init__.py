"""Hybrid RAG over a small clinical-guideline corpus.

Three layers:
  - corpus: load + parse the markdown chunks under corpus/guidelines/
  - bm25 + dense: independent retrieval indexes
  - rerank: Cohere primary, local cross-encoder fallback
  - retriever: hybrid orchestration -> top-3 with citations
"""

from agent.rag.corpus import Chunk, load_corpus

__all__ = ["Chunk", "load_corpus"]
