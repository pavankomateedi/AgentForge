import { useEffect, useState } from 'react'
import type { ChatResponse } from '../types'
import { SourceText } from './SourceText'

type Props = {
  loading: boolean
  result: ChatResponse | null
  elapsed: number | null
  error: string | null
  onRetry?: () => void
}

const LOADING_STAGES = [
  'Looking up the chart…',
  'Pulling problem list and medications…',
  'Reviewing recent labs…',
  'Verifying every fact against a source…',
  'Writing your briefing…',
]

export function BriefingCard({
  loading,
  result,
  elapsed,
  error,
  onRetry,
}: Props) {
  const [stageIndex, setStageIndex] = useState(0)

  useEffect(() => {
    if (!loading) {
      setStageIndex(0)
      return
    }
    const id = setInterval(() => {
      setStageIndex((i) => Math.min(i + 1, LOADING_STAGES.length - 1))
    }, 2400)
    return () => clearInterval(id)
  }, [loading])

  return (
    <section className="card briefing-card" aria-live="polite">
      <div className="card-header">
        <h2 className="card-title">Briefing</h2>
        <div className="card-meta">
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

      <div className="card-body">
        {!loading && !result && !error && (
          <p className="placeholder">
            Pick a patient and ask a question to see the verified briefing.
          </p>
        )}

        {loading && (
          <div className="thinking" role="status" aria-live="polite">
            <span className="dot" aria-hidden="true" />
            <span className="dot" aria-hidden="true" />
            <span className="dot" aria-hidden="true" />
            <span className="thinking-label">{LOADING_STAGES[stageIndex]}</span>
          </div>
        )}

        {!loading && error && (
          <div className="error-block" role="alert">
            <p className="error">{error}</p>
            {onRetry && (
              <button type="button" className="ghost" onClick={onRetry}>
                Try again
              </button>
            )}
          </div>
        )}

        {!loading && result && (
          <div className="response">
            {result.response ? (
              <SourceText text={result.response} />
            ) : (
              <span className="empty">No briefing was produced.</span>
            )}
          </div>
        )}
      </div>
    </section>
  )
}
