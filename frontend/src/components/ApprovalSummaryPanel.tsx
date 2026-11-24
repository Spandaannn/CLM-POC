import { Link } from 'react-router-dom'
import { getApprovalSummary } from '../api/approvals'
import type { QueueItem } from '../api/types'
import {
  formatDateTime,
  formatWorkflowStatus,
  getWorkflowBadgeClass,
} from '../lib/format'
import { useApiResource } from '../lib/useApiResource'
import { Alert } from './Alert'
import { Button } from './Button'
import { Spinner } from './Spinner'

function QueueList({ items }: { items: QueueItem[] }) {
  return (
    <ul className="queue">
      {items.map((item) => (
        <li key={`${item.contract_id}-${item.cycle_number}`}>
          <Link className="queue__link" to={`/contracts/${item.contract_id}`}>
            <span className="queue__title">
              <strong>{item.title}</strong>
              <span className="muted-text">
                {item.contract_number} · {item.counterparty_name}
              </span>
            </span>
            <span className="queue__meta">
              <span className={`badge ${getWorkflowBadgeClass(item.status)}`}>
                {formatWorkflowStatus(item.status)}
              </span>
              <span className="muted-text">
                cycle {item.cycle_number} · {formatDateTime(item.updated_at)}
              </span>
            </span>
          </Link>
        </li>
      ))}
    </ul>
  )
}

/** Small approval overview for the dashboard (real data, no placeholders). */
export function ApprovalSummaryPanel() {
  const { state, reload } = useApiResource('summary', getApprovalSummary)

  return (
    <section className="dashboard-section" aria-labelledby="approvals-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Approvals</p>
          <h2 id="approvals-title">Approval queue</h2>
        </div>
        <p>
          Contracts waiting for you, and the progress of contracts you created.
        </p>
      </div>

      {state.status === 'loading' && (
        <div className="state-panel" role="status">
          <Spinner size={24} label="Loading approvals" />
          <p>Loading approvals...</p>
        </div>
      )}

      {state.status === 'error' && (
        <div className="page-error">
          <Alert variant="error">{state.message}</Alert>
          <Button variant="secondary" onClick={reload}>
            Try again
          </Button>
        </div>
      )}

      {state.status === 'loaded' && (
        <div className="approval-summary">
          <div className="approval-summary__panel">
            <h3>
              Awaiting your action{' '}
              <span className="badge badge--brand">
                {state.data.awaiting_my_action_count}
              </span>
            </h3>
            {state.data.awaiting_my_action.length === 0 ? (
              <p className="muted-text">Nothing is waiting for you.</p>
            ) : (
              <QueueList items={state.data.awaiting_my_action} />
            )}
          </div>

          <div className="approval-summary__panel">
            <h3>
              Your contracts in approval{' '}
              <span className="badge badge--muted">
                {state.data.under_approval_count} under approval ·{' '}
                {state.data.changes_requested_count} need changes
              </span>
            </h3>
            {state.data.my_contracts.length === 0 ? (
              <p className="muted-text">
                None of your contracts are in the approval workflow.
              </p>
            ) : (
              <QueueList items={state.data.my_contracts} />
            )}
          </div>
        </div>
      )}
    </section>
  )
}
