import { ApiError } from '../lib/errors'
import { apiRequest } from './client'
import type { CsrfTokenResponse } from './types'

/**
 * CSRF handling shared by every state-changing API call.
 *
 * 1. GET /api/auth/csrf sets a readable `clm_csrf` cookie and returns the
 *    same value in the JSON body.
 * 2. Mutating requests send that value in the `X-CSRF-Token` header.
 * 3. Login rotates the token, so auth.ts stores the new value here.
 *
 * The token is intentionally kept in a module variable only. It is never
 * written to localStorage or sessionStorage.
 */
let csrfToken: string | null = null
let pendingCsrfRequest: Promise<string> | null = null

async function fetchCsrfToken(): Promise<string> {
  const data = await apiRequest<CsrfTokenResponse>('/api/auth/csrf')
  csrfToken = data.csrf_token
  return data.csrf_token
}

/**
 * Return a cached CSRF token, or fetch one from the backend.
 *
 * Concurrent callers share one in-flight request so we do not rotate the
 * cookie twice and end up with a token that no longer matches.
 */
export function ensureCsrfToken(forceRefresh = false): Promise<string> {
  if (!forceRefresh && csrfToken) {
    return Promise.resolve(csrfToken)
  }

  if (!pendingCsrfRequest) {
    pendingCsrfRequest = fetchCsrfToken().finally(() => {
      pendingCsrfRequest = null
    })
  }

  return pendingCsrfRequest
}

/** Store a token returned by login, or forget it after logout. */
export function rememberCsrfToken(token: string | null): void {
  csrfToken = token
}

/**
 * Send a state-changing request with the CSRF header.
 *
 * If the cached token is stale (for example, another browser tab signed in
 * and rotated it), refresh once and retry.
 */
export async function mutateWithCsrf<T>(
  method: 'POST' | 'PATCH',
  path: string,
  body?: unknown,
): Promise<T> {
  const token = await ensureCsrfToken()

  try {
    return await apiRequest<T>(path, {
      method,
      body,
      headers: { 'X-CSRF-Token': token },
    })
  } catch (error) {
    if (error instanceof ApiError && error.status === 403) {
      const freshToken = await ensureCsrfToken(true)
      return apiRequest<T>(path, {
        method,
        body,
        headers: { 'X-CSRF-Token': freshToken },
      })
    }

    throw error
  }
}
