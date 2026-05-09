// Per-patient documents list + extraction status. Polls every 3s when
// any document is still pending/extracting so the status badge updates
// without a manual refresh. Stops polling when everything is terminal.
//
// Documents in `needs_review` (post-extraction systematic check failed —
// typically patient identity mismatch) render with the warning text and
// inline Approve / Reject buttons. Approve clears the warning and the
// document flows into agent queries; Reject marks it failed so it stays
// in the audit trail but is excluded from chat tool reads.

import { useEffect, useState } from 'react'
import { api, type DocumentMeta } from '../api'

type Props = {
  patientId: string
  refreshKey: number  // bumped by parent after an upload to force a re-fetch
  onSelectDocument: (doc: DocumentMeta) => void
}

const POLL_MS = 3000

export function DocumentsList({ patientId, refreshKey, onSelectDocument }: Props) {
  const [docs, setDocs] = useState<DocumentMeta[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [actioning, setActioning] = useState<number | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  async function fetchOnce() {
    setLoading(true)
    const res = await api.listDocuments(patientId)
    setLoading(false)
    if (!res.ok) {
      setError(res.message)
      return
    }
    setError(null)
    setDocs(res.data.documents)
  }

  // Initial + on-refresh fetch.
  useEffect(() => {
    // fetchOnce is async + sets state inside; lint rule flags it as
    // a setState-in-effect even though the actual setState happens
    // inside the async resolution. Pattern is correct.
    // eslint-disable-next-line react-hooks/set-state-in-effect, react-hooks/exhaustive-deps
    void fetchOnce()
  }, [patientId, refreshKey])

  // Poll while anything is still in-flight.
  useEffect(() => {
    const anyPending = docs.some(
      (d) => d.extraction_status === 'pending' || d.extraction_status === 'extracting',
    )
    if (!anyPending) return
    const id = window.setInterval(fetchOnce, POLL_MS)
    return () => window.clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [docs])

  async function approve(doc: DocumentMeta) {
    setActioning(doc.id)
    setActionError(null)
    const res = await api.approveDocument(doc.id)
    setActioning(null)
    if (!res.ok) {
      setActionError(`Approve failed: ${res.message}`)
      return
    }
    void fetchOnce()
  }

  async function reject(doc: DocumentMeta) {
    if (
      !window.confirm(
        `Reject document #${doc.id}? It will be marked failed and excluded ` +
          `from agent queries. The document and audit log are preserved.`,
      )
    ) {
      return
    }
    setActioning(doc.id)
    setActionError(null)
    const res = await api.rejectDocument(doc.id)
    setActioning(null)
    if (!res.ok) {
      setActionError(`Reject failed: ${res.message}`)
      return
    }
    void fetchOnce()
  }

  if (error) {
    return (
      <p className="placeholder error" role="alert">
        Could not load documents: {error}
      </p>
    )
  }
  if (docs.length === 0) {
    return (
      <p className="placeholder">
        {loading
          ? 'Loading documents…'
          : 'No documents uploaded yet for this patient.'}
      </p>
    )
  }

  return (
    <ul className="documents-list">
      {actionError && (
        <li className="document-row">
          <p className="form-error" role="alert" style={{ margin: 0 }}>
            {actionError}
          </p>
        </li>
      )}
      {docs.map((d) => {
        const isReview = d.extraction_status === 'needs_review'
        return (
          <li
            key={d.id}
            className={`document-row${isReview ? ' document-row-review' : ''}`}
          >
            <button
              type="button"
              className="document-row-button"
              onClick={() => onSelectDocument(d)}
            >
              <span className="document-meta">
                <span className="document-type">
                  {d.doc_type === 'lab_pdf' ? 'Lab PDF' : 'Intake form'}
                </span>
                <span className="document-id">#{d.id}</span>
              </span>
              <span className="document-uploaded">
                {new Date(d.uploaded_at).toLocaleString()}
              </span>
              <StatusBadge status={d.extraction_status} error={d.extraction_error} />
            </button>
            {isReview && (
              <div className="document-review-action">
                <p className="document-review-message">
                  <strong>Review required:</strong>{' '}
                  {d.extraction_error ?? 'Systematic check flagged this document.'}
                </p>
                <div className="document-review-buttons">
                  <button
                    type="button"
                    className="btn-primary btn-compact"
                    onClick={() => approve(d)}
                    disabled={actioning === d.id}
                  >
                    {actioning === d.id ? 'Approving…' : 'Approve match'}
                  </button>
                  <button
                    type="button"
                    className="btn-secondary btn-compact"
                    onClick={() => reject(d)}
                    disabled={actioning === d.id}
                  >
                    {actioning === d.id ? 'Rejecting…' : 'Reject (wrong patient)'}
                  </button>
                </div>
              </div>
            )}
          </li>
        )
      })}
    </ul>
  )
}

function StatusBadge({
  status,
  error,
}: {
  status: DocumentMeta['extraction_status']
  error: string | null
}) {
  const label =
    status === 'pending'
      ? 'Queued'
      : status === 'extracting'
        ? 'Extracting…'
        : status === 'done'
          ? 'Ready'
          : status === 'needs_review'
            ? 'Needs review'
            : 'Failed'
  const title = error ?? `Extraction status: ${status}`
  return (
    <span className={`status-badge status-${status}`} title={title}>
      {label}
    </span>
  )
}
