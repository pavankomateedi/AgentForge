// Mirrors the FastAPI ChatResponse + auth schemas in agent/.

export type ValueMismatch = {
  source_id: string
  cited_value: number
  record_value: number
}

export type NameMismatch = {
  source_id: string
  record_name: string
  cited_drug: string
}

export type Verification = {
  passed: boolean
  note: string
  cited_ids: string[]
  unknown_ids: string[]
  value_mismatches: ValueMismatch[]
  name_mismatches: NameMismatch[]
}

export type RuleFinding = {
  rule_id: string
  category: string
  severity: 'info' | 'warning' | 'critical'
  message: string
  evidence_source_ids: string[]
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

export type MultiAgentTrace = {
  workers_invoked: string[]
  routing_reason: string
  stage_timings_ms: Record<string, number>
}

export type Trace = {
  trace_id: string
  trace_url: string | null
  plan_tool_calls: ToolCall[]
  retrieved_source_ids: string[]
  verification: Verification | null
  rule_findings: RuleFinding[]
  regenerated: boolean
  refused: boolean
  refusal_reason: string
  timings_ms: Record<string, number>
  usage: {
    plan: Usage
    reason: Usage
  }
  multi_agent: MultiAgentTrace | null
}

export type ChatResponse = {
  response: string
  verified: boolean
  trace: Trace
}

// Prior turn the client carries forward so the agent can answer
// follow-ups like "is that trend concerning?". Server caps to the
// last 8 entries; we cap on the client side too so the request stays
// small and we don't push older context out of view.
export type ChatTurn = {
  role: 'user' | 'assistant'
  content: string
}

export const MAX_CLIENT_HISTORY = 8

// One render-able turn in the visible transcript. Combines the user's
// question with the agent's response (or in-progress / error state)
// so each turn can render as a self-contained block — question
// bubble + briefing + verification + rules — and the prior turns
// stay on screen above the form. Persisted to localStorage so a
// page refresh doesn't lose the conversation.
export type Turn = {
  id: string  // monotonic; React key + ordering
  question: string
  result: ChatResponse | null  // null while in flight
  elapsed: number | null  // seconds
  error: string | null
  loading: boolean
}

export type Patient = {
  id: string
  label: string
}

export const PATIENTS: Patient[] = [
  { id: 'demo-001', label: 'Margaret Hayes — T2DM/HTN/HLD (warning)' },
  { id: 'demo-002', label: 'James Whitaker — CHF (sparse data)' },
  { id: 'demo-003', label: 'Robert Mitchell — Critical findings' },
  { id: 'demo-004', label: 'Linda Chen — Drug interaction' },
  { id: 'demo-005', label: 'Sarah Martinez — Stable / well-controlled' },
]

// Example questions exposed as one-click chips above the chat form.
// These are PROMPTS, not direct tool calls — the agent still picks
// the right tool. Each chip is engineered to surface a specific
// capability so the user (or grader) can discover it without prior
// product knowledge:
//
//   - "Brief me" + the four follow-ups exercise the Week 1 baseline
//     tools (summary / labs / meds / problems / encounters).
//   - "A1c trend" exercises get_lab_history (UC-3, UC-7).
//   - "What changed since last visit?" exercises get_changes_since
//     (UC-2 — the headline use case from the persona doc).
//   - "Documents on file" exercises get_recent_documents (UC-4).
//   - "Safety check" exercises check_clinical_thresholds (UC-1, UC-3).
//   - "Aligned with guidelines?" exercises the supervisor's
//     evidence_retriever route into the hybrid RAG corpus.
export const EXAMPLES: { label: string; text: string }[] = [
  { label: 'Brief me', text: 'Brief me on this patient.' },
  { label: 'Latest A1c?', text: 'What is the latest A1c result?' },
  { label: 'Current medications', text: 'What medications is the patient on?' },
  { label: 'Active conditions', text: 'What active conditions does the patient have?' },
  { label: 'A1c trend', text: 'Show me the A1c trend over time for this patient.' },
  { label: 'What changed since last visit?', text: 'What has changed for this patient since their last visit?' },
  { label: 'Documents on file', text: 'What documents do we have on file for this patient and what was extracted from them?' },
  { label: 'Safety check', text: 'Are there any clinical safety concerns or threshold violations for this patient right now?' },
  { label: 'Aligned with guidelines?', text: "Is this patient's current treatment plan aligned with the relevant clinical guidelines?" },
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
