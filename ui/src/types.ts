// Mirrors the FastAPI ChatResponse + auth schemas in agent/.

export type ValueMismatch = {
  source_id: string
  cited_value: number
  record_value: number
}

export type Verification = {
  passed: boolean
  note: string
  cited_ids: string[]
  unknown_ids: string[]
  value_mismatches: ValueMismatch[]
}

export type ToolCall = {
  name: string
  input: Record<string, unknown>
}

export type Usage = {
  input_tokens: number
  output_tokens: number
  cache_creation_input_tokens: number
  cache_read_input_tokens: number
}

export type Trace = {
  trace_id: string
  plan_tool_calls: ToolCall[]
  retrieved_source_ids: string[]
  verification: Verification | null
  regenerated: boolean
  refused: boolean
  refusal_reason: string
  timings_ms: Record<string, number>
  usage: {
    plan: Usage
    reason: Usage
  }
}

export type ChatResponse = {
  response: string
  verified: boolean
  trace: Trace
}

export type Patient = {
  id: string
  label: string
}

export const PATIENTS: Patient[] = [
  { id: 'demo-001', label: 'Margaret Hayes' },
  { id: 'demo-002', label: 'James Whitaker' },
]

export const EXAMPLES: { label: string; text: string }[] = [
  { label: 'Brief me', text: 'Brief me on this patient.' },
  { label: 'Latest A1c?', text: 'What is the latest A1c result?' },
  { label: 'Current medications', text: 'What medications is the patient on?' },
  { label: 'Active conditions', text: 'What active conditions does the patient have?' },
]

// ---- Auth ----

export type AuthUser = {
  id: number
  username: string
  email: string
  role: string
  totp_enrolled: boolean
}

export type LoginResponse = {
  user: AuthUser | null
  needs_mfa: boolean
  mfa_action: 'enroll' | 'challenge' | null
}

export type MfaSetupResponse = {
  provisioning_uri: string
  secret: string
  issuer: string
  account_name: string
}

export type AuthStatus =
  | 'loading'
  | 'unauthenticated'
  | 'mfa-enroll'
  | 'mfa-challenge'
  | 'password-reset-request'
  | 'password-reset-confirm'
  | 'authenticated'
