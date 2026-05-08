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
      <PatientPicker />
    </div>
  )
}
