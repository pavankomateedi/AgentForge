// Handles the redirect back from OpenEMR. Exchanges code → access_token,
// stores it via auth/storage, then navigates to the user's intended destination.

import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { handleCallback } from '../auth/oauth'
import { useAuth } from '../auth/useAuth'

export default function OAuthCallback() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const { setFromStorage } = useAuth()
  const [error, setError] = useState<string | null>(null)
  // StrictMode + double-mount in dev: guard against running the exchange
  // twice (the auth code is one-shot and the second call would 400).
  const ranRef = useRef(false)

  useEffect(() => {
    if (ranRef.current) return
    ranRef.current = true

    handleCallback(params)
      .then((result) => {
        setFromStorage()
        navigate(result.redirectTo, { replace: true })
      })
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : String(e))
      })
  }, [params, navigate, setFromStorage])

  if (error) {
    return (
      <div className="placeholder-screen">
        <div style={{ textAlign: 'center', maxWidth: 540 }}>
          <h2>Sign-in failed</h2>
          <p style={{ color: 'var(--critical-fg)', marginTop: 12 }}>{error}</p>
          <button
            type="button"
            className="primary"
            style={{ marginTop: 16 }}
            onClick={() => navigate('/login', { replace: true })}
          >
            Back to login
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="placeholder-screen">
      <p>Completing sign-in…</p>
    </div>
  )
}
