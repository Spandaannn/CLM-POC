import { apiRequest } from './client'
import { mutateWithCsrf } from './csrf'
import type {
  Contract,
  ContractCreateRequest,
  ContractListParams,
  ContractListResponse,
  ContractUpdateRequest,
} from './types'

function buildListQuery(params: ContractListParams): string {
  const search = new URLSearchParams()

  if (params.page !== undefined) search.set('page', String(params.page))
  if (params.page_size !== undefined) {
    search.set('page_size', String(params.page_size))
  }
  if (params.q) search.set('q', params.q)
  if (params.status) search.set('status', params.status)
  if (params.contract_type) {
    search.set('contract_type', params.contract_type)
  }

  const query = search.toString()
  return query ? `?${query}` : ''
}

export function listContracts(
  params: ContractListParams = {},
): Promise<ContractListResponse> {
  return apiRequest<ContractListResponse>(
    `/api/contracts${buildListQuery(params)}`,
  )
}

export function getContract(contractId: string): Promise<Contract> {
  return apiRequest<Contract>(
    `/api/contracts/${encodeURIComponent(contractId)}`,
  )
}

export function createContract(
  payload: ContractCreateRequest,
): Promise<Contract> {
  return mutateWithCsrf<Contract>('POST', '/api/contracts', payload)
}

export function updateContract(
  contractId: string,
  payload: ContractUpdateRequest,
): Promise<Contract> {
  return mutateWithCsrf<Contract>(
    'PATCH',
    `/api/contracts/${encodeURIComponent(contractId)}`,
    payload,
  )
}
