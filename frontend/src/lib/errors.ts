/**
 * A small error type that carries the HTTP status code.
 *
 * Status 0 means the request never reached the server (for example, the
 * backend was not running).
 */
export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

/**
 * FastAPI returns errors as { "detail": "message" } or, for validation
 * errors, { "detail": [{ "msg": "...", ... }] }.
 */
export function extractErrorMessage(payload: unknown): string | null {
  if (!isRecord(payload)) return null

  const detail = payload.detail

  if (typeof detail === 'string') return detail

  if (Array.isArray(detail)) {
    const messages = detail.flatMap((item) => {
      if (isRecord(item) && typeof item.msg === 'string') return [item.msg]
      return []
    })

    if (messages.length > 0) return messages.join(' ')
  }

  return null
}

/** Convert any thrown value into a message that is safe to show in the UI. */
export function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return 'Something went wrong. Please try again.'
}
