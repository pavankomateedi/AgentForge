// CareTeam first; if empty, falls back to PractitionerRole + Practitioner so
// servers that don't populate CareTeam (OpenEMR historically thin here)
// still surface a meaningful clinician list.

import { useEffect, useRef, useState } from 'react'
import type { CareTeam, Practitioner, PractitionerRole } from '../fhir/types'
import { useFhir } from '../fhir/useFhir'
import {
  formatHumanName,
  loadCareTeams,
  loadPractitionerRoles,
} from '../fhir/resources'
import { Card, Empty, ErrorMsg, Loading } from './Card'

interface CareTeamView {
  source: 'CareTeam' | 'PractitionerRole' | 'empty'
  teams: CareTeam[]
  roles: PractitionerRole[]
  practitioners: Map<string, Practitioner>
}

interface CareTeamState {
  view: CareTeamView | null
  error: string | null
  loading: boolean
}

export function CareTeamCard({ patientId }: { patientId: string }) {
  const client = useFhir()
  const [state, setState] = useState<CareTeamState>({ view: null, error: null, loading: true })
  const [reloadKey, setReloadKey] = useState(0)
  const latestRequestId = useRef(0)

  useEffect(() => {
    const id = latestRequestId.current + 1
    latestRequestId.current = id

    ;(async () => {
      try {
        const teams = await loadCareTeams(client, patientId)
        if (latestRequestId.current !== id) return
        if (teams.length > 0) {
          setState({
            view: { source: 'CareTeam', teams, roles: [], practitioners: new Map() },
            error: null,
            loading: false,
          })
          return
        }
        const { roles, practitioners } = await loadPractitionerRoles(client, patientId)
        if (latestRequestId.current !== id) return
        setState({
          view: {
            source: roles.length > 0 ? 'PractitionerRole' : 'empty',
            teams: [],
            roles,
            practitioners,
          },
          error: null,
          loading: false,
        })
      } catch (e: unknown) {
        if (latestRequestId.current !== id) return
        setState({ view: null, error: e instanceof Error ? e.message : String(e), loading: false })
      }
    })()
  }, [client, patientId, reloadKey])

  const view = state.view
  const error = state.error
  const loading = state.loading

  return (
    <Card
      title="Care Team"
      count={
        view?.source === 'CareTeam'
          ? view.teams.reduce((n, t) => n + (t.participant?.length ?? 0), 0)
          : view?.source === 'PractitionerRole'
            ? view.roles.length
            : undefined
      }
    >
      {loading && <Loading />}
      {!loading && error && <ErrorMsg message={error} onRetry={() => setReloadKey((k) => k + 1)} />}
      {!loading && !error && view?.source === 'empty' && <Empty label="No care team on file." />}

      {!loading && !error && view?.source === 'CareTeam' && (
        <ul className="record-list">
          {view.teams.flatMap((t) =>
            (t.participant ?? []).map((p, idx) => {
              const role = p.role?.[0]?.text ?? p.role?.[0]?.coding?.[0]?.display
              const name = p.member?.display ?? p.member?.reference ?? 'Unknown member'
              return (
                <li key={`${t.id}-${idx}`} className="record-row">
                  <div className="record-primary">{name}</div>
                  <div className="record-meta">
                    {role && <span className="record-secondary">{role}</span>}
                    {t.status && <span className="badge">{t.status}</span>}
                  </div>
                </li>
              )
            }),
          )}
        </ul>
      )}

      {!loading && !error && view?.source === 'PractitionerRole' && (
        <>
          <p className="state-msg" style={{ fontSize: 12, marginBottom: 8 }}>
            CareTeam empty — showing PractitionerRole.
          </p>
          <ul className="record-list">
            {view.roles.map((r) => {
              const refId = r.practitioner?.reference?.split('/').pop() ?? ''
              const p = view.practitioners.get(refId)
              const name = formatHumanName(p?.name?.[0]) || r.practitioner?.display || 'Unknown practitioner'
              const specialty = r.specialty?.[0]?.text ?? r.specialty?.[0]?.coding?.[0]?.display
              return (
                <li key={r.id} className="record-row">
                  <div className="record-primary">{name}</div>
                  <div className="record-meta">
                    {specialty && <span className="record-secondary">{specialty}</span>}
                    {r.active === false && <span className="badge">inactive</span>}
                  </div>
                </li>
              )
            })}
          </ul>
        </>
      )}
    </Card>
  )
}
