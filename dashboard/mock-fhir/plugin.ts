// Vite plugin: exposes a small in-memory FHIR R4 server at /dashboard-fhir.
// Used in dev to bypass HAPI (which has polluted test data and corp-firewall
// reachability issues). Production parity comes from the FastAPI mount that
// serves the same data shape.

import type { Plugin } from 'vite'
import { PATIENT_PROFILES } from './patients'
import {
  buildPatientGraph,
  buildPractitioner,
} from './build'
import type {
  AllergyIntolerance,
  Bundle,
  BundleEntry,
  CareTeam,
  Condition,
  MedicationRequest,
  MedicationStatement,
  Observation,
  Patient,
  PractitionerRole,
} from '../src/fhir/types'

interface PatientGraph {
  patient: Patient
  allergies: AllergyIntolerance[]
  conditions: Condition[]
  medStatements: MedicationStatement[]
  medRequests: MedicationRequest[]
  careTeams: CareTeam[]
  practitionerRoles: PractitionerRole[]
  practitionerTokens: string[]
  observations: Observation[]
}

function buildAll(): Map<string, PatientGraph> {
  const out = new Map<string, PatientGraph>()
  for (const p of PATIENT_PROFILES) {
    out.set(p.id, buildPatientGraph(p))
  }
  return out
}

function bundle<T extends { id?: string; resourceType: string }>(
  resources: T[],
): Bundle<T> {
  const entry: BundleEntry<T>[] = resources.map((r) => ({
    fullUrl: `/dashboard-fhir/${r.resourceType}/${r.id ?? ''}`,
    resource: r,
  }))
  return {
    resourceType: 'Bundle',
    type: 'searchset',
    total: resources.length,
    entry,
  }
}

function jsonResponse(res: import('http').ServerResponse, status: number, body: unknown): void {
  res.statusCode = status
  res.setHeader('Content-Type', 'application/fhir+json; charset=utf-8')
  res.end(JSON.stringify(body))
}

function operationOutcome(severity: string, code: string, details: string) {
  return {
    resourceType: 'OperationOutcome',
    issue: [{ severity, code, diagnostics: details }],
  }
}

export function mockFhirPlugin(): Plugin {
  let store: Map<string, PatientGraph>

  return {
    name: 'mock-fhir',
    configureServer(server) {
      store = buildAll()

      server.middlewares.use('/dashboard-fhir', (req, res, next) => {
        if (!req.url) return next()

        const url = new URL(req.url, 'http://localhost')
        const path = url.pathname.replace(/^\/+/, '').split('/')
        const resourceType = path[0]
        const idOrEmpty = path[1]
        const params = url.searchParams

        // ---- Dump endpoint (used to mirror data into FastAPI for prod) ----
        if (resourceType === '_dump') {
          const out: Record<string, unknown> = {}
          for (const [id, g] of store.entries()) out[id] = g
          return jsonResponse(res, 200, out)
        }

        // ---- Patient ----
        if (resourceType === 'Patient') {
          if (idOrEmpty) {
            const g = store.get(idOrEmpty)
            if (!g) return jsonResponse(res, 404, operationOutcome('error', 'not-found', `Patient/${idOrEmpty} not found`))
            return jsonResponse(res, 200, g.patient)
          }
          const count = Number(params.get('_count') ?? '50')
          const patients = Array.from(store.values()).map((g) => g.patient).slice(0, count)
          return jsonResponse(res, 200, bundle(patients))
        }

        // ---- AllergyIntolerance ----
        if (resourceType === 'AllergyIntolerance') {
          const patient = params.get('patient')
          if (!patient) return jsonResponse(res, 400, operationOutcome('error', 'invalid', 'patient parameter required'))
          const g = store.get(patient)
          return jsonResponse(res, 200, bundle(g?.allergies ?? []))
        }

        // ---- Condition (with optional clinical-status / category filters) ----
        if (resourceType === 'Condition') {
          const patient = params.get('patient')
          if (!patient) return jsonResponse(res, 400, operationOutcome('error', 'invalid', 'patient parameter required'))
          const g = store.get(patient)
          let conditions = g?.conditions ?? []
          const clinicalStatus = params.get('clinical-status')
          if (clinicalStatus) {
            conditions = conditions.filter((c) =>
              c.clinicalStatus?.coding?.some((cc) => cc.code === clinicalStatus),
            )
          }
          const category = params.get('category')
          if (category) {
            conditions = conditions.filter((c) =>
              c.category?.some((cat) => cat.coding?.some((cc) => cc.code === category)),
            )
          }
          return jsonResponse(res, 200, bundle(conditions))
        }

        // ---- MedicationStatement ----
        if (resourceType === 'MedicationStatement') {
          const patient = params.get('patient')
          if (!patient) return jsonResponse(res, 400, operationOutcome('error', 'invalid', 'patient parameter required'))
          const g = store.get(patient)
          return jsonResponse(res, 200, bundle(g?.medStatements ?? []))
        }

        // ---- MedicationRequest ----
        if (resourceType === 'MedicationRequest') {
          const patient = params.get('patient')
          if (!patient) return jsonResponse(res, 400, operationOutcome('error', 'invalid', 'patient parameter required'))
          const g = store.get(patient)
          return jsonResponse(res, 200, bundle(g?.medRequests ?? []))
        }

        // ---- CareTeam ----
        if (resourceType === 'CareTeam') {
          const patient = params.get('patient')
          if (!patient) return jsonResponse(res, 400, operationOutcome('error', 'invalid', 'patient parameter required'))
          const g = store.get(patient)
          return jsonResponse(res, 200, bundle(g?.careTeams ?? []))
        }

        // ---- PractitionerRole (fallback path) ----
        if (resourceType === 'PractitionerRole') {
          const patient = params.get('patient')
          if (!patient) return jsonResponse(res, 400, operationOutcome('error', 'invalid', 'patient parameter required'))
          const g = store.get(patient)
          return jsonResponse(res, 200, bundle(g?.practitionerRoles ?? []))
        }

        // ---- Practitioner (resolve refs from CareTeam.member.reference) ----
        if (resourceType === 'Practitioner') {
          if (!idOrEmpty) {
            return jsonResponse(res, 400, operationOutcome('error', 'invalid', 'Practitioner search not supported; use Practitioner/{id}'))
          }
          const p = buildPractitioner(idOrEmpty)
          if (!p) return jsonResponse(res, 404, operationOutcome('error', 'not-found', `Practitioner/${idOrEmpty} not found`))
          return jsonResponse(res, 200, p)
        }

        // ---- Observation (with category and _sort filters) ----
        if (resourceType === 'Observation') {
          const patient = params.get('patient')
          if (!patient) return jsonResponse(res, 400, operationOutcome('error', 'invalid', 'patient parameter required'))
          const g = store.get(patient)
          let obs = g?.observations ?? []
          const category = params.get('category')
          if (category) {
            obs = obs.filter((o) => o.category?.some((cat) => cat.coding?.some((cc) => cc.code === category)))
          }
          const sort = params.get('_sort')
          if (sort === '-date') {
            obs = [...obs].sort((a, b) => (b.effectiveDateTime ?? '').localeCompare(a.effectiveDateTime ?? ''))
          } else if (sort === 'date') {
            obs = [...obs].sort((a, b) => (a.effectiveDateTime ?? '').localeCompare(b.effectiveDateTime ?? ''))
          }
          return jsonResponse(res, 200, bundle(obs))
        }

        // ---- Unknown resource ----
        return jsonResponse(res, 404, operationOutcome('error', 'not-found', `Resource type ${resourceType} not supported by mock`))
      })
    },
  }
}
