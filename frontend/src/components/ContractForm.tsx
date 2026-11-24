import { useState } from 'react'
import type { FormEvent } from 'react'
import type { ContractStatus } from '../api/types'
import type { ContractFormValues } from '../lib/contractForm'
import { formatStatus } from '../lib/format'
import { Alert } from './Alert'
import { Button } from './Button'
import { TextField } from './TextField'

type FormErrors = Partial<Record<keyof ContractFormValues, string>>

const EMPTY_VALUES: ContractFormValues = {
  title: '',
  contract_type: '',
  counterparty_name: '',
  description: '',
  contract_value: '',
  currency: 'INR',
  start_date: '',
  end_date: '',
  status: 'draft',
}

const STATUS_OPTIONS: ContractStatus[] = [
  'draft',
  'pending_review',
  'approved',
  'rejected',
  'active',
  'expired',
  'terminated',
]

function validate(values: ContractFormValues): FormErrors {
  const errors: FormErrors = {}

  if (!values.title.trim()) {
    errors.title = 'Enter a contract title.'
  }
  if (!values.contract_type.trim()) {
    errors.contract_type = 'Enter a contract type.'
  }
  if (!values.counterparty_name.trim()) {
    errors.counterparty_name = 'Enter a counterparty name.'
  }
  if (!/^[A-Za-z]{3}$/.test(values.currency.trim())) {
    errors.currency = 'Use a three-letter currency code, for example INR.'
  }

  const amount = values.contract_value.trim()
  if (amount) {
    if (!/^\d+(\.\d{1,2})?$/.test(amount)) {
      errors.contract_value =
        'Enter zero or a positive amount with up to two decimal places.'
    }
  }

  if (
    values.start_date &&
    values.end_date &&
    values.end_date < values.start_date
  ) {
    errors.end_date = 'End date must be on or after the start date.'
  }

  return errors
}

interface ContractFormProps {
  mode: 'create' | 'edit'
  initialValues?: ContractFormValues
  isSubmitting: boolean
  error: string | null
  onSubmit: (values: ContractFormValues) => void
}

export function ContractForm({
  mode,
  initialValues,
  isSubmitting,
  error,
  onSubmit,
}: ContractFormProps) {
  const [values, setValues] = useState<ContractFormValues>(
    () => initialValues ?? EMPTY_VALUES,
  )
  const [errors, setErrors] = useState<FormErrors>({})

  function updateField<K extends keyof ContractFormValues>(
    field: K,
    value: ContractFormValues[K],
  ) {
    setValues((current) => ({ ...current, [field]: value }))

    setErrors((current) => {
      if (!current[field]) return current
      const next = { ...current }
      delete next[field]
      return next
    })
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (isSubmitting) return

    const nextErrors = validate(values)
    setErrors(nextErrors)

    if (Object.keys(nextErrors).length > 0) return
    onSubmit(values)
  }

  return (
    <form className="contract-form" onSubmit={handleSubmit} noValidate>
      {error && <Alert variant="error">{error}</Alert>}

      <div className="form-grid">
        <TextField
          className="form-grid__wide"
          label="Contract title"
          name="title"
          value={values.title}
          onChange={(event) => updateField('title', event.target.value)}
          error={errors.title}
          hint="A short name that identifies this agreement."
          maxLength={255}
          disabled={isSubmitting}
          required
        />

        <TextField
          label="Contract type"
          name="contract_type"
          value={values.contract_type}
          onChange={(event) =>
            updateField('contract_type', event.target.value)
          }
          error={errors.contract_type}
          hint="For example: Vendor agreement, NDA, Service agreement."
          maxLength={64}
          disabled={isSubmitting}
          required
        />

        <TextField
          label="Counterparty"
          name="counterparty_name"
          value={values.counterparty_name}
          onChange={(event) =>
            updateField('counterparty_name', event.target.value)
          }
          error={errors.counterparty_name}
          hint="The organisation or person on the other side."
          maxLength={255}
          disabled={isSubmitting}
          required
        />

        <TextField
          label="Contract value"
          name="contract_value"
          type="number"
          min="0"
          step="0.01"
          value={values.contract_value}
          onChange={(event) =>
            updateField('contract_value', event.target.value)
          }
          error={errors.contract_value}
          hint="Optional. Leave blank if the value is not fixed."
          disabled={isSubmitting}
        />

        <TextField
          label="Currency"
          name="currency"
          value={values.currency}
          onChange={(event) =>
            updateField('currency', event.target.value.toUpperCase())
          }
          error={errors.currency}
          hint="Three-letter ISO code, for example INR or USD."
          maxLength={3}
          autoComplete="off"
          spellCheck={false}
          disabled={isSubmitting}
          required
        />

        <TextField
          label="Start date"
          name="start_date"
          type="date"
          value={values.start_date}
          onChange={(event) =>
            updateField('start_date', event.target.value)
          }
          disabled={isSubmitting}
        />

        <TextField
          label="End date"
          name="end_date"
          type="date"
          min={values.start_date || undefined}
          value={values.end_date}
          onChange={(event) => updateField('end_date', event.target.value)}
          error={errors.end_date}
          disabled={isSubmitting}
        />

        {mode === 'edit' && (
          <div className="field">
            <label className="field__label" htmlFor="contract-status">
              Status
            </label>
            <select
              id="contract-status"
              name="status"
              className="field__input"
              value={values.status}
              onChange={(event) =>
                updateField(
                  'status',
                  event.target.value as ContractStatus,
                )
              }
              disabled={isSubmitting}
            >
              {STATUS_OPTIONS.map((status) => (
                <option key={status} value={status}>
                  {formatStatus(status)}
                </option>
              ))}
            </select>
            <p className="field__hint">
              Approval workflow rules will be added in a later phase.
            </p>
          </div>
        )}

        <div className="field form-grid__wide">
          <label className="field__label" htmlFor="contract-description">
            Description
          </label>
          <textarea
            id="contract-description"
            name="description"
            className="field__input field__textarea"
            rows={5}
            maxLength={10000}
            value={values.description}
            onChange={(event) =>
              updateField('description', event.target.value)
            }
            disabled={isSubmitting}
          />
          <p className="field__hint">
            Optional internal context. Do not paste confidential document
            text.
          </p>
        </div>
      </div>

      <div className="form-actions">
        <Button type="submit" loading={isSubmitting}>
          {isSubmitting
            ? 'Saving...'
            : mode === 'create'
              ? 'Create contract'
              : 'Save changes'}
        </Button>
      </div>
    </form>
  )
}
