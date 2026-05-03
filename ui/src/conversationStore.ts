// Persists the visible conversation across page refreshes. Keyed by
// a single localStorage entry so a refresh during the demo doesn't
// lose the prior turns the agent was reasoning about.
//
// Scope is intentionally narrow: only the most recent conversation
// for one patient. Loading restores only when the saved patient_id
// matches the current selection — switching patients flushes (the
// server's patient subject lock would refuse cross-patient memory
// anyway, but keeping the UI honest is the better story).

import type { Turn } from './types'

const KEY = 'agent-forge.conversation.v1'

type Saved = {
  patientId: string
  turns: Turn[]
}

function isBrowser(): boolean {
  return typeof window !== 'undefined' && typeof window.localStorage !== 'undefined'
}

export function loadConversation(): Saved | null {
  if (!isBrowser()) return null
  try {
    const raw = window.localStorage.getItem(KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Saved
    if (
      typeof parsed?.patientId !== 'string' ||
      !Array.isArray(parsed?.turns)
    ) {
      return null
    }
    // Defensive: drop any turns marked loading=true at save time —
    // they were in flight when the page closed and will never
    // resolve. The user can re-ask if needed.
    parsed.turns = parsed.turns.filter((t) => !t.loading)
    return parsed
  } catch {
    return null
  }
}

export function saveConversation(patientId: string, turns: Turn[]): void {
  if (!isBrowser()) return
  // Drop in-flight turns so a refresh-while-loading restores cleanly.
  const cleaned = turns.filter((t) => !t.loading)
  if (cleaned.length === 0) {
    window.localStorage.removeItem(KEY)
    return
  }
  try {
    window.localStorage.setItem(
      KEY,
      JSON.stringify({ patientId, turns: cleaned } satisfies Saved),
    )
  } catch {
    // Quota exceeded or storage disabled — silently ignore.
  }
}

export function clearConversation(): void {
  if (!isBrowser()) return
  try {
    window.localStorage.removeItem(KEY)
  } catch {
    /* noop */
  }
}
