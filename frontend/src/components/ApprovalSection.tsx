import { useState } from 'react'
import type { FormEvent } from 'react'
import {
  approverAction,
  getApprovalState,
  getAssignees,
  reviewerAction,
  submitForApproval,
} from '../api/approvals'
import type {
  ApprovalActionRecord,
  ApprovalCycle,
  ApprovalState,
  WorkflowAction,
} from '../api/types'
import { ApiError, getErrorMessage } from '../lib/errors'
import {
  formatDateTime,
  formatRole,
  formatWorkflowStatus,
  getWorkflowBadgeClass,
} from '../lib/format'
import { useApiResource } from '../lib/useApiResource'
import { Alert } from './Alert'
import { Button } from './Button'
import { Spinner } from './Spinner'

const MIN_COMMENT = 10

interface ActionCopy {
  label: string
  confirmLabel: string
  variant: 'primary' | 'secondary' | 'danger'
  commentRequired: boolean
  warning?: string
  success: string
}

const ACTION_COPY: Record<
  'recommend' | 'request_changes' | 'reject' | 'approve',
  ActionCopy
> = {
  recommend: {
    label: 'Recommend approval',
    confirmLabel: 'Recommend and forward',
    variant: 'primary',
    commentRequired: false,
    success: 'Recommended. The contract now awaits final approval.',
  },
  request_changes: {
    label: 'Request changes',
    confirmLabel: 'Send back for changes',
    variant: 'secondary',
    commentRequired: true,
    warning:
      'The contract returns to Draft so its creator can edit and resubmit it.',
    success: 'Changes requested. The creator can now edit and resubmit.',
  },
  reject: {
    label: 'Reject',
    confirmLabel: 'Confirm rejection',
    variant: 'danger',
    commentRequired: true,
    warning:
      'Rejection is final. The contract can no longer be edited or resubmitted.',
    success: 'Contract rejected.',
  },
  approve: {
    label: 'Final approve',
    confirmLabel: 'Confirm final approval',
    variant: 'primary',
    commentRequired: false,
    warning:
      'Final approval marks the contract as Approved and fixes its terms. It cannot be undone.',
    success: 'Contract approved.',
  },
}

const EVENT_LABEL: Record<string, string> = {
  submitted: 'Submitted for approval',
  resubmitted: 'Resubmitted after changes',
  recommended: 'Recommended for approval',
  changes_requested: 'Changes requested',
  rejected: 'Rejected',
  approved: 'Final approval',
}

const EVENT_BADGE: Record<string, string> = {
  approved: 'badge--success',
  rejected: 'badge--danger',
  changes_requested: 'badge--warning',
  recommended: 'badge--brand',
  submitted: 'badge--muted',
  resubmitted: 'badge--muted',
}

type StepState = 'done' | 'current' | 'todo' | 'stopped'

/** Progress of the latest cycle through the four stages. */
function stepStates(cycle: ApprovalCycle): { label: string; state: StepState }[] {
  const recommended = cycle.actions.some((a) => a.action_type === 'recommended')
  const steps: { label: string; state: StepState }[] = [
    { label: 'Submitted', state: 'done' },
    { label: 'Legal review', state: 'todo' },
    { label: 'Final approval', state: 'todo' },
    { label: 'Decision', state: 'todo' },
  ]

  switch (cycle.status) {
    case 'pending_reviewer':
      steps[1].state = 'current'
      break
    case 'pending_approver':
      steps[1].state = 'done'
      steps[2].state = 'current'
      break
    case 'approved':
      steps.forEach((step) => (step.state = 'done'))
      steps[3].label = 'Approved'
      break
    default: {
      // rejected / changes_requested: stopped at the stage that decided.
      steps[1].state = recommended ? 'done' : 'stopped'
      if (recommended) steps[2].state = 'stopped'
      steps[3].state = 'stopped'
      steps[3].label =
        cycle.status === 'rejected' ? 'Rejected' : 'Changes requested'
    }
  }
  return steps
}

function waitingMessage(state: ApprovalState): string | null {
  const cycle = state.current_cycle
  if (!cycle) return null

  switch (state.workflow_status) {
    case 'pending_reviewer':
      return `Waiting for ${cycle.reviewer.full_name} (Legal Reviewer) to review.`
    case 'pending_approver':
      return `Waiting for ${cycle.approver.full_name} (Legal Approver) for final approval.`
    case 'changes_requested':
      return 'Changes were requested. The creator can edit the contract and resubmit it.'
    default:
      return null
  }
}

// ----------------------------- submit form ----------------------------------

function SubmitForm({
  contractId,
  resubmit,
  previous,
  onDone,
}: {
  contractId: string
  resubmit: boolean
  previous: ApprovalCycle | null
  onDone: (message: string) => void
}) {
  const assignees = useApiResource('assignees', getAssignees)
  const [reviewerId, setReviewerId] = useState(previous?.reviewer.id ?? '')
  const [approverId, setApproverId] = useState(previous?.approver.id ?? '')
  const [comment, setComment] = useState('')
  const [isBusy, setIsBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (isBusy) return
    if (!reviewerId || !approverId) {
      setError('Choose both a Legal Reviewer and a Legal Approver.')
      return
    }

    setIsBusy(true)
    setError(null)
    try {
      await submitForApproval(
        contractId,
        {
          reviewer_id: reviewerId,
          approver_id: approverId,
          comment: comment.trim() || null,
        },
        resubmit,
      )
      onDone(
        resubmit
          ? 'Resubmitted. A new approval cycle has started.'
          : 'Submitted for approval.',
      )
    } catch (caughtError) {
      setError(getErrorMessage(caughtError))
      setIsBusy(false)
    }
  }

  if (assignees.state.status === 'loading') {
    return (
      <div className="state-panel" role="status">
        <Spinner size={22} label="Loading reviewers" />
        <p>Loading the legal team...</p>
      </div>
    )
  }
  if (assignees.state.status === 'error') {
    return (
      <div className="page-error">
        <Alert variant="error">{assignees.state.message}</Alert>
        <Button variant="secondary" onClick={assignees.reload}>
          Try again
        </Button>
      </div>
    )
  }
  if (assignees.state.status !== 'loaded') return null

  const { reviewers, approvers } = assignees.state.data
  const noTeam = reviewers.length === 0 || approvers.length === 0

  return (
    <form className="approval__form" onSubmit={handleSubmit} noValidate>
      <h3>{resubmit ? 'Resubmit for approval' : 'Submit for approval'}</h3>
      <p className="muted-text">
        {resubmit
          ? 'This starts a new approval cycle. The previous cycle and its comments stay in the history.'
          : 'Choose who will review and who will give final approval. After you submit, the contract and its documents are locked unless changes are requested.'}
      </p>

      {noTeam && (
        <Alert variant="info">
          There must be at least one active Legal Reviewer and one active
          Legal Approver. Ask an administrator to create them.
        </Alert>
      )}

      <div className="form-grid">
        <div className="field">
          <label className="field__label" htmlFor="approval-reviewer">
            Legal Reviewer
          </label>
          <select
            id="approval-reviewer"
            className="field__input"
            value={reviewerId}
            onChange={(event) => setReviewerId(event.target.value)}
            disabled={isBusy}
          >
            <option value="">Select a Legal Reviewer</option>
            {reviewers.map((person) => (
              <option key={person.id} value={person.id}>
                {person.full_name} ({person.email})
              </option>
            ))}
          </select>
        </div>

        <div className="field">
          <label className="field__label" htmlFor="approval-approver">
            Legal Approver
          </label>
          <select
            id="approval-approver"
            className="field__input"
            value={approverId}
            onChange={(event) => setApproverId(event.target.value)}
            disabled={isBusy}
          >
            <option value="">Select a Legal Approver</option>
            {approvers.map((person) => (
              <option key={person.id} value={person.id}>
                {person.full_name} ({person.email})
              </option>
            ))}
          </select>
        </div>

        <div className="field form-grid__wide">
          <label className="field__label" htmlFor="approval-submit-comment">
            Note for the reviewer (optional)
          </label>
          <textarea
            id="approval-submit-comment"
            className="field__input field__textarea"
            rows={3}
            maxLength={2000}
            value={comment}
            onChange={(event) => setComment(event.target.value)}
            disabled={isBusy}
          />
        </div>
      </div>

      {error && <Alert variant="error">{error}</Alert>}

      <div className="form-actions">
        <Button
          type="submit"
          loading={isBusy}
          disabled={noTeam || !reviewerId || !approverId}
        >
          {isBusy
            ? 'Submitting...'
            : resubmit
              ? 'Resubmit for approval'
              : 'Submit for approval'}
        </Button>
      </div>
    </form>
  )
}

// --------------------------- decision panel ---------------------------------

function DecisionPanel({
  contractId,
  state,
  action,
  onCancel,
  onDone,
  onStale,
}: {
  contractId: string
  state: ApprovalState
  action: 'recommend' | 'request_changes' | 'reject' | 'approve'
  onCancel: () => void
  onDone: (message: string) => void
  onStale: () => void
}) {
  const copy = ACTION_COPY[action]
  const [comment, setComment] = useState('')
  const [isBusy, setIsBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [commentError, setCommentError] = useState<string | null>(null)

  async function handleConfirm() {
    if (isBusy) return

    const trimmed = comment.trim()
    if (copy.commentRequired && trimmed.length < MIN_COMMENT) {
      setCommentError(
        `Enter a comment of at least ${MIN_COMMENT} characters explaining your decision.`,
      )
      return
    }

    setIsBusy(true)
    setError(null)
    setCommentError(null)

    try {
      if (state.workflow_status === 'pending_reviewer') {
        await reviewerAction(
          contractId,
          action as 'recommend' | 'request_changes' | 'reject',
          trimmed || null,
        )
      } else {
        await approverAction(
          contractId,
          action as 'approve' | 'request_changes' | 'reject',
          trimmed || null,
        )
      }
      onDone(copy.success)
    } catch (caughtError) {
      setError(getErrorMessage(caughtError))
      setIsBusy(false)
      // Someone else may have acted first: refresh what the user can do.
      if (
        caughtError instanceof ApiError &&
        (caughtError.status === 409 || caughtError.status === 403)
      ) {
        onStale()
      }
    }
  }

  return (
    <div className="decision" role="group" aria-label={copy.label}>
      <h3>{copy.label}</h3>
      {copy.warning && (
        <Alert variant={action === 'approve' ? 'info' : 'error'}>
          {copy.warning}
        </Alert>
      )}

      <div className="field">
        <label className="field__label" htmlFor="decision-comment">
          {copy.commentRequired
            ? `Comment (required, at least ${MIN_COMMENT} characters)`
            : 'Comment (optional)'}
        </label>
        <textarea
          id="decision-comment"
          className={`field__input field__textarea${commentError ? ' field__input--error' : ''}`}
          rows={4}
          maxLength={2000}
          value={comment}
          onChange={(event) => {
            setComment(event.target.value)
            setCommentError(null)
          }}
          disabled={isBusy}
          aria-invalid={commentError ? true : undefined}
          aria-describedby={commentError ? 'decision-comment-error' : undefined}
        />
        {commentError && (
          <p className="field__error" id="decision-comment-error" role="alert">
            {commentError}
          </p>
        )}
      </div>

      {error && <Alert variant="error">{error}</Alert>}

      <div className="decision__buttons">
        <Button variant={copy.variant} onClick={handleConfirm} loading={isBusy}>
          {isBusy ? 'Saving...' : copy.confirmLabel}
        </Button>
        <Button variant="ghost" onClick={onCancel} disabled={isBusy}>
          Cancel
        </Button>
      </div>
    </div>
  )
}

// ------------------------------ timeline ------------------------------------

function ActionItem({ action }: { action: ApprovalActionRecord }) {
  return (
    <li className="timeline__item">
      <div className="timeline__head">
        <span className={`badge ${EVENT_BADGE[action.action_type] ?? 'badge--muted'}`}>
          {EVENT_LABEL[action.action_type] ?? action.action_type}
        </span>
        <span>
          {action.actor ? action.actor.full_name : 'Unknown user'}
          {action.actor ? ` (${formatRole(action.actor.role)})` : ''}
        </span>
        <time className="muted-text" dateTime={action.created_at}>
          {formatDateTime(action.created_at)}
        </time>
      </div>
      {action.comment ? (
        <blockquote className="excerpt">
          <p>{action.comment}</p>
        </blockquote>
      ) : (
        <p className="muted-text">No comment.</p>
      )}
    </li>
  )
}

function CycleHistory({
  cycles,
  currentCycleId,
}: {
  cycles: ApprovalCycle[]
  currentCycleId: string | undefined
}) {
  return (
    <div className="cycle-list">
      {cycles.map((cycle) => (
        <details
          key={cycle.id}
          className="cycle"
          open={cycle.id === currentCycleId || cycles.length === 1}
        >
          <summary>
            <strong>Cycle {cycle.cycle_number}</strong>{' '}
            <span className={`badge ${getWorkflowBadgeClass(cycle.status)}`}>
              {formatWorkflowStatus(cycle.status)}
            </span>{' '}
            <span className="muted-text">
              submitted {formatDateTime(cycle.submitted_at)}
              {cycle.document_version !== null
                ? ` · document version ${cycle.document_version}`
                : ''}
            </span>
          </summary>
          <dl className="detail-list">
            <div>
              <dt>Submitted by</dt>
              <dd>{cycle.submitted_by.full_name}</dd>
            </div>
            <div>
              <dt>Legal Reviewer</dt>
              <dd>{cycle.reviewer.full_name}</dd>
            </div>
            <div>
              <dt>Legal Approver</dt>
              <dd>{cycle.approver.full_name}</dd>
            </div>
            {cycle.completed_at && (
              <div>
                <dt>Completed</dt>
                <dd>{formatDateTime(cycle.completed_at)}</dd>
              </div>
            )}
          </dl>
          <ol className="timeline">
            {cycle.actions.map((action) => (
              <ActionItem key={action.id} action={action} />
            ))}
          </ol>
        </details>
      ))}
    </div>
  )
}

// ------------------------------ main panel ----------------------------------

interface ApprovalSectionProps {
  contractId: string
  /** Called after a successful action so the page can refresh the contract. */
  onChanged: (message: string) => void
}

/** Approval workflow panel for the contract detail page. */
export function ApprovalSection({ contractId, onChanged }: ApprovalSectionProps) {
  const { state, reload } = useApiResource(contractId, getApprovalState)
  const [pendingAction, setPendingAction] = useState<
    'recommend' | 'request_changes' | 'reject' | 'approve' | null
  >(null)

  return (
    <section className="detail-card approval" aria-labelledby="approval-title">
      <div className="approval__header">
        <div>
          <h2 id="approval-title">Approval workflow</h2>
          <p className="muted-text">
            Legal review, then final approval. AI review findings are advisory
            only and never change this status.
          </p>
        </div>
        {state.status === 'loaded' && (
          <span
            className={`badge ${getWorkflowBadgeClass(state.data.workflow_status)}`}
          >
            {formatWorkflowStatus(state.data.workflow_status)}
          </span>
        )}
      </div>

      {state.status === 'loading' && (
        <div className="state-panel" role="status">
          <Spinner size={24} label="Loading approval status" />
          <p>Loading approval status...</p>
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
        <ApprovalBody
          contractId={contractId}
          data={state.data}
          pendingAction={pendingAction}
          setPendingAction={setPendingAction}
          onChanged={onChanged}
          reload={reload}
        />
      )}
    </section>
  )
}

function ApprovalBody({
  contractId,
  data,
  pendingAction,
  setPendingAction,
  onChanged,
  reload,
}: {
  contractId: string
  data: ApprovalState
  pendingAction: 'recommend' | 'request_changes' | 'reject' | 'approve' | null
  setPendingAction: (
    action: 'recommend' | 'request_changes' | 'reject' | 'approve' | null,
  ) => void
  onChanged: (message: string) => void
  reload: () => void
}) {
  const cycle = data.current_cycle
  const actions = data.available_actions as WorkflowAction[]
  const canSubmit = actions.includes('submit')
  const canResubmit = actions.includes('resubmit')
  const decisions = actions.filter(
    (action): action is 'recommend' | 'request_changes' | 'reject' | 'approve' =>
      action in ACTION_COPY,
  )
  const waiting = waitingMessage(data)

  return (
    <>
      {cycle && (
        <>
          <ol className="stepper" aria-label="Approval progress">
            {stepStates(cycle).map((step) => (
              <li
                key={step.label}
                className="stepper__step"
                data-state={step.state}
                aria-current={step.state === 'current' ? 'step' : undefined}
              >
                {step.label}
              </li>
            ))}
          </ol>

          <dl className="detail-list">
            <div>
              <dt>Approval cycle</dt>
              <dd>
                {cycle.cycle_number}
                {cycle.document_version !== null
                  ? ` · submitted document version ${cycle.document_version}`
                  : ''}
              </dd>
            </div>
            <div>
              <dt>Legal Reviewer</dt>
              <dd>{cycle.reviewer.full_name}</dd>
            </div>
            <div>
              <dt>Legal Approver</dt>
              <dd>{cycle.approver.full_name}</dd>
            </div>
            <div>
              <dt>Submitted</dt>
              <dd>
                {formatDateTime(cycle.submitted_at)} by{' '}
                {cycle.submitted_by.full_name}
              </dd>
            </div>
          </dl>
        </>
      )}

      {!cycle && !canSubmit && (
        <div className="empty-state documents__empty">
          <h3>Not submitted for approval</h3>
          <p>
            {data.contract_status === 'draft'
              ? 'This contract has not been submitted for approval yet.'
              : 'This contract’s status was set before the approval workflow existed, so there is no approval history.'}
          </p>
        </div>
      )}

      {waiting && decisions.length === 0 && !canResubmit && (
        <p className="approval__waiting" role="status">
          {waiting}
        </p>
      )}

      {decisions.length > 0 && !pendingAction && (
        <div className="approval__actions">
          <p>
            <strong>
              {data.workflow_status === 'pending_reviewer'
                ? 'Your decision as Legal Reviewer'
                : 'Your decision as Legal Approver'}
            </strong>
            {' — '}review the documents and AI findings below first.
          </p>
          <div className="decision__buttons">
            {decisions.map((action) => (
              <Button
                key={action}
                variant={ACTION_COPY[action].variant}
                onClick={() => setPendingAction(action)}
              >
                {ACTION_COPY[action].label}
              </Button>
            ))}
          </div>
        </div>
      )}

      {pendingAction && decisions.includes(pendingAction) && (
        <DecisionPanel
          contractId={contractId}
          state={data}
          action={pendingAction}
          onCancel={() => setPendingAction(null)}
          onDone={onChanged}
          onStale={() => {
            setPendingAction(null)
            reload()
          }}
        />
      )}

      {(canSubmit || canResubmit) && (
        <SubmitForm
          contractId={contractId}
          resubmit={canResubmit}
          previous={canResubmit ? cycle : null}
          onDone={onChanged}
        />
      )}

      {data.cycles.length > 0 && (
        <div>
          <h3 className="documents__subheading">
            Approval history ({data.cycles.length}{' '}
            {data.cycles.length === 1 ? 'cycle' : 'cycles'})
          </h3>
          <CycleHistory cycles={data.cycles} currentCycleId={cycle?.id} />
        </div>
      )}
    </>
  )
}
