import type { ChatResponse } from '../types'

type Props = {
  loading: boolean
  result: ChatResponse | null
}

export function VerificationCard({ loading, result }: Props) {
  const v = result?.trace.verification ?? null

  return (
    <section className="card verification-card">
      <div className="card-header">
        <h3 className="card-title compact">Verification</h3>
      </div>
      <div className="card-body">
        {!result && !loading && (
          <p className="placeholder">Source-id matching + value-tolerance.</p>
        )}

        {loading && <p className="placeholder">Checking…</p>}

        {!loading && result && v && (
          <ul className="kv-list">
            <li>
              <span className="kv-key">Cited sources</span>
              <span className="kv-val">{v.cited_ids.length}</span>
            </li>
            <li>
              <span className="kv-key">Retrieved</span>
              <span className="kv-val">
                {result.trace.retrieved_source_ids.length}
              </span>
            </li>
            <li>
              <span className="kv-key">Unknown ids</span>
              <span
                className={
                  v.unknown_ids.length
                    ? 'kv-val warn-text'
                    : 'kv-val ok-text'
                }
              >
                {v.unknown_ids.length}
              </span>
            </li>
            <li>
              <span className="kv-key">Value mismatches</span>
              <span
                className={
                  v.value_mismatches.length
                    ? 'kv-val warn-text'
                    : 'kv-val ok-text'
                }
              >
                {v.value_mismatches.length}
              </span>
            </li>
            {result.trace.regenerated && (
              <li>
                <span className="kv-key">Regenerated</span>
                <span className="kv-val warn-text">Yes (1 retry)</span>
              </li>
            )}
          </ul>
        )}
      </div>
    </section>
  )
}
