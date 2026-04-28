import { useState } from 'react'
import { ChatForm } from './components/ChatForm'
import { ResponsePanel } from './components/ResponsePanel'
import type { ChatResponse } from './types'
import './App.css'

function App() {
  const [patientId, setPatientId] = useState('demo-001')
  const [message, setMessage] = useState('Brief me on this patient.')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<ChatResponse | null>(null)
  const [elapsed, setElapsed] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showResult, setShowResult] = useState(false)

  async function ask() {
    if (!message.trim()) return
    setLoading(true)
    setShowResult(true)
    setResult(null)
    setError(null)
    setElapsed(null)

    const t0 = performance.now()
    try {
      const res = await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ patient_id: patientId, message }),
      })
      const elapsedSec = (performance.now() - t0) / 1000
      setElapsed(elapsedSec)

      if (!res.ok) {
        setError(`The server returned an error (HTTP ${res.status}).`)
        return
      }
      const data: ChatResponse = await res.json()
      setResult(data)
    } catch (err) {
      setError(
        'Could not reach the server. ' +
          (err instanceof Error ? err.message : String(err)),
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="app">
      <header className="page-header">
        <h1>Clinical Co-Pilot</h1>
        <p className="tagline">Pre-visit briefings, grounded in the chart.</p>
      </header>

      <main>
        <ChatForm
          patientId={patientId}
          setPatientId={setPatientId}
          message={message}
          setMessage={setMessage}
          loading={loading}
          onSubmit={ask}
        />

        {showResult && (
          <ResponsePanel
            loading={loading}
            result={result}
            elapsed={elapsed}
            error={error}
          />
        )}
      </main>
    </div>
  )
}

export default App
