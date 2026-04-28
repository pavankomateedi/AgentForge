import { type KeyboardEvent } from 'react'
import { EXAMPLES, PATIENTS } from '../types'

type Props = {
  patientId: string
  setPatientId: (id: string) => void
  message: string
  setMessage: (msg: string) => void
  loading: boolean
  onSubmit: () => void
}

export function ChatForm({
  patientId,
  setPatientId,
  message,
  setMessage,
  loading,
  onSubmit,
}: Props) {
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault()
      onSubmit()
    }
  }

  return (
    <div className="card">
      <label htmlFor="patient">Patient (locked for the conversation)</label>
      <select
        id="patient"
        value={patientId}
        onChange={(e) => setPatientId(e.target.value)}
        disabled={loading}
      >
        {PATIENTS.map((p) => (
          <option key={p.id} value={p.id}>
            {p.label}
          </option>
        ))}
      </select>

      <label htmlFor="message" style={{ marginTop: 16 }}>
        Your question
      </label>
      <textarea
        id="message"
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        onKeyDown={onKey}
        placeholder="brief me"
        disabled={loading}
      />
      <div className="examples">
        {EXAMPLES.map((ex) => (
          <span
            key={ex.label}
            className="example"
            onClick={() => !loading && setMessage(ex.text)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault()
                if (!loading) setMessage(ex.text)
              }
            }}
          >
            {ex.label}
          </span>
        ))}
      </div>

      <button
        type="button"
        onClick={onSubmit}
        disabled={loading || !message.trim()}
      >
        {loading ? 'Thinking…' : 'Ask'}
      </button>
      <span className="hint">Ctrl/⌘+Enter to submit</span>
    </div>
  )
}
