// API helpers. All requests include credentials so the session cookie rides along.

import type {
  AuthUser,
  ChatResponse,
  ChatTurn,
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
  passwordResetRequest: (email: string) =>
    request<{ status: string }>('/auth/password-reset/request', {
      method: 'POST',
      body: JSON.stringify({ email }),
    }),
  passwordResetConfirm: (token: string, newPassword: string) =>
    request<{ status: string }>('/auth/password-reset/confirm', {
      method: 'POST',
      body: JSON.stringify({ token, new_password: newPassword }),
    }),
  chat: (
    patientId: string,
    message: string,
    history: ChatTurn[] = [],
    multiAgent: boolean = true,
  ) =>
    request<ChatResponse>('/chat', {
      method: 'POST',
      body: JSON.stringify({
        patient_id: patientId,
        message,
        history,
        multi_agent: multiAgent,
      }),
    }),

  // ---- Documents (Week 2 multimodal) ----
  listDocuments: (patientId: string) =>
    request<{
      patient_id: string
      documents: DocumentMeta[]
    }>(`/documents/list?patient_id=${encodeURIComponent(patientId)}`),

  uploadDocument: async (
    patientId: string,
    docType: 'lab_pdf' | 'intake_form',
    file: File,
  ): Promise<
    | { ok: true; data: UploadResp }
    | { ok: false; status: number; message: string }
  > => {
    const form = new FormData()
    form.append('patient_id', patientId)
    form.append('doc_type', docType)
    form.append('file', file)
    try {
      const res = await fetch('/documents/upload', {
        method: 'POST',
        credentials: 'include',
        body: form,
      })
      if (!res.ok) {
        let message = `Upload failed (HTTP ${res.status}).`
        try {
          const body = await res.json()
          if (body && typeof body.detail === 'string') message = body.detail
        } catch {
          /* non-JSON */
        }
        return { ok: false, status: res.status, message }
      }
      const data = (await res.json()) as UploadResp
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
  },

  documentBlobUrl: (documentId: number) => `/documents/${documentId}/blob`,

  documentDerived: (documentId: number) =>
    request<{
      document_id: number
      extraction_status: string
      extraction_error: string | null
      rows: DerivedObservation[]
    }>(`/documents/${documentId}/derived`),
}

// ---- Documents-related types kept here so api callers don't need
// to reach into types.ts for them. ----

export type DocumentMeta = {
  id: number
  doc_type: 'lab_pdf' | 'intake_form'
  content_type: string
  uploaded_at: string
  extraction_status: 'pending' | 'extracting' | 'done' | 'failed'
  extraction_error: string | null
  uploaded_by_user_id: number
  file_hash: string
}

export type UploadResp = {
  document_id: number
  status: 'pending' | 'extracting' | 'done' | 'failed'
  deduplicated: boolean
}

export type DerivedObservation = {
  id: number
  document_id: number
  source_id: string
  schema_kind: string
  payload: Record<string, unknown>
  confidence: number | null
  page_number: number | null
  bbox: { x0: number; y0: number; x1: number; y1: number } | null
  created_at: string
}
