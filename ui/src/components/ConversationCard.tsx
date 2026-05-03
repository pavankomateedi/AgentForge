// One render-able exchange in the visible transcript. Question bubble
// + briefing + rule findings. The verification and trace cards were
// removed — both are operator signal, not clinician signal. The
// clinician's verification cue is the green checkmark badge in the
// BriefingCard header; the trace and verifier-detail counts still
// run server-side and live in the audit log + Langfuse for ops use.
// Loading and error states are scoped to the per-turn props so older
// turns stay rendered as you ask follow-ups.

import { BriefingCard } from './BriefingCard'
import { RuleFindingsCard } from './RuleFindingsCard'
import type { Turn } from '../types'

type Props = {
  turn: Turn
  onRetry?: () => void
}

export function ConversationCard({ turn, onRetry }: Props) {
  return (
    <article className="conversation-turn" aria-label="Conversation turn">
      <div className="user-bubble" aria-label="Your question">
        <span className="user-bubble-label">You</span>
        <p className="user-bubble-text">{turn.question}</p>
      </div>

      <BriefingCard
        loading={turn.loading}
        result={turn.result}
        elapsed={turn.elapsed}
        error={turn.error}
        onRetry={turn.error && !turn.loading ? onRetry : undefined}
      />

      <RuleFindingsCard loading={turn.loading} result={turn.result} />
    </article>
  )
}
