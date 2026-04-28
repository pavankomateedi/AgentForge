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
    <section className="card form-card">
      <div className="field">
        <label htmlFor="patient">Patient</label>
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
      </div>

      <div className="field">
        <label htmlFor="message">What would you like to know?</label>
        <textarea
          id="message"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={onKey}
          placeholder="Brief me on this patient."
          disabled={loading}
          rows={3}
        />
      </div>

      <div className="examples" aria-label="Example questions">
        {EXAMPLES.map((ex) => (
          <button
            key={ex.label}
            type="button"
            className="example"
            onClick={() => !loading && setMessage(ex.text)}
            disabled={loading}
          >
            {ex.label}
          </button>
        ))}
      </div>

      <div className="actions">
        <button
          type="button"
          className="primary"
          onClick={onSubmit}
          disabled={loading || !message.trim()}
        >
          {loading ? 'Thinking…' : 'Ask'}
        </button>
        <span className="hint">Ctrl/⌘ + Enter</span>
      </div>
    </section>
  )
}
