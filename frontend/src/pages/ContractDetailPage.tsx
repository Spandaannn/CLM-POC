import { useEffect, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { getContract } from '../api/contracts'
import type { Contract } from '../api/types'
import { useAuth } from '../auth/useAuth'
import { Alert } from '../components/Alert'
import { Button } from '../components/Button'
import { PageMessage } from '../components/PageMessage'
import { Spinner } from '../components/Spinner'
import { ApiError, getErrorMessage } from '../lib/errors'
import {
  formatDate,
  formatDateTime,
  formatMoney,
  formatStatus,
  getStatusBadgeClass,
} from '../lib/format'

interface DetailLocationState {
  created?: boolean
  updated?: boolean
}

export function ContractDetailPage() {
  const { contractId } = useParams<{ contractId: string }>()
  const { user } = useAuth()
  const location = useLocation()
  const locationState = location.state as DetailLocationState | null

  const [contract, setContract] = useState<Contract | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notFound, setNotFound] = useState(false)
  const [forbidden, setForbidden] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    if (!contractId) {
      setIsLoading(false)
      setNotFound(true)
      return
    }

    let cancelled = false
    setIsLoading(true)
    setError(null)
    setNotFound(false)
    setForbidden(false)
    setContract(null)

    getContract(contractId)
      .then((data) => {
        if (!cancelled) setContract(data)
      })
      .catch((caughtError: unknown) => {
        if (cancelled) return

        if (caughtError instanceof ApiError) {
          if (caughtError.status === 404) {
            setNotFound(true)
            return
          }
          if (caughtError.status === 403) {
            setForbidden(true)
            return
          }
        }

        setError(getErrorMessage(caughtError))
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [contractId, reloadKey])

  if (isLoading) {
    return (
      <div className="state-panel" role="status">
        <Spinner size={30} label="Loading contract" />
        <p>Loading contract...</p>
      </div>
    )
  }

  if (notFound) {
    return (
      <PageMessage
        eyebrow="Not found"
        title="Contract not found"
        action={
          <Link className="button button--secondary" to="/contracts">
            Back to contracts
          </Link>
        }
      >
        The contract may have been removed, or the link may be incorrect.
      </PageMessage>
    )
  }

  if (forbidden) {
    return (
      <PageMessage
        eyebrow="Access denied"
        title="You do not have access to this contract"
        action={
          <Link className="button button--secondary" to="/contracts">
            Back to contracts
          </Link>
        }
      >
        Ask an administrator if you believe you should be able to view this
        record.
      </PageMessage>
    )
  }

  if (error || !contract) {
    return (
      <PageMessage
        eyebrow="Connection problem"
        title="Unable to load this contract"
        action={
          <Button
            variant="secondary"
            onClick={() => setReloadKey((current) => current + 1)}
          >
            Try again
          </Button>
        }
      >
        {error ?? 'The contract could not be loaded.'}
      </PageMessage>
    )
  }

  const canEdit = Boolean(
    user &&
      (user.role === 'admin' || contract.created_by === user.id),
  )

  return (
    <div className="contract-detail-page">
      <div className="page-header">
        <div className="page-header__intro">
          <p className="eyebrow">{contract.contract_number}</p>
          <h1>{contract.title}</h1>
          <p className="contract-subtitle">
            <span
              className={`badge ${getStatusBadgeClass(contract.status)}`}
            >
              {formatStatus(contract.status)}
            </span>
            <span>{contract.counterparty_name}</span>
            <span>{contract.contract_type}</span>
          </p>
        </div>
        <div className="page-actions">
          <Link className="button button--secondary" to="/contracts">
            Back to contracts
          </Link>
          {canEdit && (
            <Link
              className="button button--primary"
              to={`/contracts/${contract.id}/edit`}
            >
              Edit contract
            </Link>
          )}
        </div>
      </div>

      {locationState?.created && (
        <Alert variant="success">Contract created successfully.</Alert>
      )}
      {locationState?.updated && (
        <Alert variant="success">Contract updated successfully.</Alert>
      )}

      <div className="detail-grid">
        <section className="detail-card" aria-labelledby="overview-title">
          <h2 id="overview-title">Overview</h2>
          <dl className="detail-list">
            <div>
              <dt>Contract number</dt>
              <dd>{contract.contract_number}</dd>
            </div>
            <div>
              <dt>Contract type</dt>
              <dd>{contract.contract_type}</dd>
            </div>
            <div>
              <dt>Counterparty</dt>
              <dd>{contract.counterparty_name}</dd>
            </div>
            <div>
              <dt>Contract value</dt>
              <dd>
                {formatMoney(contract.contract_value, contract.currency)}
              </dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd>{formatStatus(contract.status)}</dd>
            </div>
          </dl>
        </section>

        <section className="detail-card" aria-labelledby="dates-title">
          <h2 id="dates-title">Dates and ownership</h2>
          <dl className="detail-list">
            <div>
              <dt>Start date</dt>
              <dd>{formatDate(contract.start_date)}</dd>
            </div>
            <div>
              <dt>End date</dt>
              <dd>{formatDate(contract.end_date)}</dd>
            </div>
            <div>
              <dt>Created by</dt>
              <dd>{contract.created_by_name ?? contract.created_by}</dd>
            </div>
            <div>
              <dt>Created</dt>
              <dd>{formatDateTime(contract.created_at)}</dd>
            </div>
            <div>
              <dt>Last updated</dt>
              <dd>{formatDateTime(contract.updated_at)}</dd>
            </div>
          </dl>
        </section>
      </div>

      <section className="detail-card" aria-labelledby="description-title">
        <h2 id="description-title">Description</h2>
        <p className="description-block">
          {contract.description || 'No description has been added.'}
        </p>
      </section>
    </div>
  )
}
