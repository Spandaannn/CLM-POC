import type {
  ExcerptStatus,
  PlaybookStatus,
  ReviewDetail,
  RiskSeverity,
} from '../api/types'
import { formatDateTime } from '../lib/format'

const SEVERITY_BADGE: Record<RiskSeverity, string> = {
  critical: 'badge--danger',
  high: 'badge--danger',
  medium: 'badge--warning',
  low: 'badge--muted',
}

const PLAYBOOK_LABEL: Record<PlaybookStatus, string> = {
  met: 'Met',
  partially_met: 'Partially met',
  not_met: 'Not met',
  not_assessed: 'Not assessed',
}

const PLAYBOOK_BADGE: Record<PlaybookStatus, string> = {
  met: 'badge--success',
  partially_met: 'badge--warning',
  not_met: 'badge--danger',
  not_assessed: 'badge--muted',
}

function formatCategory(category: string): string {
  const text = category.replaceAll('_', ' ')
  return text.charAt(0).toUpperCase() + text.slice(1)
}

export function SeverityBadge({ severity }: { severity: RiskSeverity }) {
  return (
    <span className={`badge ${SEVERITY_BADGE[severity]}`}>
      {severity}
    </span>
  )
}

/** Avoid "INR INR 100" when the AI repeats the currency in both fields. */
function formatContractValue(
  value: string | null,
  currency: string | null,
): string | null {
  if (!value) return null
  if (!currency || value.toUpperCase().includes(currency.toUpperCase())) {
    return value
  }
  return `${currency} ${value}`
}

/** Value that may be missing: show "Not found" instead of leaving it blank. */
function Value({ value }: { value: string | null | undefined }) {
  return value ? (
    <>{value}</>
  ) : (
    <span className="review__missing">Not found in the document</span>
  )
}

function Excerpt({
  excerpt,
  status,
}: {
  excerpt: string | null
  status: ExcerptStatus
}) {
  if (excerpt && status === 'verified') {
    return (
      <blockquote className="excerpt">
        <p>{excerpt}</p>
        <footer>
          Quoted from the document text (matched). Page and clause numbers
          are not determined.
        </footer>
      </blockquote>
    )
  }

  return (
    <p className="excerpt-note">
      {status === 'not_verified'
        ? 'The AI quoted text that could not be matched to the document, so no excerpt is shown. Source reference not established.'
        : 'No source excerpt provided. Source reference not established.'}
    </p>
  )
}

interface ReviewViewProps {
  review: ReviewDetail
  /** Latest document version, to flag reviews of earlier versions. */
  currentVersion: number | null
}

export function ReviewView({ review, currentVersion }: ReviewViewProps) {
  const { summary, metadata, source_info: source } = review
  // Compare with the live current version (the upload may be newer than the
  // list the review was loaded with).
  const isCurrent =
    currentVersion === null
      ? review.is_current_version
      : review.document_version === currentVersion

  return (
    <div className="review">
      <div className="review__header">
        <div>
          <h3>
            Review of version {review.document_version ?? '?'}
            {review.document_filename ? ` · ${review.document_filename}` : ''}
          </h3>
          <p className="muted-text">
            {formatDateTime(review.created_at)}
            {review.initiated_by_name
              ? ` · started by ${review.initiated_by_name}`
              : ''}
            {` · ${review.provider} (${review.model})`}
          </p>
        </div>
        <span
          className={`badge ${isCurrent ? 'badge--success' : 'badge--muted'}`}
        >
          {isCurrent ? 'Current version' : 'Earlier version'}
        </span>
      </div>

      {!isCurrent && currentVersion !== null && (
        <p className="review__notice">
          This review covers version {review.document_version}. The contract
          now has version {currentVersion}; run a new review to analyse it.
        </p>
      )}

      {source.truncated && (
        <p className="review__notice">
          This document was long, so only the first{' '}
          {source.characters_analyzed?.toLocaleString() ?? 'part'} characters
          were analysed. Sections after that were not reviewed.
        </p>
      )}

      <section className="review__section" aria-labelledby="rv-summary">
        <h4 id="rv-summary">Executive summary</h4>
        <p className="review__overview">
          <Value value={summary.overview} />
        </p>
        <dl className="detail-list">
          <div>
            <dt>Parties</dt>
            <dd>
              {summary.parties.length > 0 ? (
                summary.parties.join(', ')
              ) : (
                <Value value={null} />
              )}
            </dd>
          </div>
          <div>
            <dt>Commercial terms</dt>
            <dd>
              <Value value={summary.commercial_terms} />
            </dd>
          </div>
          <div>
            <dt>Key dates and obligations</dt>
            <dd>
              <Value value={summary.key_dates_and_obligations} />
            </dd>
          </div>
        </dl>
      </section>

      <section className="review__section" aria-labelledby="rv-metadata">
        <h4 id="rv-metadata">Extracted metadata</h4>
        <dl className="detail-list">
          <div>
            <dt>Parties</dt>
            <dd>
              {metadata.parties.length > 0 ? (
                metadata.parties.join(', ')
              ) : (
                <Value value={null} />
              )}
            </dd>
          </div>
          <div>
            <dt>Effective date</dt>
            <dd>
              <Value value={metadata.effective_date} />
            </dd>
          </div>
          <div>
            <dt>Expiry date</dt>
            <dd>
              <Value value={metadata.expiry_date} />
            </dd>
          </div>
          <div>
            <dt>Contract value</dt>
            <dd>
              <Value
                value={formatContractValue(
                  metadata.contract_value,
                  metadata.currency,
                )}
              />
            </dd>
          </div>
          <div>
            <dt>Governing law</dt>
            <dd>
              <Value value={metadata.governing_law} />
            </dd>
          </div>
          <div>
            <dt>Renewal terms</dt>
            <dd>
              <Value value={metadata.renewal_terms} />
            </dd>
          </div>
        </dl>
      </section>

      <section className="review__section" aria-labelledby="rv-risks">
        <h4 id="rv-risks">
          Risk findings{' '}
          <span className="review__tag">AI observations</span>
        </h4>
        {review.risk_findings.length === 0 ? (
          <p className="muted-text">
            The AI did not report any risk findings. This does not mean the
            contract is risk-free.
          </p>
        ) : (
          <ul className="finding-list">
            {review.risk_findings.map((finding, index) => (
              <li
                key={`${finding.title}-${index}`}
                className={`finding finding--${finding.severity}`}
              >
                <div className="finding__head">
                  <strong>{finding.title}</strong>
                  <SeverityBadge severity={finding.severity} />
                  <span className="review__tag">
                    {formatCategory(finding.category)}
                  </span>
                </div>
                <p>{finding.description}</p>
                <p>
                  <strong>Why it may be a concern: </strong>
                  {finding.concern}
                </p>
                <p>
                  <strong>Suggested action for the legal reviewer: </strong>
                  {finding.suggested_action}
                </p>
                <Excerpt
                  excerpt={finding.excerpt}
                  status={finding.excerpt_status}
                />
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="review__section" aria-labelledby="rv-playbook">
        <h4 id="rv-playbook">
          Playbook comparison{' '}
          <span className="review__tag review__tag--playbook">
            Configured rules
          </span>
        </h4>
        <p className="muted-text">
          {review.playbook.disclaimer}
          {review.playbook.version ? ` (playbook ${review.playbook.version})` : ''}
        </p>
        <div className="table-wrap">
          <table className="data-table">
            <caption className="visually-hidden">
              Contract compared with the configured playbook rules
            </caption>
            <thead>
              <tr>
                <th scope="col">Rule</th>
                <th scope="col">Result</th>
                <th scope="col">Explanation and source</th>
              </tr>
            </thead>
            <tbody>
              {review.playbook.results.map((rule) => (
                <tr key={rule.rule_id}>
                  <td>
                    <span className="data-table__primary">{rule.title}</span>
                    <span className="data-table__secondary">
                      {rule.requirement}
                    </span>
                  </td>
                  <td>
                    <span className={`badge ${PLAYBOOK_BADGE[rule.status]}`}>
                      {PLAYBOOK_LABEL[rule.status]}
                    </span>
                  </td>
                  <td>
                    <p>{rule.explanation}</p>
                    {rule.excerpt && rule.excerpt_status === 'verified' && (
                      <Excerpt
                        excerpt={rule.excerpt}
                        status={rule.excerpt_status}
                      />
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="review__section" aria-labelledby="rv-clauses">
        <h4 id="rv-clauses">Extracted clauses ({review.clauses.length})</h4>
        {review.clauses.length === 0 ? (
          <p className="muted-text">No clauses were extracted.</p>
        ) : (
          <div className="clause-list">
            {review.clauses.map((clause, index) => (
              <details key={`${clause.title}-${index}`} className="clause">
                <summary>
                  <span className="review__tag">
                    {formatCategory(clause.category)}
                  </span>{' '}
                  {clause.title}
                </summary>
                <p>{clause.summary}</p>
                <Excerpt
                  excerpt={clause.excerpt}
                  status={clause.excerpt_status}
                />
              </details>
            ))}
          </div>
        )}
      </section>

      <p className="review__disclaimer">{review.disclaimer}</p>
    </div>
  )
}
