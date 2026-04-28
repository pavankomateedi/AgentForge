import { useEffect, useState, type FormEvent } from 'react'
import { QRCodeSVG } from 'qrcode.react'
import { api } from '../api'
import type { AuthUser, MfaSetupResponse } from '../types'

type Props = {
  onAuthenticated: (user: AuthUser) => void
  onCancel: () => void
}

export function MfaSetup({ onAuthenticated, onCancel }: Props) {
  const [setup, setSetup] = useState<MfaSetupResponse | null>(null)
  const [setupError, setSetupError] = useState<string | null>(null)
  const [code, setCode] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [verifyError, setVerifyError] = useState<string | null>(null)
  const [showSecret, setShowSecret] = useState(false)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const res = await api.mfaSetup()
      if (cancelled) return
      if (res.ok) {
        setSetup(res.data)
      } else {
        setSetupError(res.message)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  async function onVerify(e: FormEvent) {
    e.preventDefault()
    if (code.replace(/\s/g, '').length !== 6) return
    setVerifyError(null)
    setSubmitting(true)
    const res = await api.mfaVerifySetup(code.replace(/\s/g, ''))
    setSubmitting(false)
    if (!res.ok) {
      setVerifyError(res.message)
      return
    }
    if (res.data.user) onAuthenticated(res.data.user)
  }

  return (
    <div className="login-page">
      <header className="page-header login-header">
        <h1>Set up two-factor authentication</h1>
        <p className="tagline">
          Required to protect access to patient information.
        </p>
      </header>

      <section className="card login-card" aria-label="MFA setup">
        {setupError && (
          <p className="error" role="alert">
            {setupError}
          </p>
        )}

        {setup && (
          <>
            <ol className="instructions">
              <li>
                Install an authenticator app such as <strong>Google
                Authenticator</strong>, <strong>1Password</strong>, or{' '}
                <strong>Authy</strong> on your phone.
              </li>
              <li>Scan the QR code below with the app.</li>
              <li>
                Enter the 6-digit code the app shows to finish enrollment.
              </li>
            </ol>

            <div className="qr-block">
              <div className="qr-canvas">
                <QRCodeSVG
                  value={setup.provisioning_uri}
                  size={196}
                  level="M"
                  includeMargin
                />
              </div>
              <button
                type="button"
                className="link"
                onClick={() => setShowSecret((s) => !s)}
              >
                {showSecret
                  ? 'Hide manual entry key'
                  : "Can't scan? Enter the key manually"}
              </button>
              {showSecret && (
                <div className="secret-block">
                  <code>{setup.secret}</code>
                  <p className="card-sub">
                    Account: {setup.account_name} · Issuer: {setup.issuer}
                  </p>
                </div>
              )}
            </div>

            <form onSubmit={onVerify} noValidate>
              <div className="field">
                <label htmlFor="setup-code">6-digit code from your app</label>
                <input
                  id="setup-code"
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

              {verifyError && (
                <p className="error" role="alert">
                  {verifyError}
                </p>
              )}

              <div className="actions actions-row">
                <button
                  type="submit"
                  className="primary"
                  disabled={submitting || code.replace(/\s/g, '').length !== 6}
                >
                  {submitting ? 'Verifying…' : 'Verify and finish'}
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
          </>
        )}
      </section>
    </div>
  )
}
