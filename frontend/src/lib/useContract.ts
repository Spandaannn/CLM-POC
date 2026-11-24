import { useCallback, useEffect, useState } from 'react'
import { getContract } from '../api/contracts'
import type { Contract } from '../api/types'
import { ApiError, getErrorMessage } from './errors'

export type ContractLoadState =
  | { status: 'loading' }
  | { status: 'loaded'; contract: Contract }
  | { status: 'not-found' }
  | { status: 'forbidden' }
  | { status: 'error'; message: string }

type SettledState = Exclude<ContractLoadState, { status: 'loading' }>

/**
 * Load one contract by ID.
 *
 * Each result is tagged with the request it answers. While the newest request
 * has no result yet the state is "loading", so the effect never has to reset
 * state synchronously when the ID changes or the user retries.
 */
export function useContract(contractId: string | undefined): {
  state: ContractLoadState
  reload: () => void
} {
  const [reloadKey, setReloadKey] = useState(0)
  const [result, setResult] = useState<{
    key: string
    state: SettledState
  } | null>(null)

  const requestKey = `${contractId ?? ''}:${reloadKey}`

  useEffect(() => {
    if (!contractId) return

    let cancelled = false
    const settle = (state: SettledState) => {
      if (!cancelled) setResult({ key: requestKey, state })
    }

    getContract(contractId)
      .then((contract) => settle({ status: 'loaded', contract }))
      .catch((caughtError: unknown) => {
        if (caughtError instanceof ApiError) {
          if (caughtError.status === 404) return settle({ status: 'not-found' })
          if (caughtError.status === 403) return settle({ status: 'forbidden' })
        }
        settle({ status: 'error', message: getErrorMessage(caughtError) })
      })

    return () => {
      cancelled = true
    }
  }, [contractId, requestKey])

  const reload = useCallback(() => setReloadKey((current) => current + 1), [])

  let state: ContractLoadState
  if (!contractId) {
    state = { status: 'not-found' }
  } else if (result?.key === requestKey) {
    state = result.state
  } else {
    state = { status: 'loading' }
  }

  return { state, reload }
}
