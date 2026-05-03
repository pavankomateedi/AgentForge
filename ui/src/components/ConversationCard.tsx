// One render-able exchange in the visible transcript. Question bubble
// at top, then briefing + verification + rule findings (the technical
// trace card was removed — it's operator signal, not clinician
// signal). Loading and error states are scoped to the per-turn props
// so older turns stay rendered as you ask follow-ups.

import { BriefingCard } from './BriefingCard'
import { VerificationCard } from './VerificationCard'
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

      <div className="conversation-meta">
        <VerificationCard loading={turn.loading} result={turn.result} />
        <RuleFindingsCard loading={turn.loading} result={turn.result} />
      </div>
    </article>
  )
}
