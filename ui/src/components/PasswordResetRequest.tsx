import { useState, type FormEvent } from 'react'
import { api } from '../api'

type Props = {
  onBackToLogin: () => void
}

export function PasswordResetRequest({ onBackToLogin }: Props) {
  const [email, setEmail] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!email.trim()) return
    setError(null)
    setSubmitting(true)
    const res = await api.passwordResetRequest(email.trim())
    setSubmitting(false)
    if (!res.ok) {
      setError(res.message)
      return
    }
    setSubmitted(true)
  }

  return (
    <div className="login-page">
      <header className="page-header login-header">
        <h1>Reset your password</h1>
        <p className="tagline">
          We'll send a reset link to your email if an account exists.
        </p>
      </header>

      <section className="card login-card" aria-label="Password reset request">
        {submitted ? (
          <>
            <p className="success">
              If an account with that email exists, we've sent a reset link.
              The link is valid for 1 hour.
            </p>
            <p className="card-sub">
              Check your inbox (and spam folder, just in case). If you don't
              see anything in a few minutes, contact your administrator.
            </p>
            <div className="actions">
              <button
                type="button"
                className="primary"
                onClick={onBackToLogin}
              >
                Back to sign in
              </button>
            </div>
          </>
        ) : (
          <>
            <p className="card-sub">
              Enter the email associated with your account. If we recognize it,
              we'll send a link to reset your password.
            </p>
            <form onSubmit={onSubmit} noValidate>
              <div className="field">
                <label htmlFor="reset-email">Email</label>
                <input
                  id="reset-email"
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
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
                  disabled={submitting || !email.trim()}
                >
                  {submitting ? 'Sending…' : 'Send reset link'}
                </button>
                <button
                  type="button"
                  className="ghost"
                  onClick={onBackToLogin}
                  disabled={submitting}
                >
                  Back
                </button>
              </div>
            </form>
          </>
        )}
      </section>
    </div>
  )
}
