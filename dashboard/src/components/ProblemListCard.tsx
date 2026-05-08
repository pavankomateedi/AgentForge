// Condition — active problem-list items.

import type { Condition } from '../fhir/types'
import { useFhirQuery } from '../fhir/useFhirQuery'
import { loadProblems } from '../fhir/resources'
import { Card, Empty, ErrorMsg, Loading } from './Card'

function describe(c: Condition): string {
  return c.code?.text ?? c.code?.coding?.[0]?.display ?? c.code?.coding?.[0]?.code ?? 'Unspecified problem'
}

function status(c: Condition): string | undefined {
  return c.clinicalStatus?.coding?.[0]?.code ?? c.clinicalStatus?.text
}

function onset(c: Condition): string | undefined {
  return c.onsetDateTime?.slice(0, 10) ?? c.onsetPeriod?.start?.slice(0, 10)
}

export function ProblemListCard({ patientId }: { patientId: string }) {
  const { data, error, loading, reload } = useFhirQuery(
    (c) => loadProblems(c, patientId),
    [patientId],
  )

  return (
    <Card title="Problem List" count={data?.length}>
      {loading && <Loading />}
      {!loading && error && <ErrorMsg message={error} onRetry={reload} />}
      {!loading && !error && data && data.length === 0 && <Empty label="No active problems." />}
      {!loading && !error && data && data.length > 0 && (
        <ul className="record-list">
          {data.map((c) => (
            <li key={c.id} className="record-row">
              <div className="record-primary">{describe(c)}</div>
              <div className="record-meta">
                {status(c) && <span className="badge">{status(c)}</span>}
                {onset(c) && <span className="record-date">since {onset(c)}</span>}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}
