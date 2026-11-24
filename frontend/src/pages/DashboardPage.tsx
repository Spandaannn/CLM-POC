import { Link } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import { ApprovalSummaryPanel } from '../components/ApprovalSummaryPanel'
import { formatRole, getFirstName } from '../lib/format'

interface PlannedModule {
  number: string
  title: string
  description: string
  to?: string
}

/**
 * Module summaries. Only Contracts is backed by an API in this phase; the
 * other cards deliberately contain no counts or sample data.
 */
const PLANNED_MODULES: PlannedModule[] = [
  {
    number: '01',
    title: 'Contracts',
    description:
      'Contract intake, metadata, ownership, and lifecycle status tracking.',
    to: '/contracts',
  },
  {
    number: '02',
    title: 'Documents',
    description:
      'Versioned PDF and DOCX storage with authorized downloads.',
    to: '/contracts',
  },
  {
    number: '03',
    title: 'AI Reviews',
    description:
      'Assisted summaries and risk findings, always subject to human review.',
    to: '/contracts',
  },
  {
    number: '04',
    title: 'Approvals',
    description:
      'Legal review and final approval with a full decision history.',
    to: '/contracts',
  },
]

export function DashboardPage() {
  const { user } = useAuth()

  if (!user) return null

  const memberSince = new Date(user.created_at).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })

  return (
    <div className="dashboard">
      <section className="dashboard-hero" aria-labelledby="dashboard-title">
        <div className="dashboard-hero__intro">
          <p className="eyebrow">Workspace overview</p>
          <h1 id="dashboard-title">
            Welcome back, {getFirstName(user.full_name)}.
          </h1>
          <p className="dashboard-hero__lead">
            You are signed in with the {formatRole(user.role)} role. Manage
            contracts, documents, AI reviews, and approvals from each
            contract&apos;s page.
          </p>
        </div>

        <dl className="account-card" aria-label="Your account">
          <div>
            <dt>Name</dt>
            <dd>{user.full_name}</dd>
          </div>
          <div>
            <dt>Email</dt>
            <dd>{user.email}</dd>
          </div>
          <div>
            <dt>Role</dt>
            <dd>
              <span className="badge badge--brand">
                {formatRole(user.role)}
              </span>
            </dd>
          </div>
          <div>
            <dt>Status</dt>
            <dd>
              <span
                className={`badge ${
                  user.is_active ? 'badge--success' : 'badge--danger'
                }`}
              >
                {user.is_active ? 'Active' : 'Inactive'}
              </span>
            </dd>
          </div>
          <div>
            <dt>Member since</dt>
            <dd>{memberSince}</dd>
          </div>
        </dl>
      </section>

      <ApprovalSummaryPanel />

      <section className="dashboard-section" aria-labelledby="modules-title">
        <div className="section-heading">
          <div>
            <p className="eyebrow">CLM modules</p>
            <h2 id="modules-title">Workspace modules</h2>
          </div>
          <p>
            Documents, AI reviews, and approvals are used from within a
            contract.
          </p>
        </div>

        <div className="module-grid">
          {PLANNED_MODULES.map((module) => (
            <article className="module-card" key={module.title}>
              <span className="module-card__number" aria-hidden="true">
                {module.number}
              </span>
              <h3>{module.title}</h3>
              <p>{module.description}</p>
              {module.to && (
                <Link className="text-link" to={module.to}>
                  {module.title === 'Contracts'
                    ? 'Open contracts'
                    : 'Available in each contract'}
                </Link>
              )}
            </article>
          ))}
        </div>
      </section>

      <section className="empty-state" aria-labelledby="activity-title">
        <p className="eyebrow">Activity</p>
        <h2 id="activity-title">Recent activity is not shown yet</h2>
        <p>
          Every action is recorded in the audit log, but a combined activity
          feed has not been built yet. Each contract shows its own document,
          review, and approval history.
        </p>
      </section>
    </div>
  )
}
