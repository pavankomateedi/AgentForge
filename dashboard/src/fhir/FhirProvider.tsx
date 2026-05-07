// Provides a single FhirClient configured with the current access token and
// FHIR base URL. Recreated whenever the token changes so future requests
// pick up the new bearer.

import { useMemo } from 'react'
import type { ReactNode } from 'react'
import { config } from '../config'
import { FhirClient } from './client'
import { FhirContext } from './fhirState'
import { useAuth } from '../auth/useAuth'

export function FhirProvider({ children }: { children: ReactNode }) {
  const { accessToken, invalidateOnAuthError } = useAuth()

  const client = useMemo(() => {
    return new FhirClient({
      baseUrl: config.fhirBase,
      getAccessToken: () => accessToken,
      onAuthError: () => invalidateOnAuthError(),
    })
  }, [accessToken, invalidateOnAuthError])

  return <FhirContext.Provider value={client}>{children}</FhirContext.Provider>
}
