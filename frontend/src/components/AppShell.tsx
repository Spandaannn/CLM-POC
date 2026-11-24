import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import { getErrorMessage } from '../lib/errors'
import { formatRole, getInitials } from '../lib/format'
import { Alert } from './Alert'
import { Button } from './Button'

/**
 * Layout for signed-in pages: brand, navigation, current user, and sign out.
 * The user object is guaranteed by RequireAuth, but we still guard for null.
 */
export function AppShell() {
  const { user, logout } = useAuth()
  const [isSigningOut, setIsSigningOut] = useState(false)
  const [logoutError, setLogoutError] = useState<string | null>(null)

  async function handleSignOut() {
    setIsSigningOut(true)
    setLogoutError(null)

    try {
      await logout()
    } catch (error) {
      setLogoutError(getErrorMessage(error))
    } finally {
      setIsSigningOut(false)
    }
  }

  if (!user) return null

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>

      <header className="app-header">
        <div className="app-header__inner">
          <NavLink to="/dashboard" className="app-brand">
            <span className="app-brand__mark" aria-hidden="true">
              CL
            </span>
            <span className="app-brand__text">
              <strong>CLM Workspace</strong>
              <small>Contract Lifecycle Management</small>
            </span>
          </NavLink>

          <nav className="app-nav" aria-label="Main navigation">
            <NavLink
              to="/dashboard"
              className={({ isActive }) =>
                `app-nav__link${isActive ? ' app-nav__link--active' : ''}`
              }
            >
              Dashboard
            </NavLink>
            <NavLink
              to="/contracts"
              className={({ isActive }) =>
                `app-nav__link${isActive ? ' app-nav__link--active' : ''}`
              }
            >
              Contracts
            </NavLink>
          </nav>

          <div className="app-user">
            <span className="avatar" aria-hidden="true">
              {getInitials(user.full_name)}
            </span>
            <span className="app-user__details">
              <strong>{user.full_name}</strong>
              <small>{formatRole(user.role)}</small>
            </span>
            <Button
              variant="secondary"
              onClick={handleSignOut}
              loading={isSigningOut}
            >
              {isSigningOut ? 'Signing out...' : 'Sign out'}
            </Button>
          </div>
        </div>

        {logoutError && (
          <div className="app-header__alert">
            <Alert variant="error">
              Could not sign out: {logoutError}
            </Alert>
          </div>
        )}
      </header>

      <main id="main-content" className="app-main">
        <Outlet />
      </main>

      <footer className="app-footer">
        <p>
          CLM POC · Session-based authentication · Contract metadata management
          · Documents, reviews, and approvals are not implemented yet.
        </p>
      </footer>
    </div>
  )
}
