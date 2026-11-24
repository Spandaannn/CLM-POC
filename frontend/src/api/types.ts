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
