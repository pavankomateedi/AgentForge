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
    // When fhirBase is relative (e.g. "/fhir-api"), the browser is going
    // through the Vite dev proxy because direct calls to the public FHIR
    // server are blocked (typical on corporate networks with HTTPS
    // interception). HAPI returns Bundle.link.next as absolute URLs that
    // the browser can't reach directly — rewrite those to the proxy base.
    const isProxied = !/^https?:\/\//i.test(config.fhirBase)
    const upstream = config.fhirProxyTarget?.replace(/\/+$/, '')
    const rewriteUrl =
      isProxied && upstream
        ? (url: string) =>
            url.startsWith(upstream)
              ? config.fhirBase + url.slice(upstream.length)
              : url
        : undefined

    return new FhirClient({
      baseUrl: config.fhirBase,
      getAccessToken: () => accessToken,
      onAuthError: () => invalidateOnAuthError(),
      rewriteUrl,
    })
  }, [accessToken, invalidateOnAuthError])

  return <FhirContext.Provider value={client}>{children}</FhirContext.Provider>
}
