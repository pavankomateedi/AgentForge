// Persistent identity bar. Renders name + DOB + sex + MRN + active status.

import type { Patient } from '../fhir/types'
import { pickMRN, pickPatientName } from '../fhir/resources'

function age(birthDate?: string): string | null {
  if (!birthDate) return null
  const d = new Date(birthDate)
  if (Number.isNaN(d.getTime())) return null
  const now = new Date()
  let years = now.getFullYear() - d.getFullYear()
  const m = now.getMonth() - d.getMonth()
  if (m < 0 || (m === 0 && now.getDate() < d.getDate())) years -= 1
  return `${years} y`
}

export function PatientHeader({ patient }: { patient: Patient }) {
  const name = pickPatientName(patient)
  const mrn = pickMRN(patient)
  const dob = patient.birthDate ?? ''
  const sex = patient.gender ?? ''
  const yrs = age(patient.birthDate)
  const active = patient.active ?? true

  return (
    <section className="patient-header">
      <div className="patient-header-name">
        <h2>{name || 'Unknown patient'}</h2>
        <span className={`badge ${active ? 'active' : 'inactive'}`}>{active ? 'Active' : 'Inactive'}</span>
      </div>
      <dl className="patient-header-meta">
        {dob && (
          <span>
            <dt>DOB</dt>
            <dd>
              {dob}
              {yrs && <span className="muted"> · {yrs}</span>}
            </dd>
          </span>
        )}
        {sex && (
          <span>
            <dt>Sex</dt>
            <dd>{sex}</dd>
          </span>
        )}
        {mrn && (
          <span>
            <dt>MRN</dt>
            <dd>{mrn}</dd>
          </span>
        )}
        <span>
          <dt>FHIR ID</dt>
          <dd>{patient.id}</dd>
        </span>
      </dl>
    </section>
  )
}
