"""Lab PDF extraction schema.

Maps to the FHIR `Observation` resource so the v1 storage migration
(SQLite -> OpenEMR) is a translation, not a redesign. `LabReport.values`
is one row per `LabValue` in `derived_observations` — schema_kind =
`lab_observation`, payload_json = the LabValue dict.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agent.schemas.citation import Citation


AbnormalFlag = Literal["low", "normal", "high", "critical"]


class LabValue(BaseModel):
    """One discrete lab result. Numeric or categorical (e.g. 'positive')
    so we can carry common qualitative tests without a separate schema.

    Confidence is the VLM's reported confidence in the extraction
    itself, not in the lab's measurement quality. Surfaced for ops
    debugging only — clinicians shouldn't act on the probability.
    """

    model_config = ConfigDict(extra="forbid")

    test_name: str = Field(..., min_length=1, max_length=128)
    value: float | str
    unit: str | None = Field(default=None, max_length=64)
    reference_range: str | None = Field(default=None, max_length=128)
    collection_date: date
    abnormal_flag: AbnormalFlag | None = None
    citation: Citation
    confidence: float = Field(..., ge=0.0, le=1.0)


class LabReport(BaseModel):
    """The whole document. `values` may be empty if extraction found no
    interpretable rows — that is itself a valid (recorded) outcome and
    `extraction_warnings` will explain why.
    """

    model_config = ConfigDict(extra="forbid")

    patient_id: str = Field(..., min_length=1, max_length=128)
    document_id: int = Field(..., ge=1)
    ordering_provider: str | None = Field(default=None, max_length=256)
    lab_name: str | None = Field(default=None, max_length=256)
    collection_date: date
    values: list[LabValue] = Field(default_factory=list)
    extraction_warnings: list[str] = Field(default_factory=list)
