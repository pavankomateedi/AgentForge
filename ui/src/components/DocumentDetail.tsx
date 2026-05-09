// Per-document detail panel. Renders the source PDF as a server-rasterized
// PNG so we can absolutely-position bbox overlays on top — clicking any
// derived row highlights its source region with a red rectangle. For
// non-PDF (intake form image) documents the page-image endpoint passes the
// original image through unchanged.

import { useEffect, useMemo, useRef, useState } from 'react'
import { api, type DerivedObservation, type DocumentMeta } from '../api'

type Props = {
  doc: DocumentMeta
  onClose: () => void
}

// PDF coords from pdfplumber are at 72 dpi. The page-image endpoint
// rasterizes at 144 dpi, so a coord of x in PDF space maps to 2x in the
// PNG's natural pixel space. We then scale by displayed/natural ratio.
const RENDER_DPI = 144
const PDF_DPI = 72
const PDF_TO_PNG_SCALE = RENDER_DPI / PDF_DPI

export function DocumentDetail({ doc, onClose }: Props) {
  const [rows, setRows] = useState<DerivedObservation[]>([])
  const [extractionStatus, setExtractionStatus] = useState(doc.extraction_status)
  const [extractionError, setExtractionError] = useState<string | null>(
    doc.extraction_error,
  )
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedRowId, setSelectedRowId] = useState<number | null>(null)
  const [imageNaturalSize, setImageNaturalSize] = useState<{
    width: number
    height: number
  } | null>(null)
  const [imageDisplaySize, setImageDisplaySize] = useState<{
    width: number
    height: number
  } | null>(null)
  const imgRef = useRef<HTMLImageElement | null>(null)

  // Fetch derived rows when the document changes.
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
      // Auto-select the first row that has a bbox so the overlay shows
      // something on initial render.
      const first = res.data.rows.find((r) => r.bbox && r.page_number)
      if (first) setSelectedRowId(first.id)
    })()
    return () => {
      cancelled = true
    }
  }, [doc.id])

  const selectedRow = useMemo(
    () => rows.find((r) => r.id === selectedRowId) ?? null,
    [rows, selectedRowId],
  )

  // Which page to render. For image-content-type docs we always use page=1
  // (the endpoint passes the image through). For PDFs we use the selected
  // row's page, defaulting to 1.
  const currentPage = selectedRow?.page_number ?? 1

  const isPdf = doc.content_type === 'application/pdf'

  const imageSrc = isPdf
    ? api.documentPageImageUrl(doc.id, currentPage, RENDER_DPI)
    : api.documentBlobUrl(doc.id)

  // Recompute the displayed image size whenever the image element is
  // resized (e.g. modal width changes). ResizeObserver gives us live
  // updates without an interval.
  useEffect(() => {
    const el = imgRef.current
    if (!el) return
    const update = () => {
      const rect = el.getBoundingClientRect()
      setImageDisplaySize({ width: rect.width, height: rect.height })
    }
    update()
    const ro = new ResizeObserver(update)
    ro.observe(el)
    return () => ro.disconnect()
  }, [imageNaturalSize])

  const onImageLoad = () => {
    const el = imgRef.current
    if (!el) return
    setImageNaturalSize({
      width: el.naturalWidth,
      height: el.naturalHeight,
    })
    setImageDisplaySize({
      width: el.getBoundingClientRect().width,
      height: el.getBoundingClientRect().height,
    })
  }

  // Convert a PDF-coord bbox into displayed-pixel coords. For non-PDF
  // image documents we treat coords as already in image pixel space
  // (1:1 with natural).
  const overlayRect = useMemo(() => {
    if (!selectedRow?.bbox || !imageNaturalSize || !imageDisplaySize) return null
    const { x0, y0, x1, y1 } = selectedRow.bbox
    const naturalScale = isPdf ? PDF_TO_PNG_SCALE : 1
    const displayScaleX = imageDisplaySize.width / imageNaturalSize.width
    const displayScaleY = imageDisplaySize.height / imageNaturalSize.height
    return {
      left: x0 * naturalScale * displayScaleX,
      top: y0 * naturalScale * displayScaleY,
      width: (x1 - x0) * naturalScale * displayScaleX,
      height: (y1 - y0) * naturalScale * displayScaleY,
    }
  }, [selectedRow, imageNaturalSize, imageDisplaySize, isPdf])

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
            {selectedRow?.page_number && (
              <span className="document-page-indicator">
                {' '}
                · page {selectedRow.page_number}
              </span>
            )}
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
            <div className="document-image-wrap">
              <img
                ref={imgRef}
                key={`${doc.id}-${currentPage}`}
                src={imageSrc}
                alt={`document #${doc.id} page ${currentPage}`}
                className="document-image"
                onLoad={onImageLoad}
              />
              {overlayRect && (
                <div
                  className="document-bbox-overlay"
                  style={{
                    left: `${overlayRect.left}px`,
                    top: `${overlayRect.top}px`,
                    width: `${overlayRect.width}px`,
                    height: `${overlayRect.height}px`,
                  }}
                  aria-hidden="true"
                />
              )}
            </div>
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
                {rows.map((row) => {
                  const isSelected = row.id === selectedRowId
                  const hasBbox = !!row.bbox && !!row.page_number
                  return (
                    <li
                      key={row.id}
                      className={`derived-row${isSelected ? ' derived-row-selected' : ''}${hasBbox ? ' derived-row-clickable' : ''}`}
                      onClick={() => hasBbox && setSelectedRowId(row.id)}
                      role={hasBbox ? 'button' : undefined}
                      tabIndex={hasBbox ? 0 : undefined}
                      onKeyDown={(e) => {
                        if (hasBbox && (e.key === 'Enter' || e.key === ' ')) {
                          e.preventDefault()
                          setSelectedRowId(row.id)
                        }
                      }}
                      title={hasBbox ? 'Click to highlight in source' : undefined}
                    >
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
                      {hasBbox && (
                        <p className="derived-locator">
                          Page {row.page_number} · bbox (
                          {Math.round(row.bbox!.x0)},{Math.round(row.bbox!.y0)})
                          → ({Math.round(row.bbox!.x1)},{Math.round(row.bbox!.y1)})
                          {isSelected && (
                            <span className="derived-locator-active">
                              {' · '}highlighted
                            </span>
                          )}
                        </p>
                      )}
                    </li>
                  )
                })}
              </ul>
            )}
          </section>
        </div>
      </div>
    </div>
  )
}
