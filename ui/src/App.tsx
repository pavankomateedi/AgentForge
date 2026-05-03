import { useEffect, useState } from 'react'
import { ChatForm } from './components/ChatForm'
import { BriefingCard } from './components/BriefingCard'
import { VerificationCard } from './components/VerificationCard'
import { RuleFindingsCard } from './components/RuleFindingsCard'
import { TraceCard } from './components/TraceCard'
import { Login } from './components/Login'
import { MfaSetup } from './components/MfaSetup'
import { MfaChallenge } from './components/MfaChallenge'
import { PasswordResetRequest } from './components/PasswordResetRequest'
import { PasswordResetConfirm } from './components/PasswordResetConfirm'
import { Header } from './components/Header'
import { api } from './api'
import type { AuthStatus, AuthUser, ChatResponse, ChatTurn } from './types'
import { MAX_CLIENT_HISTORY } from './types'
import './App.css'

function getResetTokenFromUrl(): string | null {
  if (typeof window === 'undefined') return null
  const params = new URLSearchParams(window.location.search)
  return params.get('reset_token')
}

function clearResetTokenFromUrl(): void {
  if (typeof window === 'undefined') return
  const url = new URL(window.location.href)
  url.searchParams.delete('reset_token')
  window.history.replaceState({}, '', url.toString())
}

function App() {
  // ---- Auth state ----
  const [authStatus, setAuthStatus] = useState<AuthStatus>('loading')
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loggingOut, setLoggingOut] = useState(false)
  const [resetToken, setResetToken] = useState<string | null>(null)
  const [sessionExpired, setSessionExpired] = useState(false)

  // ---- Chat state ----
  const [patientId, setPatientId] = useState('demo-001')
  const [message, setMessage] = useState('Brief me on this patient.')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<ChatResponse | null>(null)
  const [elapsed, setElapsed] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showResult, setShowResult] = useState(false)
  // Conversation history for follow-up coherence (UC-2 "what changed
  // since last visit?", UC-3 "is this trend concerning?"). Kept on
  // the client and resent on each /chat call. Clears when the patient
  // changes — different patient = different conversation.
  const [history, setHistory] = useState<ChatTurn[]>([])

  // On mount: check for a reset_token in the URL first, otherwise check session.
  useEffect(() => {
    const token = getResetTokenFromUrl()
    if (token) {
      setResetToken(token)
      setAuthStatus('password-reset-confirm')
      // Strip the token from the URL so a refresh / share doesn't re-trigger.
      clearResetTokenFromUrl()
      return
    }
    let cancelled = false
    ;(async () => {
      const res = await api.me()
      if (cancelled) return
      if (res.ok) {
        setUser(res.data)
        setAuthStatus('authenticated')
      } else {
        setAuthStatus('unauthenticated')
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  function onAuthenticated(u: AuthUser) {
    setUser(u)
    setAuthStatus('authenticated')
    setSessionExpired(false)
    // Reset any prior chat state in case this is a re-auth.
    setShowResult(false)
    setResult(null)
    setError(null)
    setHistory([])
  }

  async function onLogout() {
    setLoggingOut(true)
    await api.logout()
    setLoggingOut(false)
    setUser(null)
    setAuthStatus('unauthenticated')
    setSessionExpired(false)
    setShowResult(false)
    setResult(null)
    setError(null)
    setHistory([])
  }

  // Patient changed → flush history. Carrying turns about a different
  // patient into a new conversation would confuse the agent and is
  // exactly the kind of cross-patient leakage the patient-subject
  // lock exists to prevent.
  function changePatient(next: string) {
    if (next === patientId) return
    setPatientId(next)
    setHistory([])
    setShowResult(false)
    setResult(null)
    setError(null)
  }

  function clearConversation() {
    setHistory([])
    setShowResult(false)
    setResult(null)
    setError(null)
  }

  async function ask() {
    if (!message.trim()) return
    setLoading(true)
    setShowResult(true)
    setResult(null)
    setError(null)
    setElapsed(null)

    const askedMessage = message
    const t0 = performance.now()
    const res = await api.chat(patientId, askedMessage, history)
    setElapsed((performance.now() - t0) / 1000)
    setLoading(false)

    if (!res.ok) {
      // Session expired or revoked mid-use — bounce to login with a notice.
      if (res.status === 401) {
        setUser(null)
        setSessionExpired(true)
        setAuthStatus('unauthenticated')
        return
      }
      setError(res.message)
      return
    }
    setResult(res.data)
    // Append this turn to history, keeping only the tail. Stripping
    // trailing whitespace keeps the cost-vs-context tradeoff sane.
    setHistory((prev) => {
      const next: ChatTurn[] = [
        ...prev,
        { role: 'user', content: askedMessage.trim() },
        { role: 'assistant', content: res.data.response.trim() },
      ]
      return next.slice(-MAX_CLIENT_HISTORY)
    })
  }

  if (authStatus === 'loading') {
    return (
      <div className="app">
        <div className="splash" role="status" aria-label="Loading">
          <span className="dot" aria-hidden="true" />
          <span className="dot" aria-hidden="true" />
          <span className="dot" aria-hidden="true" />
        </div>
      </div>
    )
  }

  function onMfaRequired(action: 'enroll' | 'challenge') {
    setAuthStatus(action === 'enroll' ? 'mfa-enroll' : 'mfa-challenge')
  }

  async function onCancelMfa() {
    await api.logout()
    setUser(null)
    setAuthStatus('unauthenticated')
  }

  function onForgotPassword() {
    setAuthStatus('password-reset-request')
  }

  function onBackToLogin() {
    setResetToken(null)
    setAuthStatus('unauthenticated')
  }

  if (authStatus === 'unauthenticated') {
    return (
      <div className="app">
        <Login
          onAuthenticated={onAuthenticated}
          onMfaRequired={onMfaRequired}
          onForgotPassword={onForgotPassword}
          sessionExpired={sessionExpired}
          onDismissSessionExpired={() => setSessionExpired(false)}
        />
      </div>
    )
  }

  if (authStatus === 'mfa-enroll') {
    return (
      <div className="app">
        <MfaSetup onAuthenticated={onAuthenticated} onCancel={onCancelMfa} />
      </div>
    )
  }

  if (authStatus === 'mfa-challenge') {
    return (
      <div className="app">
        <MfaChallenge
          onAuthenticated={onAuthenticated}
          onCancel={onCancelMfa}
        />
      </div>
    )
  }

  if (authStatus === 'password-reset-request') {
    return (
      <div className="app">
        <PasswordResetRequest onBackToLogin={onBackToLogin} />
      </div>
    )
  }

  if (authStatus === 'password-reset-confirm' && resetToken) {
    return (
      <div className="app">
        <PasswordResetConfirm
          token={resetToken}
          onBackToLogin={onBackToLogin}
        />
      </div>
    )
  }

  if (!user) {
    // authenticated but user not loaded — should not happen, fall back to login.
    return (
      <div className="app">
        <Login
          onAuthenticated={onAuthenticated}
          onMfaRequired={onMfaRequired}
          onForgotPassword={onForgotPassword}
          sessionExpired={sessionExpired}
          onDismissSessionExpired={() => setSessionExpired(false)}
        />
      </div>
    )
  }

  // Once a result is in, the empty placeholders in the right-column
  // cards swap to populated content. Loading state is per-card so the
  // briefing card can show a thinking indicator while the meta cards
  // show "checking…" placeholders. Error in the briefing card; the
  // meta cards quietly stay placeholder.
  return (
    <div className="app workspace">
      <Header user={user} onLogout={onLogout} loggingOut={loggingOut} />

      <main className="workspace-grid">
        <aside className="workspace-form">
          <ChatForm
            patientId={patientId}
            setPatientId={changePatient}
            message={message}
            setMessage={setMessage}
            loading={loading}
            onSubmit={ask}
            historyTurns={history.length / 2}
            onClearConversation={
              history.length > 0 ? clearConversation : undefined
            }
          />
        </aside>

        <section className="workspace-result">
          <BriefingCard
            loading={loading}
            result={showResult ? result : null}
            elapsed={elapsed}
            error={showResult ? error : null}
            onRetry={!loading && showResult && error ? ask : undefined}
          />

          <div className="workspace-meta">
            <VerificationCard
              loading={loading}
              result={showResult ? result : null}
            />
            <RuleFindingsCard
              loading={loading}
              result={showResult ? result : null}
            />
            <TraceCard
              loading={loading}
              result={showResult ? result : null}
            />
          </div>
        </section>
      </main>
    </div>
  )
}

export default App
