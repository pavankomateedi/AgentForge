// OAuth2 Authorization Code + PKCE flow against OpenEMR.
//
// startLogin() — kicks off the redirect to OpenEMR's /authorize endpoint.
// handleCallback() — runs on /oauth/callback, exchanges code for an access
// token, validates the state parameter, returns the token + suggested redirect
// path. No refresh-token rotation: when access_token expires the user re-auths.

import { config } from '../config'
import { deriveCodeChallenge, generateCodeVerifier, generateState } from './pkce'
import {
  popPkceVerifier,
  popPostLoginRedirect,
  popState,
  savePkceVerifier,
  saveState,
  saveToken,
} from './storage'

export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
  scope?: string
  refresh_token?: string
  id_token?: string
}

export async function startLogin(returnTo?: string): Promise<void> {
  const verifier = generateCodeVerifier()
  const challenge = await deriveCodeChallenge(verifier)
  const state = generateState()

  savePkceVerifier(verifier)
  saveState(state)
  if (returnTo) {
    sessionStorage.setItem('dashboard.post_login_redirect', returnTo)
  }

  const url = new URL(config.oauthAuthorizeUrl)
  url.searchParams.set('response_type', 'code')
  url.searchParams.set('client_id', config.oauthClientId)
  url.searchParams.set('redirect_uri', config.oauthRedirectUri)
  url.searchParams.set('scope', config.oauthScopes)
  url.searchParams.set('state', state)
  url.searchParams.set('code_challenge', challenge)
  url.searchParams.set('code_challenge_method', 'S256')

  window.location.assign(url.toString())
}

export interface CallbackResult {
  accessToken: string
  expiresIn: number
  redirectTo: string
}

export async function handleCallback(searchParams: URLSearchParams): Promise<CallbackResult> {
  const error = searchParams.get('error')
  if (error) {
    const desc = searchParams.get('error_description') ?? 'OAuth provider returned an error.'
    throw new Error(`${error}: ${desc}`)
  }

  const code = searchParams.get('code')
  const returnedState = searchParams.get('state')
  if (!code) throw new Error('Missing authorization code in callback URL.')

  const expectedState = popState()
  if (!expectedState || expectedState !== returnedState) {
    throw new Error('OAuth state mismatch. Possible CSRF; please log in again.')
  }

  const verifier = popPkceVerifier()
  if (!verifier) {
    throw new Error('PKCE verifier missing from session. Please restart login.')
  }

  const body = new URLSearchParams()
  body.set('grant_type', 'authorization_code')
  body.set('code', code)
  body.set('redirect_uri', config.oauthRedirectUri)
  body.set('client_id', config.oauthClientId)
  body.set('code_verifier', verifier)

  const res = await fetch(config.oauthTokenUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      Accept: 'application/json',
    },
    body: body.toString(),
  })

  const text = await res.text()
  let parsed: unknown = null
  if (text) {
    try {
      parsed = JSON.parse(text)
    } catch {
      // Some token endpoints return form-encoded errors; surface raw text.
    }
  }

  if (!res.ok) {
    const message =
      parsed && typeof parsed === 'object'
        ? (parsed as { error_description?: string; error?: string }).error_description ??
          (parsed as { error?: string }).error ??
          `Token exchange failed (${res.status})`
        : `Token exchange failed (${res.status}): ${text}`
    throw new Error(message)
  }

  const token = parsed as TokenResponse
  if (!token.access_token || !token.expires_in) {
    throw new Error('Token response missing access_token or expires_in.')
  }

  saveToken(token.access_token, token.expires_in)
  return {
    accessToken: token.access_token,
    expiresIn: token.expires_in,
    redirectTo: popPostLoginRedirect() ?? '/',
  }
}
