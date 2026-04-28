// Mirrors the FastAPI ChatResponse + auth schemas in agent/.

export type Verification = {
  passed: boolean
  note: string
  cited_ids: string[]
  unknown_ids: string[]
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
  plan_tool_calls: ToolCall[]
  retrieved_source_ids: string[]
  verification: Verification | null
  refused: boolean
  refusal_reason: string
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
  user: AuthUser
  needs_mfa: boolean
}

export type AuthStatus = 'loading' | 'authenticated' | 'unauthenticated'
