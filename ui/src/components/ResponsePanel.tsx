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
    <section className="card response-card" aria-live="polite">
      <div className="response-header">
        <h2 className="response-title">Briefing</h2>
        <div className="response-meta">
          {!loading && result && (
            <>
              {result.verified ? (
                <span className="badge verified" aria-label="Verified">
                  <svg
                    width="12"
                    height="12"
                    viewBox="0 0 12 12"
                    aria-hidden="true"
                  >
                    <path
                      d="M2.5 6.5L4.5 8.5L9.5 3.5"
                      stroke="currentColor"
                      strokeWidth="2"
                      fill="none"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                  Verified
                </span>
              ) : (
                <span className="badge needs-review" aria-label="Needs review">
                  Needs review
                </span>
              )}
              {elapsed != null && (
                <span className="elapsed">{elapsed.toFixed(1)}s</span>
              )}
            </>
          )}
        </div>
      </div>

      <div className="response-body">
        {loading && (
          <div className="thinking">
            <span className="dot" />
            <span className="dot" />
            <span className="dot" />
            <span className="thinking-label">
              Reviewing the chart and writing your briefing…
            </span>
          </div>
        )}

        {!loading && error && <p className="error">{error}</p>}

        {!loading && result && (
          <p className="response">
            {result.response ? (
              <SourceText text={result.response} />
            ) : (
              <span className="empty">No briefing was produced.</span>
            )}
          </p>
        )}
      </div>
    </section>
  )
}
