import { useEffect, useState } from 'react'
import { ChatForm } from './components/ChatForm'
import { ConversationCard } from './components/ConversationCard'
import { Login } from './components/Login'
import { MfaSetup } from './components/MfaSetup'
import { MfaChallenge } from './components/MfaChallenge'
import { PasswordResetRequest } from './components/PasswordResetRequest'
import { PasswordResetConfirm } from './components/PasswordResetConfirm'
import { Header } from './components/Header'
import { api } from './api'
import type { AuthStatus, AuthUser, ChatTurn, Turn } from './types'
import { MAX_CLIENT_HISTORY } from './types'
import {
  clearConversation as clearStoredConversation,
  loadConversation,
  saveConversation,
} from './conversationStore'
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

// Build the history payload the server expects from the visible
// turns. Skips the in-flight turn (it has no result yet) and skips
// turns whose result was an error. Caps to the last MAX_CLIENT_HISTORY.
function deriveHistoryFromTurns(turns: Turn[]): ChatTurn[] {
  const flat: ChatTurn[] = []
  for (const t of turns) {
    if (t.loading) continue
    if (!t.result) continue
    flat.push({ role: 'user', content: t.question })
    flat.push({ role: 'assistant', content: t.result.response })
  }
  return flat.slice(-MAX_CLIENT_HISTORY)
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
  // Visible transcript. Each entry is one user-question / agent-
  // response pair. The agent's reasoning over prior turns is what the
  // server reads via ChatRequest.history; the array here is what the
  // user sees on screen, so they can read the conversation back.
  const [turns, setTurns] = useState<Turn[]>([])

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
        // Restore any persisted conversation for the current patient.
        // Restoration is best-effort and silent; nothing to surface
        // if the saved data is stale or for a different patient.
        const saved = loadConversation()
        if (saved && saved.patientId) {
          setPatientId(saved.patientId)
          setTurns(saved.turns)
        }
      } else {
        setAuthStatus('unauthenticated')
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  // Persist the visible conversation on every change so a page
  // refresh during the demo doesn't lose context.
  useEffect(() => {
    if (authStatus !== 'authenticated') return
    saveConversation(patientId, turns)
  }, [authStatus, patientId, turns])

  function onAuthenticated(u: AuthUser) {
    setUser(u)
    setAuthStatus('authenticated')
    setSessionExpired(false)
    // Reset chat state on (re-)auth so a stale prior session doesn't
    // bleed into a fresh login.
    setTurns([])
    clearStoredConversation()
  }

  async function onLogout() {
    setLoggingOut(true)
    await api.logout()
    setLoggingOut(false)
    setUser(null)
    setAuthStatus('unauthenticated')
    setSessionExpired(false)
    setTurns([])
    clearStoredConversation()
  }

  // Patient changed → flush the visible conversation. Different
  // patient = different conversation; the patient-subject lock on
  // the server would refuse cross-patient memory anyway.
  function changePatient(next: string) {
    if (next === patientId) return
    setPatientId(next)
    setTurns([])
    clearStoredConversation()
  }

  function clearConversation() {
    setTurns([])
    clearStoredConversation()
  }

  async function ask() {
    const askedMessage = message.trim()
    if (!askedMessage) return

    const turnId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    const inFlightTurn: Turn = {
      id: turnId,
      question: askedMessage,
      result: null,
      elapsed: null,
      error: null,
      loading: true,
    }

    // Snapshot the history BEFORE we append the in-flight turn, so
    // we don't accidentally send the in-flight question as both the
    // current message AND a history entry.
    const historyPayload = deriveHistoryFromTurns(turns)

    setTurns((prev) => [...prev, inFlightTurn])

    const t0 = performance.now()
    const res = await api.chat(patientId, askedMessage, historyPayload)
    const elapsed = (performance.now() - t0) / 1000

    if (!res.ok) {
      // Session expired or revoked mid-use — bounce to login.
      if (res.status === 401) {
        setUser(null)
        setSessionExpired(true)
        setAuthStatus('unauthenticated')
        return
      }
      setTurns((prev) =>
        prev.map((t) =>
          t.id === turnId
            ? { ...t, loading: false, error: res.message, elapsed }
            : t,
        ),
      )
      return
    }

    setTurns((prev) =>
      prev.map((t) =>
        t.id === turnId
          ? { ...t, loading: false, result: res.data, elapsed }
          : t,
      ),
    )
  }

  function retryTurn(turnId: string) {
    const turn = turns.find((t) => t.id === turnId)
    if (!turn) return
    // Drop the failed turn, restore its question into the form, ask again.
    setMessage(turn.question)
    setTurns((prev) => prev.filter((t) => t.id !== turnId))
    void ask()
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

  const anyLoading = turns.some((t) => t.loading)
  const completedTurns = turns.filter((t) => t.result).length

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
            loading={anyLoading}
            onSubmit={ask}
            historyTurns={completedTurns}
            onClearConversation={
              turns.length > 0 ? clearConversation : undefined
            }
          />
        </aside>

        <section className="workspace-result">
          {turns.length === 0 ? (
            <div className="conversation-empty">
              <p className="placeholder">
                Pick a patient and ask a question to begin. The conversation
                stays on screen so you can follow up.
              </p>
            </div>
          ) : (
            // Render newest-first so the most recent question + answer
            // is at the top of the panel without scrolling. Underlying
            // `turns` array stays chronological — only the rendering is
            // reversed, so deriveHistoryFromTurns() (which builds the
            // server-side history payload) keeps its oldest-first
            // semantics that the LLM expects.
            <ol className="conversation-list">
              {[...turns].reverse().map((t) => (
                <li key={t.id}>
                  <ConversationCard
                    turn={t}
                    onRetry={() => retryTurn(t.id)}
                  />
                </li>
              ))}
            </ol>
          )}
        </section>
      </main>
    </div>
  )
}

export default App
