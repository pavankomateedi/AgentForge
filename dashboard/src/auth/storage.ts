// Token + PKCE state storage in sessionStorage. Tokens stay scoped to the
// browser tab and are cleared on tab close — this is the simplest model
// for a behind-OAuth clinical SPA without persistent login state.

const TOKEN_KEY = 'dashboard.access_token'
const TOKEN_EXPIRES_KEY = 'dashboard.access_token_expires_at'
const PKCE_VERIFIER_KEY = 'dashboard.pkce_verifier'
const STATE_KEY = 'dashboard.oauth_state'
const POST_LOGIN_REDIRECT_KEY = 'dashboard.post_login_redirect'
const PATIENT_CONTEXT_KEY = 'dashboard.patient_context'

export interface StoredToken {
  accessToken: string
  expiresAt: number // ms epoch
}

export function saveToken(accessToken: string, expiresInSec: number): void {
  const expiresAt = Date.now() + expiresInSec * 1000
  sessionStorage.setItem(TOKEN_KEY, accessToken)
  sessionStorage.setItem(TOKEN_EXPIRES_KEY, String(expiresAt))
}

export function readToken(): StoredToken | null {
  const t = sessionStorage.getItem(TOKEN_KEY)
  const e = sessionStorage.getItem(TOKEN_EXPIRES_KEY)
  if (!t || !e) return null
  const expiresAt = Number(e)
  if (!Number.isFinite(expiresAt) || expiresAt <= Date.now()) {
    clearToken()
    return null
  }
  return { accessToken: t, expiresAt }
}

export function clearToken(): void {
  sessionStorage.removeItem(TOKEN_KEY)
  sessionStorage.removeItem(TOKEN_EXPIRES_KEY)
  sessionStorage.removeItem(PATIENT_CONTEXT_KEY)
}

export function savePatientContext(patientId: string): void {
  sessionStorage.setItem(PATIENT_CONTEXT_KEY, patientId)
}
export function readPatientContext(): string | null {
  return sessionStorage.getItem(PATIENT_CONTEXT_KEY)
}

export function savePkceVerifier(verifier: string): void {
  sessionStorage.setItem(PKCE_VERIFIER_KEY, verifier)
}
export function popPkceVerifier(): string | null {
  const v = sessionStorage.getItem(PKCE_VERIFIER_KEY)
  if (v !== null) sessionStorage.removeItem(PKCE_VERIFIER_KEY)
  return v
}

export function saveState(state: string): void {
  sessionStorage.setItem(STATE_KEY, state)
}
export function popState(): string | null {
  const s = sessionStorage.getItem(STATE_KEY)
  if (s !== null) sessionStorage.removeItem(STATE_KEY)
  return s
}

export function savePostLoginRedirect(path: string): void {
  sessionStorage.setItem(POST_LOGIN_REDIRECT_KEY, path)
}
export function popPostLoginRedirect(): string | null {
  const p = sessionStorage.getItem(POST_LOGIN_REDIRECT_KEY)
  if (p !== null) sessionStorage.removeItem(POST_LOGIN_REDIRECT_KEY)
  return p
}
