import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { createContract } from '../api/contracts'
import { ContractForm } from '../components/ContractForm'
import { toContractPayload } from '../lib/contractForm'
import type { ContractFormValues } from '../lib/contractForm'
import { getErrorMessage } from '../lib/errors'

export function NewContractPage() {
  const navigate = useNavigate()
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(values: ContractFormValues) {
    setIsSubmitting(true)
    setError(null)

    try {
      const contract = await createContract(toContractPayload(values))
      navigate(`/contracts/${contract.id}`, {
        replace: true,
        state: { created: true },
      })
    } catch (caughtError) {
      setError(getErrorMessage(caughtError))
      setIsSubmitting(false)
    }
  }

  return (
    <div className="contract-form-page">
      <div className="page-header">
        <div className="page-header__intro">
          <p className="eyebrow">New record</p>
          <h1>Create contract</h1>
          <p className="muted-text">
            Add the core metadata for a new agreement. The contract number is
            generated automatically, and new records start as drafts.
          </p>
        </div>
        <div className="page-actions">
          <Link className="button button--secondary" to="/contracts">
            Cancel
          </Link>
        </div>
      </div>

      <div className="form-card">
        <ContractForm
          mode="create"
          isSubmitting={isSubmitting}
          error={error}
          onSubmit={handleSubmit}
        />
      </div>
    </div>
  )
}
