import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import {
  getCurrentUser,
  login as loginRequest,
  logout as logoutRequest,
} from '../api/auth'
import type { User } from '../api/types'
import { ApiError, getErrorMessage } from '../lib/errors'
import { AuthContext } from './authContext'
import type { AuthStatus } from './authContext'

/**
 * Holds the current user and restores the session from the HttpOnly cookie.
 *
 * On first load we call GET /api/auth/me. A 401/403 means "not signed in";
 * other failures (network, 5xx) surface as a retryable error instead of
 * pretending the user is logged out.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('checking')
  const [user, setUser] = useState<User | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [sessionCheckId, setSessionCheckId] = useState(0)

  useEffect(() => {
    let cancelled = false

    getCurrentUser()
      .then((currentUser) => {
        if (cancelled) return
        setUser(currentUser)
        setStatus('authenticated')
      })
      .catch((caughtError: unknown) => {
        if (cancelled) return

        setUser(null)

        if (
          caughtError instanceof ApiError &&
          (caughtError.status === 401 || caughtError.status === 403)
        ) {
          setStatus('anonymous')
          return
        }

        setError(getErrorMessage(caughtError))
        setStatus('error')
      })

    return () => {
      cancelled = true
    }
  }, [sessionCheckId])

  const login = useCallback(async (email: string, password: string) => {
    const result = await loginRequest({ email, password })
    setUser(result.user)
    setError(null)
    setStatus('authenticated')
  }, [])

  const logout = useCallback(async () => {
    // If this throws, the caller keeps the current user state and can retry.
    await logoutRequest()
    setUser(null)
    setError(null)
    setStatus('anonymous')
  }, [])

  const retrySession = useCallback(() => {
    // Reset here (an event handler) rather than synchronously inside the effect.
    setStatus('checking')
    setError(null)
    setSessionCheckId((current) => current + 1)
  }, [])

  const value = useMemo(
    () => ({ status, user, error, login, logout, retrySession }),
    [status, user, error, login, logout, retrySession],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
