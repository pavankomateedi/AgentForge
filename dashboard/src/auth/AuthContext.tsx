// AuthProvider. Owns access-token state derived from sessionStorage and
// schedules an auto-clear timer when the token expires.

import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { AuthContext } from './authState'
import type { AuthContextValue } from './authState'
import { clearToken, readToken } from './storage'

interface AuthState {
  accessToken: string | null
  expiresAt: number | null
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(() => {
    const t = readToken()
    return t
      ? { accessToken: t.accessToken, expiresAt: t.expiresAt }
      : { accessToken: null, expiresAt: null }
  })

  const setFromStorage = useCallback(() => {
    const t = readToken()
    setState(
      t
        ? { accessToken: t.accessToken, expiresAt: t.expiresAt }
        : { accessToken: null, expiresAt: null },
    )
  }, [])

  const signOut = useCallback(() => {
    clearToken()
    setState({ accessToken: null, expiresAt: null })
  }, [])

  const invalidateOnAuthError = useCallback(() => {
    clearToken()
    setState({ accessToken: null, expiresAt: null })
  }, [])

  // Auto-clear when token expires (no refresh token; user re-auths).
  useEffect(() => {
    if (!state.expiresAt) return
    const ms = Math.max(0, state.expiresAt - Date.now())
    const id = window.setTimeout(() => {
      signOut()
    }, ms)
    return () => window.clearTimeout(id)
  }, [state.expiresAt, signOut])

  const value = useMemo<AuthContextValue>(
    () => ({
      accessToken: state.accessToken,
      expiresAt: state.expiresAt,
      signOut,
      invalidateOnAuthError,
      setFromStorage,
    }),
    [state, signOut, invalidateOnAuthError, setFromStorage],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
