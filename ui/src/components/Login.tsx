import { useState, type FormEvent } from 'react'
import { api } from '../api'
import type { AuthUser } from '../types'

type Props = {
  onAuthenticated: (user: AuthUser) => void
}

export function Login({ onAuthenticated }: Props) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!username.trim() || !password) return
    setError(null)
    setSubmitting(true)
    const res = await api.login(username.trim(), password)
    setSubmitting(false)
    if (!res.ok) {
      setError(res.message)
      return
    }
    onAuthenticated(res.data.user)
  }

  return (
    <div className="login-page">
      <header className="page-header login-header">
        <h1>Clinical Co-Pilot</h1>
        <p className="tagline">Pre-visit briefings, grounded in the chart.</p>
      </header>

      <section className="card login-card" aria-label="Sign in">
        <h2 className="card-title">Sign in</h2>
        <p className="card-sub">
          Access is restricted to authorized clinicians.
        </p>

        <form onSubmit={onSubmit} noValidate>
          <div className="field">
            <label htmlFor="username">Username</label>
            <input
              id="username"
              type="text"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={submitting}
              autoFocus
              required
            />
          </div>

          <div className="field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={submitting}
              required
            />
          </div>

          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}

          <button
            type="submit"
            className="primary"
            disabled={submitting || !username.trim() || !password}
          >
            {submitting ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <p className="footnote">
          Forgot your password? Contact your administrator.
        </p>
      </section>
    </div>
  )
}
