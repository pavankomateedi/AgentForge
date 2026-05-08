"""In-process mock FHIR R4 server for the OpenEMR Patient Dashboard.

The dashboard SPA (dashboard/) consumes OpenEMR's REST + FHIR R4 API at
runtime. For development without a running OpenEMR instance, a Vite dev
plugin (dashboard/mock-fhir/plugin.ts) serves 20 curated synthetic
patients. This module mirrors that plugin so the production deployed
dashboard has a working backend even when no OpenEMR is wired.

Data is loaded from agent/dashboard_fhir_data.json — generated once via
`curl http://localhost:5174/dashboard-fhir/_dump` against the dev
plugin. Single source of truth lives in TypeScript; this is a frozen
snapshot. To rebuild: rerun the dev server and re-curl.

Endpoints (mounted at /dashboard-fhir):
  GET /Patient                        — Bundle, supports _count
  GET /Patient/{id}                   — single resource
  GET /AllergyIntolerance?patient=    — Bundle filtered by patient
  GET /Condition?patient=&clinical-status=&category=
  GET /MedicationStatement?patient=
  GET /MedicationRequest?patient=
  GET /CareTeam?patient=
  GET /PractitionerRole?patient=
  GET /Practitioner/{token}
  GET /Observation?patient=&category=&_sort=

Production parity: this is intentionally a substitute for OpenEMR.
The dashboard's OAuth2 PKCE flow, FHIR resource shapes, and search
parameters match real OpenEMR; pointing dashboard/.env at a real
OpenEMR instance requires zero code changes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/dashboard-fhir", include_in_schema=False)

_DATA_PATH = Path(__file__).parent / "dashboard_fhir_data.json"


def _load() -> dict[str, dict[str, Any]]:
    """Load the JSON dump once at import. If missing, return empty so the
    rest of the FastAPI app still boots — the dashboard surfaces an empty
    picker rather than a 500 in that case."""
    if not _DATA_PATH.is_file():
        return {}
    with _DATA_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


_DATA: dict[str, dict[str, Any]] = _load()


# ---------- Helpers ----------


def _bundle(resources: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "resourceType": "Bundle",
        "type": "searchset",
        "total": len(resources),
        "entry": [
            {
                "fullUrl": f"/dashboard-fhir/{r.get('resourceType', '')}/{r.get('id', '')}",
                "resource": r,
            }
            for r in resources
        ],
    }


def _operation_outcome(severity: str, code: str, details: str) -> dict[str, Any]:
    return {
        "resourceType": "OperationOutcome",
        "issue": [{"severity": severity, "code": code, "diagnostics": details}],
    }


def _fhir_response(body: dict[str, Any], status: int = 200) -> JSONResponse:
    return JSONResponse(
        content=body,
        status_code=status,
        media_type="application/fhir+json",
    )


def _require_patient_param(request: Request) -> str:
    patient = request.query_params.get("patient")
    if not patient:
        raise HTTPException(
            status_code=400,
            detail=_operation_outcome("error", "invalid", "patient parameter required"),
        )
    return patient


# ---------- Routes ----------


@router.get("/_dump")
async def dump_all() -> JSONResponse:
    """Returns the full in-memory dataset. Used by tests + as a sanity probe."""
    return _fhir_response(_DATA)


@router.get("/Patient")
async def search_patients(request: Request) -> JSONResponse:
    count_str = request.query_params.get("_count", "50")
    try:
        count = int(count_str)
    except ValueError:
        count = 50
    patients = [g["patient"] for g in _DATA.values()][:count]
    return _fhir_response(_bundle(patients))


@router.get("/Patient/{patient_id}")
async def get_patient(patient_id: str) -> JSONResponse:
    g = _DATA.get(patient_id)
    if not g:
        return _fhir_response(
            _operation_outcome("error", "not-found", f"Patient/{patient_id} not found"),
            status=404,
        )
    return _fhir_response(g["patient"])


@router.get("/AllergyIntolerance")
async def search_allergies(request: Request) -> JSONResponse:
    patient_id = _require_patient_param(request)
    g = _DATA.get(patient_id, {})
    return _fhir_response(_bundle(g.get("allergies", [])))


@router.get("/Condition")
async def search_conditions(request: Request) -> JSONResponse:
    patient_id = _require_patient_param(request)
    g = _DATA.get(patient_id, {})
    conditions: list[dict[str, Any]] = list(g.get("conditions", []))

    clinical_status = request.query_params.get("clinical-status")
    if clinical_status:
        conditions = [
            c
            for c in conditions
            if any(
                cc.get("code") == clinical_status
                for cc in (c.get("clinicalStatus", {}) or {}).get("coding", []) or []
            )
        ]

    category = request.query_params.get("category")
    if category:
        conditions = [
            c
            for c in conditions
            if any(
                any(cc.get("code") == category for cc in (cat.get("coding") or []))
                for cat in (c.get("category") or [])
            )
        ]

    return _fhir_response(_bundle(conditions))


@router.get("/MedicationStatement")
async def search_med_statements(request: Request) -> JSONResponse:
    patient_id = _require_patient_param(request)
    g = _DATA.get(patient_id, {})
    return _fhir_response(_bundle(g.get("medStatements", [])))


@router.get("/MedicationRequest")
async def search_med_requests(request: Request) -> JSONResponse:
    patient_id = _require_patient_param(request)
    g = _DATA.get(patient_id, {})
    return _fhir_response(_bundle(g.get("medRequests", [])))


@router.get("/CareTeam")
async def search_care_teams(request: Request) -> JSONResponse:
    patient_id = _require_patient_param(request)
    g = _DATA.get(patient_id, {})
    return _fhir_response(_bundle(g.get("careTeams", [])))


@router.get("/PractitionerRole")
async def search_practitioner_roles(request: Request) -> JSONResponse:
    patient_id = _require_patient_param(request)
    g = _DATA.get(patient_id, {})
    return _fhir_response(_bundle(g.get("practitionerRoles", [])))


# Practitioner directory: built on demand from any patient that lists the token
# in their care team. Lookups are O(patients) but the set is tiny (20), so
# correctness over micro-optimization here.
@router.get("/Practitioner/{token}")
async def get_practitioner(token: str) -> JSONResponse:
    for g in _DATA.values():
        for role in g.get("practitionerRoles", []):
            ref = (role.get("practitioner") or {}).get("reference", "")
            if ref.endswith(f"/{token}") or ref == token:
                # Reconstruct a minimal Practitioner from PractitionerRole's display.
                display = (role.get("practitioner") or {}).get("display", "")
                given = display.split(" ")[0] if display else ""
                family = " ".join(display.split(" ")[1:]) if display else ""
                return _fhir_response(
                    {
                        "resourceType": "Practitioner",
                        "id": token,
                        "active": True,
                        "name": [
                            {"given": [given] if given else [], "family": family}
                        ],
                    }
                )
    return _fhir_response(
        _operation_outcome("error", "not-found", f"Practitioner/{token} not found"),
        status=404,
    )


@router.get("/Observation")
async def search_observations(request: Request) -> JSONResponse:
    patient_id = _require_patient_param(request)
    g = _DATA.get(patient_id, {})
    obs: list[dict[str, Any]] = list(g.get("observations", []))

    category = request.query_params.get("category")
    if category:
        obs = [
            o
            for o in obs
            if any(
                any(cc.get("code") == category for cc in (cat.get("coding") or []))
                for cat in (o.get("category") or [])
            )
        ]

    sort = request.query_params.get("_sort")
    if sort == "-date":
        obs = sorted(obs, key=lambda o: o.get("effectiveDateTime") or "", reverse=True)
    elif sort == "date":
        obs = sorted(obs, key=lambda o: o.get("effectiveDateTime") or "")

    return _fhir_response(_bundle(obs))
