// MedicationStatement — patient-reported / current medications.

import type { MedicationStatement } from '../fhir/types'
import { useFhirQuery } from '../fhir/useFhirQuery'
import { loadMedicationStatements, pickMedicationLabel } from '../fhir/resources'
import { Card, Empty, ErrorMsg, Loading } from './Card'

function dosageLine(m: MedicationStatement): string | undefined {
  return m.dosage?.find((d) => d.text)?.text
}

function timeframe(m: MedicationStatement): string | undefined {
  if (m.effectiveDateTime) return `since ${m.effectiveDateTime.slice(0, 10)}`
  if (m.effectivePeriod?.start) return `since ${m.effectivePeriod.start.slice(0, 10)}`
  return undefined
}

export function MedicationsCard({ patientId }: { patientId: string }) {
  const { data, error, loading, reload } = useFhirQuery(
    (c) => loadMedicationStatements(c, patientId),
    [patientId],
  )

  return (
    <Card title="Medications" count={data?.length}>
      {loading && <Loading />}
      {!loading && error && <ErrorMsg message={error} onRetry={reload} />}
      {!loading && !error && data && data.length === 0 && <Empty label="No current medications." />}
      {!loading && !error && data && data.length > 0 && (
        <ul className="record-list">
          {data.map((m) => (
            <li key={m.id} className="record-row">
              <div className="record-primary">{pickMedicationLabel(m)}</div>
              <div className="record-meta">
                {dosageLine(m) && <span className="record-secondary">{dosageLine(m)}</span>}
                {m.status && <span className="badge">{m.status}</span>}
                {timeframe(m) && <span className="record-date">{timeframe(m)}</span>}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}
