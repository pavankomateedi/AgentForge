// Protected landing — shows the PatientPicker. Clicking a row navigates
// to /patients/:id (PatientView).

import { PatientPicker } from '../components/PatientPicker'

export default function Home() {
  return (
    <div>
      <PatientPicker />
    </div>
  )
}
