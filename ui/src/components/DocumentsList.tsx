// Per-patient documents list + extraction status. Polls every 3s when
// any document is still pending/extracting so the status badge updates
// without a manual refresh. Stops polling when everything is terminal.

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
    void fetchOnce()
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
      {docs.map((d) => (
        <li key={d.id} className="document-row">
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
        </li>
      ))}
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
          : 'Failed'
  const title = error ?? `Extraction status: ${status}`
  return (
    <span className={`status-badge status-${status}`} title={title}>
      {label}
    </span>
  )
}
