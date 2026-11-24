import { useState } from 'react'
import type { FormEvent } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import { Alert } from '../components/Alert'
import { Button } from '../components/Button'
import { PageLoader } from '../components/Spinner'
import { TextField } from '../components/TextField'
import { getErrorMessage } from '../lib/errors'
import { getSafeReturnTo } from '../lib/navigation'

export function LoginPage() {
  const { status, error, login, retrySession } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const returnTo = getSafeReturnTo(searchParams.get('returnTo'))

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [formError, setFormError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  if (status === 'checking') {
    return <PageLoader message="Checking your session..." />
  }

  if (status === 'error') {
    return (
      <main className="centered-page">
        <div className="status-card">
          <p className="eyebrow">Connection problem</p>
          <h1>Unable to reach the CLM API</h1>
          <Alert variant="error">{error ?? 'The backend did not respond.'}</Alert>
          <p className="muted-text">
            Start the FastAPI backend on port 8000, then try again.
          </p>
          <Button onClick={retrySession}>Try again</Button>
        </div>
      </main>
    )
  }

  if (status === 'authenticated') {
    return <Navigate to={returnTo} replace />
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (isSubmitting) return
    setFormError(null)

    const trimmedEmail = email.trim()

    if (!trimmedEmail || !password) {
      setFormError('Enter your email address and password.')
      return
    }

    setIsSubmitting(true)

    try {
      await login(trimmedEmail, password)
      navigate(returnTo, { replace: true })
    } catch (caughtError) {
      setFormError(getErrorMessage(caughtError))
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <main className="login-page">
      <section className="login-brand" aria-labelledby="login-brand-title">
        <div className="login-brand__top">
          <span className="login-brand__mark" aria-hidden="true">
            CL
          </span>
          <span className="login-brand__name">CLM Workspace</span>
        </div>

        <div className="login-brand__content">
          <p className="eyebrow eyebrow--light">Legal operations</p>
          <h1 id="login-brand-title">
            Contracts, organized from first draft to final approval.
          </h1>
          <p>
            A secure workspace for contract intake, review, and approvals. This
            proof of concept currently provides authentication, the
            application shell, and contract metadata management.
          </p>
        </div>

        <ul className="login-brand__points">
          <li>
            <span aria-hidden="true">01</span>
            Server-side sessions with secure cookies
          </li>
          <li>
            <span aria-hidden="true">02</span>
            Role-aware access for legal teams
          </li>
          <li>
            <span aria-hidden="true">03</span>
            Ready to grow into contract workflows
          </li>
        </ul>
      </section>

      <section className="login-panel" aria-labelledby="login-title">
        <div className="login-card">
          <header className="login-card__header">
            <p className="eyebrow">Welcome back</p>
            <h2 id="login-title">Sign in to your workspace</h2>
            <p className="muted-text">
              Use the account created for you by an administrator.
            </p>
          </header>

          {formError && <Alert variant="error">{formError}</Alert>}

          <form className="login-form" onSubmit={handleSubmit} noValidate>
            <TextField
              label="Email address"
              type="email"
              name="email"
              value={email}
              onChange={(event) => {
                setEmail(event.target.value)
                if (formError) setFormError(null)
              }}
              autoComplete="email"
              inputMode="email"
              spellCheck={false}
              placeholder="you@example.com"
              disabled={isSubmitting}
              required
            />

            <TextField
              label="Password"
              type="password"
              name="password"
              value={password}
              onChange={(event) => {
                setPassword(event.target.value)
                if (formError) setFormError(null)
              }}
              autoComplete="current-password"
              placeholder="Enter your password"
              disabled={isSubmitting}
              required
            />

            <Button
              type="submit"
              className="login-form__submit"
              loading={isSubmitting}
            >
              {isSubmitting ? 'Signing in...' : 'Sign in'}
            </Button>
          </form>

          <p className="login-card__note">
            Public registration is disabled. Contact an administrator if you
            need access.
          </p>
        </div>
      </section>
    </main>
  )
}
