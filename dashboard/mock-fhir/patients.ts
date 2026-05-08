// 20 curated synthetic patients. Each has a profile tag that the resource
// generator (data.ts) uses to populate clinically-coherent allergies,
// problems, medications, prescriptions, care team, and labs.
//
// All names are ASCII so the demo doesn't trip on encoding paths. The
// profiles span age, sex, and complexity to exercise every card's
// loading/empty/populated states.

export type ClinicalProfile =
  | 't2dm-controlled'
  | 'hfref-ckd'
  | 't2dm-uncontrolled'
  | 'asthma-mild'
  | 'multimorbidity-elderly'
  | 'htn-hyperlipidemia'
  | 'gestational-diabetes'
  | 'copd'
  | 'breast-cancer-survivor'
  | 'afib-warfarin'
  | 'fibromyalgia'
  | 'crohns'
  | 'rheumatoid-arthritis'
  | 'hyperlipidemia'
  | 'dementia'
  | 'pediatric-adhd'
  | 't1dm-adolescent'
  | 'sickle-cell'
  | 'hypothyroidism'
  | 'healthy-adult'

export interface PatientProfile {
  id: string
  mrn: string
  family: string
  given: string
  gender: 'male' | 'female'
  birthDate: string
  active: boolean
  profile: ClinicalProfile
}

export const PATIENT_PROFILES: PatientProfile[] = [
  { id: 'mrn-001', mrn: 'MRN-001', family: 'Hayes', given: 'Margaret', gender: 'female', birthDate: '1962-04-14', active: true, profile: 't2dm-controlled' },
  { id: 'mrn-002', mrn: 'MRN-002', family: 'Patterson', given: 'James', gender: 'male', birthDate: '1953-07-22', active: true, profile: 'hfref-ckd' },
  { id: 'mrn-003', mrn: 'MRN-003', family: 'Mitchell', given: 'Robert', gender: 'male', birthDate: '1966-09-08', active: true, profile: 't2dm-uncontrolled' },
  { id: 'mrn-004', mrn: 'MRN-004', family: 'Kim', given: 'Sarah', gender: 'female', birthDate: '1990-02-11', active: true, profile: 'asthma-mild' },
  { id: 'mrn-005', mrn: 'MRN-005', family: 'Brooks', given: 'Eleanor', gender: 'female', birthDate: '1945-11-27', active: true, profile: 'multimorbidity-elderly' },
  { id: 'mrn-006', mrn: 'MRN-006', family: 'Chen', given: 'David', gender: 'male', birthDate: '1979-06-03', active: true, profile: 'htn-hyperlipidemia' },
  { id: 'mrn-007', mrn: 'MRN-007', family: 'Gonzalez', given: 'Maria', gender: 'female', birthDate: '1996-08-17', active: true, profile: 'gestational-diabetes' },
  { id: 'mrn-008', mrn: 'MRN-008', family: 'Foster', given: 'William', gender: 'male', birthDate: '1957-12-30', active: true, profile: 'copd' },
  { id: 'mrn-009', mrn: 'MRN-009', family: 'Patel', given: 'Aisha', gender: 'female', birthDate: '1972-03-25', active: true, profile: 'breast-cancer-survivor' },
  { id: 'mrn-010', mrn: 'MRN-010', family: 'Reed', given: 'Thomas', gender: 'male', birthDate: '1951-05-09', active: true, profile: 'afib-warfarin' },
  { id: 'mrn-011', mrn: 'MRN-011', family: 'Walsh', given: 'Jennifer', gender: 'female', birthDate: '1984-01-19', active: true, profile: 'fibromyalgia' },
  { id: 'mrn-012', mrn: 'MRN-012', family: 'Johnson', given: 'Marcus', gender: 'male', birthDate: '2002-10-04', active: true, profile: 'crohns' },
  { id: 'mrn-013', mrn: 'MRN-013', family: 'Park', given: 'Linda', gender: 'female', birthDate: '1959-04-29', active: true, profile: 'rheumatoid-arthritis' },
  { id: 'mrn-014', mrn: 'MRN-014', family: 'Singh', given: 'Daniel', gender: 'male', birthDate: '1974-07-13', active: true, profile: 'hyperlipidemia' },
  { id: 'mrn-015', mrn: 'MRN-015', family: 'Ortiz', given: 'Patricia', gender: 'female', birthDate: '1936-09-21', active: true, profile: 'dementia' },
  { id: 'mrn-016', mrn: 'MRN-016', family: 'Lee', given: 'Christopher', gender: 'male', birthDate: '2015-03-08', active: true, profile: 'pediatric-adhd' },
  { id: 'mrn-017', mrn: 'MRN-017', family: 'Williams', given: 'Hannah', gender: 'female', birthDate: '2008-12-12', active: true, profile: 't1dm-adolescent' },
  { id: 'mrn-018', mrn: 'MRN-018', family: 'Adebayo', given: 'George', gender: 'male', birthDate: '1964-08-05', active: true, profile: 'sickle-cell' },
  { id: 'mrn-019', mrn: 'MRN-019', family: 'Nakamura', given: 'Karen', gender: 'female', birthDate: '1969-02-18', active: true, profile: 'hypothyroidism' },
  { id: 'mrn-020', mrn: 'MRN-020', family: "O'Brien", given: 'Steven', gender: 'male', birthDate: '1989-06-22', active: true, profile: 'healthy-adult' },
]
