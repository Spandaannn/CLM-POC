import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { Alert } from '../components/Alert'
import { Button } from '../components/Button'
import { PageLoader } from '../components/Spinner'
import { useAuth } from './useAuth'

/**
 * Protects every child route.
 *
 * - While the session is being checked, show a loader.
 * - If the API cannot be reached, show a retryable error.
 * - If the user is signed out, redirect to /login and remember the target.
 */
export function RequireAuth() {
  const { status, error, retrySession } = useAuth()
  const location = useLocation()

  if (status === 'checking') {
    return <PageLoader message="Checking your session..." />
  }

  if (status === 'error') {
    return (
      <main className="centered-page">
        <div className="status-card">
          <p className="eyebrow">Connection problem</p>
          <h1>Unable to check your session</h1>
          <Alert variant="error">
            {error ?? 'The backend did not respond.'}
          </Alert>
          <p className="muted-text">
            Make sure the FastAPI backend is running on port 8000, then try
            again.
          </p>
          <Button onClick={retrySession}>Try again</Button>
        </div>
      </main>
    )
  }

  if (status === 'anonymous') {
    const returnTo = `${location.pathname}${location.search}`
    const loginUrl =
      returnTo && returnTo !== '/'
        ? `/login?returnTo=${encodeURIComponent(returnTo)}`
        : '/login'

    return <Navigate to={loginUrl} replace />
  }

  return <Outlet />
}
