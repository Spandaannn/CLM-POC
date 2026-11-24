import { apiRequest } from './client'
import { mutateWithCsrf } from './csrf'
import type {
  ApprovalState,
  ApprovalSummary,
  AssigneesResponse,
  SubmitApprovalRequest,
} from './types'

const base = (contractId: string) =>
  `/api/contracts/${encodeURIComponent(contractId)}/approval`

export function getApprovalState(contractId: string): Promise<ApprovalState> {
  return apiRequest<ApprovalState>(base(contractId))
}

export function getAssignees(): Promise<AssigneesResponse> {
  return apiRequest<AssigneesResponse>('/api/approvals/assignees')
}

export function getApprovalSummary(): Promise<ApprovalSummary> {
  return apiRequest<ApprovalSummary>('/api/approvals/summary')
}

/** Start cycle 1 (submit) or cycle N+1 (resubmit after changes). */
export function submitForApproval(
  contractId: string,
  request: SubmitApprovalRequest,
  resubmit: boolean,
): Promise<ApprovalState> {
  return mutateWithCsrf<ApprovalState>(
    'POST',
    `${base(contractId)}/${resubmit ? 'resubmit' : 'submit'}`,
    request,
  )
}

export function reviewerAction(
  contractId: string,
  action: 'recommend' | 'request_changes' | 'reject',
  comment: string | null,
): Promise<ApprovalState> {
  return mutateWithCsrf<ApprovalState>(
    'POST',
    `${base(contractId)}/reviewer-action`,
    { action, comment },
  )
}

export function approverAction(
  contractId: string,
  action: 'approve' | 'request_changes' | 'reject',
  comment: string | null,
): Promise<ApprovalState> {
  return mutateWithCsrf<ApprovalState>(
    'POST',
    `${base(contractId)}/approver-action`,
    { action, comment },
  )
}
