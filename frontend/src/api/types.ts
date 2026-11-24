/**
 * Types that mirror the JSON returned by the FastAPI backend.
 *
 * The backend exposes:
 *   GET  /api/auth/me      -> User
 *   GET  /api/auth/csrf    -> CsrfTokenResponse
 *   POST /api/auth/login   -> LoginResponse
 *   POST /api/auth/logout  -> 204 No Content
 */

export interface User {
  id: string
  full_name: string
  email: string
  role: string
  is_active: boolean
  created_at: string
}

export interface LoginRequest {
  email: string
  password: string
}

export interface LoginResponse {
  user: User
  /** A fresh token that must be sent in X-CSRF-Token on logout. */
  csrf_token: string
}

export interface CsrfTokenResponse {
  csrf_token: string
}

export type ContractStatus =
  | 'draft'
  | 'pending_review'
  | 'approved'
  | 'rejected'
  | 'active'
  | 'expired'
  | 'terminated'

export interface Contract {
  id: string
  contract_number: string
  title: string
  contract_type: string
  counterparty_name: string
  description: string | null
  /** Decimal values arrive as strings so money stays exact. */
  contract_value: string | number | null
  currency: string
  start_date: string | null
  end_date: string | null
  status: ContractStatus
  created_by: string
  created_by_name: string | null
  created_at: string
  updated_at: string
}

export interface ContractListResponse {
  items: Contract[]
  total: number
  page: number
  page_size: number
  pages: number
}

export interface ContractListParams {
  page?: number
  page_size?: number
  q?: string
  status?: ContractStatus
  contract_type?: string
}

export interface ContractCreateRequest {
  title: string
  contract_type: string
  counterparty_name: string
  description: string | null
  contract_value: string | null
  currency: string
  start_date: string | null
  end_date: string | null
}

export interface ContractUpdateRequest
  extends Partial<ContractCreateRequest> {
  status?: ContractStatus
}

/** One stored version of a contract's document. */
export interface ContractDocument {
  id: string
  contract_id: string
  original_filename: string
  mime_type: string
  /** Size in bytes. */
  file_size: number
  version_number: number
  /** True for the latest version. */
  is_current: boolean
  uploaded_by: string
  uploaded_by_name: string | null
  uploaded_at: string
}

export interface ContractDocumentListResponse {
  /** Every version, newest first. */
  items: ContractDocument[]
  total: number
  current: ContractDocument | null
}

// ---- AI reviews (Step 9) ----------------------------------------------------

export type RiskSeverity = 'low' | 'medium' | 'high' | 'critical'
export type PlaybookStatus =
  | 'met'
  | 'partially_met'
  | 'not_met'
  | 'not_assessed'
/** Whether a source excerpt was matched against the real document text. */
export type ExcerptStatus = 'verified' | 'not_verified' | 'not_provided'

export interface AiStatus {
  configured: boolean
  provider: string | null
  model: string | null
  message: string | null
  max_input_chars: number
}

export interface RiskCounts {
  critical: number
  high: number
  medium: number
  low: number
}

export interface ReviewListItem {
  id: string
  document_id: string | null
  document_version: number | null
  document_filename: string | null
  /** True if the review covers the document's latest version. */
  is_current_version: boolean
  provider: string
  model: string
  status: string
  created_at: string
  initiated_by_name: string | null
  finding_count: number
  risk_counts: RiskCounts
}

export interface ReviewListResponse {
  items: ReviewListItem[]
  total: number
}

export interface ReviewSummary {
  overview: string | null
  parties: string[]
  commercial_terms: string | null
  key_dates_and_obligations: string | null
}

export interface ReviewMetadata {
  parties: string[]
  effective_date: string | null
  expiry_date: string | null
  contract_value: string | null
  currency: string | null
  governing_law: string | null
  renewal_terms: string | null
}

export interface ReviewClause {
  category: string
  title: string
  summary: string
  excerpt: string | null
  excerpt_status: ExcerptStatus
}

export interface ReviewRiskFinding {
  title: string
  description: string
  severity: RiskSeverity
  category: string
  concern: string
  suggested_action: string
  excerpt: string | null
  excerpt_status: ExcerptStatus
  source: 'ai_observation'
}

export interface ReviewPlaybookResult {
  rule_id: string
  category: string
  title: string
  requirement: string
  severity_if_not_met: RiskSeverity
  status: PlaybookStatus
  explanation: string
  excerpt: string | null
  excerpt_status: ExcerptStatus
  source: 'playbook'
}

export interface ReviewDetail extends ReviewListItem {
  contract_id: string
  review_type: string
  summary: ReviewSummary
  metadata: ReviewMetadata
  clauses: ReviewClause[]
  risk_findings: ReviewRiskFinding[]
  playbook: {
    version: string | null
    results: ReviewPlaybookResult[]
    disclaimer: string
  }
  source_info: {
    method: string | null
    pages: number | null
    characters_extracted: number | null
    characters_analyzed: number | null
    truncated: boolean
  }
  disclaimer: string
}
