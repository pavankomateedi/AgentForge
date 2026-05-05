"""Intake extractor worker.

In Week 2's design, document extraction itself happens in the
background after upload (see `agent/extractors/extraction.py`). This
worker's job at /chat time is to SURFACE the already-persisted
derived_observations for the patient as a context block the answer
pipeline can cite.

If no documents have been uploaded for the patient, the worker
returns an empty string — the supervisor still benefits from the
explicit "nothing to surface" signal in audit + Langfuse.
"""

from __future__ import annotations

import json
import logging

from agent import documents as doc_storage

log = logging.getLogger(__name__)

# Cap on how much of each derived row's payload we render so a chatty
# extraction (e.g., a long chief_concern free-text) doesn't blow up
# the prompt. We surface the full payload in the source-detail panel.
_MAX_PAYLOAD_CHARS = 512


def _render_row(row: dict) -> str:
    payload = json.dumps(row["payload"])
    if len(payload) > _MAX_PAYLOAD_CHARS:
        payload = payload[: _MAX_PAYLOAD_CHARS - 3] + "..."
    bbox = row.get("bbox")
    bbox_attr = (
        f" bbox='{bbox['x0']:.0f},{bbox['y0']:.0f},"
        f"{bbox['x1']:.0f},{bbox['y1']:.0f}'"
        if bbox
        else ""
    )
    return (
        f"  <source id='{row['source_id']}' kind='{row['schema_kind']}' "
        f"document_id='{row['document_id']}' "
        f"page='{row.get('page_number') or 'n/a'}'{bbox_attr}>\n"
        f"    {payload}\n"
        f"  </source>"
    )


async def run_intake_extractor_worker(
    *, database_url: str, patient_id: str
) -> str:
    """Return an `<extracted_documents>` block ready to inject into the
    answer pipeline's user_message. Empty string when there's nothing
    extracted for this patient."""
    rows = doc_storage.list_derived_for_patient(database_url, patient_id)
    log.info(
        "intake_extractor: patient_id=%s found %d derived rows",
        patient_id, len(rows),
    )
    if not rows:
        return ""
    lines = [f"<extracted_documents patient_id='{patient_id}'>"]
    for row in rows:
        lines.append(_render_row(row))
    lines.append("</extracted_documents>")
    return "\n".join(lines)


def count_derived_for_patient(database_url: str, patient_id: str) -> int:
    """Used by the supervisor to populate `extracted_docs` in patient
    context. Avoids loading payloads when only the count is needed."""
    return len(doc_storage.list_derived_for_patient(database_url, patient_id))


def count_unprocessed_docs(database_url: str, patient_id: str) -> int:
    """Documents whose extraction hasn't completed yet. Surfaced to the
    supervisor so it can decide to invoke intake_extractor when there's
    fresh, not-yet-readable content the user might be asking about."""
    docs = doc_storage.list_for_patient(database_url, patient_id)
    return sum(1 for d in docs if d.extraction_status != "done")
