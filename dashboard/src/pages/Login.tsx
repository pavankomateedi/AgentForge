// Renders a sign-in button that kicks off the OAuth2 PKCE redirect.
// When VITE_DEV_BYPASS=true (development only), shows an extra button that
// drops a fake token in sessionStorage so cards can be developed against a
// no-auth FHIR server (e.g. HAPI test) before OpenEMR is available.

import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { config } from '../config'
import { startLogin } from '../auth/oauth'
import { saveToken } from '../auth/storage'
import { useAuth } from '../auth/useAuth'

export default function Login() {
  const [error, setError] = useState<string | null>(null)
  const [working, setWorking] = useState(!config.devBypass)
  const location = useLocation()
  const navigate = useNavigate()
  const { setFromStorage } = useAuth()
  const returnTo =
    new URLSearchParams(location.search).get('returnTo') ?? '/'

  useEffect(() => {
    // In dev-bypass mode, do nothing on mount — let the user click the
    // dev button. In production mode, redirect to OpenEMR immediately.
    if (config.devBypass) return
    let cancelled = false
    startLogin(returnTo).catch((e: unknown) => {
      if (cancelled) return
      const message = e instanceof Error ? e.message : String(e)
      setError(message)
      setWorking(false)
    })
    return () => {
      cancelled = true
    }
  }, [returnTo])

  const devContinue = () => {
    saveToken('dev-bypass-token', 60 * 60) // 1 hour
    setFromStorage()
    navigate(returnTo, { replace: true })
  }

  return (
    <div className="placeholder-screen">
      <div style={{ textAlign: 'center', maxWidth: 480 }}>
        <h2 style={{ marginBottom: 16 }}>Sign in</h2>
        {working && !error && <p>Redirecting to OpenEMR…</p>}

        {error && (
          <>
            <p style={{ color: 'var(--critical-fg)', marginBottom: 16 }}>{error}</p>
            <button
              type="button"
              className="primary"
              onClick={() => {
                setError(null)
                setWorking(true)
                startLogin(returnTo).catch((e: unknown) => {
                  setError(e instanceof Error ? e.message : String(e))
                  setWorking(false)
                })
              }}
            >
              Try again
            </button>
          </>
        )}

        {config.devBypass && (
          <div style={{ marginTop: 24 }}>
            <button type="button" className="primary" onClick={() => startLogin(returnTo)}>
              Sign in with OpenEMR
            </button>
            <div style={{ marginTop: 12, fontSize: 13, color: 'var(--text-muted)' }}>
              Dev mode: OpenEMR not configured.
            </div>
            <button
              type="button"
              className="ghost"
              style={{ marginTop: 8 }}
              onClick={devContinue}
            >
              Continue without OAuth (dev)
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
