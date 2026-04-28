import { useState, type FormEvent } from 'react'
import { api } from '../api'
import type { AuthUser } from '../types'

type Props = {
  onAuthenticated: (user: AuthUser) => void
  onCancel: () => void
}

export function MfaChallenge({ onAuthenticated, onCancel }: Props) {
  const [code, setCode] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (code.replace(/\s/g, '').length !== 6) return
    setError(null)
    setSubmitting(true)
    const res = await api.mfaChallenge(code.replace(/\s/g, ''))
    setSubmitting(false)
    if (!res.ok) {
      setError(res.message)
      return
    }
    if (res.data.user) onAuthenticated(res.data.user)
  }

  return (
    <div className="login-page">
      <header className="page-header login-header">
        <h1>Two-factor verification</h1>
        <p className="tagline">
          Enter the code from your authenticator app to continue.
        </p>
      </header>

      <section className="card login-card" aria-label="MFA challenge">
        <form onSubmit={onSubmit} noValidate>
          <div className="field">
            <label htmlFor="challenge-code">6-digit code</label>
            <input
              id="challenge-code"
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              value={code}
              onChange={(e) =>
                setCode(e.target.value.replace(/[^0-9 ]/g, '').slice(0, 9))
              }
              placeholder="000 000"
              disabled={submitting}
              autoFocus
              required
            />
          </div>

          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}

          <div className="actions actions-row">
            <button
              type="submit"
              className="primary"
              disabled={submitting || code.replace(/\s/g, '').length !== 6}
            >
              {submitting ? 'Verifying…' : 'Verify'}
            </button>
            <button
              type="button"
              className="ghost"
              onClick={onCancel}
              disabled={submitting}
            >
              Cancel
            </button>
          </div>
        </form>

        <p className="footnote">
          Lost access to your authenticator? Contact your administrator.
        </p>
      </section>
    </div>
  )
}
