import { useState } from 'react'
import { ChatForm } from './components/ChatForm'
import { ResponsePanel } from './components/ResponsePanel'
import type { ChatResponse } from './types'
import './App.css'

function App() {
  const [patientId, setPatientId] = useState('demo-001')
  const [message, setMessage] = useState('brief me')
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
        setError(`HTTP ${res.status} — see server logs`)
        return
      }
      const data: ChatResponse = await res.json()
      setResult(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="app">
      <header>
        <h1>Clinical Co-Pilot — v0 Demo</h1>
        <p className="subtitle">
          AgentForge Week 1 · Mock FHIR · Two synthetic patients · Claude Opus 4.7
        </p>
      </header>

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
    </div>
  )
}

export default App
