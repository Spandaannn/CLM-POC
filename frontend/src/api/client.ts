import { ApiError, extractErrorMessage } from '../lib/errors'

/**
 * An empty base URL means "same origin". In development, Vite proxies /api
 * and /health to the FastAPI server, so requests stay same-origin and the
 * session cookie works without CORS.
 */
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH'
  body?: unknown
  headers?: Record<string, string>
}

async function parseResponseBody(response: Response): Promise<unknown> {
  if (response.status === 204) return null

  const contentType = response.headers.get('content-type') ?? ''
  if (!contentType.includes('application/json')) return null

  try {
    return await response.json()
  } catch {
    return null
  }
}

/**
 * Perform a JSON request against the API.
 *
 * `credentials: 'include'` is required so the browser sends the HttpOnly
 * session cookie. We never read or store that cookie in JavaScript.
 */
export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const headers = new Headers(options.headers)
  const hasBody = options.body !== undefined
  // FormData (file uploads) must not get a JSON Content-Type: the browser
  // sets multipart/form-data together with its boundary.
  const isFormData = options.body instanceof FormData

  if (hasBody && !isFormData) {
    headers.set('Content-Type', 'application/json')
  }

  let response: Response

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: options.method ?? 'GET',
      headers,
      body: hasBody
        ? isFormData
          ? (options.body as FormData)
          : JSON.stringify(options.body)
        : undefined,
      credentials: 'include',
    })
  } catch {
    throw new ApiError(
      0,
      'Unable to reach the server. Check that the backend is running and try again.',
    )
  }

  const payload = await parseResponseBody(response)

  if (!response.ok) {
    const message =
      extractErrorMessage(payload) ?? `Request failed (${response.status}).`
    throw new ApiError(response.status, message)
  }

  return payload as T
}

/** Download a binary response (for example a stored document) as a Blob. */
export async function apiDownload(path: string): Promise<Blob> {
  let response: Response

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      credentials: 'include',
    })
  } catch {
    throw new ApiError(
      0,
      'Unable to reach the server. Check that the backend is running and try again.',
    )
  }

  if (!response.ok) {
    const payload = await parseResponseBody(response)
    const message =
      extractErrorMessage(payload) ?? `Download failed (${response.status}).`
    throw new ApiError(response.status, message)
  }

  return response.blob()
}
