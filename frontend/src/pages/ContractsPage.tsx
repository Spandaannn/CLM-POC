import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { listContracts } from '../api/contracts'
import type { Contract, ContractStatus } from '../api/types'
import { Alert } from '../components/Alert'
import { Button } from '../components/Button'
import { Spinner } from '../components/Spinner'
import { getErrorMessage } from '../lib/errors'
import {
  formatDate,
  formatMoney,
  formatStatus,
  getStatusBadgeClass,
} from '../lib/format'

const PAGE_SIZE = 10

const STATUS_OPTIONS: ContractStatus[] = [
  'draft',
  'pending_review',
  'approved',
  'rejected',
  'active',
  'expired',
  'terminated',
]

function getPage(params: URLSearchParams): number {
  const value = Number(params.get('page') ?? '1')
  return Number.isInteger(value) && value > 0 ? value : 1
}

export function ContractsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [searchInput, setSearchInput] = useState('')
  const [statusInput, setStatusInput] = useState('')
  const [typeInput, setTypeInput] = useState('')
  const [contracts, setContracts] = useState<Contract[]>([])
  const [total, setTotal] = useState(0)
  const [pages, setPages] = useState(0)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  const queryString = searchParams.toString()
  const page = getPage(new URLSearchParams(queryString))
  const hasFilters = Boolean(
    searchParams.get('q') ||
      searchParams.get('status') ||
      searchParams.get('contract_type'),
  )

  // Keep the filter form in sync with browser back/forward navigation.
  useEffect(() => {
    const params = new URLSearchParams(queryString)
    setSearchInput(params.get('q') ?? '')
    setStatusInput(params.get('status') ?? '')
    setTypeInput(params.get('contract_type') ?? '')
  }, [queryString])

  useEffect(() => {
    let cancelled = false
    const params = new URLSearchParams(queryString)
    const status = params.get('status')

    setIsLoading(true)
    setError(null)

    listContracts({
      page: getPage(params),
      page_size: PAGE_SIZE,
      q: params.get('q') ?? undefined,
      status: status ? (status as ContractStatus) : undefined,
      contract_type: params.get('contract_type') ?? undefined,
    })
      .then((data) => {
        if (cancelled) return
        setContracts(data.items)
        setTotal(data.total)
        setPages(data.pages)
      })
      .catch((caughtError: unknown) => {
        if (cancelled) return
        setError(getErrorMessage(caughtError))
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [queryString, reloadKey])

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    const next = new URLSearchParams()
    if (searchInput.trim()) next.set('q', searchInput.trim())
    if (statusInput) next.set('status', statusInput)
    if (typeInput.trim()) {
      next.set('contract_type', typeInput.trim())
    }
    next.set('page', '1')

    setSearchParams(next)
  }

  function clearFilters() {
    setSearchInput('')
    setStatusInput('')
    setTypeInput('')
    setSearchParams({})
  }

  function goToPage(nextPage: number) {
    const next = new URLSearchParams(queryString)
    next.set('page', String(nextPage))
    setSearchParams(next)
  }

  return (
    <div className="contracts-page">
      <div className="page-header">
        <div className="page-header__intro">
          <p className="eyebrow">Contract register</p>
          <h1>Contracts</h1>
          <p className="muted-text">
            Search and manage contract metadata. Document uploads, AI reviews,
            and approvals will be added in later phases.
          </p>
        </div>
        <div className="page-actions">
          <Link className="button button--primary" to="/contracts/new">
            New contract
          </Link>
        </div>
      </div>

      <form className="filter-bar" onSubmit={applyFilters} role="search">
        <div className="field filter-bar__search">
          <label className="field__label" htmlFor="contract-search">
            Search
          </label>
          <input
            id="contract-search"
            className="field__input"
            type="search"
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            placeholder="Title, number, or counterparty"
          />
        </div>

        <div className="field">
          <label className="field__label" htmlFor="contract-status-filter">
            Status
          </label>
          <select
            id="contract-status-filter"
            className="field__input"
            value={statusInput}
            onChange={(event) => setStatusInput(event.target.value)}
          >
            <option value="">All statuses</option>
            {STATUS_OPTIONS.map((status) => (
              <option key={status} value={status}>
                {formatStatus(status)}
              </option>
            ))}
          </select>
        </div>

        <div className="field">
          <label className="field__label" htmlFor="contract-type-filter">
            Contract type
          </label>
          <input
            id="contract-type-filter"
            className="field__input"
            value={typeInput}
            onChange={(event) => setTypeInput(event.target.value)}
            placeholder="Any type"
          />
        </div>

        <div className="filter-bar__actions">
          <Button type="submit">Apply filters</Button>
          <Button
            type="button"
            variant="secondary"
            onClick={clearFilters}
            disabled={!hasFilters && !searchInput && !statusInput && !typeInput}
          >
            Clear
          </Button>
        </div>
      </form>

      {error && (
        <div className="page-error">
          <Alert variant="error">{error}</Alert>
          <Button
            variant="secondary"
            onClick={() => setReloadKey((current) => current + 1)}
          >
            Try again
          </Button>
        </div>
      )}

      {isLoading && !error ? (
        <div className="state-panel" role="status">
          <Spinner size={30} label="Loading contracts" />
          <p>Loading contracts...</p>
        </div>
      ) : error ? null : contracts.length === 0 ? (
        <div className="empty-state">
          <p className="eyebrow">
            {hasFilters ? 'No matches' : 'Get started'}
          </p>
          <h2>
            {hasFilters
              ? 'No contracts match these filters'
              : 'No contracts yet'}
          </h2>
          <p>
            {hasFilters
              ? 'Try a different search term or clear the filters to see every contract you can access.'
              : 'Create the first contract record to start tracking agreements in this workspace.'}
          </p>
          {hasFilters ? (
            <Button variant="secondary" onClick={clearFilters}>
              Clear filters
            </Button>
          ) : (
            <Link className="button button--primary" to="/contracts/new">
              Create the first contract
            </Link>
          )}
        </div>
      ) : (
        <>
          <p className="result-count" role="status">
            {total} contract{total === 1 ? '' : 's'}
          </p>

          <div className="table-wrap">
            <table className="data-table">
              <caption className="visually-hidden">
                Contracts matching the current filters
              </caption>
              <thead>
                <tr>
                  <th scope="col">Contract</th>
                  <th scope="col">Title</th>
                  <th scope="col">Counterparty</th>
                  <th scope="col">Status</th>
                  <th scope="col">Value</th>
                  <th scope="col">End date</th>
                </tr>
              </thead>
              <tbody>
                {contracts.map((contract) => (
                  <tr key={contract.id}>
                    <td>
                      <Link
                        className="data-table__primary"
                        to={`/contracts/${contract.id}`}
                      >
                        {contract.contract_number}
                      </Link>
                    </td>
                    <td>
                      <Link
                        className="data-table__primary"
                        to={`/contracts/${contract.id}`}
                      >
                        {contract.title}
                      </Link>
                      <span className="data-table__secondary">
                        {contract.contract_type}
                      </span>
                    </td>
                    <td>{contract.counterparty_name}</td>
                    <td>
                      <span
                        className={`badge ${getStatusBadgeClass(
                          contract.status,
                        )}`}
                      >
                        {formatStatus(contract.status)}
                      </span>
                    </td>
                    <td>
                      {formatMoney(
                        contract.contract_value,
                        contract.currency,
                      )}
                    </td>
                    <td>{formatDate(contract.end_date)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {pages > 1 && (
            <nav className="pagination" aria-label="Contract pages">
              <Button
                variant="secondary"
                onClick={() => goToPage(page - 1)}
                disabled={page <= 1}
              >
                Previous
              </Button>
              <span>
                Page {page} of {pages}
              </span>
              <Button
                variant="secondary"
                onClick={() => goToPage(page + 1)}
                disabled={page >= pages}
              >
                Next
              </Button>
            </nav>
          )}
        </>
      )}
    </div>
  )
}
