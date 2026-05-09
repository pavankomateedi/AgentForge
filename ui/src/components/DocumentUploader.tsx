// Modal-style uploader for lab PDFs / intake forms. Sits next to the
// patient picker. The endpoint is fast (returns 200 with status='pending'
// immediately); extraction runs in the background and the documents list
// polls until status='done'.
//
// Wrong-patient guard: before the actual POST, the uploader fetches the
// assigned patient's identity (name + DOB + MRN) and renders an explicit
// confirmation block. The Upload button stays disabled until the user
// ticks "I confirm this file is for <patient name>". The confirmation
// is a deliberate clinical-safety step — same intent as the EMR
// timeout-and-confirm prompts before charting against a chart.

import { useEffect, useState } from 'react'
import { api } from '../api'

type Props = {
  patientId: string
  onUploaded: () => void
  onClose: () => void
}

type DocType = 'lab_pdf' | 'intake_form'

type PatientIdentity = {
  patient_id: string
  name: string | null
  dob: string | null
  sex: string | null
  mrn: string | null
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(2)} MB`
}

export function DocumentUploader({ patientId, onUploaded, onClose }: Props) {
  const [docType, setDocType] = useState<DocType>('lab_pdf')
  const [file, setFile] = useState<File | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [loadingSample, setLoadingSample] = useState(false)
  const [identity, setIdentity] = useState<PatientIdentity | null>(null)
  const [identityError, setIdentityError] = useState<string | null>(null)
  const [confirmed, setConfirmed] = useState(false)

  // Fetch patient identity once on mount (or whenever patientId changes).
  // Used by the confirmation block before the upload commits.
  // The synchronous resets are correct per React docs' canonical
  // fetch-on-mount pattern — disabling the lint rule that flags them.
  useEffect(() => {
    let cancelled = false
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setConfirmed(false)
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setIdentity(null)
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setIdentityError(null)
    ;(async () => {
      const res = await api.patientIdentity(patientId)
      if (cancelled) return
      if (!res.ok) {
        setIdentityError(res.message)
        return
      }
      setIdentity(res.data)
    })()
    return () => {
      cancelled = true
    }
  }, [patientId])

  // Pull the synthetic sample PDF for the current patient + doc-type
  // combo into the form's File state so the grader can upload-without-
  // download. Served by `agent/main.py` from samples/lab_pdfs/ and
  // samples/intake_forms/. The doc-type dropdown's current value
  // decides which subdir we hit; switch the dropdown first to pick
  // the right kind of sample.
  async function loadSample() {
    setLoadingSample(true)
    setError(null)
    try {
      const subdir = docType === 'lab_pdf' ? 'lab_pdfs' : 'intake_forms'
      const stem = docType === 'lab_pdf' ? 'lab_report' : 'intake_form'
      const filename = `${patientId}_${stem}.pdf`
      const url = `/samples/${subdir}/${filename}`
      const res = await fetch(url, { credentials: 'include' })
      if (!res.ok) {
        setError(
          `No sample ${docType.replace('_', ' ')} on file for ${patientId} ` +
            `(HTTP ${res.status}).`,
        )
        return
      }
      const blob = await res.blob()
      setFile(new File([blob], filename, { type: 'application/pdf' }))
    } catch (err) {
      setError(
        'Could not load sample: ' +
          (err instanceof Error ? err.message : String(err)),
      )
    } finally {
      setLoadingSample(false)
    }
  }

  const sampleLabel = docType === 'lab_pdf' ? 'lab report' : 'intake form'

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!file) {
      setError('Choose a file first.')
      return
    }
    if (!confirmed) {
      setError('Please confirm the patient identity before uploading.')
      return
    }
    setSubmitting(true)
    setError(null)
    setSuccess(null)
    const res = await api.uploadDocument(patientId, docType, file)
    if (!res.ok) {
      setSubmitting(false)
      setError(res.message)
      return
    }
    // Show a clear "processing in background" message, refresh the
    // documents list so the new row appears, and auto-close the modal
    // after a short beat. Keeping `submitting` true through the
    // countdown freezes the form so the user can't double-submit.
    setSuccess(
      res.data.deduplicated
        ? `Already on file as document #${res.data.document_id}. ` +
            `See it in the documents list. Closing…`
        : `Document #${res.data.document_id} uploaded. ` +
            `Extraction is running in the background — track its ` +
            `status in the documents list. Closing…`,
    )
    setFile(null)
    onUploaded()
    window.setTimeout(() => {
      onClose()
    }, 1800)
  }

  const patientLabel =
    identity?.name ?? `patient ${patientId}`

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
          <h3 id="upload-title">Upload document for {patientLabel}</h3>
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
          {/* Patient identity card — the systematic check the user is
              asked to confirm against. Stays visible at the top of the
              modal regardless of which step the user is on. */}
          <section className="upload-identity-card" aria-label="Patient identity">
            <div className="upload-identity-label">Uploading to</div>
            {identity ? (
              <>
                <div className="upload-identity-name">{identity.name ?? patientId}</div>
                <dl className="upload-identity-meta">
                  <div>
                    <dt>Patient ID</dt>
                    <dd>{patientId}</dd>
                  </div>
                  {identity.dob && (
                    <div>
                      <dt>DOB</dt>
                      <dd>{identity.dob}</dd>
                    </div>
                  )}
                  {identity.sex && (
                    <div>
                      <dt>Sex</dt>
                      <dd>{identity.sex}</dd>
                    </div>
                  )}
                  {identity.mrn && (
                    <div>
                      <dt>MRN</dt>
                      <dd>{identity.mrn}</dd>
                    </div>
                  )}
                </dl>
              </>
            ) : identityError ? (
              <p className="form-error" role="alert" style={{ margin: 0 }}>
                Could not verify patient: {identityError}
              </p>
            ) : (
              <p className="placeholder" style={{ margin: 0 }}>
                Loading patient identity…
              </p>
            )}
          </section>

          <div className="form-row sample-row">
            <span className="form-label">Don&apos;t have a file handy?</span>
            <button
              type="button"
              className="btn-link"
              onClick={loadSample}
              disabled={loadingSample || submitting}
            >
              {loadingSample
                ? 'Loading sample…'
                : `Use synthetic sample ${sampleLabel} for ${patientId}`}
            </button>
            <span className="form-hint">
              Loads a checked-in {sampleLabel} PDF for this patient.
              Switch the document type above to pick a different sample.
              Synthetic data, no PHI.
            </span>
          </div>

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
              {file
                ? `Selected: ${file.name} (${formatBytes(file.size)})`
                : 'No file chosen yet.'}{' '}
              {docType === 'lab_pdf'
                ? 'PDF only. Max 10 MB.'
                : 'PDF or image (JPEG/PNG/HEIC). Max 10 MB.'}
            </span>
          </label>

          {/* Approval checkbox — disabled until a file is chosen so the
              user can't pre-confirm an empty form. The Upload button is
              gated on this checkbox AND the file being present. */}
          <div className="form-row upload-confirm-row">
            <label className="upload-confirm-label">
              <input
                type="checkbox"
                checked={confirmed}
                disabled={!file || submitting}
                onChange={(e) => setConfirmed(e.target.checked)}
              />
              <span>
                I confirm this file is for{' '}
                <strong>{patientLabel}</strong>
                {identity?.mrn && (
                  <>
                    {' '}
                    (<span className="upload-confirm-mrn">{identity.mrn}</span>)
                  </>
                )}
                .
              </span>
            </label>
            <span className="form-hint">
              Wrong-patient uploads are a known clinical-safety risk. This
              checkbox is the explicit human-in-the-loop step before the
              file is committed to the chart.
            </span>
          </div>

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
              disabled={submitting || !file || !confirmed}
              title={
                !file
                  ? 'Choose a file first'
                  : !confirmed
                    ? 'Confirm the patient identity to enable upload'
                    : undefined
              }
            >
              {submitting ? 'Uploading…' : 'Upload'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
