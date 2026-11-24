import type { ReactNode } from 'react'

interface PageMessageProps {
  eyebrow?: string
  title: string
  children?: ReactNode
  action?: ReactNode
}

/** A consistent in-page message for empty, missing, or unavailable states. */
export function PageMessage({
  eyebrow = 'Unavailable',
  title,
  children,
  action,
}: PageMessageProps) {
  return (
    <div className="empty-state">
      <p className="eyebrow">{eyebrow}</p>
      <h2>{title}</h2>
      {children && <p>{children}</p>}
      {action}
    </div>
  )
}
