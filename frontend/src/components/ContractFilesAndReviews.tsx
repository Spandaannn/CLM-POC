import { useDocuments } from '../lib/useDocuments'
import { AiReviewsSection } from './AiReviewsSection'
import { DocumentsSection } from './DocumentsSection'

interface ContractFilesAndReviewsProps {
  contractId: string
  canUpload: boolean
}

/**
 * Documents and AI reviews share one document query, so the review section
 * always knows the current version (even right after an upload).
 */
export function ContractFilesAndReviews({
  contractId,
  canUpload,
}: ContractFilesAndReviewsProps) {
  const documents = useDocuments(contractId)

  return (
    <>
      <DocumentsSection
        contractId={contractId}
        documents={documents}
        canUpload={canUpload}
      />
      <AiReviewsSection contractId={contractId} documents={documents} />
    </>
  )
}
