/** Return a human-readable label for a backend role value. */
const ROLE_LABELS: Record<string, string> = {
  admin: 'Administrator',
  business_user: 'Business user',
  legal_reviewer: 'Legal reviewer',
  legal_approver: 'Legal approver',
}

export function formatRole(role: string): string {
  return ROLE_LABELS[role] ?? role.replaceAll('_', ' ')
}

/** Build initials for the header avatar, e.g. "Ada Lovelace" -> "AL". */
export function getInitials(fullName: string): string {
  const parts = fullName
    .trim()
    .split(/\s+/)
    .filter((part) => part.length > 0)

  if (parts.length === 0) return '?'

  const first = parts[0]?.[0] ?? ''
  const last = parts.length > 1 ? parts[parts.length - 1]?.[0] ?? '' : ''

  return `${first}${last}`.toUpperCase() || '?'
}

/** Greet the user with their first name when possible. */
export function getFirstName(fullName: string): string {
  const first = fullName.trim().split(/\s+/)[0]
  return first || fullName
}

const STATUS_LABELS: Record<string, string> = {
  draft: 'Draft',
  pending_review: 'Pending review',
  approved: 'Approved',
  rejected: 'Rejected',
  active: 'Active',
  expired: 'Expired',
  terminated: 'Terminated',
}

export function formatStatus(status: string): string {
  return STATUS_LABELS[status] ?? status.replaceAll('_', ' ')
}

/** Return the badge modifier class for a contract status. */
export function getStatusBadgeClass(status: string): string {
  switch (status) {
    case 'approved':
    case 'active':
      return 'badge--success'
    case 'rejected':
    case 'expired':
    case 'terminated':
      return 'badge--danger'
    case 'pending_review':
      return 'badge--brand'
    default:
      return 'badge--muted'
  }
}

/** Format a decimal money value using its ISO currency code. */
export function formatMoney(
  value: string | number | null,
  currency: string,
): string {
  if (value === null || value === '') return '—'

  const amount = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(amount)) return `${currency} ${value}`

  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency,
      maximumFractionDigits: 2,
    }).format(amount)
  } catch {
    return `${currency} ${amount.toLocaleString(undefined, {
      maximumFractionDigits: 2,
    })}`
  }
}

/** Format an ISO date (YYYY-MM-DD) for display. */
export function formatDate(value: string | null): string {
  if (!value) return '—'

  const date = new Date(`${value}T00:00:00`)
  if (Number.isNaN(date.getTime())) return value

  return date.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

/** Format an ISO timestamp for display. */
export function formatDateTime(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value

  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}
