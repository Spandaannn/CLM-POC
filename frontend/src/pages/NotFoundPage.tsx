import { Link } from 'react-router-dom'

export function NotFoundPage() {
  return (
    <main className="centered-page">
      <div className="status-card">
        <p className="eyebrow">404</p>
        <h1>Page not found</h1>
        <p className="muted-text">
          The page you requested does not exist in this workspace.
        </p>
        <Link className="text-link" to="/dashboard">
          Go to the dashboard
        </Link>
      </div>
    </main>
  )
}
