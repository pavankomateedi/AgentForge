import { useContext } from 'react'
import { AuthContext } from './authState'
import type { AuthContextValue } from './authState'

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
