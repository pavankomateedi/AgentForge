"""Pydantic schemas for Week 2 multimodal extraction.

Every schema field that represents a clinical claim carries a `Citation`
or is explicitly nullable with a documented reason. The verifier walks
`Citation.source_id` the same way it walks the Week 1 `<source/>` tag —
a citation that doesn't appear in the turn's retrieval bundle is
rejected as fabricated.
"""

from agent.schemas.citation import BBox, Citation
from agent.schemas.document import DocumentMetadata, DocType, ExtractionStatus
from agent.schemas.intake import (
    Allergy,
    Demographics,
    IntakeForm,
    Medication,
)
from agent.schemas.lab import LabReport, LabValue

__all__ = [
    "Allergy",
    "BBox",
    "Citation",
    "Demographics",
    "DocType",
    "DocumentMetadata",
    "ExtractionStatus",
    "IntakeForm",
    "LabReport",
    "LabValue",
    "Medication",
]
