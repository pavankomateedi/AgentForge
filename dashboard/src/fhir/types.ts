// FHIR R4 type subset — only the fields the dashboard actually reads.
// FHIR's full type surface is enormous; mirroring all of it would be noise.
// If you need a field that isn't here, add it to the relevant interface
// rather than reaching for `any`.

export type FhirString = string

export interface Coding {
  system?: FhirString
  code?: FhirString
  display?: FhirString
}

export interface CodeableConcept {
  coding?: Coding[]
  text?: FhirString
}

export interface Period {
  start?: FhirString
  end?: FhirString
}

export interface Quantity {
  value?: number
  unit?: FhirString
  system?: FhirString
  code?: FhirString
  comparator?: '<' | '<=' | '>=' | '>'
}

export interface Range {
  low?: Quantity
  high?: Quantity
}

export interface Identifier {
  use?: FhirString
  type?: CodeableConcept
  system?: FhirString
  value?: FhirString
}

export interface HumanName {
  use?: FhirString
  text?: FhirString
  family?: FhirString
  given?: FhirString[]
  prefix?: FhirString[]
  suffix?: FhirString[]
}

export interface Reference {
  reference?: FhirString
  type?: FhirString
  display?: FhirString
}

export interface Annotation {
  text?: FhirString
  time?: FhirString
  authorString?: FhirString
}

// --- Bundle ---

export interface BundleLink {
  relation: FhirString
  url: FhirString
}

export interface BundleEntry<T> {
  fullUrl?: FhirString
  resource?: T
  search?: { mode?: FhirString; score?: number }
}

export interface Bundle<T> {
  resourceType: 'Bundle'
  type: FhirString
  total?: number
  link?: BundleLink[]
  entry?: BundleEntry<T>[]
}

// --- OperationOutcome (error envelope) ---

export interface OperationOutcomeIssue {
  severity?: 'fatal' | 'error' | 'warning' | 'information'
  code?: FhirString
  diagnostics?: FhirString
  details?: CodeableConcept
}

export interface OperationOutcome {
  resourceType: 'OperationOutcome'
  issue?: OperationOutcomeIssue[]
}

// --- Patient ---

export interface Patient {
  resourceType: 'Patient'
  id?: FhirString
  identifier?: Identifier[]
  active?: boolean
  name?: HumanName[]
  gender?: 'male' | 'female' | 'other' | 'unknown'
  birthDate?: FhirString
  deceasedBoolean?: boolean
  deceasedDateTime?: FhirString
}

// --- AllergyIntolerance ---

export interface AllergyReaction {
  manifestation?: CodeableConcept[]
  description?: FhirString
  severity?: 'mild' | 'moderate' | 'severe'
}

export interface AllergyIntolerance {
  resourceType: 'AllergyIntolerance'
  id?: FhirString
  clinicalStatus?: CodeableConcept
  verificationStatus?: CodeableConcept
  type?: 'allergy' | 'intolerance'
  category?: Array<'food' | 'medication' | 'environment' | 'biologic'>
  criticality?: 'low' | 'high' | 'unable-to-assess'
  code?: CodeableConcept
  patient?: Reference
  recordedDate?: FhirString
  reaction?: AllergyReaction[]
  note?: Annotation[]
}

// --- Condition (problem list) ---

export interface Condition {
  resourceType: 'Condition'
  id?: FhirString
  clinicalStatus?: CodeableConcept
  verificationStatus?: CodeableConcept
  category?: CodeableConcept[]
  severity?: CodeableConcept
  code?: CodeableConcept
  subject?: Reference
  onsetDateTime?: FhirString
  onsetPeriod?: Period
  recordedDate?: FhirString
  note?: Annotation[]
}

// --- MedicationStatement (current meds) ---

export interface Dosage {
  text?: FhirString
  patientInstruction?: FhirString
}

export interface MedicationStatement {
  resourceType: 'MedicationStatement'
  id?: FhirString
  status?: FhirString
  medicationCodeableConcept?: CodeableConcept
  medicationReference?: Reference
  subject?: Reference
  effectiveDateTime?: FhirString
  effectivePeriod?: Period
  dateAsserted?: FhirString
  dosage?: Dosage[]
  note?: Annotation[]
}

// --- MedicationRequest (prescriptions) ---

export interface MedicationRequest {
  resourceType: 'MedicationRequest'
  id?: FhirString
  status?: FhirString
  intent?: FhirString
  medicationCodeableConcept?: CodeableConcept
  medicationReference?: Reference
  subject?: Reference
  authoredOn?: FhirString
  requester?: Reference
  dosageInstruction?: Dosage[]
  note?: Annotation[]
}

// --- CareTeam ---

export interface CareTeamParticipant {
  role?: CodeableConcept[]
  member?: Reference
  onBehalfOf?: Reference
  period?: Period
}

export interface CareTeam {
  resourceType: 'CareTeam'
  id?: FhirString
  status?: FhirString
  name?: FhirString
  subject?: Reference
  participant?: CareTeamParticipant[]
  period?: Period
}

// --- Practitioner / PractitionerRole (CareTeam fallback) ---

export interface Practitioner {
  resourceType: 'Practitioner'
  id?: FhirString
  identifier?: Identifier[]
  active?: boolean
  name?: HumanName[]
}

export interface PractitionerRole {
  resourceType: 'PractitionerRole'
  id?: FhirString
  active?: boolean
  practitioner?: Reference
  code?: CodeableConcept[]
  specialty?: CodeableConcept[]
  organization?: Reference
}

// --- Observation (labs, vitals) ---

export interface ObservationReferenceRange {
  low?: Quantity
  high?: Quantity
  type?: CodeableConcept
  text?: FhirString
}

export interface ObservationComponent {
  code: CodeableConcept
  valueQuantity?: Quantity
  valueCodeableConcept?: CodeableConcept
  valueString?: FhirString
  valueBoolean?: boolean
  interpretation?: CodeableConcept[]
}

export interface Observation {
  resourceType: 'Observation'
  id?: FhirString
  status?: FhirString
  category?: CodeableConcept[]
  code?: CodeableConcept
  subject?: Reference
  effectiveDateTime?: FhirString
  effectivePeriod?: Period
  issued?: FhirString
  valueQuantity?: Quantity
  valueCodeableConcept?: CodeableConcept
  valueString?: FhirString
  valueBoolean?: boolean
  interpretation?: CodeableConcept[]
  referenceRange?: ObservationReferenceRange[]
  component?: ObservationComponent[]
  note?: Annotation[]
}
