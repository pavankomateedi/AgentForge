import { useState, type FormEvent } from 'react'
import { api } from '../api'

type Props = {
  token: string
  onBackToLogin: () => void
}

const MIN_PASSWORD_LENGTH = 8

export function PasswordResetConfirm({ token, onBackToLogin }: Props) {
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const mismatch = confirm.length > 0 && password !== confirm
  const tooShort = password.length > 0 && password.length < MIN_PASSWORD_LENGTH

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (mismatch || tooShort || !password) return
    setError(null)
    setSubmitting(true)
    const res = await api.passwordResetConfirm(token, password)
    setSubmitting(false)
    if (!res.ok) {
      setError(res.message)
      return
    }
    setDone(true)
  }

  return (
    <div className="login-page">
      <header className="page-header login-header">
        <h1>Choose a new password</h1>
        <p className="tagline">
          {done
            ? 'Your password has been updated.'
            : 'Set a new password for your account.'}
        </p>
      </header>

      <section className="card login-card" aria-label="Set new password">
        {done ? (
          <>
            <p className="success">
              Password updated. You can sign in with your new password.
            </p>
            <div className="actions">
              <button
                type="button"
                className="primary"
                onClick={onBackToLogin}
              >
                Sign in
              </button>
            </div>
          </>
        ) : (
          <form onSubmit={onSubmit} noValidate>
            <div className="field">
              <label htmlFor="new-password">New password</label>
              <input
                id="new-password"
                type="password"
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={submitting}
                autoFocus
                minLength={MIN_PASSWORD_LENGTH}
                required
              />
            </div>

            <div className="field">
              <label htmlFor="confirm-password">Confirm new password</label>
              <input
                id="confirm-password"
                type="password"
                autoComplete="new-password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                disabled={submitting}
                minLength={MIN_PASSWORD_LENGTH}
                required
              />
            </div>

            {tooShort && (
              <p className="hint hint-warn">
                Use at least {MIN_PASSWORD_LENGTH} characters.
              </p>
            )}
            {mismatch && (
              <p className="hint hint-warn">Passwords don't match.</p>
            )}
            {error && (
              <p className="error" role="alert">
                {error}
              </p>
            )}

            <div className="actions actions-row">
              <button
                type="submit"
                className="primary"
                disabled={
                  submitting ||
                  !password ||
                  password !== confirm ||
                  tooShort
                }
              >
                {submitting ? 'Updating…' : 'Update password'}
              </button>
              <button
                type="button"
                className="ghost"
                onClick={onBackToLogin}
                disabled={submitting}
              >
                Cancel
              </button>
            </div>
          </form>
        )}
      </section>
    </div>
  )
}
