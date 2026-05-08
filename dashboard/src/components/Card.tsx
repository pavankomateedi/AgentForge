// Visual shell for each clinical card. Pure presentation; data + loader
// live in the specific card files.

import type { ReactNode } from 'react'

interface CardProps {
  title: string
  count?: number
  children: ReactNode
  action?: ReactNode
}

export function Card({ title, count, children, action }: CardProps) {
  return (
    <section className="card">
      <header className="card-header">
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
          <h3 className="card-title">{title}</h3>
          {typeof count === 'number' && <span className="card-count">{count}</span>}
        </div>
        {action}
      </header>
      <div className="card-body">{children}</div>
    </section>
  )
}

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return <p className="state-msg">{label}</p>
}

export function ErrorMsg({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="state-error">
      <p>{message}</p>
      {onRetry && (
        <button type="button" className="ghost" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  )
}

export function Empty({ label = 'No records.' }: { label?: string }) {
  return <p className="state-empty">{label}</p>
}
