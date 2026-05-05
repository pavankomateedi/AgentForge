// Per-document detail panel. Embeds the source PDF/image and renders
// the schema-validated extracted facts (one row per derived observation).
// Bbox visualization is text-based for v0 — the bbox coordinates are
// exposed so a future PDF-overlay component can render the rectangle.

import { useEffect, useState } from 'react'
import { api, type DerivedObservation, type DocumentMeta } from '../api'

type Props = {
  doc: DocumentMeta
  onClose: () => void
}

export function DocumentDetail({ doc, onClose }: Props) {
  const [rows, setRows] = useState<DerivedObservation[]>([])
  const [extractionStatus, setExtractionStatus] = useState(doc.extraction_status)
  const [extractionError, setExtractionError] = useState<string | null>(
    doc.extraction_error,
  )
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      const res = await api.documentDerived(doc.id)
      setLoading(false)
      if (cancelled) return
      if (!res.ok) {
        setError(res.message)
        return
      }
      setError(null)
      setRows(res.data.rows)
      setExtractionStatus(
        res.data.extraction_status as DocumentMeta['extraction_status'],
      )
      setExtractionError(res.data.extraction_error)
    })()
    return () => {
      cancelled = true
    }
  }, [doc.id])

  return (
    <div
      className="modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="doc-detail-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="modal-card modal-card-wide">
        <header className="modal-header">
          <h3 id="doc-detail-title">
            {doc.doc_type === 'lab_pdf' ? 'Lab PDF' : 'Intake form'} #{doc.id}
          </h3>
          <button
            type="button"
            className="modal-close"
            aria-label="Close"
            onClick={onClose}
          >
            ×
          </button>
        </header>

        <div className="modal-body two-pane">
          <section className="document-source">
            <h4>Source</h4>
            {doc.content_type === 'application/pdf' ? (
              <embed
                src={api.documentBlobUrl(doc.id)}
                type="application/pdf"
                className="document-embed"
              />
            ) : (
              <img
                src={api.documentBlobUrl(doc.id)}
                alt={`document #${doc.id}`}
                className="document-image"
              />
            )}
          </section>

          <section className="document-derived">
            <h4>
              Extracted facts{' '}
              <span className={`status-badge status-${extractionStatus}`}>
                {extractionStatus}
              </span>
            </h4>
            {error && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}
            {extractionError && (
              <p className="form-error" role="alert">
                Extraction error: {extractionError}
              </p>
            )}
            {loading ? (
              <p className="placeholder">Loading…</p>
            ) : rows.length === 0 ? (
              <p className="placeholder">
                {extractionStatus === 'done'
                  ? 'No structured facts were extracted.'
                  : 'Extraction not yet complete.'}
              </p>
            ) : (
              <ul className="derived-list">
                {rows.map((row) => (
                  <li key={row.id} className="derived-row">
                    <div className="derived-row-header">
                      <span className="derived-kind">{row.schema_kind}</span>
                      <span className="derived-source-id">{row.source_id}</span>
                      {row.confidence !== null && (
                        <span className="derived-confidence">
                          conf {Math.round(row.confidence * 100)}%
                        </span>
                      )}
                    </div>
                    <pre className="derived-payload">
                      {JSON.stringify(row.payload, null, 2)}
                    </pre>
                    {(row.page_number || row.bbox) && (
                      <p className="derived-locator">
                        {row.page_number
                          ? `Page ${row.page_number}`
                          : 'No page number'}
                        {row.bbox &&
                          ` · bbox (${Math.round(row.bbox.x0)},${Math.round(
                            row.bbox.y0,
                          )}) → (${Math.round(row.bbox.x1)},${Math.round(
                            row.bbox.y1,
                          )})`}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      </div>
    </div>
  )
}
