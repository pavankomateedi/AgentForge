// MedicationRequest — orders/prescriptions written by a provider.

import type { MedicationRequest } from '../fhir/types'
import { useFhirQuery } from '../fhir/useFhirQuery'
import { loadMedicationRequests, pickMedicationLabel } from '../fhir/resources'
import { Card, Empty, ErrorMsg, Loading } from './Card'

function dosageLine(m: MedicationRequest): string | undefined {
  return m.dosageInstruction?.find((d) => d.text)?.text
}

export function PrescriptionsCard({ patientId }: { patientId: string }) {
  const { data, error, loading, reload } = useFhirQuery(
    (c) => loadMedicationRequests(c, patientId),
    [patientId],
  )

  return (
    <Card title="Prescriptions" count={data?.length}>
      {loading && <Loading />}
      {!loading && error && <ErrorMsg message={error} onRetry={reload} />}
      {!loading && !error && data && data.length === 0 && <Empty label="No prescriptions." />}
      {!loading && !error && data && data.length > 0 && (
        <ul className="record-list">
          {data.map((m) => (
            <li key={m.id} className="record-row">
              <div className="record-primary">{pickMedicationLabel(m)}</div>
              <div className="record-meta">
                {dosageLine(m) && <span className="record-secondary">{dosageLine(m)}</span>}
                {m.status && <span className="badge">{m.status}</span>}
                {m.intent && <span className="badge">{m.intent}</span>}
                {m.authoredOn && <span className="record-date">{m.authoredOn.slice(0, 10)}</span>}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}
