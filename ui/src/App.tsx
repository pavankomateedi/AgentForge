import { useEffect, useState } from 'react'
import { ChatForm } from './components/ChatForm'
import { ResponsePanel } from './components/ResponsePanel'
import { Login } from './components/Login'
import { MfaSetup } from './components/MfaSetup'
import { MfaChallenge } from './components/MfaChallenge'
import { Header } from './components/Header'
import { api } from './api'
import type { AuthStatus, AuthUser, ChatResponse } from './types'
import './App.css'

function App() {
  // ---- Auth state ----
  const [authStatus, setAuthStatus] = useState<AuthStatus>('loading')
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loggingOut, setLoggingOut] = useState(false)

  // ---- Chat state ----
  const [patientId, setPatientId] = useState('demo-001')
  const [message, setMessage] = useState('Brief me on this patient.')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<ChatResponse | null>(null)
  const [elapsed, setElapsed] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showResult, setShowResult] = useState(false)

  // On mount: check existing session.
  useEffect(() => {
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
    // Reset any prior chat state in case this is a re-auth.
    setShowResult(false)
    setResult(null)
    setError(null)
  }

  async function onLogout() {
    setLoggingOut(true)
    await api.logout()
    setLoggingOut(false)
    setUser(null)
    setAuthStatus('unauthenticated')
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

    const t0 = performance.now()
    const res = await api.chat(patientId, message)
    setElapsed((performance.now() - t0) / 1000)
    setLoading(false)

    if (!res.ok) {
      // Session expired or revoked mid-use — bounce to login.
      if (res.status === 401) {
        setUser(null)
        setAuthStatus('unauthenticated')
        return
      }
      setError(res.message)
      return
    }
    setResult(res.data)
  }

  if (authStatus === 'loading') {
    return (
      <div className="app">
        <div className="splash">
          <span className="dot" />
          <span className="dot" />
          <span className="dot" />
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

  if (authStatus === 'unauthenticated') {
    return (
      <div className="app">
        <Login
          onAuthenticated={onAuthenticated}
          onMfaRequired={onMfaRequired}
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

  if (!user) {
    // authenticated but user not loaded — should not happen, fall back to login.
    return (
      <div className="app">
        <Login
          onAuthenticated={onAuthenticated}
          onMfaRequired={onMfaRequired}
        />
      </div>
    )
  }

  return (
    <div className="app">
      <Header user={user} onLogout={onLogout} loggingOut={loggingOut} />

      <main>
        <ChatForm
          patientId={patientId}
          setPatientId={setPatientId}
          message={message}
          setMessage={setMessage}
          loading={loading}
          onSubmit={ask}
        />

        {showResult && (
          <ResponsePanel
            loading={loading}
            result={result}
            elapsed={elapsed}
            error={error}
          />
        )}
      </main>
    </div>
  )
}

export default App
