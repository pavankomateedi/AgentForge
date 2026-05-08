// Per-profile clinical spec. Each profile lists tokens that resolve to
// fully-formed FHIR resources via the catalogs in catalog.ts. Keeping the
// per-patient data declarative (and short) instead of hand-rolling 20×30
// FHIR JSON blobs.

import type { ClinicalProfile } from './patients'

export interface ProfileSpec {
  allergies: string[]                     // tokens from ALLERGY_CATALOG
  conditions: string[]                    // tokens from CONDITION_CATALOG
  medStatements: string[]                 // tokens from MED_CATALOG
  medRequests: string[]                   // tokens from MED_CATALOG
  careTeam: string[]                      // tokens from PRACTITIONER_CATALOG
  // Each lab spec is "<labToken>@<daysAgo>". Multiple of the same token
  // yield a series the LabsSection table can sort by date.
  labs: string[]
}

export const PROFILE_SPECS: Record<ClinicalProfile, ProfileSpec> = {
  't2dm-controlled': {
    allergies: ['penicillin'],
    conditions: ['t2dm', 'hyperlipidemia', 'htn'],
    medStatements: ['metformin-1000', 'atorvastatin-40', 'lisinopril-20'],
    medRequests: ['metformin-1000-rx', 'lisinopril-20-rx'],
    careTeam: ['dr-chen-pcp', 'rn-adams', 'dr-patel-endocrinology'],
    labs: ['a1c-7.0@30', 'a1c-6.8@180', 'a1c-7.4@365', 'ldl-92@60', 'hdl-52@60', 'creatinine-0.9@30', 'glucose-128@30'],
  },
  'hfref-ckd': {
    allergies: ['sulfa'],
    conditions: ['hfref', 'ckd-3', 'htn', 'hyperlipidemia'],
    medStatements: ['lisinopril-10', 'metoprolol-50', 'furosemide-40', 'atorvastatin-20'],
    medRequests: ['furosemide-40-rx', 'metoprolol-50-rx'],
    careTeam: ['dr-chen-pcp', 'rn-adams', 'dr-reyes-cardiology'],
    labs: ['creatinine-1.6@21', 'creatinine-1.5@90', 'creatinine-1.4@180', 'egfr-44@21', 'bnp-820@21', 'potassium-4.8@21', 'sodium-138@21'],
  },
  't2dm-uncontrolled': {
    allergies: ['nkda'],
    conditions: ['t2dm', 'aki', 'hyperlipidemia', 'htn', 'obesity'],
    medStatements: ['metformin-1000', 'atorvastatin-40'],
    medRequests: ['insulin-glargine-rx', 'lisinopril-20-rx'],
    careTeam: ['dr-chen-pcp', 'dr-patel-endocrinology', 'rn-johnson'],
    labs: ['a1c-10.5@14', 'a1c-9.8@90', 'a1c-9.2@180', 'creatinine-1.8@14', 'creatinine-1.2@90', 'egfr-42@14', 'glucose-256@14'],
  },
  'asthma-mild': {
    allergies: ['peanut', 'pollen'],
    conditions: ['asthma'],
    medStatements: ['albuterol-prn'],
    medRequests: ['albuterol-prn-rx'],
    careTeam: ['dr-chen-pcp'],
    labs: ['a1c-5.4@45', 'tsh-2.1@45', 'cbc-normal@45'],
  },
  'multimorbidity-elderly': {
    allergies: ['penicillin', 'aspirin'],
    conditions: ['t2dm', 'hfref', 'ckd-3', 'osteoarthritis', 'hyperlipidemia'],
    medStatements: ['metformin-500', 'lisinopril-10', 'atorvastatin-40', 'furosemide-20', 'aspirin-81'],
    medRequests: ['furosemide-20-rx'],
    careTeam: ['dr-chen-pcp', 'rn-adams', 'dr-reyes-cardiology', 'sw-perez'],
    labs: ['a1c-7.6@30', 'a1c-7.4@180', 'creatinine-1.4@30', 'egfr-50@30', 'potassium-4.6@30', 'ldl-78@60'],
  },
  'htn-hyperlipidemia': {
    allergies: ['nkda'],
    conditions: ['htn', 'hyperlipidemia'],
    medStatements: ['lisinopril-20', 'atorvastatin-40'],
    medRequests: ['atorvastatin-40-rx'],
    careTeam: ['dr-chen-pcp', 'rn-adams'],
    labs: ['ldl-145@30', 'ldl-118@180', 'hdl-44@30', 'creatinine-1.0@30', 'glucose-104@30'],
  },
  'gestational-diabetes': {
    allergies: ['nkda'],
    conditions: ['gdm', 'pregnancy'],
    medStatements: ['insulin-glargine-15u'],
    medRequests: ['insulin-glargine-15u-rx'],
    careTeam: ['dr-romero-obgyn', 'rn-johnson'],
    labs: ['a1c-6.2@14', 'glucose-fasting-118@14', 'glucose-fasting-104@45'],
  },
  'copd': {
    allergies: ['nkda'],
    conditions: ['copd', 'htn'],
    medStatements: ['tiotropium-inh', 'albuterol-prn', 'lisinopril-10'],
    medRequests: ['tiotropium-inh-rx'],
    careTeam: ['dr-chen-pcp', 'dr-singh-pulmonology'],
    labs: ['cbc-normal@30', 'creatinine-1.0@30', 'sodium-140@30'],
  },
  'breast-cancer-survivor': {
    allergies: ['latex'],
    conditions: ['breast-cancer-history', 'osteopenia'],
    medStatements: ['tamoxifen-20', 'calcium-d'],
    medRequests: ['tamoxifen-20-rx'],
    careTeam: ['dr-chen-pcp', 'dr-park-oncology'],
    labs: ['cbc-normal@30', 'liver-alt-32@30', 'liver-ast-28@30'],
  },
  'afib-warfarin': {
    allergies: ['nkda'],
    conditions: ['afib', 'htn'],
    medStatements: ['warfarin-5', 'metoprolol-25'],
    medRequests: ['warfarin-5-rx'],
    careTeam: ['dr-chen-pcp', 'dr-reyes-cardiology', 'rn-adams'],
    labs: ['inr-2.4@7', 'inr-2.6@30', 'inr-3.1@60', 'inr-2.2@90', 'cbc-normal@30'],
  },
  'fibromyalgia': {
    allergies: ['nkda'],
    conditions: ['fibromyalgia', 'depression'],
    medStatements: ['duloxetine-60', 'gabapentin-300'],
    medRequests: ['duloxetine-60-rx'],
    careTeam: ['dr-chen-pcp', 'rn-johnson'],
    labs: ['tsh-1.8@60', 'vitamin-d-22@60', 'cbc-normal@60'],
  },
  'crohns': {
    allergies: ['penicillin'],
    conditions: ['crohns'],
    medStatements: ['mesalamine-2400', 'azathioprine-100'],
    medRequests: ['mesalamine-2400-rx'],
    careTeam: ['dr-chen-pcp', 'dr-okafor-gi'],
    labs: ['cbc-normal@21', 'crp-elevated@21', 'liver-alt-28@21'],
  },
  'rheumatoid-arthritis': {
    allergies: ['nkda'],
    conditions: ['ra'],
    medStatements: ['methotrexate-15', 'folic-acid-1'],
    medRequests: ['methotrexate-15-rx'],
    careTeam: ['dr-chen-pcp', 'dr-thompson-rheumatology'],
    labs: ['rf-positive@90', 'crp-elevated@30', 'cbc-normal@30', 'liver-alt-25@30'],
  },
  hyperlipidemia: {
    allergies: ['nkda'],
    conditions: ['hyperlipidemia'],
    medStatements: ['atorvastatin-20'],
    medRequests: ['atorvastatin-20-rx'],
    careTeam: ['dr-chen-pcp'],
    labs: ['ldl-128@30', 'ldl-152@180', 'hdl-48@30', 'triglycerides-180@30'],
  },
  dementia: {
    allergies: ['nkda'],
    conditions: ['dementia', 'osteoarthritis', 'htn'],
    medStatements: ['donepezil-10', 'lisinopril-10'],
    medRequests: ['donepezil-10-rx'],
    careTeam: ['dr-chen-pcp', 'rn-adams', 'sw-perez'],
    labs: ['tsh-2.4@90', 'b12-340@90', 'cbc-normal@90'],
  },
  'pediatric-adhd': {
    allergies: ['nkda'],
    conditions: ['adhd'],
    medStatements: ['methylphenidate-20'],
    medRequests: ['methylphenidate-20-rx'],
    careTeam: ['dr-yang-pediatrics'],
    labs: ['cbc-normal@180'],
  },
  't1dm-adolescent': {
    allergies: ['nkda'],
    conditions: ['t1dm'],
    medStatements: ['insulin-glargine-20u', 'insulin-lispro'],
    medRequests: ['insulin-glargine-20u-rx', 'insulin-lispro-rx'],
    careTeam: ['dr-yang-pediatrics', 'dr-patel-endocrinology', 'rn-johnson'],
    labs: ['a1c-7.8@30', 'a1c-8.0@180', 'glucose-fasting-156@30', 'creatinine-0.7@30'],
  },
  'sickle-cell': {
    allergies: ['nkda'],
    conditions: ['sickle-cell'],
    medStatements: ['hydroxyurea-1000', 'folic-acid-1'],
    medRequests: ['hydroxyurea-1000-rx'],
    careTeam: ['dr-chen-pcp', 'dr-park-oncology', 'rn-adams'],
    labs: ['hemoglobin-low-9@30', 'reticulocyte-elevated@30', 'creatinine-0.8@30'],
  },
  hypothyroidism: {
    allergies: ['nkda'],
    conditions: ['hypothyroidism'],
    medStatements: ['levothyroxine-75'],
    medRequests: ['levothyroxine-75-rx'],
    careTeam: ['dr-chen-pcp'],
    labs: ['tsh-3.4@45', 'tsh-2.1@180', 'free-t4-1.1@45'],
  },
  'healthy-adult': {
    allergies: ['nkda'],
    conditions: [],
    medStatements: [],
    medRequests: [],
    careTeam: ['dr-chen-pcp'],
    labs: ['cbc-normal@90', 'a1c-5.2@90', 'ldl-104@90', 'creatinine-0.9@90', 'tsh-2.0@90'],
  },
}
