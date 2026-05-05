"""Intake form extraction schema.

Demographics, current meds, allergies, family history, chief concern.
Each field carries a Citation. Free-text fields like `chief_concern`
are PHI and must not appear in audit-log details or Langfuse trace
metadata — see `agent/observability.py:_redact_phi`.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agent.schemas.citation import Citation


Sex = Literal["male", "female", "other", "unknown"]


class Demographics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=256)
    name_citation: Citation
    dob: date | None = None
    dob_citation: Citation | None = None
    sex: Sex | None = None
    sex_citation: Citation | None = None
    mrn: str | None = Field(default=None, max_length=64)
    mrn_citation: Citation | None = None


class Medication(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=256)
    dose: str | None = Field(default=None, max_length=128)
    frequency: str | None = Field(default=None, max_length=128)
    citation: Citation


AllergySeverity = Literal["mild", "moderate", "severe", "anaphylactic"]


class Allergy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    substance: str = Field(..., min_length=1, max_length=256)
    reaction: str | None = Field(default=None, max_length=512)
    severity: AllergySeverity | None = None
    citation: Citation


class IntakeForm(BaseModel):
    """The whole form. Lists may be empty when the form has no entries.
    `chief_concern` is null when the form lacks that field outright;
    `extraction_warnings` records any soft failures (illegible block,
    cropped page, etc.) so the UI can surface a "review the source"
    nudge without bouncing the upload."""

    model_config = ConfigDict(extra="forbid")

    patient_id: str = Field(..., min_length=1, max_length=128)
    document_id: int = Field(..., ge=1)
    demographics: Demographics
    chief_concern: str | None = Field(default=None, max_length=2048)
    chief_concern_citation: Citation | None = None
    current_medications: list[Medication] = Field(default_factory=list)
    allergies: list[Allergy] = Field(default_factory=list)
    family_history: list[str] = Field(default_factory=list)
    extraction_warnings: list[str] = Field(default_factory=list)
