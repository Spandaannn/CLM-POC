import { apiDownload, apiRequest } from './client'
import { mutateWithCsrf } from './csrf'
import type { ContractDocument, ContractDocumentListResponse } from './types'

export function listDocuments(
  contractId: string,
): Promise<ContractDocumentListResponse> {
  return apiRequest<ContractDocumentListResponse>(
    `/api/contracts/${encodeURIComponent(contractId)}/documents`,
  )
}

/** Upload a file as the next version of the contract's document. */
export function uploadDocument(
  contractId: string,
  file: File,
): Promise<ContractDocument> {
  const body = new FormData()
  body.append('file', file)

  return mutateWithCsrf<ContractDocument>(
    'POST',
    `/api/contracts/${encodeURIComponent(contractId)}/documents`,
    body,
  )
}

/**
 * Download one version. The file is fetched with the session cookie (so
 * errors can be shown in the page) and then saved under its original name.
 */
export async function downloadDocument(
  document: ContractDocument,
): Promise<void> {
  const blob = await apiDownload(
    `/api/documents/${encodeURIComponent(document.id)}/download`,
  )

  const url = URL.createObjectURL(blob)
  const link = window.document.createElement('a')
  link.href = url
  link.download = document.original_filename
  window.document.body.append(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}
