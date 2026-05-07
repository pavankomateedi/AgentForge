// Small custom hook for "fetch on mount, expose {data,error,loading}" against
// any async loader bound to the FhirClient. We intentionally avoid pulling
// react-query into a 22-hour build — the surface is tiny and the deps add
// weight that would have to be defended in the migration doc.
//
// Implementation notes
// - The loader is captured inside the effect closure each time deps change.
//   The exhaustive-deps lint rule can't see through the user-supplied deps
//   array, so we suppress it on the effect itself.
// - We don't synchronously reset to {loading: true, data: null} on deps
//   change. Instead, we use the "request id" pattern: each fetch increments
//   `requestId`; only the response whose id is still `latestRequestId.current`
//   is allowed to call setState. This keeps the React-19 lint rule happy
//   AND avoids a render-stale-then-render-loading flash.

import { useEffect, useRef, useState } from 'react'
import type { FhirClient } from './client'
import { useFhir } from './useFhir'

interface QueryState<T> {
  data: T | null
  error: string | null
  loading: boolean
}

export function useFhirQuery<T>(
  loader: (client: FhirClient) => Promise<T>,
  deps: ReadonlyArray<unknown>,
): QueryState<T> & { reload: () => void } {
  const client = useFhir()
  const [state, setState] = useState<QueryState<T>>({
    data: null,
    error: null,
    loading: true,
  })
  const [tick, setTick] = useState(0)
  const latestRequestId = useRef(0)

  useEffect(() => {
    const id = latestRequestId.current + 1
    latestRequestId.current = id

    loader(client)
      .then((data) => {
        if (latestRequestId.current !== id) return
        setState({ data, error: null, loading: false })
      })
      .catch((e: unknown) => {
        if (latestRequestId.current !== id) return
        const message = e instanceof Error ? e.message : String(e)
        setState({ data: null, error: message, loading: false })
      })

    return () => {
      // The cleanup function runs before the next effect or unmount; bumping
      // latestRequestId here would invalidate the in-flight call's setState.
      // We rely on the id-equality check inside the .then/.catch instead.
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client, tick, ...deps])

  return { ...state, reload: () => setTick((t) => t + 1) }
}
