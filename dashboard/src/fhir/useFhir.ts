import { useContext } from 'react'
import { FhirContext } from './fhirState'
import type { FhirClient } from './client'

export function useFhir(): FhirClient {
  const ctx = useContext(FhirContext)
  if (!ctx) throw new Error('useFhir must be used inside <FhirProvider>')
  return ctx
}
