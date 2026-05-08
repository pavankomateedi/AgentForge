// Catalog of clinical items keyed by short tokens. The profile templates
// reference these tokens; the resource builders (build.ts) read this
// catalog to assemble fully-typed FHIR R4 resources.

export interface AllergyDef {
  display: string
  rxnormOrSystem?: string
  code?: string
  criticality: 'low' | 'high' | 'unable-to-assess'
  reactions: string[]
}

export interface ConditionDef {
  display: string
  icd10?: string
  snomed?: string
  category: 'problem-list-item' | 'encounter-diagnosis'
  clinicalStatus: 'active' | 'inactive' | 'resolved'
  onsetYearOffset: number // years before today
}

export interface MedDef {
  display: string
  rxnorm?: string
  dose: string
  frequency: string
  startedYearsAgo: number
}

export interface PractitionerDef {
  family: string
  given: string
  prefix?: string
  role: string
  specialty?: string
}

export interface LabDef {
  display: string
  loinc?: string
  value: number | string
  unit?: string
  refLow?: number
  refHigh?: number
  refText?: string
  // 'H' = high, 'L' = low, 'A' = abnormal, undefined = normal
  flag?: 'H' | 'L' | 'A'
}

// --- Allergies ---

export const ALLERGY_CATALOG: Record<string, AllergyDef> = {
  penicillin: { display: 'Penicillin', criticality: 'high', reactions: ['Hives', 'Anaphylaxis'] },
  sulfa: { display: 'Sulfa drugs', criticality: 'high', reactions: ['Rash'] },
  peanut: { display: 'Peanut', criticality: 'high', reactions: ['Anaphylaxis'] },
  pollen: { display: 'Pollen', criticality: 'low', reactions: ['Rhinitis', 'Itchy eyes'] },
  latex: { display: 'Latex', criticality: 'high', reactions: ['Contact dermatitis'] },
  aspirin: { display: 'Aspirin', criticality: 'high', reactions: ['Asthma exacerbation'] },
  nkda: { display: 'No known drug allergies', criticality: 'low', reactions: [] },
}

// --- Conditions ---

export const CONDITION_CATALOG: Record<string, ConditionDef> = {
  t2dm: { display: 'Type 2 diabetes mellitus', icd10: 'E11.9', category: 'problem-list-item', clinicalStatus: 'active', onsetYearOffset: 8 },
  t1dm: { display: 'Type 1 diabetes mellitus', icd10: 'E10.9', category: 'problem-list-item', clinicalStatus: 'active', onsetYearOffset: 4 },
  htn: { display: 'Essential hypertension', icd10: 'I10', category: 'problem-list-item', clinicalStatus: 'active', onsetYearOffset: 7 },
  hyperlipidemia: { display: 'Hyperlipidemia, unspecified', icd10: 'E78.5', category: 'problem-list-item', clinicalStatus: 'active', onsetYearOffset: 6 },
  hfref: { display: 'Heart failure with reduced ejection fraction', icd10: 'I50.20', category: 'problem-list-item', clinicalStatus: 'active', onsetYearOffset: 3 },
  'ckd-3': { display: 'Chronic kidney disease, stage 3', icd10: 'N18.30', category: 'problem-list-item', clinicalStatus: 'active', onsetYearOffset: 4 },
  aki: { display: 'Acute kidney injury', icd10: 'N17.9', category: 'problem-list-item', clinicalStatus: 'active', onsetYearOffset: 0 },
  asthma: { display: 'Mild persistent asthma', icd10: 'J45.30', category: 'problem-list-item', clinicalStatus: 'active', onsetYearOffset: 12 },
  copd: { display: 'Chronic obstructive pulmonary disease', icd10: 'J44.9', category: 'problem-list-item', clinicalStatus: 'active', onsetYearOffset: 9 },
  obesity: { display: 'Obesity, BMI 30-34.9', icd10: 'E66.9', category: 'problem-list-item', clinicalStatus: 'active', onsetYearOffset: 10 },
  osteoarthritis: { display: 'Osteoarthritis, generalized', icd10: 'M15.9', category: 'problem-list-item', clinicalStatus: 'active', onsetYearOffset: 5 },
  osteopenia: { display: 'Osteopenia', icd10: 'M85.80', category: 'problem-list-item', clinicalStatus: 'active', onsetYearOffset: 3 },
  'breast-cancer-history': { display: 'Personal history of breast cancer', icd10: 'Z85.3', category: 'problem-list-item', clinicalStatus: 'active', onsetYearOffset: 4 },
  afib: { display: 'Atrial fibrillation', icd10: 'I48.91', category: 'problem-list-item', clinicalStatus: 'active', onsetYearOffset: 2 },
  fibromyalgia: { display: 'Fibromyalgia', icd10: 'M79.7', category: 'problem-list-item', clinicalStatus: 'active', onsetYearOffset: 6 },
  depression: { display: 'Major depressive disorder, recurrent', icd10: 'F33.1', category: 'problem-list-item', clinicalStatus: 'active', onsetYearOffset: 3 },
  crohns: { display: "Crohn's disease, unspecified", icd10: 'K50.90', category: 'problem-list-item', clinicalStatus: 'active', onsetYearOffset: 3 },
  ra: { display: 'Rheumatoid arthritis', icd10: 'M06.9', category: 'problem-list-item', clinicalStatus: 'active', onsetYearOffset: 8 },
  dementia: { display: 'Dementia, unspecified', icd10: 'F03.90', category: 'problem-list-item', clinicalStatus: 'active', onsetYearOffset: 2 },
  adhd: { display: 'ADHD, predominantly inattentive type', icd10: 'F90.0', category: 'problem-list-item', clinicalStatus: 'active', onsetYearOffset: 3 },
  'sickle-cell': { display: 'Sickle-cell disease, unspecified', icd10: 'D57.1', category: 'problem-list-item', clinicalStatus: 'active', onsetYearOffset: 30 },
  hypothyroidism: { display: 'Hypothyroidism, unspecified', icd10: 'E03.9', category: 'problem-list-item', clinicalStatus: 'active', onsetYearOffset: 7 },
  gdm: { display: 'Gestational diabetes mellitus', icd10: 'O24.419', category: 'problem-list-item', clinicalStatus: 'active', onsetYearOffset: 0 },
  pregnancy: { display: 'Pregnancy, second trimester', icd10: 'Z3A.20', category: 'problem-list-item', clinicalStatus: 'active', onsetYearOffset: 0 },
}

// --- Medications ---

export const MED_CATALOG: Record<string, MedDef> = {
  'metformin-1000': { display: 'Metformin 1000 mg', dose: '1000 mg', frequency: 'twice daily', startedYearsAgo: 6 },
  'metformin-500': { display: 'Metformin 500 mg', dose: '500 mg', frequency: 'twice daily', startedYearsAgo: 4 },
  'atorvastatin-40': { display: 'Atorvastatin 40 mg', dose: '40 mg', frequency: 'daily at bedtime', startedYearsAgo: 4 },
  'atorvastatin-20': { display: 'Atorvastatin 20 mg', dose: '20 mg', frequency: 'daily at bedtime', startedYearsAgo: 2 },
  'lisinopril-20': { display: 'Lisinopril 20 mg', dose: '20 mg', frequency: 'daily', startedYearsAgo: 3 },
  'lisinopril-10': { display: 'Lisinopril 10 mg', dose: '10 mg', frequency: 'daily', startedYearsAgo: 5 },
  'metoprolol-50': { display: 'Metoprolol succinate 50 mg', dose: '50 mg', frequency: 'daily', startedYearsAgo: 2 },
  'metoprolol-25': { display: 'Metoprolol succinate 25 mg', dose: '25 mg', frequency: 'daily', startedYearsAgo: 2 },
  'furosemide-40': { display: 'Furosemide 40 mg', dose: '40 mg', frequency: 'daily', startedYearsAgo: 2 },
  'furosemide-20': { display: 'Furosemide 20 mg', dose: '20 mg', frequency: 'daily', startedYearsAgo: 2 },
  'warfarin-5': { display: 'Warfarin 5 mg', dose: '5 mg', frequency: 'daily', startedYearsAgo: 2 },
  'aspirin-81': { display: 'Aspirin 81 mg', dose: '81 mg', frequency: 'daily', startedYearsAgo: 5 },
  'albuterol-prn': { display: 'Albuterol HFA inhaler', dose: '90 mcg/actuation', frequency: '2 puffs every 4-6h as needed', startedYearsAgo: 8 },
  'tiotropium-inh': { display: 'Tiotropium inhaler', dose: '18 mcg', frequency: 'daily', startedYearsAgo: 5 },
  'tamoxifen-20': { display: 'Tamoxifen 20 mg', dose: '20 mg', frequency: 'daily', startedYearsAgo: 4 },
  'calcium-d': { display: 'Calcium 600 mg / Vitamin D 400 IU', dose: '600 mg / 400 IU', frequency: 'twice daily', startedYearsAgo: 3 },
  'duloxetine-60': { display: 'Duloxetine 60 mg', dose: '60 mg', frequency: 'daily', startedYearsAgo: 3 },
  'gabapentin-300': { display: 'Gabapentin 300 mg', dose: '300 mg', frequency: 'three times daily', startedYearsAgo: 3 },
  'mesalamine-2400': { display: 'Mesalamine 2.4 g', dose: '2.4 g', frequency: 'daily', startedYearsAgo: 3 },
  'azathioprine-100': { display: 'Azathioprine 100 mg', dose: '100 mg', frequency: 'daily', startedYearsAgo: 2 },
  'methotrexate-15': { display: 'Methotrexate 15 mg', dose: '15 mg', frequency: 'weekly', startedYearsAgo: 6 },
  'folic-acid-1': { display: 'Folic acid 1 mg', dose: '1 mg', frequency: 'daily', startedYearsAgo: 6 },
  'donepezil-10': { display: 'Donepezil 10 mg', dose: '10 mg', frequency: 'daily at bedtime', startedYearsAgo: 1 },
  'methylphenidate-20': { display: 'Methylphenidate ER 20 mg', dose: '20 mg', frequency: 'daily in morning', startedYearsAgo: 1 },
  'insulin-glargine-15u': { display: 'Insulin glargine 15 units', dose: '15 units', frequency: 'subcutaneous at bedtime', startedYearsAgo: 0 },
  'insulin-glargine-20u': { display: 'Insulin glargine 20 units', dose: '20 units', frequency: 'subcutaneous at bedtime', startedYearsAgo: 4 },
  'insulin-lispro': { display: 'Insulin lispro', dose: 'sliding scale', frequency: 'with meals', startedYearsAgo: 4 },
  'hydroxyurea-1000': { display: 'Hydroxyurea 1000 mg', dose: '1000 mg', frequency: 'daily', startedYearsAgo: 8 },
  'levothyroxine-75': { display: 'Levothyroxine 75 mcg', dose: '75 mcg', frequency: 'daily', startedYearsAgo: 5 },
  'metformin-1000-rx': { display: 'Metformin 1000 mg', dose: '1000 mg', frequency: 'twice daily', startedYearsAgo: 0 },
  'lisinopril-20-rx': { display: 'Lisinopril 20 mg', dose: '20 mg', frequency: 'daily', startedYearsAgo: 0 },
  'furosemide-40-rx': { display: 'Furosemide 40 mg', dose: '40 mg', frequency: 'daily', startedYearsAgo: 0 },
  'metoprolol-50-rx': { display: 'Metoprolol succinate 50 mg', dose: '50 mg', frequency: 'daily', startedYearsAgo: 0 },
  'furosemide-20-rx': { display: 'Furosemide 20 mg', dose: '20 mg', frequency: 'daily', startedYearsAgo: 0 },
  'atorvastatin-40-rx': { display: 'Atorvastatin 40 mg', dose: '40 mg', frequency: 'daily at bedtime', startedYearsAgo: 0 },
  'atorvastatin-20-rx': { display: 'Atorvastatin 20 mg', dose: '20 mg', frequency: 'daily at bedtime', startedYearsAgo: 0 },
  'insulin-glargine-rx': { display: 'Insulin glargine', dose: '20 units', frequency: 'subcutaneous at bedtime', startedYearsAgo: 0 },
  'insulin-glargine-15u-rx': { display: 'Insulin glargine 15 units', dose: '15 units', frequency: 'subcutaneous at bedtime', startedYearsAgo: 0 },
  'insulin-glargine-20u-rx': { display: 'Insulin glargine 20 units', dose: '20 units', frequency: 'subcutaneous at bedtime', startedYearsAgo: 0 },
  'insulin-lispro-rx': { display: 'Insulin lispro', dose: 'sliding scale', frequency: 'with meals', startedYearsAgo: 0 },
  'albuterol-prn-rx': { display: 'Albuterol HFA inhaler', dose: '90 mcg/actuation', frequency: '2 puffs every 4-6h as needed', startedYearsAgo: 0 },
  'tiotropium-inh-rx': { display: 'Tiotropium inhaler', dose: '18 mcg', frequency: 'daily', startedYearsAgo: 0 },
  'tamoxifen-20-rx': { display: 'Tamoxifen 20 mg', dose: '20 mg', frequency: 'daily', startedYearsAgo: 0 },
  'warfarin-5-rx': { display: 'Warfarin 5 mg', dose: '5 mg', frequency: 'daily', startedYearsAgo: 0 },
  'duloxetine-60-rx': { display: 'Duloxetine 60 mg', dose: '60 mg', frequency: 'daily', startedYearsAgo: 0 },
  'mesalamine-2400-rx': { display: 'Mesalamine 2.4 g', dose: '2.4 g', frequency: 'daily', startedYearsAgo: 0 },
  'methotrexate-15-rx': { display: 'Methotrexate 15 mg', dose: '15 mg', frequency: 'weekly', startedYearsAgo: 0 },
  'donepezil-10-rx': { display: 'Donepezil 10 mg', dose: '10 mg', frequency: 'daily at bedtime', startedYearsAgo: 0 },
  'methylphenidate-20-rx': { display: 'Methylphenidate ER 20 mg', dose: '20 mg', frequency: 'daily in morning', startedYearsAgo: 0 },
  'hydroxyurea-1000-rx': { display: 'Hydroxyurea 1000 mg', dose: '1000 mg', frequency: 'daily', startedYearsAgo: 0 },
  'levothyroxine-75-rx': { display: 'Levothyroxine 75 mcg', dose: '75 mcg', frequency: 'daily', startedYearsAgo: 0 },
}

// --- Practitioners ---

export const PRACTITIONER_CATALOG: Record<string, PractitionerDef> = {
  'dr-chen-pcp': { family: 'Chen', given: 'Lisa', prefix: 'Dr', role: 'Primary care physician', specialty: 'Internal Medicine' },
  'dr-yang-pediatrics': { family: 'Yang', given: 'Andrew', prefix: 'Dr', role: 'Pediatrician', specialty: 'Pediatrics' },
  'dr-romero-obgyn': { family: 'Romero', given: 'Elena', prefix: 'Dr', role: 'Obstetrician', specialty: 'Obstetrics & Gynecology' },
  'dr-reyes-cardiology': { family: 'Reyes', given: 'Miguel', prefix: 'Dr', role: 'Cardiologist', specialty: 'Cardiology' },
  'dr-patel-endocrinology': { family: 'Patel', given: 'Anika', prefix: 'Dr', role: 'Endocrinologist', specialty: 'Endocrinology' },
  'dr-singh-pulmonology': { family: 'Singh', given: 'Rajiv', prefix: 'Dr', role: 'Pulmonologist', specialty: 'Pulmonology' },
  'dr-park-oncology': { family: 'Park', given: 'Joon', prefix: 'Dr', role: 'Oncologist', specialty: 'Hematology/Oncology' },
  'dr-thompson-rheumatology': { family: 'Thompson', given: 'Rachel', prefix: 'Dr', role: 'Rheumatologist', specialty: 'Rheumatology' },
  'dr-okafor-gi': { family: 'Okafor', given: 'Chidi', prefix: 'Dr', role: 'Gastroenterologist', specialty: 'Gastroenterology' },
  'rn-adams': { family: 'Adams', given: 'Jordan', role: 'Registered Nurse' },
  'rn-johnson': { family: 'Johnson', given: 'Priya', role: 'Registered Nurse' },
  'sw-perez': { family: 'Perez', given: 'Camila', role: 'Social Worker' },
}

// --- Labs ---

export const LAB_CATALOG: Record<string, LabDef> = {
  'a1c-7.0': { display: 'Hemoglobin A1c', loinc: '4548-4', value: 7.0, unit: '%', refLow: 4, refHigh: 5.6, flag: 'H' },
  'a1c-6.8': { display: 'Hemoglobin A1c', loinc: '4548-4', value: 6.8, unit: '%', refLow: 4, refHigh: 5.6, flag: 'H' },
  'a1c-7.4': { display: 'Hemoglobin A1c', loinc: '4548-4', value: 7.4, unit: '%', refLow: 4, refHigh: 5.6, flag: 'H' },
  'a1c-7.6': { display: 'Hemoglobin A1c', loinc: '4548-4', value: 7.6, unit: '%', refLow: 4, refHigh: 5.6, flag: 'H' },
  'a1c-7.8': { display: 'Hemoglobin A1c', loinc: '4548-4', value: 7.8, unit: '%', refLow: 4, refHigh: 5.6, flag: 'H' },
  'a1c-8.0': { display: 'Hemoglobin A1c', loinc: '4548-4', value: 8.0, unit: '%', refLow: 4, refHigh: 5.6, flag: 'H' },
  'a1c-9.2': { display: 'Hemoglobin A1c', loinc: '4548-4', value: 9.2, unit: '%', refLow: 4, refHigh: 5.6, flag: 'H' },
  'a1c-9.8': { display: 'Hemoglobin A1c', loinc: '4548-4', value: 9.8, unit: '%', refLow: 4, refHigh: 5.6, flag: 'H' },
  'a1c-10.5': { display: 'Hemoglobin A1c', loinc: '4548-4', value: 10.5, unit: '%', refLow: 4, refHigh: 5.6, flag: 'H' },
  'a1c-6.2': { display: 'Hemoglobin A1c', loinc: '4548-4', value: 6.2, unit: '%', refLow: 4, refHigh: 5.6, flag: 'H' },
  'a1c-5.4': { display: 'Hemoglobin A1c', loinc: '4548-4', value: 5.4, unit: '%', refLow: 4, refHigh: 5.6 },
  'a1c-5.2': { display: 'Hemoglobin A1c', loinc: '4548-4', value: 5.2, unit: '%', refLow: 4, refHigh: 5.6 },
  'glucose-128': { display: 'Glucose, plasma', loinc: '2345-7', value: 128, unit: 'mg/dL', refLow: 70, refHigh: 99, flag: 'H' },
  'glucose-256': { display: 'Glucose, plasma', loinc: '2345-7', value: 256, unit: 'mg/dL', refLow: 70, refHigh: 99, flag: 'H' },
  'glucose-148': { display: 'Glucose, plasma', loinc: '2345-7', value: 148, unit: 'mg/dL', refLow: 70, refHigh: 99, flag: 'H' },
  'glucose-104': { display: 'Glucose, plasma', loinc: '2345-7', value: 104, unit: 'mg/dL', refLow: 70, refHigh: 99, flag: 'H' },
  'glucose-fasting-118': { display: 'Glucose, fasting', loinc: '1558-6', value: 118, unit: 'mg/dL', refLow: 70, refHigh: 99, flag: 'H' },
  'glucose-fasting-104': { display: 'Glucose, fasting', loinc: '1558-6', value: 104, unit: 'mg/dL', refLow: 70, refHigh: 99, flag: 'H' },
  'glucose-fasting-156': { display: 'Glucose, fasting', loinc: '1558-6', value: 156, unit: 'mg/dL', refLow: 70, refHigh: 99, flag: 'H' },
  'creatinine-0.7': { display: 'Creatinine, serum', loinc: '2160-0', value: 0.7, unit: 'mg/dL', refLow: 0.6, refHigh: 1.2 },
  'creatinine-0.8': { display: 'Creatinine, serum', loinc: '2160-0', value: 0.8, unit: 'mg/dL', refLow: 0.6, refHigh: 1.2 },
  'creatinine-0.9': { display: 'Creatinine, serum', loinc: '2160-0', value: 0.9, unit: 'mg/dL', refLow: 0.6, refHigh: 1.2 },
  'creatinine-1.0': { display: 'Creatinine, serum', loinc: '2160-0', value: 1.0, unit: 'mg/dL', refLow: 0.6, refHigh: 1.2 },
  'creatinine-1.2': { display: 'Creatinine, serum', loinc: '2160-0', value: 1.2, unit: 'mg/dL', refLow: 0.6, refHigh: 1.2 },
  'creatinine-1.4': { display: 'Creatinine, serum', loinc: '2160-0', value: 1.4, unit: 'mg/dL', refLow: 0.6, refHigh: 1.2, flag: 'H' },
  'creatinine-1.5': { display: 'Creatinine, serum', loinc: '2160-0', value: 1.5, unit: 'mg/dL', refLow: 0.6, refHigh: 1.2, flag: 'H' },
  'creatinine-1.6': { display: 'Creatinine, serum', loinc: '2160-0', value: 1.6, unit: 'mg/dL', refLow: 0.6, refHigh: 1.2, flag: 'H' },
  'creatinine-1.8': { display: 'Creatinine, serum', loinc: '2160-0', value: 1.8, unit: 'mg/dL', refLow: 0.6, refHigh: 1.2, flag: 'H' },
  'egfr-42': { display: 'eGFR (CKD-EPI)', loinc: '62238-1', value: 42, unit: 'mL/min/1.73m2', refLow: 60, refText: '> 60', flag: 'L' },
  'egfr-44': { display: 'eGFR (CKD-EPI)', loinc: '62238-1', value: 44, unit: 'mL/min/1.73m2', refLow: 60, refText: '> 60', flag: 'L' },
  'egfr-50': { display: 'eGFR (CKD-EPI)', loinc: '62238-1', value: 50, unit: 'mL/min/1.73m2', refLow: 60, refText: '> 60', flag: 'L' },
  'sodium-138': { display: 'Sodium, serum', loinc: '2951-2', value: 138, unit: 'mmol/L', refLow: 136, refHigh: 145 },
  'sodium-140': { display: 'Sodium, serum', loinc: '2951-2', value: 140, unit: 'mmol/L', refLow: 136, refHigh: 145 },
  'potassium-4.6': { display: 'Potassium, serum', loinc: '2823-3', value: 4.6, unit: 'mmol/L', refLow: 3.5, refHigh: 5.0 },
  'potassium-4.8': { display: 'Potassium, serum', loinc: '2823-3', value: 4.8, unit: 'mmol/L', refLow: 3.5, refHigh: 5.0 },
  'bnp-820': { display: 'BNP', loinc: '30934-4', value: 820, unit: 'pg/mL', refLow: 0, refHigh: 100, flag: 'H' },
  'ldl-78': { display: 'LDL cholesterol', loinc: '13457-7', value: 78, unit: 'mg/dL', refLow: 0, refHigh: 100 },
  'ldl-92': { display: 'LDL cholesterol', loinc: '13457-7', value: 92, unit: 'mg/dL', refLow: 0, refHigh: 100 },
  'ldl-95': { display: 'LDL cholesterol', loinc: '13457-7', value: 95, unit: 'mg/dL', refLow: 0, refHigh: 100 },
  'ldl-104': { display: 'LDL cholesterol', loinc: '13457-7', value: 104, unit: 'mg/dL', refLow: 0, refHigh: 100, flag: 'H' },
  'ldl-118': { display: 'LDL cholesterol', loinc: '13457-7', value: 118, unit: 'mg/dL', refLow: 0, refHigh: 100, flag: 'H' },
  'ldl-128': { display: 'LDL cholesterol', loinc: '13457-7', value: 128, unit: 'mg/dL', refLow: 0, refHigh: 100, flag: 'H' },
  'ldl-145': { display: 'LDL cholesterol', loinc: '13457-7', value: 145, unit: 'mg/dL', refLow: 0, refHigh: 100, flag: 'H' },
  'ldl-152': { display: 'LDL cholesterol', loinc: '13457-7', value: 152, unit: 'mg/dL', refLow: 0, refHigh: 100, flag: 'H' },
  'hdl-44': { display: 'HDL cholesterol', loinc: '2085-9', value: 44, unit: 'mg/dL', refLow: 40, refHigh: 200, flag: 'L' },
  'hdl-48': { display: 'HDL cholesterol', loinc: '2085-9', value: 48, unit: 'mg/dL', refLow: 40, refHigh: 200 },
  'hdl-52': { display: 'HDL cholesterol', loinc: '2085-9', value: 52, unit: 'mg/dL', refLow: 40, refHigh: 200 },
  'triglycerides-180': { display: 'Triglycerides', loinc: '2571-8', value: 180, unit: 'mg/dL', refLow: 0, refHigh: 150, flag: 'H' },
  'inr-2.2': { display: 'INR', loinc: '6301-6', value: 2.2, unit: '', refText: '2.0–3.0' },
  'inr-2.4': { display: 'INR', loinc: '6301-6', value: 2.4, unit: '', refText: '2.0–3.0' },
  'inr-2.6': { display: 'INR', loinc: '6301-6', value: 2.6, unit: '', refText: '2.0–3.0' },
  'inr-3.1': { display: 'INR', loinc: '6301-6', value: 3.1, unit: '', refText: '2.0–3.0', flag: 'H' },
  'tsh-1.8': { display: 'TSH', loinc: '3016-3', value: 1.8, unit: 'mIU/L', refLow: 0.4, refHigh: 4.0 },
  'tsh-2.0': { display: 'TSH', loinc: '3016-3', value: 2.0, unit: 'mIU/L', refLow: 0.4, refHigh: 4.0 },
  'tsh-2.1': { display: 'TSH', loinc: '3016-3', value: 2.1, unit: 'mIU/L', refLow: 0.4, refHigh: 4.0 },
  'tsh-2.4': { display: 'TSH', loinc: '3016-3', value: 2.4, unit: 'mIU/L', refLow: 0.4, refHigh: 4.0 },
  'tsh-3.4': { display: 'TSH', loinc: '3016-3', value: 3.4, unit: 'mIU/L', refLow: 0.4, refHigh: 4.0 },
  'free-t4-1.1': { display: 'Free T4', loinc: '3024-7', value: 1.1, unit: 'ng/dL', refLow: 0.8, refHigh: 1.8 },
  'vitamin-d-22': { display: '25-Hydroxy vitamin D', loinc: '1989-3', value: 22, unit: 'ng/mL', refLow: 30, refHigh: 100, flag: 'L' },
  'b12-340': { display: 'Vitamin B12', loinc: '2132-9', value: 340, unit: 'pg/mL', refLow: 200, refHigh: 900 },
  'cbc-normal': { display: 'CBC with differential', loinc: '57021-8', value: 'Within normal limits' },
  'liver-alt-25': { display: 'ALT (SGPT)', loinc: '1742-6', value: 25, unit: 'U/L', refLow: 0, refHigh: 40 },
  'liver-alt-28': { display: 'ALT (SGPT)', loinc: '1742-6', value: 28, unit: 'U/L', refLow: 0, refHigh: 40 },
  'liver-alt-32': { display: 'ALT (SGPT)', loinc: '1742-6', value: 32, unit: 'U/L', refLow: 0, refHigh: 40 },
  'liver-ast-28': { display: 'AST (SGOT)', loinc: '1920-8', value: 28, unit: 'U/L', refLow: 0, refHigh: 40 },
  'crp-elevated': { display: 'C-reactive protein', loinc: '1988-5', value: 18, unit: 'mg/L', refLow: 0, refHigh: 5, flag: 'H' },
  'rf-positive': { display: 'Rheumatoid factor', loinc: '11572-5', value: 42, unit: 'IU/mL', refLow: 0, refHigh: 14, flag: 'H' },
  'reticulocyte-elevated': { display: 'Reticulocyte count', loinc: '4679-7', value: 4.8, unit: '%', refLow: 0.5, refHigh: 2.5, flag: 'H' },
  'hemoglobin-low-9': { display: 'Hemoglobin', loinc: '718-7', value: 9.0, unit: 'g/dL', refLow: 13.5, refHigh: 17.5, flag: 'L' },
}
