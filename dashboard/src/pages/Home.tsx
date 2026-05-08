// Protected landing — when the OAuth flow returned a patient launch
// context (SMART-on-FHIR `launch/patient` scope), route directly to that
// patient's view. Otherwise show the patient picker (still useful when the
// dashboard runs against a confidential client with `user/*` scopes that
// can list every patient).

import { Navigate } from 'react-router-dom'
import { readPatientContext } from '../auth/storage'
import { PatientPicker } from '../components/PatientPicker'

export default function Home() {
  const patientId = readPatientContext()
  if (patientId) {
    return <Navigate to={`/patients/${patientId}`} replace />
  }
  return (
    <div>
      <section className="cross-app-banner" aria-label="Sibling app pointer">
        <div>
          <strong>This is the OpenEMR Patient Dashboard surprise-challenge port.</strong>
          {' '}The Week 2 Clinical Co-Pilot — document upload, multimodal extraction with citations, hybrid RAG, and grounded chat — lives at the root URL.
        </div>
        <a href="/" className="cross-app-banner-cta" title="Open the Week 2 Clinical Co-Pilot">
          Open Clinical Co-Pilot →
        </a>
      </section>
      <PatientPicker />
    </div>
  )
}
