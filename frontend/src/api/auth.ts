import { mutateWithCsrf, rememberCsrfToken } from './csrf'
import { apiRequest } from './client'
import type { LoginRequest, LoginResponse, User } from './types'

/** Log in and remember the rotated CSRF token for later requests. */
export async function login(credentials: LoginRequest): Promise<LoginResponse> {
  const result = await mutateWithCsrf<LoginResponse>(
    'POST',
    '/api/auth/login',
    credentials,
  )

  rememberCsrfToken(result.csrf_token)
  return result
}

export async function logout(): Promise<void> {
  try {
    await mutateWithCsrf<void>('POST', '/api/auth/logout')
  } finally {
    // The server clears the cookies. Forget the in-memory token too.
    rememberCsrfToken(null)
  }
}

export function getCurrentUser(): Promise<User> {
  return apiRequest<User>('/api/auth/me')
}
