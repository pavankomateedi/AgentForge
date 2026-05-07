// Typed wrappers per resource the dashboard cards consume. These exist so
// each card stays declarative — call `loadAllergies(patientId)` rather than
// reach into search params.

import type { FhirClient } from './client'
import type {
  AllergyIntolerance,
  CareTeam,
  Condition,
  HumanName,
  MedicationRequest,
  MedicationStatement,
  Observation,
  Patient,
  Practitioner,
  PractitionerRole,
} from './types'

export async function getPatient(client: FhirClient, id: string): Promise<Patient> {
  return client.get<Patient>(`/Patient/${id}`)
}

export async function listAllPatients(client: FhirClient, count = 25): Promise<Patient[]> {
  return client.searchAll<Patient>('Patient', { _count: count })
}

export async function loadAllergies(client: FhirClient, patientId: string): Promise<AllergyIntolerance[]> {
  return client.searchAll<AllergyIntolerance>('AllergyIntolerance', { patient: patientId })
}

export async function loadProblems(client: FhirClient, patientId: string): Promise<Condition[]> {
  return client.searchAll<Condition>('Condition', {
    patient: patientId,
    'clinical-status': 'active',
    category: 'problem-list-item',
  })
}

export async function loadMedicationStatements(
  client: FhirClient,
  patientId: string,
): Promise<MedicationStatement[]> {
  return client.searchAll<MedicationStatement>('MedicationStatement', { patient: patientId })
}

export async function loadMedicationRequests(
  client: FhirClient,
  patientId: string,
): Promise<MedicationRequest[]> {
  return client.searchAll<MedicationRequest>('MedicationRequest', { patient: patientId })
}

export async function loadCareTeams(client: FhirClient, patientId: string): Promise<CareTeam[]> {
  return client.searchAll<CareTeam>('CareTeam', { patient: patientId })
}

export async function loadObservationsLab(
  client: FhirClient,
  patientId: string,
): Promise<Observation[]> {
  return client.searchAll<Observation>('Observation', {
    patient: patientId,
    category: 'laboratory',
    _sort: '-date',
  })
}

// CareTeam fallback: hit Practitioner+PractitionerRole when CareTeam is empty.
export async function loadPractitionerRoles(
  client: FhirClient,
  patientId: string,
): Promise<{ roles: PractitionerRole[]; practitioners: Map<string, Practitioner> }> {
  const roles = await client.searchAll<PractitionerRole>('PractitionerRole', {
    patient: patientId,
    _include: 'PractitionerRole:practitioner',
  })
  const practitioners = new Map<string, Practitioner>()
  for (const r of roles) {
    const refId = r.practitioner?.reference?.split('/').pop()
    if (refId && !practitioners.has(refId)) {
      try {
        const p = await client.get<Practitioner>(`/Practitioner/${refId}`)
        practitioners.set(refId, p)
      } catch {
        // Best-effort enrichment; skip on failure.
      }
    }
  }
  return { roles, practitioners }
}

// --- Display helpers (pure, no I/O). Kept here so card components are render-only. ---

export function formatHumanName(name?: HumanName): string {
  if (!name) return ''
  if (name.text) return name.text
  const given = (name.given ?? []).join(' ').trim()
  const parts = [given, name.family].filter(Boolean)
  return parts.join(' ').trim()
}

export function pickPatientName(patient: Patient): string {
  const official = patient.name?.find((n) => n.use === 'official')
  return formatHumanName(official ?? patient.name?.[0])
}

export function pickMRN(patient: Patient): string | undefined {
  // Prefer the identifier whose type.coding includes "MR" (FHIR code for medical record number).
  const mr = patient.identifier?.find((i) =>
    i.type?.coding?.some((c) => c.code === 'MR'),
  )
  return mr?.value ?? patient.identifier?.[0]?.value
}

export function pickMedicationLabel(
  res: MedicationStatement | MedicationRequest,
): string {
  const cc = res.medicationCodeableConcept
  if (cc?.text) return cc.text
  const coding = cc?.coding?.[0]
  if (coding?.display) return coding.display
  if (coding?.code) return coding.code
  if (res.medicationReference?.display) return res.medicationReference.display
  return 'Unknown medication'
}
