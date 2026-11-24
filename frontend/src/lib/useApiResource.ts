import { useCallback, useEffect, useState } from 'react'
import { getErrorMessage } from './errors'

export type ResourceState<T> =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'loaded'; data: T }
  | { status: 'error'; message: string }

type Settled<T> = Extract<ResourceState<T>, { status: 'loaded' | 'error' }>

/**
 * Load a resource identified by `key` (null = nothing to load).
 *
 * Each result is tagged with the request it answers, so "loading" is derived
 * whenever the newest request has no result yet; effects never reset state
 * synchronously. `fetcher` must be a stable (module-level) function.
 */
export function useApiResource<T>(
  key: string | null,
  fetcher: (key: string) => Promise<T>,
): { state: ResourceState<T>; reload: () => void } {
  const [reloadKey, setReloadKey] = useState(0)
  const [result, setResult] = useState<{
    key: string
    state: Settled<T>
  } | null>(null)

  const requestKey = key === null ? null : `${key}:${reloadKey}`

  useEffect(() => {
    if (key === null || requestKey === null) return

    let cancelled = false
    const settle = (state: Settled<T>) => {
      if (!cancelled) setResult({ key: requestKey, state })
    }

    fetcher(key)
      .then((data) => settle({ status: 'loaded', data }))
      .catch((caughtError: unknown) =>
        settle({ status: 'error', message: getErrorMessage(caughtError) }),
      )

    return () => {
      cancelled = true
    }
  }, [key, requestKey, fetcher])

  const reload = useCallback(() => setReloadKey((current) => current + 1), [])

  let state: ResourceState<T>
  if (requestKey === null) state = { status: 'idle' }
  else if (result?.key === requestKey) state = result.state
  else state = { status: 'loading' }

  return { state, reload }
}
