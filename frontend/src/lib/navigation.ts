/**
 * Only allow internal return paths after login. This prevents an open
 * redirect such as /login?returnTo=https://example.com.
 */
export function getSafeReturnTo(value: string | null): string {
  if (!value) return '/dashboard'

  if (!value.startsWith('/') || value.startsWith('//')) {
    return '/dashboard'
  }

  // Do not send an authenticated user back to the login page.
  if (value === '/login' || value.startsWith('/login?')) {
    return '/dashboard'
  }

  return value
}
