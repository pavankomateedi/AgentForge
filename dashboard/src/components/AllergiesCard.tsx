// AllergyIntolerance — name + criticality + reactions + recordedDate.

import type { AllergyIntolerance } from '../fhir/types'
import { useFhirQuery } from '../fhir/useFhirQuery'
import { loadAllergies } from '../fhir/resources'
import { Card, Empty, ErrorMsg, Loading } from './Card'

function summary(a: AllergyIntolerance): string {
  return a.code?.text ?? a.code?.coding?.[0]?.display ?? a.code?.coding?.[0]?.code ?? 'Unknown allergen'
}

function reactions(a: AllergyIntolerance): string {
  const list: string[] = []
  for (const r of a.reaction ?? []) {
    for (const m of r.manifestation ?? []) {
      const t = m.text ?? m.coding?.[0]?.display ?? m.coding?.[0]?.code
      if (t) list.push(t)
    }
  }
  return list.join(', ')
}

export function AllergiesCard({ patientId }: { patientId: string }) {
  const { data, error, loading, reload } = useFhirQuery(
    (c) => loadAllergies(c, patientId),
    [patientId],
  )

  return (
    <Card title="Allergies" count={data?.length}>
      {loading && <Loading />}
      {!loading && error && <ErrorMsg message={error} onRetry={reload} />}
      {!loading && !error && data && data.length === 0 && <Empty label="No known allergies." />}
      {!loading && !error && data && data.length > 0 && (
        <ul className="record-list">
          {data.map((a) => {
            const crit = a.criticality
            const r = reactions(a)
            return (
              <li key={a.id} className="record-row">
                <div className="record-primary">{summary(a)}</div>
                <div className="record-meta">
                  {crit && <span className={`badge crit-${crit}`}>{crit}</span>}
                  {r && <span className="record-secondary">{r}</span>}
                  {a.recordedDate && <span className="record-date">{a.recordedDate.slice(0, 10)}</span>}
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </Card>
  )
}
