// Modal-style uploader for lab PDFs / intake forms. Sits next to the
// patient picker. The endpoint is fast (returns 200 with status='pending'
// immediately); extraction runs in the background and the documents list
// polls until status='done'.

import { useState } from 'react'
import { api } from '../api'

type Props = {
  patientId: string
  onUploaded: () => void
  onClose: () => void
}

type DocType = 'lab_pdf' | 'intake_form'

export function DocumentUploader({ patientId, onUploaded, onClose }: Props) {
  const [docType, setDocType] = useState<DocType>('lab_pdf')
  const [file, setFile] = useState<File | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!file) {
      setError('Choose a file first.')
      return
    }
    setSubmitting(true)
    setError(null)
    setSuccess(null)
    const res = await api.uploadDocument(patientId, docType, file)
    setSubmitting(false)
    if (!res.ok) {
      setError(res.message)
      return
    }
    setSuccess(
      res.data.deduplicated
        ? `Already uploaded — using existing document #${res.data.document_id}.`
        : `Uploaded as document #${res.data.document_id}. Extraction queued.`,
    )
    setFile(null)
    onUploaded()
  }

  return (
    <div
      className="modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="upload-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="modal-card">
        <header className="modal-header">
          <h3 id="upload-title">Upload document for {patientId}</h3>
          <button
            type="button"
            className="modal-close"
            aria-label="Close"
            onClick={onClose}
          >
            ×
          </button>
        </header>

        <form onSubmit={submit} className="modal-body">
          <label className="form-row">
            <span className="form-label">Document type</span>
            <select
              value={docType}
              onChange={(e) => setDocType(e.target.value as DocType)}
              disabled={submitting}
            >
              <option value="lab_pdf">Lab PDF</option>
              <option value="intake_form">Intake form (PDF or image)</option>
            </select>
          </label>

          <label className="form-row">
            <span className="form-label">File</span>
            <input
              type="file"
              accept={
                docType === 'lab_pdf'
                  ? 'application/pdf'
                  : 'application/pdf,image/jpeg,image/png,image/heic'
              }
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              disabled={submitting}
            />
            <span className="form-hint">
              {docType === 'lab_pdf'
                ? 'PDF only. Max 10 MB.'
                : 'PDF or image (JPEG/PNG/HEIC). Max 10 MB.'}
            </span>
          </label>

          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          {success && (
            <p className="form-success" role="status">
              {success}
            </p>
          )}

          <div className="modal-actions">
            <button
              type="button"
              className="btn-secondary"
              onClick={onClose}
              disabled={submitting}
            >
              Close
            </button>
            <button
              type="submit"
              className="btn-primary"
              disabled={submitting || !file}
            >
              {submitting ? 'Uploading…' : 'Upload'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
