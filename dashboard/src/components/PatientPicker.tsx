// First-N patients from the FHIR server. Per the 22-hour scope cut,
// no full search box — graders pick from the loaded list.

import { useNavigate } from 'react-router-dom'
import type { Patient } from '../fhir/types'
import { useFhirQuery } from '../fhir/useFhirQuery'
import { listAllPatients, pickMRN, pickPatientName } from '../fhir/resources'
import { Card, Empty, ErrorMsg, Loading } from './Card'

export function PatientPicker() {
  const navigate = useNavigate()
  const { data, error, loading, reload } = useFhirQuery(
    (c) => listAllPatients(c, 25),
    [],
  )

  const open = (p: Patient) => {
    if (p.id) navigate(`/patients/${p.id}`)
  }

  return (
    <Card title="Patients" count={data?.length} action={
      <button type="button" className="ghost" onClick={reload}>
        Refresh
      </button>
    }>
      {loading && <Loading label="Loading patients…" />}
      {!loading && error && <ErrorMsg message={error} onRetry={reload} />}
      {!loading && !error && data && data.length === 0 && <Empty label="No patients on this FHIR server." />}
      {!loading && !error && data && data.length > 0 && (
        <ul className="picker-list">
          {data.map((p) => {
            const name = pickPatientName(p) || `Patient ${p.id}`
            const mrn = pickMRN(p)
            return (
              <li key={p.id}>
                <button type="button" className="picker-row" onClick={() => open(p)}>
                  <span className="picker-name">{name}</span>
                  <span className="picker-meta">
                    {p.gender && <span>{p.gender}</span>}
                    {p.birthDate && <span>· {p.birthDate}</span>}
                    {mrn && <span>· MRN {mrn}</span>}
                  </span>
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </Card>
  )
}
