import { useState } from 'react'
import { getAiStatus, getReview, listReviews, startReview } from '../api/reviews'
import type { ReviewListItem } from '../api/types'
import { ApiError, getErrorMessage } from '../lib/errors'
import { formatDateTime } from '../lib/format'
import { useApiResource } from '../lib/useApiResource'
import type { DocumentsLoadState } from '../lib/useDocuments'
import { Alert } from './Alert'
import { Button } from './Button'
import { ReviewView, SeverityBadge } from './ReviewView'
import { Spinner } from './Spinner'

interface AiReviewsSectionProps {
  contractId: string
  documents: { state: DocumentsLoadState; reload: () => void }
}

interface RunFailure {
  title: string
  message: string
}

// Stable module-level fetchers (the resource hook keys requests by input).
const fetchAiStatus = () => getAiStatus()

function describeFailure(error: unknown): RunFailure {
  const message = getErrorMessage(error)
  if (error instanceof ApiError) {
    if (error.status === 429) return { title: 'Rate limit reached', message }
    if (error.status === 503) return { title: 'AI is not configured', message }
    if (error.status === 409 || error.status === 422) {
      return { title: 'This document cannot be reviewed', message }
    }
    if (error.status === 504) return { title: 'The AI took too long', message }
  }
  return { title: 'The AI review failed', message }
}

function HistoryItem({
  item,
  currentVersion,
  selected,
  onSelect,
}: {
  item: ReviewListItem
  /** Latest document version right now (may be newer than when listed). */
  currentVersion: number | null
  selected: boolean
  onSelect: () => void
}) {
  const counts = item.risk_counts
  const isCurrent =
    currentVersion === null
      ? item.is_current_version
      : item.document_version === currentVersion

  return (
    <li>
      <button
        type="button"
        className={`review-history__item${selected ? ' review-history__item--active' : ''}`}
        onClick={onSelect}
        aria-pressed={selected}
      >
        <span className="review-history__main">
          <strong>Version {item.document_version ?? '?'}</strong>
          {item.document_filename && (
            <span className="muted-text">{item.document_filename}</span>
          )}
        </span>
        <span className="review-history__meta">
          {formatDateTime(item.created_at)}
          {item.initiated_by_name ? ` · ${item.initiated_by_name}` : ''}
        </span>
        <span className="review-history__badges">
          {(['critical', 'high', 'medium', 'low'] as const).map((level) =>
            counts[level] > 0 ? (
              <span key={level} className="review-history__count">
                {counts[level]} <SeverityBadge severity={level} />
              </span>
            ) : null,
          )}
          {item.finding_count === 0 && (
            <span className="muted-text">No findings</span>
          )}
          <span
            className={`badge ${isCurrent ? 'badge--success' : 'badge--muted'}`}
          >
            {isCurrent ? 'Current version' : 'Earlier version'}
          </span>
        </span>
      </button>
    </li>
  )
}

/** AI review panel for the contract detail page. */
export function AiReviewsSection({
  contractId,
  documents,
}: AiReviewsSectionProps) {
  const aiStatus = useApiResource('status', fetchAiStatus)
  const reviews = useApiResource(contractId, listReviews)

  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [isRunning, setIsRunning] = useState(false)
  const [failure, setFailure] = useState<RunFailure | null>(null)

  const items =
    reviews.state.status === 'loaded' ? reviews.state.data.items : []
  const activeId = selectedId ?? items[0]?.id ?? null
  const detail = useApiResource(activeId, getReview)

  const currentDocument =
    documents.state.status === 'loaded' ? documents.state.data.current : null
  const documentsLoading = documents.state.status === 'loading'
  const noDocument =
    documents.state.status === 'loaded' && currentDocument === null
  const configured =
    aiStatus.state.status === 'loaded' && aiStatus.state.data.configured

  async function handleRun() {
    if (isRunning) return

    setIsRunning(true)
    setFailure(null)

    try {
      const review = await startReview(contractId)
      setSelectedId(review.id)
      reviews.reload()
    } catch (caughtError) {
      setFailure(describeFailure(caughtError))
    } finally {
      setIsRunning(false)
    }
  }

  const canRun =
    configured && currentDocument !== null && !isRunning && !documentsLoading

  return (
    <section
      className="detail-card ai-reviews"
      aria-labelledby="ai-reviews-title"
    >
      <div>
        <h2 id="ai-reviews-title">AI review</h2>
        <p className="muted-text">
          Summarise the current document, extract key terms and clauses, flag
          possible risks, and compare it with the configured playbook.
        </p>
      </div>

      <Alert variant="info">
        <strong>AI-generated suggestions only.</strong> Every result needs
        review by a qualified legal reviewer. An AI review never approves,
        rejects, or changes this contract.
      </Alert>

      {aiStatus.state.status === 'loading' && (
        <div className="state-panel" role="status">
          <Spinner size={22} label="Checking AI availability" />
          <p>Checking AI availability...</p>
        </div>
      )}

      {aiStatus.state.status === 'error' && (
        <div className="page-error">
          <Alert variant="error">{aiStatus.state.message}</Alert>
          <Button variant="secondary" onClick={aiStatus.reload}>
            Try again
          </Button>
        </div>
      )}

      {aiStatus.state.status === 'loaded' && !aiStatus.state.data.configured && (
        <Alert variant="info">
          <strong>AI review is not available.</strong>{' '}
          {aiStatus.state.data.message ??
            'AI review is not configured on this server.'}{' '}
          The rest of the application works normally.
        </Alert>
      )}

      {noDocument && (
        <Alert variant="info">
          No document has been uploaded yet. Upload a PDF or Word (.docx)
          file in the Documents section to enable AI review.
        </Alert>
      )}

      {currentDocument && (
        <div className="ai-reviews__run">
          <div>
            <p>
              <strong>Document to review:</strong> version{' '}
              {currentDocument.version_number} ·{' '}
              {currentDocument.original_filename}
            </p>
            {aiStatus.state.status === 'loaded' &&
              aiStatus.state.data.configured && (
                <p className="muted-text">
                  Running a review sends this document&apos;s text to{' '}
                  {aiStatus.state.data.provider} ({aiStatus.state.data.model}).
                  Text is only sent when you click the button.
                </p>
              )}
          </div>
          <Button onClick={handleRun} loading={isRunning} disabled={!canRun}>
            {isRunning
              ? 'Analysing...'
              : `Run AI review of version ${currentDocument.version_number}`}
          </Button>
        </div>
      )}

      {isRunning && (
        <div className="state-panel" role="status">
          <Spinner size={26} label="Analysing the document" />
          <p>
            Analysing the document with AI. This can take up to a minute.
            Please keep this page open.
          </p>
        </div>
      )}

      {failure && (
        <Alert variant="error">
          <strong>{failure.title}.</strong> {failure.message}
        </Alert>
      )}

      {reviews.state.status === 'loading' && (
        <div className="state-panel" role="status">
          <Spinner size={22} label="Loading reviews" />
          <p>Loading review history...</p>
        </div>
      )}

      {reviews.state.status === 'error' && (
        <div className="page-error">
          <Alert variant="error">{reviews.state.message}</Alert>
          <Button variant="secondary" onClick={reviews.reload}>
            Try again
          </Button>
        </div>
      )}

      {reviews.state.status === 'loaded' && items.length === 0 && !isRunning && (
        <div className="empty-state documents__empty">
          <h3>No AI reviews yet</h3>
          <p>
            {currentDocument
              ? 'Run an AI review to see a summary, risks and playbook comparison here.'
              : 'Reviews will appear here after a document is uploaded and reviewed.'}
          </p>
        </div>
      )}

      {items.length > 0 && (
        <div>
          <h3 className="documents__subheading">
            Review history ({items.length})
          </h3>
          <ul className="review-history">
            {items.map((item) => (
              <HistoryItem
                key={item.id}
                item={item}
                currentVersion={currentDocument?.version_number ?? null}
                selected={item.id === activeId}
                onSelect={() => setSelectedId(item.id)}
              />
            ))}
          </ul>
        </div>
      )}

      {activeId !== null && detail.state.status === 'loading' && (
        <div className="state-panel" role="status">
          <Spinner size={26} label="Loading review" />
          <p>Loading review...</p>
        </div>
      )}

      {detail.state.status === 'error' && (
        <div className="page-error">
          <Alert variant="error">{detail.state.message}</Alert>
          <Button variant="secondary" onClick={detail.reload}>
            Try again
          </Button>
        </div>
      )}

      {detail.state.status === 'loaded' && (
        <ReviewView
          review={detail.state.data}
          currentVersion={currentDocument?.version_number ?? null}
        />
      )}
    </section>
  )
}
