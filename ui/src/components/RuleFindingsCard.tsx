import type { ChatResponse, RuleFinding } from '../types'

type Props = {
  loading: boolean
  result: ChatResponse | null
}

const SEVERITY_LABEL: Record<RuleFinding['severity'], string> = {
  critical: 'Critical',
  warning: 'Warning',
  info: 'Info',
}

export function RuleFindingsCard({ loading, result }: Props) {
  const findings = result?.trace.rule_findings ?? []

  return (
    <section className="card findings-card">
      <div className="card-header">
        <h3 className="card-title compact">
          Test findings
          {findings.length > 0 && (
            <span className="count">({findings.length})</span>
          )}
        </h3>
      </div>
      <div className="card-body">
        {!result && !loading && (
          <p className="placeholder">
            Clinical tests (A1c, LDL, dosage, interactions) run on retrieval.
          </p>
        )}

        {loading && <p className="placeholder">Evaluating tests…</p>}

        {!loading && result && findings.length === 0 && (
          <p className="placeholder">
            No test findings — patient is within thresholds.
          </p>
        )}

        {!loading && result && findings.length > 0 && (
          <ul className="findings-list">
            {findings.map((f) => (
              <li key={f.rule_id} className={`finding finding-${f.severity}`}>
                <div className="finding-row">
                  <span className={`severity sev-${f.severity}`}>
                    {SEVERITY_LABEL[f.severity]}
                  </span>
                  <span className="rule-id">{f.rule_id}</span>
                </div>
                <p className="finding-message">{f.message}</p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  )
}
