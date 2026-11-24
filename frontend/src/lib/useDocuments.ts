import { useCallback, useEffect, useState } from 'react'
import { listDocuments } from '../api/documents'
import type { ContractDocumentListResponse } from '../api/types'
import { getErrorMessage } from './errors'

export type DocumentsLoadState =
  | { status: 'loading' }
  | { status: 'loaded'; data: ContractDocumentListResponse }
  | { status: 'error'; message: string }

type SettledState = Exclude<DocumentsLoadState, { status: 'loading' }>

/**
 * Load a contract's document versions.
 *
 * Results are tagged with the request they answer, so "loading" is derived
 * while the newest request has no result yet (same approach as useContract).
 */
export function useDocuments(contractId: string): {
  state: DocumentsLoadState
  reload: () => void
} {
  const [reloadKey, setReloadKey] = useState(0)
  const [result, setResult] = useState<{
    key: string
    state: SettledState
  } | null>(null)

  const requestKey = `${contractId}:${reloadKey}`

  useEffect(() => {
    let cancelled = false
    const settle = (state: SettledState) => {
      if (!cancelled) setResult({ key: requestKey, state })
    }

    listDocuments(contractId)
      .then((data) => settle({ status: 'loaded', data }))
      .catch((caughtError: unknown) =>
        settle({ status: 'error', message: getErrorMessage(caughtError) }),
      )

    return () => {
      cancelled = true
    }
  }, [contractId, requestKey])

  const reload = useCallback(() => setReloadKey((current) => current + 1), [])

  const state: DocumentsLoadState =
    result?.key === requestKey ? result.state : { status: 'loading' }

  return { state, reload }
}
