import { apiRequest } from './client'
import { mutateWithCsrf } from './csrf'
import type {
  AiStatus,
  ReviewDetail,
  ReviewListResponse,
} from './types'

export function getAiStatus(): Promise<AiStatus> {
  return apiRequest<AiStatus>('/api/ai/status')
}

export function listReviews(contractId: string): Promise<ReviewListResponse> {
  return apiRequest<ReviewListResponse>(
    `/api/contracts/${encodeURIComponent(contractId)}/reviews`,
  )
}

export function getReview(reviewId: string): Promise<ReviewDetail> {
  return apiRequest<ReviewDetail>(
    `/api/reviews/${encodeURIComponent(reviewId)}`,
  )
}

/**
 * Run an AI review of the contract's current document version. This is the
 * only call that makes the server send contract text to the AI provider.
 */
export function startReview(contractId: string): Promise<ReviewDetail> {
  return mutateWithCsrf<ReviewDetail>(
    'POST',
    `/api/contracts/${encodeURIComponent(contractId)}/reviews`,
  )
}
