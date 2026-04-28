// API helpers. All requests include credentials so the session cookie rides along.

import type {
  AuthUser,
  ChatResponse,
  LoginResponse,
  MfaSetupResponse,
} from './types'

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<{ ok: true; data: T } | { ok: false; status: number; message: string }> {
  try {
    const res = await fetch(path, {
      ...options,
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...(options.headers ?? {}),
      },
    })
    if (!res.ok) {
      let message = `Request failed (HTTP ${res.status}).`
      try {
        const body = await res.json()
        if (body && typeof body.detail === 'string') message = body.detail
      } catch {
        /* non-JSON body */
      }
      return { ok: false, status: res.status, message }
    }
    const data = (await res.json()) as T
    return { ok: true, data }
  } catch (err) {
    return {
      ok: false,
      status: 0,
      message:
        'Could not reach the server. ' +
        (err instanceof Error ? err.message : String(err)),
    }
  }
}

export const api = {
  me: () => request<AuthUser>('/auth/me', { method: 'GET' }),
  login: (username: string, password: string) =>
    request<LoginResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
  logout: () => request<{ status: string }>('/auth/logout', { method: 'POST' }),
  mfaSetup: () =>
    request<MfaSetupResponse>('/auth/mfa/setup', {
      method: 'POST',
      body: '{}',
    }),
  mfaVerifySetup: (code: string) =>
    request<LoginResponse>('/auth/mfa/verify-setup', {
      method: 'POST',
      body: JSON.stringify({ code }),
    }),
  mfaChallenge: (code: string) =>
    request<LoginResponse>('/auth/mfa/challenge', {
      method: 'POST',
      body: JSON.stringify({ code }),
    }),
  chat: (patientId: string, message: string) =>
    request<ChatResponse>('/chat', {
      method: 'POST',
      body: JSON.stringify({ patient_id: patientId, message }),
    }),
}
