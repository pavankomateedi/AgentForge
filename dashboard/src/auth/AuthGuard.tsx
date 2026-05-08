// Wraps protected routes. If the user has no valid access token, redirects
// to /login with the originally-requested path captured in `returnTo` so we
// can land them back where they were after sign-in.

import { Navigate, useLocation } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useAuth } from './useAuth'

export function AuthGuard({ children }: { children: ReactNode }) {
  const { accessToken } = useAuth()
  const location = useLocation()

  if (!accessToken) {
    const returnTo = encodeURIComponent(location.pathname + location.search)
    return <Navigate to={`/login?returnTo=${returnTo}`} replace />
  }

  return <>{children}</>
}
