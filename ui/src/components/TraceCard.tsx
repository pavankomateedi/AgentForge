import type { ChatResponse } from '../types'

type Props = {
  loading: boolean
  result: ChatResponse | null
}

const NODE_LABELS: Record<string, string> = {
  plan: 'Plan',
  retrieve: 'Retrieve',
  rules: 'Rules',
  reason: 'Reason',
  verify: 'Verify',
  reason_retry: 'Reason (retry)',
  verify_retry: 'Verify (retry)',
}

export function TraceCard({ loading, result }: Props) {
  const t = result?.trace ?? null
  const timings = t?.timings_ms ?? {}
  const totalMs = Object.values(timings).reduce((a, b) => a + b, 0)

  return (
    <section className="card trace-card">
      <div className="card-header">
        <h3 className="card-title compact">Trace</h3>
        {t?.trace_id && (
          <span className="trace-id" title="Trace identifier">
            {t.trace_id}
          </span>
        )}
      </div>
      <div className="card-body">
        {!result && !loading && (
          <p className="placeholder">Per-node timing + Langfuse link.</p>
        )}

        {loading && <p className="placeholder">Tracking…</p>}

        {!loading && result && t && (
          <>
            <ul className="timing-list">
              {Object.entries(timings).map(([node, ms]) => (
                <li key={node} className="timing-row">
                  <span className="timing-label">
                    {NODE_LABELS[node] ?? node}
                  </span>
                  <div className="timing-bar-wrap">
                    <span
                      className="timing-bar"
                      style={{
                        width: `${
                          totalMs > 0 ? Math.max(2, (ms / totalMs) * 100) : 0
                        }%`,
                      }}
                    />
                  </div>
                  <span className="timing-ms">{ms}ms</span>
                </li>
              ))}
            </ul>
            {t.trace_url && (
              <a
                className="trace-link"
                href={t.trace_url}
                target="_blank"
                rel="noopener noreferrer"
              >
                Open in Langfuse →
              </a>
            )}
          </>
        )}
      </div>
    </section>
  )
}
