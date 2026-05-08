// Resource builders: take a PatientProfile + ProfileSpec, return a complete
// set of FHIR R4 resources for that patient. Pure functions, no I/O.

import type {
  AllergyIntolerance,
  CareTeam,
  Condition,
  MedicationRequest,
  MedicationStatement,
  Observation,
  Patient,
  Practitioner,
  PractitionerRole,
} from '../src/fhir/types'
import {
  ALLERGY_CATALOG,
  CONDITION_CATALOG,
  LAB_CATALOG,
  MED_CATALOG,
  PRACTITIONER_CATALOG,
} from './catalog'
import type { PatientProfile } from './patients'
import { PROFILE_SPECS } from './templates'

// Today's date as a fixed anchor; multiple seeds make for stable demos.
const TODAY = new Date()
function isoDateOffset(daysAgo: number): string {
  const d = new Date(TODAY)
  d.setDate(d.getDate() - daysAgo)
  return d.toISOString().slice(0, 10)
}
function isoDateYearOffset(years: number): string {
  const d = new Date(TODAY)
  d.setFullYear(d.getFullYear() - years)
  return d.toISOString().slice(0, 10)
}

export function buildPatient(p: PatientProfile): Patient {
  return {
    resourceType: 'Patient',
    id: p.id,
    active: p.active,
    name: [
      {
        use: 'official',
        family: p.family,
        given: [p.given],
      },
    ],
    gender: p.gender,
    birthDate: p.birthDate,
    identifier: [
      {
        use: 'usual',
        type: { coding: [{ system: 'http://terminology.hl7.org/CodeSystem/v2-0203', code: 'MR', display: 'Medical Record Number' }] },
        value: p.mrn,
      },
    ],
  }
}

export function buildAllergies(p: PatientProfile, tokens: string[]): AllergyIntolerance[] {
  return tokens.flatMap((t, idx) => {
    const def = ALLERGY_CATALOG[t]
    if (!def) return []
    if (t === 'nkda') {
      // No-known-drug-allergies isn't a real allergy resource. Skip the
      // resource and let the card render "No known allergies."
      return []
    }
    const a: AllergyIntolerance = {
      resourceType: 'AllergyIntolerance',
      id: `${p.id}-allergy-${idx + 1}`,
      clinicalStatus: { coding: [{ system: 'http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical', code: 'active' }] },
      verificationStatus: { coding: [{ system: 'http://terminology.hl7.org/CodeSystem/allergyintolerance-verification', code: 'confirmed' }] },
      criticality: def.criticality,
      code: { text: def.display },
      patient: { reference: `Patient/${p.id}` },
      recordedDate: isoDateYearOffset(2),
      reaction: def.reactions.length > 0
        ? [{ manifestation: def.reactions.map((m) => ({ text: m })), severity: def.criticality === 'high' ? 'severe' : 'mild' }]
        : undefined,
    }
    return [a]
  })
}

export function buildConditions(p: PatientProfile, tokens: string[]): Condition[] {
  return tokens.flatMap((t, idx) => {
    const def = CONDITION_CATALOG[t]
    if (!def) return []
    const c: Condition = {
      resourceType: 'Condition',
      id: `${p.id}-cond-${idx + 1}`,
      clinicalStatus: { coding: [{ system: 'http://terminology.hl7.org/CodeSystem/condition-clinical', code: def.clinicalStatus }] },
      verificationStatus: { coding: [{ system: 'http://terminology.hl7.org/CodeSystem/condition-ver-status', code: 'confirmed' }] },
      category: [
        { coding: [{ system: 'http://terminology.hl7.org/CodeSystem/condition-category', code: def.category }] },
      ],
      code: {
        coding: def.icd10
          ? [{ system: 'http://hl7.org/fhir/sid/icd-10-cm', code: def.icd10, display: def.display }]
          : undefined,
        text: def.display,
      },
      subject: { reference: `Patient/${p.id}` },
      onsetDateTime: isoDateYearOffset(def.onsetYearOffset),
      recordedDate: isoDateYearOffset(def.onsetYearOffset),
    }
    return [c]
  })
}

export function buildMedicationStatements(p: PatientProfile, tokens: string[]): MedicationStatement[] {
  return tokens.flatMap((t, idx) => {
    const def = MED_CATALOG[t]
    if (!def) return []
    const m: MedicationStatement = {
      resourceType: 'MedicationStatement',
      id: `${p.id}-med-${idx + 1}`,
      status: 'active',
      medicationCodeableConcept: { text: def.display },
      subject: { reference: `Patient/${p.id}` },
      effectiveDateTime: isoDateYearOffset(def.startedYearsAgo),
      dosage: [{ text: `${def.dose} ${def.frequency}` }],
    }
    return [m]
  })
}

export function buildMedicationRequests(p: PatientProfile, tokens: string[]): MedicationRequest[] {
  return tokens.flatMap((t, idx) => {
    const def = MED_CATALOG[t]
    if (!def) return []
    const r: MedicationRequest = {
      resourceType: 'MedicationRequest',
      id: `${p.id}-rx-${idx + 1}`,
      status: 'active',
      intent: 'order',
      medicationCodeableConcept: { text: def.display },
      subject: { reference: `Patient/${p.id}` },
      authoredOn: isoDateOffset(14 + idx * 10),
      dosageInstruction: [{ text: `${def.dose} ${def.frequency}` }],
    }
    return [r]
  })
}

export function buildCareTeam(p: PatientProfile, tokens: string[]): CareTeam[] {
  if (tokens.length === 0) return []
  const team: CareTeam = {
    resourceType: 'CareTeam',
    id: `${p.id}-careteam`,
    status: 'active',
    name: `${p.given} ${p.family} Care Team`,
    subject: { reference: `Patient/${p.id}` },
    participant: tokens.map((t) => {
      const def = PRACTITIONER_CATALOG[t]
      const display = def ? `${def.prefix ? def.prefix + '. ' : ''}${def.given} ${def.family}` : t
      return {
        role: def ? [{ text: def.role }] : undefined,
        member: { reference: `Practitioner/${t}`, display },
      }
    }),
  }
  return [team]
}

// Practitioner.read targets — used by CareTeamCard's PractitionerRole fallback.
export function buildPractitioner(token: string): Practitioner | null {
  const def = PRACTITIONER_CATALOG[token]
  if (!def) return null
  return {
    resourceType: 'Practitioner',
    id: token,
    active: true,
    name: [{ family: def.family, given: [def.given], prefix: def.prefix ? [def.prefix] : undefined }],
  }
}

// PractitionerRoles aren't strictly needed since CareTeam is populated, but
// a minimal set keeps the fallback path testable.
export function buildPractitionerRoles(p: PatientProfile, tokens: string[]): PractitionerRole[] {
  return tokens.flatMap((t, idx) => {
    const def = PRACTITIONER_CATALOG[t]
    if (!def) return []
    const r: PractitionerRole = {
      resourceType: 'PractitionerRole',
      id: `${p.id}-role-${idx + 1}`,
      active: true,
      practitioner: { reference: `Practitioner/${t}`, display: `${def.given} ${def.family}` },
      specialty: def.specialty ? [{ text: def.specialty }] : undefined,
    }
    return [r]
  })
}

export function buildObservations(p: PatientProfile, labSpecs: string[]): Observation[] {
  return labSpecs.flatMap((spec, idx) => {
    const [token, daysAgoRaw] = spec.split('@')
    const def = LAB_CATALOG[token]
    if (!def) return []
    const daysAgo = Number(daysAgoRaw ?? '30')
    const o: Observation = {
      resourceType: 'Observation',
      id: `${p.id}-obs-${idx + 1}`,
      status: 'final',
      category: [
        { coding: [{ system: 'http://terminology.hl7.org/CodeSystem/observation-category', code: 'laboratory', display: 'Laboratory' }] },
      ],
      code: {
        coding: def.loinc
          ? [{ system: 'http://loinc.org', code: def.loinc, display: def.display }]
          : undefined,
        text: def.display,
      },
      subject: { reference: `Patient/${p.id}` },
      effectiveDateTime: isoDateOffset(daysAgo),
      issued: isoDateOffset(daysAgo),
      valueQuantity:
        typeof def.value === 'number'
          ? { value: def.value, unit: def.unit, system: def.unit ? 'http://unitsofmeasure.org' : undefined, code: def.unit }
          : undefined,
      valueString: typeof def.value === 'string' ? def.value : undefined,
      referenceRange:
        def.refLow !== undefined || def.refHigh !== undefined || def.refText
          ? [
              {
                low: def.refLow !== undefined ? { value: def.refLow, unit: def.unit } : undefined,
                high: def.refHigh !== undefined ? { value: def.refHigh, unit: def.unit } : undefined,
                text: def.refText,
              },
            ]
          : undefined,
      interpretation: def.flag
        ? [{ coding: [{ system: 'http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation', code: def.flag }] }]
        : undefined,
    }
    return [o]
  })
}

// Top-level helper: build the full resource graph for a patient.
export function buildPatientGraph(p: PatientProfile) {
  const spec = PROFILE_SPECS[p.profile]
  return {
    patient: buildPatient(p),
    allergies: buildAllergies(p, spec.allergies),
    conditions: buildConditions(p, spec.conditions),
    medStatements: buildMedicationStatements(p, spec.medStatements),
    medRequests: buildMedicationRequests(p, spec.medRequests),
    careTeams: buildCareTeam(p, spec.careTeam),
    practitionerRoles: buildPractitionerRoles(p, spec.careTeam),
    practitionerTokens: spec.careTeam,
    observations: buildObservations(p, spec.labs),
  }
}
