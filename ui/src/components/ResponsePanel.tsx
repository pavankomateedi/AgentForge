import type { ChatResponse } from '../types'
import { SourceText } from './SourceText'

type Props = {
  loading: boolean
  result: ChatResponse | null
  elapsed: number | null
  error: string | null
}

export function ResponsePanel({ loading, result, elapsed, error }: Props) {
  return (
    <div className="card">
      <div className="status">
        {loading && (
          <span className="loading">
            Calling agent (5–15s with adaptive thinking)…
          </span>
        )}
        {!loading && error && <span className="error">{error}</span>}
        {!loading && result && (
          <>
            <strong>Response</strong>
            {result.verified ? (
              <span className="badge verified">✓ Verified</span>
            ) : (
              <span className="badge failed">⚠ Not verified — fallback panel</span>
            )}
            {elapsed != null && (
              <span className="meta">{elapsed.toFixed(1)}s</span>
            )}
          </>
        )}
      </div>

      {!loading && result && (
        <>
          <div className="response">
            {result.response ? (
              <SourceText text={result.response} />
            ) : (
              <span className="empty">(empty response)</span>
            )}
          </div>

          <details className="trace">
            <summary>
              Trace — tools called, sources retrieved, verification, token usage
            </summary>

            <div className="trace-section">
              <h4>Plan: tools called</h4>
              {result.trace.plan_tool_calls.length === 0 ? (
                <p className="muted">none</p>
              ) : (
                <ul className="tool-list">
                  {result.trace.plan_tool_calls.map((tc, i) => (
                    <li key={i}>
                      <code>{tc.name}</code>
                      <span className="muted">
                        ({JSON.stringify(tc.input)})
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="trace-section">
              <h4>Retrieve: source ids returned</h4>
              {result.trace.retrieved_source_ids.length === 0 ? (
                <p className="muted">none</p>
              ) : (
                <div className="chips">
                  {result.trace.retrieved_source_ids.map((id) => (
                    <span key={id} className="chip">
                      {id}
                    </span>
                  ))}
                </div>
              )}
            </div>

            <div className="trace-section">
              <h4>Verify</h4>
              {result.trace.verification ? (
                <p className={result.trace.verification.passed ? 'ok' : 'warn'}>
                  {result.trace.verification.note}
                </p>
              ) : (
                <p className="muted">no verification recorded</p>
              )}
            </div>

            <div className="trace-section">
              <h4>Token usage</h4>
              <table className="usage">
                <thead>
                  <tr>
                    <th></th>
                    <th>input</th>
                    <th>output</th>
                    <th>cache write</th>
                    <th>cache read</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>plan</td>
                    <td>{result.trace.usage.plan.input_tokens}</td>
                    <td>{result.trace.usage.plan.output_tokens}</td>
                    <td>{result.trace.usage.plan.cache_creation_input_tokens}</td>
                    <td>{result.trace.usage.plan.cache_read_input_tokens}</td>
                  </tr>
                  <tr>
                    <td>reason</td>
                    <td>{result.trace.usage.reason.input_tokens}</td>
                    <td>{result.trace.usage.reason.output_tokens}</td>
                    <td>{result.trace.usage.reason.cache_creation_input_tokens}</td>
                    <td>{result.trace.usage.reason.cache_read_input_tokens}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <details className="raw-trace">
              <summary>Raw JSON</summary>
              <pre>{JSON.stringify(result.trace, null, 2)}</pre>
            </details>
          </details>
        </>
      )}
    </div>
  )
}
