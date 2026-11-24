import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { getContract, updateContract } from '../api/contracts'
import type { Contract } from '../api/types'
import { useAuth } from '../auth/useAuth'
import { Button } from '../components/Button'
import { ContractForm } from '../components/ContractForm'
import { contractToFormValues, toContractPayload } from '../lib/contractForm'
import type { ContractFormValues } from '../lib/contractForm'
import { PageMessage } from '../components/PageMessage'
import { Spinner } from '../components/Spinner'
import { ApiError, getErrorMessage } from '../lib/errors'

export function EditContractPage() {
  const { contractId } = useParams<{ contractId: string }>()
  const { user } = useAuth()
  const navigate = useNavigate()

  const [contract, setContract] = useState<Contract | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)
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
    setLoadError(null)
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

        setLoadError(getErrorMessage(caughtError))
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [contractId, reloadKey])

  const canEdit = Boolean(
    user &&
      contract &&
      (user.role === 'admin' || contract.created_by === user.id),
  )

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

  if (forbidden || (contract && !canEdit)) {
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

  if (loadError || !contract) {
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
        {loadError ?? 'The contract could not be loaded.'}
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
          isSubmitting={isSubmitting}
          error={submitError}
          onSubmit={handleSubmit}
        />
      </div>
    </div>
  )
}
