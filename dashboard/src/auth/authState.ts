// Bare context + value-type. Lives in its own non-JSX file so the React-Refresh
// "components-only" rule stays happy on AuthContext.tsx.

import { createContext } from 'react'

export interface AuthContextValue {
  accessToken: string | null
  expiresAt: number | null
  signOut: () => void
  invalidateOnAuthError: () => void
  setFromStorage: () => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)
