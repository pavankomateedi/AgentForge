// Per-patient dashboard. PatientHeader on top + the five clinical cards
// and Labs section in a responsive grid below.

import { Link, useParams } from 'react-router-dom'
import { useFhirQuery } from '../fhir/useFhirQuery'
import { getPatient } from '../fhir/resources'
import { PatientHeader } from '../components/PatientHeader'
import { AllergiesCard } from '../components/AllergiesCard'
import { ProblemListCard } from '../components/ProblemListCard'
import { MedicationsCard } from '../components/MedicationsCard'
import { PrescriptionsCard } from '../components/PrescriptionsCard'
import { CareTeamCard } from '../components/CareTeamCard'
import { LabsSection } from '../components/LabsSection'

export default function PatientView() {
  const { id } = useParams<{ id: string }>()
  const patientId = id ?? ''
  const { data: patient, error, loading, reload } = useFhirQuery(
    (c) => getPatient(c, patientId),
    [patientId],
  )

  if (!patientId) {
    return (
      <div className="placeholder-screen">
        <p>No patient id in URL.</p>
      </div>
    )
  }

  if (loading) {
    return <p className="state-msg" style={{ padding: 24 }}>Loading patient…</p>
  }

  if (error || !patient) {
    return (
      <div className="placeholder-screen">
        <div style={{ textAlign: 'center', maxWidth: 540 }}>
          <p style={{ color: 'var(--critical-fg)' }}>{error ?? 'Patient not found.'}</p>
          <button type="button" className="ghost" onClick={reload} style={{ marginRight: 8 }}>
            Try again
          </button>
          <Link to="/" className="ghost-link">Back to patients</Link>
        </div>
      </div>
    )
  }

  return (
    <div className="patient-view">
      <div style={{ marginBottom: 12 }}>
        <Link to="/" className="ghost-link">&larr; Back to patients</Link>
      </div>
      <PatientHeader patient={patient} />
      <div className="card-grid">
        <AllergiesCard patientId={patientId} />
        <ProblemListCard patientId={patientId} />
        <MedicationsCard patientId={patientId} />
        <PrescriptionsCard patientId={patientId} />
        <CareTeamCard patientId={patientId} />
        <div className="card-wide">
          <LabsSection patientId={patientId} />
        </div>
      </div>
    </div>
  )
}
