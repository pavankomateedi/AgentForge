import type { AuthUser } from '../types'

type Props = {
  user: AuthUser
  onLogout: () => void
  loggingOut: boolean
}

export function Header({ user, onLogout, loggingOut }: Props) {
  const display = user.username
  return (
    <header className="page-header app-header">
      <div className="page-header-text">
        <h1>Clinical Co-Pilot</h1>
        <p className="tagline">Pre-visit briefings, grounded in the chart.</p>
      </div>
      <div className="user-block">
        <a
          href="/dashboard/"
          className="ghost cross-app-link"
          aria-label="Open OpenEMR Patient Dashboard"
          title="Open the OpenEMR Patient Dashboard surprise-challenge port"
        >
          Patient Dashboard →
        </a>
        <span className="user-info" title={user.email}>
          {display}
        </span>
        <button
          type="button"
          className="ghost"
          onClick={onLogout}
          disabled={loggingOut}
          aria-label="Sign out"
        >
          {loggingOut ? 'Signing out…' : 'Sign out'}
        </button>
      </div>
    </header>
  )
}
