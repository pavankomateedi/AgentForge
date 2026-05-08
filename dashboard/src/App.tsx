import { Routes, Route, Navigate } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useAuth } from './auth/useAuth'
import { AuthGuard } from './auth/AuthGuard'
import { FhirProvider } from './fhir/FhirProvider'
import Login from './pages/Login'
import OAuthCallback from './pages/OAuthCallback'
import Home from './pages/Home'
import PatientView from './pages/PatientView'

function TopBar() {
  const { accessToken, signOut } = useAuth()
  return (
    <header className="app-topbar">
      <h1>OpenEMR Patient Dashboard</h1>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <span className="who">{accessToken ? 'Signed in' : 'Not signed in'}</span>
        {accessToken && (
          <button type="button" className="ghost" onClick={signOut}>
            Sign out
          </button>
        )}
      </div>
    </header>
  )
}

// Wraps any route that needs both an access token AND a configured FhirClient.
function Protected({ children }: { children: ReactNode }) {
  return (
    <AuthGuard>
      <FhirProvider>{children}</FhirProvider>
    </AuthGuard>
  )
}

export default function App() {
  return (
    <div className="app-shell">
      <TopBar />
      <main className="app-main">
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/oauth/callback" element={<OAuthCallback />} />
          <Route path="/" element={<Protected><Home /></Protected>} />
          <Route path="/patients/:id" element={<Protected><PatientView /></Protected>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}
