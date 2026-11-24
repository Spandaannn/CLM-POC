import { useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import { Alert } from '../components/Alert'
import { ApprovalSection } from '../components/ApprovalSection'
import { Button } from '../components/Button'
import { ContractFilesAndReviews } from '../components/ContractFilesAndReviews'
import { PageMessage } from '../components/PageMessage'
import { Spinner } from '../components/Spinner'
import { useContract } from '../lib/useContract'
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

/** Why documents are locked for this status (null = open for uploads). */
function documentLockReason(status: string): string | null {
  switch (status) {
    case 'draft':
      return null
    case 'pending_review':
      return 'Documents are locked while this contract is under approval. They can be changed again only if changes are requested.'
    case 'rejected':
      return 'Documents are locked because this contract was rejected.'
    default:
      return 'Documents are fixed because this contract has been approved.'
  }
}

export function ContractDetailPage() {
  const { contractId } = useParams<{ contractId: string }>()
  const { user } = useAuth()
  const location = useLocation()
  const locationState = location.state as DetailLocationState | null

  const { state, reload } = useContract(contractId)
  // Survives the refresh that follows an approval action.
  const [flash, setFlash] = useState<string | null>(null)

  if (state.status === 'loading') {
    return (
      <div className="state-panel" role="status">
        <Spinner size={30} label="Loading contract" />
        <p>Loading contract...</p>
      </div>
    )
  }

  if (state.status === 'not-found') {
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

  if (state.status === 'forbidden') {
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

  if (state.status === 'error') {
    return (
      <PageMessage
        eyebrow="Connection problem"
        title="Unable to load this contract"
        action={
          <Button variant="secondary" onClick={reload}>
            Try again
          </Button>
        }
      >
        {state.message}
      </PageMessage>
    )
  }

  const { contract } = state
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
          {canEdit &&
            !['pending_review', 'rejected'].includes(contract.status) && (
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
      {flash && <Alert variant="success">{flash}</Alert>}

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

      <ApprovalSection
        contractId={contract.id}
        onChanged={(message) => {
          setFlash(message)
          reload()
        }}
      />

      <ContractFilesAndReviews
        contractId={contract.id}
        canUpload={canEdit}
        lockedReason={documentLockReason(contract.status)}
      />
    </div>
  )
}
