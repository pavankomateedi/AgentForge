// Observation (category=laboratory) — sortable table.
// Sortable on Test name, Value, Date columns. Pure client-side sort over
// the already-loaded result set. No trend chart; that was cut for the
// 22-hour window.

import { useMemo, useState } from 'react'
import type { Observation, Quantity } from '../fhir/types'
import { useFhirQuery } from '../fhir/useFhirQuery'
import { loadObservationsLab } from '../fhir/resources'
import { Card, Empty, ErrorMsg, Loading } from './Card'

type SortKey = 'name' | 'value' | 'date'
type SortDir = 'asc' | 'desc'

function valueText(v?: Quantity): string {
  if (!v || v.value === undefined) return ''
  const unit = v.unit ?? v.code ?? ''
  return `${v.value} ${unit}`.trim()
}

function obsDate(o: Observation): string {
  return o.effectiveDateTime ?? o.effectivePeriod?.start ?? o.issued ?? ''
}

function obsName(o: Observation): string {
  return o.code?.text ?? o.code?.coding?.[0]?.display ?? o.code?.coding?.[0]?.code ?? ''
}

function refRange(o: Observation): string {
  const r = o.referenceRange?.[0]
  if (!r) return ''
  if (r.text) return r.text
  if (r.low && r.high) return `${r.low.value}–${r.high.value} ${r.low.unit ?? r.high.unit ?? ''}`.trim()
  if (r.low) return `>= ${r.low.value} ${r.low.unit ?? ''}`.trim()
  if (r.high) return `<= ${r.high.value} ${r.high.unit ?? ''}`.trim()
  return ''
}

function interpretation(o: Observation): string {
  return o.interpretation?.[0]?.coding?.[0]?.code ?? o.interpretation?.[0]?.text ?? ''
}

export function LabsSection({ patientId }: { patientId: string }) {
  const { data, error, loading, reload } = useFhirQuery(
    (c) => loadObservationsLab(c, patientId),
    [patientId],
  )

  const [sortKey, setSortKey] = useState<SortKey>('date')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  const sorted = useMemo(() => {
    if (!data) return []
    const arr = [...data]
    arr.sort((a, b) => {
      let cmp: number
      if (sortKey === 'name') {
        cmp = obsName(a).localeCompare(obsName(b))
      } else if (sortKey === 'value') {
        const av = a.valueQuantity?.value ?? Number.NEGATIVE_INFINITY
        const bv = b.valueQuantity?.value ?? Number.NEGATIVE_INFINITY
        cmp = av - bv
      } else {
        cmp = obsDate(a).localeCompare(obsDate(b))
      }
      return sortDir === 'asc' ? cmp : -cmp
    })
    return arr
  }, [data, sortKey, sortDir])

  const onSort = (k: SortKey) => {
    if (k === sortKey) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    else {
      setSortKey(k)
      setSortDir(k === 'name' ? 'asc' : 'desc')
    }
  }

  const arrow = (k: SortKey) => (sortKey === k ? (sortDir === 'asc' ? ' ▲' : ' ▼') : '')

  return (
    <Card title="Labs" count={data?.length}>
      {loading && <Loading />}
      {!loading && error && <ErrorMsg message={error} onRetry={reload} />}
      {!loading && !error && data && data.length === 0 && <Empty label="No lab results." />}
      {!loading && !error && sorted.length > 0 && (
        <div className="table-wrap">
          <table className="labs-table">
            <thead>
              <tr>
                <th onClick={() => onSort('name')}>Test{arrow('name')}</th>
                <th onClick={() => onSort('value')}>Value{arrow('value')}</th>
                <th>Reference</th>
                <th>Flag</th>
                <th onClick={() => onSort('date')}>Date{arrow('date')}</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((o) => {
                const flag = interpretation(o)
                return (
                  <tr key={o.id}>
                    <td>{obsName(o)}</td>
                    <td>{valueText(o.valueQuantity) || o.valueString || ''}</td>
                    <td>{refRange(o)}</td>
                    <td>{flag && <span className={`badge crit-${flag.toLowerCase()}`}>{flag}</span>}</td>
                    <td>{obsDate(o).slice(0, 10)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}
