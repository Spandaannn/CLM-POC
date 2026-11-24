import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { updateContract } from '../api/contracts'
import { useAuth } from '../auth/useAuth'
import { Button } from '../components/Button'
import { ContractForm } from '../components/ContractForm'
import { contractToFormValues, toContractPayload } from '../lib/contractForm'
import type { ContractFormValues } from '../lib/contractForm'
import { PageMessage } from '../components/PageMessage'
import { Spinner } from '../components/Spinner'
import { getErrorMessage } from '../lib/errors'
import { useContract } from '../lib/useContract'

export function EditContractPage() {
  const { contractId } = useParams<{ contractId: string }>()
  const { user } = useAuth()
  const navigate = useNavigate()

  const { state, reload } = useContract(contractId)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  async function handleSubmit(values: ContractFormValues) {
    if (!contractId) return

    setIsSubmitting(true)
    setSubmitError(null)

    try {
      const updated = await updateContract(contractId, {
        ...toContractPayload(values),
        status: values.status,
      })
      navigate(`/contracts/${updated.id}`, {
        replace: true,
        state: { updated: true },
      })
    } catch (caughtError) {
      setSubmitError(getErrorMessage(caughtError))
      setIsSubmitting(false)
    }
  }

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

  const contract = state.status === 'loaded' ? state.contract : null
  const canEdit = Boolean(
    user &&
      contract &&
      (user.role === 'admin' || contract.created_by === user.id),
  )

  if (contract && canEdit && ['pending_review', 'rejected'].includes(contract.status)) {
    return (
      <PageMessage
        eyebrow="Locked"
        title="This contract cannot be edited"
        action={
          <Link
            className="button button--secondary"
            to={`/contracts/${contract.id}`}
          >
            Back to contract
          </Link>
        }
      >
        {contract.status === 'pending_review'
          ? 'It is under approval. It can be edited again only if changes are requested.'
          : 'It was rejected and can no longer be edited.'}
      </PageMessage>
    )
  }

  if (!contract || !canEdit) {
    return (
      <PageMessage
        eyebrow="Access denied"
        title="You cannot edit this contract"
        action={
          <Link
            className="button button--secondary"
            to={contract ? `/contracts/${contract.id}` : '/contracts'}
          >
            {contract ? 'Back to contract' : 'Back to contracts'}
          </Link>
        }
      >
        Only the user who created the contract or an administrator can edit its
        metadata.
      </PageMessage>
    )
  }

  return (
    <div className="contract-form-page">
      <div className="page-header">
        <div className="page-header__intro">
          <p className="eyebrow">{contract.contract_number}</p>
          <h1>Edit contract</h1>
          <p className="muted-text">
            Update the metadata for {contract.title}. The contract number,
            creator, and timestamps are managed by the system.
          </p>
        </div>
        <div className="page-actions">
          <Link
            className="button button--secondary"
            to={`/contracts/${contract.id}`}
          >
            Cancel
          </Link>
        </div>
      </div>

      <div className="form-card">
        <ContractForm
          mode="edit"
          initialValues={contractToFormValues(contract)}
          contentLocked={contract.status !== 'draft'}
          showLifecycleStatus={contract.status !== 'draft'}
          isSubmitting={isSubmitting}
          error={submitError}
          onSubmit={handleSubmit}
        />
      </div>
    </div>
  )
}
