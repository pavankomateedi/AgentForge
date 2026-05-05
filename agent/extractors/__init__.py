"""Document extraction pipeline.

Three modules:
  - pdf_fragments: pdfplumber wrapper that yields text fragments with
    page+bbox coordinates. Pure (no LLM).
  - lab_extractor / intake_extractor: Claude vision extractors that
    take the original blob + fragments and return a strict-schema
    Pydantic model (LabReport / IntakeForm).

Vision-only extraction tells you the value but not where it came from;
without the pdfplumber pre-pass, the bbox citation is at best a guess
by the model. See W2_ARCHITECTURE.md §3.
"""

from agent.extractors.pdf_fragments import Fragment, extract_fragments

__all__ = ["Fragment", "extract_fragments"]
